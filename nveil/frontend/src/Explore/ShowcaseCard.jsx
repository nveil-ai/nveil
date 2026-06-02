// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useRef, useState, useEffect, Suspense, lazy, useCallback } from "react";
import styles from "./Explore.module.css";

/** Unwrap CJS interop layers: { default: { default: fn } } → fn */
function unwrap(mod) {
  let v = mod;
  while (v && typeof v !== "function" && v.default) v = v.default;
  return v;
}

const Plot = lazy(async () => {
  const [factoryMod, plotlyMod] = await Promise.all([
    import("react-plotly.js/factory"),
    import("plotly.js-dist-min"),
  ]);
  const factory = unwrap(factoryMod);
  const Plotly = unwrap(plotlyMod);
  return { default: factory(Plotly) };
});

const ForceGraph2D = lazy(async () => {
  const mod = await import("react-force-graph-2d");
  return { default: unwrap(mod) };
});

const PLOTLY_LAYOUT = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  margin: { l: 30, r: 10, t: 10, b: 30 },
  font: { color: "#a1a1aa", size: 10 },
  xaxis: { gridcolor: "rgba(255,255,255,0.03)", zerolinecolor: "rgba(255,255,255,0.03)" },
  yaxis: { gridcolor: "rgba(255,255,255,0.03)", zerolinecolor: "rgba(255,255,255,0.03)" },
  showlegend: false,
  autosize: true,
};

const PLOTLY_CONFIG = { displayModeBar: false, responsive: true };

export default function ShowcaseCard({ item, index, onClick }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);
  const [json, setJson] = useState(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); io.disconnect(); } },
      { rootMargin: "200px" }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!visible || !item.jsonPath) return;
    let cancelled = false;
    item.jsonPath().then((mod) => { if (!cancelled) setJson(mod.default || mod); });
    return () => { cancelled = true; };
  }, [visible, item.jsonPath]);

  const handleClick = useCallback(() => onClick(item, json), [onClick, item, json]);

  return (
    <button
      ref={ref}
      className={styles.card}
      onClick={handleClick}
      style={{ animationDelay: `${index * 0.06}s` }}
    >
      <div className={styles.cardGlow} aria-hidden="true" />
      <div className={styles.cardInner}>
        <div className={styles.preview}>
          {visible && (
            <Suspense fallback={<div className={styles.previewPlaceholder} />}>
              {item.backend === "plotly" && json && (
                <Plot
                  data={json.data}
                  layout={{
                    ...PLOTLY_LAYOUT,
                    ...json.layout,
                    paper_bgcolor: "rgba(0,0,0,0)",
                    plot_bgcolor: "rgba(0,0,0,0)",
                    xaxis: {
                      ...PLOTLY_LAYOUT.xaxis,
                      ...(json.layout?.xaxis || {}),
                      gridcolor: PLOTLY_LAYOUT.xaxis.gridcolor,
                      zerolinecolor: PLOTLY_LAYOUT.xaxis.zerolinecolor,
                    },
                    yaxis: {
                      ...PLOTLY_LAYOUT.yaxis,
                      ...(json.layout?.yaxis || {}),
                      gridcolor: PLOTLY_LAYOUT.yaxis.gridcolor,
                      zerolinecolor: PLOTLY_LAYOUT.yaxis.zerolinecolor,
                    },
                  }}
                  config={PLOTLY_CONFIG}
                  useResizeHandler
                  style={{ width: "100%", height: "100%" }}
                />
              )}
              {item.backend === "graph" && json && (
                <ForceGraph2D
                  graphData={json}
                  width={280}
                  height={200}
                  backgroundColor="rgba(0,0,0,0)"
                  nodeColor={(n) => n.color || "#1b90ba"}
                  linkColor={() => "rgba(255,255,255,0.15)"}
                  nodeRelSize={5}
                  cooldownTicks={60}
                  enableZoomInteraction={false}
                  enablePanInteraction={false}
                  enableNodeDrag={false}
                />
              )}
              {item.backend === "image" && (
                <img src={item.src} alt={item.label} loading="lazy" className={styles.previewImg} />
              )}
            </Suspense>
          )}
          {!visible && <div className={styles.previewPlaceholder} />}
        </div>
        <h3 className={styles.cardTitle}>{item.label}</h3>
        {item.tags && (
          <div className={styles.cardTags}>
            {item.tags.map((tag) => (
              <span key={tag} className={styles.cardTag}>{tag}</span>
            ))}
          </div>
        )}
        <p className={styles.cardDesc}>{item.shortDesc}</p>
        <span className={styles.promptChip}>{item.examplePrompt}</span>
      </div>
    </button>
  );
}
