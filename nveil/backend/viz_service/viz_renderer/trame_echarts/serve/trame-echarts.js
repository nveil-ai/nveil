/*
 * trame-echarts — a minimal Vue 3 wrapper around Apache ECharts.
 *
 * Registers a single global <v-chart> component that:
 *   - Accepts an `option` prop (a plain ECharts option dict).
 *   - Calls echarts.init() on mount, setOption() whenever the option changes.
 *   - Auto-resizes via ResizeObserver.
 *   - Emits "click", "mouseover", "mouseout", "legendselectchanged" as DOM events.
 *
 * Requires echarts (and optionally echarts-gl) to be loaded as UMD scripts
 * BEFORE this file, so window.echarts is available.
 *
 * Registers itself as a trame Vue plugin on window.trame_echarts so trame's
 * `vue_use` mechanism picks it up during server.enable_module(...).
 */
(function () {
    if (typeof window === "undefined") return;

    function getEcharts() {
        return window.echarts;
    }

    // ECharts template formatter strings can't access array elements in
    // multi-dim series (heatmap/scatter/parallel), so Python builders emit
    // function bodies prefixed with "__JSFN__" and we compile them to real
    // JS functions before handing the option dict to ECharts.  This keeps
    // the Python side JSON-serialisable while unlocking the full formatter
    // API (params.data, params.value, params.dataIndex, ...).
    const JSFN_PREFIX = "__JSFN__";

    // ---- Lazy loader for deferred echarts extensions ----------------------
    //
    // We keep the initial page load cheap by shipping only echarts.min.js +
    // this wrapper upfront. Additional extensions are fetched on demand the
    // first time a chart uses a series type that requires them:
    //
    //   - echarts-gl.min.js   — 3D series (scatter3D, line3D, surface,
    //                            bar3D, flowGL, linesGL, scatter3D, …)
    //
    // Violin uses an inline __JSFN__ renderItem (data-adaptive KDE) —
    // no external bundle. Contour iso-lines are pre-computed server-side
    // in Python via skimage — no client bundle needed either.
    //
    // Each extension is loaded at most once. The URLs match the Python-side
    // `serve={"__trame_echarts": ...}` mapping in module.py — trame exposes
    // the sibling `serve/` directory at that prefix, so a relative
    // `__trame_echarts/<file>.js` URL works from any page path.

    // Series types (read from `series[i].type`) that require echarts-gl.
    var GL_SERIES_TYPES = {
        scatter3D: true, line3D: true, surface: true,
        bar3D: true, map3D: true, globe: true, polygons3D: true,
        lines3D: true, linesGL: true, scatterGL: true, flowGL: true,
    };

    // Read the renderer hint from the option. Each Python mark builder
    // sets ``option["renderer"] = "svg"`` or ``"canvas"`` based on what
    // makes sense for its series type. SVG renders sharper at small
    // sizes for line/bar/pie/etc; canvas is required for echarts-gl 3D
    // and preferred for dense heatmaps / large point clouds. The key is
    // stripped before the option is handed to echarts.setOption (echarts
    // ignores unknown top-level keys, but we strip it anyway for clean
    // option dumps). GL series force canvas regardless as a safety net.
    function pickRenderer(option) {
        if (!option) return "canvas";
        var hint = option.renderer;
        if (option.series) {
            var series = Array.isArray(option.series) ? option.series : [option.series];
            for (var i = 0; i < series.length; i++) {
                var s = series[i];
                if (s && typeof s.type === "string" && GL_SERIES_TYPES[s.type]) {
                    return "canvas";  // WebGL requires canvas
                }
            }
        }
        if (hint === "svg" || hint === "canvas") return hint;
        return "canvas";
    }

    // `renderItem` identifiers (read from custom-series) that require a
    // specific echarts-custom-series bundle. The apache violin bundle is
    // NOT listed here — it hardcodes bin range to [0, 10] and kernel
    // bandwidth to 1, so it only works for toy data. We use our own
    // inline ``__JSFN__`` renderItem instead (see box_mark.py).
    // URL prefix ``__echarts/`` maps to dive's package data
    // (dive/builder/_echarts_assets) — see module.py's serve dict.
    // Contour iso-lines are now computed server-side in Python via
    // skimage.measure.find_contours — no client-side bundle needed.
    var CUSTOM_SERIES_BUNDLES = {};

    // Return the set of extension URLs that must be loaded before the
    // given option can be passed to setOption. Empty set = no deferred
    // load needed.
    function deferredBundlesFor(option) {
        var needed = {};
        if (!option || !option.series) return needed;
        var s = option.series;
        if (!Array.isArray(s)) s = [s];
        for (var i = 0; i < s.length; i++) {
            var ser = s[i];
            if (!ser || typeof ser.type !== "string") continue;
            if (GL_SERIES_TYPES[ser.type]) {
                needed["__echarts/echarts-gl.min.js"] = true;
            }
            if (ser.type === "custom"
                && typeof ser.renderItem === "string"
                && CUSTOM_SERIES_BUNDLES[ser.renderItem]) {
                needed[CUSTOM_SERIES_BUNDLES[ser.renderItem]] = true;
            }
        }
        return needed;
    }

    function loadScriptOnce(url) {
        var existing = document.querySelector('script[data-trame-echarts="' + url + '"]');
        if (existing && existing._loadPromise) return existing._loadPromise;
        var p = new Promise(function (resolve, reject) {
            var tag = document.createElement("script");
            tag.type = "text/javascript";
            tag.src = url;
            tag.setAttribute("data-trame-echarts", url);
            tag.onload = function () { resolve(true); };
            tag.onerror = function () { reject(new Error("failed to load " + url)); };
            document.body.appendChild(tag);
            tag._loadPromise = p;  // eslint-disable-line no-param-reassign
        });
        return p;
    }

    var _bundleLoadPromises = {};
    // Return a promise that resolves once every extension the given option
    // needs is loaded. Each bundle is loaded at most once (cached).
    function ensureDeferredExtensions(option) {
        var needed = deferredBundlesFor(option);
        var urls = Object.keys(needed);
        if (urls.length === 0) return Promise.resolve();
        var promises = urls.map(function (url) {
            if (!_bundleLoadPromises[url]) {
                _bundleLoadPromises[url] = loadScriptOnce(url).catch(function (err) {
                    delete _bundleLoadPromises[url];
                    console.error("[trame-echarts] failed to load " + url + ":", err);
                    throw err;
                });
            }
            return _bundleLoadPromises[url];
        });
        return Promise.all(promises);
    }

    function hydrateJsFunctions(obj) {
        if (obj === null || obj === undefined) return obj;
        if (typeof obj === "string") {
            if (obj.indexOf(JSFN_PREFIX) === 0) {
                try {
                    // Compile with (params, api) so the same prefix covers
                    // both single-arg callbacks (tooltip.formatter,
                    // valueFormatter, visualMap.formatter) and two-arg
                    // custom-series renderItem. The extra ``api`` param is
                    // harmless for single-arg callers — they just ignore it.
                    var inner = new Function("params", "api", obj.slice(JSFN_PREFIX.length));
                    // Wrap every compiled formatter in a guard: if a stale
                    // formatter from a previous chart shape is briefly still
                    // bound when new data arrives (e.g. during a bar → heatmap
                    // swap) the indexing code inside the body can throw. Echarts'
                    // tooltip pipeline is not resilient to that — one bad call
                    // leaves the whole chart stuck. Returning null keeps rendering
                    // (null is safe for both tooltip formatters and renderItem).
                    return function (params, api) {
                        try { return inner(params, api); }
                        catch (e) { return null; }
                    };
                } catch (e) {
                    console.error("[trame-echarts] failed to compile JS function:", e, obj);
                    return obj;
                }
            }
            return obj;
        }
        if (Array.isArray(obj)) {
            for (let i = 0; i < obj.length; i++) {
                obj[i] = hydrateJsFunctions(obj[i]);
            }
            return obj;
        }
        if (typeof obj === "object") {
            for (const key in obj) {
                if (Object.prototype.hasOwnProperty.call(obj, key)) {
                    obj[key] = hydrateJsFunctions(obj[key]);
                }
            }
            return obj;
        }
        return obj;
    }

    var VChart = {
        name: "VChart",
        props: {
            option: { type: Object, default: function () { return {}; } },
            theme: { type: [String, Object], default: "default" },
            initOptions: { type: Object, default: null },
            notMerge: { type: Boolean, default: false },
            lazyUpdate: { type: Boolean, default: true },
            autoresize: { type: Boolean, default: true },
            // Monotonic counter bumped by the Python wrapper when the next
            // option push represents a fresh visualization (new chat plot or
            // history click). When it increments the watcher calls
            // chart.clear() before setOption so stale series / visualMap /
            // formatters from the previous chart are wiped.
            clearCounter: { type: Number, default: 0 },
        },
        emits: ["click", "dblclick", "mouseover", "mouseout", "mousemove", "legendselectchanged", "chart-ready"],
        methods: {
            // Wire dblclick, legendselectchanged, and zrender cursor events
            // onto the current self._chart instance. Called once on mount and
            // again after every dispose+reinit so a fresh instance inherits
            // the same event plumbing.
            _wireChartEvents: function () {
                var self = this;
                if (!self._chart) return;

                ["dblclick", "legendselectchanged"].forEach(function (evt) {
                    self._chart.on(evt, function (params) { self.$emit(evt, params); });
                });

                // Cursor → data-coordinate plumbing.
                //
                // ECharts has no single-call "cursor-in-data-space" helper; the
                // idiomatic pattern is zrender pointer events + convertFromPixel
                // (see https://echarts.apache.org/handbook/en/how-to/interaction/drag/).
                // containPixel() guards against reporting hovers over legend /
                // title / toolbox / visualMap. Finders are tried in priority
                // order so polar / geo / parallel / singleAxis marks also report
                // usable coordinates instead of silently dropping the event.
                var CURSOR_FINDERS = ["grid", "polar", "geo", "singleAxis", "parallel"];
                function cursorPayload(e) {
                    var chart = self._chart;
                    if (!chart) return null;
                    var px = e.offsetX, py = e.offsetY;
                    if (px == null || py == null) return null;
                    var pixel = [px, py];
                    for (var i = 0; i < CURSOR_FINDERS.length; i++) {
                        var finder = CURSOR_FINDERS[i];
                        var inside = false;
                        try { inside = chart.containPixel(finder, pixel); } catch (err) { inside = false; }
                        if (!inside) continue;
                        var data = null;
                        try { data = chart.convertFromPixel(finder, pixel); } catch (err) { data = null; }
                        if (data == null) continue;
                        var x, y;
                        if (Array.isArray(data)) { x = data[0]; y = data.length > 1 ? data[1] : null; }
                        else { x = data; y = null; }
                        return {
                            cursor: { x: x, y: y },
                            pixel: { x: px, y: py },
                            coordSystem: finder,
                        };
                    }
                    return null;
                }

                var zr = self._chart.getZr && self._chart.getZr();
                if (zr) {
                    zr.on("click", function (e) {
                        var payload = cursorPayload(e);
                        if (payload) self.$emit("click", payload);
                    });
                    var lastHover = 0;
                    zr.on("mousemove", function (e) {
                        var now = Date.now();
                        if (now - lastHover < 120) return;
                        lastHover = now;
                        var payload = cursorPayload(e);
                        if (payload) self.$emit("mousemove", payload);
                    });
                }
            },

            // Lazily create the echarts instance against this.$el and wire
            // events on it. Callers MUST invoke this only after every
            // deferred extension the next option needs has been loaded —
            // echarts-gl in particular needs to be registered on the global
            // echarts object BEFORE an instance is created, otherwise the
            // first scatter3D / line3D / surface / flowGL setOption crashes
            // in its render pipeline reading [0] off a buffer that was
            // never populated.
            //
            // ``option`` is used only to pick the right renderer (svg vs
            // canvas) for the specific chart about to be drawn. The choice
            // is remembered on ``this._activeRenderer`` so the watcher can
            // detect renderer changes between option pushes and dispose
            // if needed (the renderer is fixed at init time).
            _ensureChartInitialized: function (option) {
                var echarts = getEcharts();
                if (!echarts || !this.$el) return null;
                if (this._chart) return this._chart;
                var renderer = pickRenderer(option);
                this._activeRenderer = renderer;
                var initOpts = Object.assign(
                    {},
                    this.initOptions || {},
                    { renderer: renderer }
                );
                this._chart = echarts.init(this.$el, this.theme, initOpts);
                this._wireChartEvents();
                this.$emit("chart-ready", this._chart);
                return this._chart;
            },

            // Dispose the echarts instance entirely so the next call to
            // _ensureChartInitialized creates a fresh one. Used by the
            // new-viz path (clearCounter bump), renderer change, and the
            // theme-change watcher.
            _disposeChart: function () {
                if (this._chart) {
                    try { this._chart.dispose(); } catch (e) {}
                    this._chart = null;
                }
                this._activeRenderer = null;
            },
        },
        mounted: function () {
            var self = this;
            if (!getEcharts()) {
                console.error("[trame-echarts] window.echarts is not loaded");
                return;
            }
            this._lastClearCounter = this.clearCounter || 0;

            // IMPORTANT: do NOT call echarts.init here. Defer it to the
            // first option push so the instance is created AFTER any
            // deferred extension (echarts-gl, violin, contour) has been
            // loaded. Pre-init would produce a chart that doesn't know
            // scatter3D / line3D / surface and crashes on first setOption
            // with those types.
            if (this.option && Object.keys(this.option).length > 0) {
                var hydrated = hydrateJsFunctions(JSON.parse(JSON.stringify(this.option)));
                ensureDeferredExtensions(hydrated).then(function () {
                    var chart = self._ensureChartInitialized(hydrated);
                    if (!chart) return;  // unmounted during load
                    // Strip the python-side renderer hint — echarts ignores
                    // unknown keys but we drop it for clean option dumps.
                    delete hydrated.renderer;
                    chart.setOption(hydrated, { notMerge: self.notMerge, lazyUpdate: self.lazyUpdate });
                }, function () {
                    // Error already logged by ensureDeferredExtensions.
                });
            }

            if (this.autoresize && typeof ResizeObserver !== "undefined") {
                // The chart div sits absolutely-positioned inside its
                // parent (see the render() function), so its dimensions
                // track the parent directly and shrinking works without
                // flex min-size gymnastics. We observe the parent element
                // to catch every size change — observing self.$el only
                // fires when echarts actually resizes its canvas, which
                // creates a feedback loop.
                var observeTarget = self.$el.parentElement || self.$el;
                var resizeRaf = null;
                this._ro = new ResizeObserver(function () {
                    if (resizeRaf) return;
                    resizeRaf = (window.requestAnimationFrame || function (cb) { return setTimeout(cb, 16); })(function () {
                        resizeRaf = null;
                        if (!self._chart || !self.$el) return;
                        var rect = self.$el.getBoundingClientRect();
                        var w = Math.max(0, Math.floor(rect.width));
                        var h = Math.max(0, Math.floor(rect.height));
                        if (w === 0 || h === 0) return;  // hidden panel
                        try { self._chart.resize({ width: w, height: h }); } catch (e) {}
                    });
                });
                this._ro.observe(observeTarget);
            }
        },
        beforeUnmount: function () {
            if (this._rafHandle) {
                try { (window.cancelAnimationFrame || clearTimeout)(this._rafHandle); } catch (e) {}
                this._rafHandle = null;
            }
            this._pendingOption = null;
            if (this._ro) { try { this._ro.disconnect(); } catch (e) {} this._ro = null; }
            if (this._chart) { try { this._chart.dispose(); } catch (e) {} this._chart = null; }
        },
        watch: {
            // Dispose synchronously the moment Python signals "fresh viz"
            // (clearCounter bump). Doing this inside the option watcher's
            // RAF leaves a window where the new option could be applied to
            // the old chart (wrong renderer, stale flowGL layers) — the
            // echarts-gl ``isSingleCanvas`` crash on replay traces back to
            // exactly that race. Disposing on the counter edge guarantees
            // the next option push hits a fresh ``_ensureChartInitialized``.
            clearCounter: function (newVal, oldVal) {
                if (newVal === oldVal) return;
                this._disposeChart();
                this._lastClearCounter = newVal || 0;
                // Re-apply the current option after dispose. When the user
                // re-loads the same history entry, Python pushes a
                // structurally identical ``option`` dict — trame diffs it
                // and skips the propagation, so the deep watcher below
                // never fires. Without this, the chart stays disposed and
                // the panel goes blank. Mirrors the theme watcher.
                if (this.option && Object.keys(this.option).length > 0) {
                    var self = this;
                    var hydrated = hydrateJsFunctions(JSON.parse(JSON.stringify(this.option)));
                    ensureDeferredExtensions(hydrated).then(function () {
                        var chart = self._ensureChartInitialized(hydrated);
                        if (!chart) return;
                        delete hydrated.renderer;
                        chart.setOption(hydrated, { notMerge: true });
                    }, function () {});
                }
            },
            option: {
                deep: true,
                handler: function (newOption) {
                    if (!newOption) return;
                    // Coalesce rapid-fire option pushes (slider drags in 3D
                    // trigger several state changes per frame; each setOption
                    // in echarts-gl rebuilds the WebGL pipeline, causing
                    // visible flicker). Store the latest option on the
                    // instance and render once per animation frame.
                    this._pendingOption = newOption;
                    if (this._rafHandle) return;
                    var self = this;
                    this._rafHandle = (window.requestAnimationFrame || function (cb) { return setTimeout(cb, 16); })(function () {
                        self._rafHandle = null;
                        var pending = self._pendingOption;
                        self._pendingOption = null;
                        if (!pending) return;
                        var hydrated = hydrateJsFunctions(JSON.parse(JSON.stringify(pending)));
                        // Dispose when the renderer hint changed — echarts'
                        // renderer is fixed at init time, so the only way to
                        // switch between svg and canvas is a dispose+reinit.
                        // Happens e.g. when a widget update swaps a 2D bar
                        // (svg) for a 3D scatter (canvas). The clearCounter
                        // watcher above already covers the new-viz path.
                        if (self._chart && self._activeRenderer &&
                            self._activeRenderer !== pickRenderer(hydrated)) {
                            self._disposeChart();
                        }
                        var apply = function () {
                            var chart = self._ensureChartInitialized(hydrated);
                            if (!chart) return;  // unmounted during lazy load
                            delete hydrated.renderer;
                            chart.setOption(hydrated, { notMerge: self.notMerge, lazyUpdate: self.lazyUpdate });
                        };
                        ensureDeferredExtensions(hydrated).then(apply, function () {});
                    });
                },
            },
            theme: function () {
                // Theme changes require a full reinit. Dispose the current
                // instance and let the next option push (or the tail of this
                // handler) recreate it under the new theme.
                this._disposeChart();
                if (this.option && Object.keys(this.option).length > 0) {
                    var self = this;
                    var hydrated = hydrateJsFunctions(JSON.parse(JSON.stringify(this.option)));
                    ensureDeferredExtensions(hydrated).then(function () {
                        var chart = self._ensureChartInitialized(hydrated);
                        if (!chart) return;
                        delete hydrated.renderer;
                        chart.setOption(hydrated, { notMerge: true });
                    }, function () {});
                }
            },
        },
        render: function () {
            var h = (window.Vue && window.Vue.h) ? window.Vue.h : null;
            // The chart root is absolutely-positioned and pinned to all
            // four edges of its parent. This is how production dashboards
            // (Grafana, Kibana, Redash) embed ECharts: escape flex/grid
            // layout entirely so shrinking works in every direction
            // without min-width hacks. The parent container must be
            // ``position: relative`` (or any non-static positioning) so
            // our absolute positioning resolves against it — this is set
            // in _build_echarts_container on the Python side.
            var style = {
                position: "absolute",
                top: "0",
                left: "0",
                right: "0",
                bottom: "0",
                // overflow: "hidden",
            };
            if (h) {
                return h("div", { style: style });
            }
            return null;
        },
        template: '<div style="position:absolute;top:0;left:0;right:0;bottom:0;overflow:hidden;"></div>',
    };

    window.trame_echarts = {
        install: function (app) {
            app.component("v-chart", VChart);
            app.component("VChart", VChart);
        },
    };
})();
