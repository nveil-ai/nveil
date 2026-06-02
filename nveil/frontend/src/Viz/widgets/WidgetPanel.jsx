// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Clément Baraille
// SPDX-FileContributor: Guillaume Franque
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState, useCallback, useRef, useEffect, useLayoutEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { MdViewSidebar, MdOpenInNew, MdClose, MdTune, MdFileDownload, MdPalette } from 'react-icons/md';
import Select from 'react-select';
import WidgetRenderer from './WidgetRenderer';
import ExportDialog from './controls/ExportDialog';
import { getIcon } from './iconMap';
import { mergeSelectStyles, darkSelectTheme } from '../../utils/selectStyles';
import styles from './WidgetPanel.module.css';

const themeSelectStyles = mergeSelectStyles({
    container: (base) => ({ ...base, flex: 1 }),
    control: (base, state) => ({
        ...base,
        backgroundColor: "rgba(255, 255, 255, 0.05)",
        borderRadius: "10px",
        outline: 'none',
        border: "1px solid rgba(255, 255, 255, 0.08)",
        borderColor: state.isFocused ? 'rgba(27, 144, 186, 0.5)' : 'rgba(255, 255, 255, 0.08)',
        boxShadow: 'none',
        minHeight: 32,
        ':hover': { borderColor: 'rgba(27, 144, 186, 0.3)' },
    }),
});

const DEV = import.meta.env.VITE_DEV;
const STORAGE_KEY = 'nveil_widgetPanel';
const MIN_W = 280;
const MIN_H = 200;
const FLOAT_DEFAULTS = { right: 16, top: 80, width: 340, height: 520 };

// const DEFAULT_PANNEL_STATE = "pinned";

// // 1. On vérifie si la clé est absente (null)
// if (localStorage.getItem(STORAGE_KEY) === null) {
//     // 2. Si elle n'y est pas, on la crée avec la valeur par défaut
//     localStorage.setItem(STORAGE_KEY, DEFAULT_PANNEL_STATE);
// }

function loadPanelState() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; }
    catch { return {}; }
}

/**
 * Widget Panel — two modes:
 *
 * **Pinned** (default): Full-height rail on right side. Narrow (48px) showing
 * icon. On hover, expands to 300px over the viz with glass morphism. Collapses
 * on mouse leave.
 *
 * **Unpinned**: Floating window matching the chat panel pattern — drag header,
 * resize from edges/corners, minimize to header-only, viewport-clamped.
 */
export default function WidgetPanel({ communicatorRef, descriptors = [], prefix = '', onModeChange }) {
    const { t } = useTranslation();
    const [mode, setMode] = useState(() => loadPanelState().mode || 'pinned');
    const [minimized, setMinimized] = useState(false);
    const [hovered, setHovered] = useState(false);
    const [showExport, setShowExport] = useState(false);
    const [plotTheme, setPlotTheme] = useState('deep_blue');
    const [plotThemeItems, setPlotThemeItems] = useState([]);

    // ── Lifecycle metrics ──
    useEffect(() => {
        performance.mark('widgets:panel-mount');
        try {
            const ms = Math.round(performance.measure('viz:build-to-panel-mount', 'viz:build-start', 'widgets:panel-mount').duration);
            DEV && console.info(`[WidgetPanel] Mounted ${ms}ms after build-start — ${descriptors.length} descriptor(s):`, descriptors.map(d => d.type + (d.key ? ':' + d.key : '')));
        } catch {
            DEV && console.info(`[WidgetPanel] Mounted (no build-start mark) — ${descriptors.length} descriptor(s):`, descriptors.map(d => d.type + (d.key ? ':' + d.key : '')));
        }
        return () => { DEV && console.info('[WidgetPanel] Unmounted'); };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // All widget values in one object
    const [widgetState, setWidgetState] = useState({});

    // --- Floating window (pointer-capture drag + resize) ---
    const floatingRef = useRef(null);
    const bodyRef = useRef(null);
    const pos = useRef({ ...FLOAT_DEFAULTS });
    const savedHeight = useRef(FLOAT_DEFAULTS.height);
    const interaction = useRef(null);

    const applyPos = useCallback(() => {
        const el = floatingRef.current;
        if (!el) return;
        const p = pos.current;
        el.style.right = p.right + 'px';
        el.style.top = p.top + 'px';
        el.style.left = 'auto';
        el.style.bottom = 'auto';
        el.style.width = p.width + 'px';
        if (minimized) {
            el.style.height = 'auto';
            if (bodyRef.current) bodyRef.current.style.display = 'none';
        } else {
            el.style.height = p.height + 'px';
            if (bodyRef.current) bodyRef.current.style.display = '';
        }
    }, [minimized]);

    useLayoutEffect(() => {
        if (mode === 'floating') applyPos();
    });

    // Drag (pointer capture on header)
    const onDragStart = useCallback((e) => {
        if (e.target.closest('button')) return;
        const el = floatingRef.current;
        if (!el) return;
        interaction.current = { type: 'drag', sx: e.clientX, sy: e.clientY, startRight: pos.current.right, startTop: pos.current.top };
        e.currentTarget.setPointerCapture(e.pointerId);
    }, []);

    const onDragMove = useCallback((e) => {
        const i = interaction.current;
        if (!i || i.type !== 'drag') return;
        const el = floatingRef.current;
        if (!el) return;
        const dx = e.clientX - i.sx;
        const dy = e.clientY - i.sy;
        let right = i.startRight - dx;
        let top = i.startTop + dy;
        right = Math.max(0, Math.min(right, window.innerWidth - el.offsetWidth));
        top = Math.max(0, Math.min(top, window.innerHeight - el.offsetHeight));
        pos.current.right = right;
        pos.current.top = top;
        el.style.right = right + 'px';
        el.style.top = top + 'px';
        el.style.left = 'auto';
    }, []);

    const onDragEnd = useCallback(() => { interaction.current = null; }, []);

    // Resize (pointer capture on edge handles)
    const onResizeStart = useCallback((edge, e) => {
        const el = floatingRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        interaction.current = {
            type: edge, sx: e.clientX, sy: e.clientY,
            sp: { right: pos.current.right, top: pos.current.top, width: rect.width, height: rect.height },
        };
        e.currentTarget.setPointerCapture(e.pointerId);
        e.stopPropagation();
    }, []);

    const onResizeMove = useCallback((e) => {
        const i = interaction.current;
        if (!i || i.type === 'drag') return;
        const dx = e.clientX - i.sx;
        const dy = e.clientY - i.sy;
        const edge = i.type;
        const b = { ...i.sp };

        // Right-anchored: west = left edge (far from anchor), east = right edge (near anchor)
        if (edge.includes('w')) {
            // Dragging left edge left (dx<0) → wider
            b.width = Math.max(MIN_W, i.sp.width - dx);
        }
        if (edge.includes('e')) {
            // Dragging right edge right (dx>0) → right offset decreases, width stays
            const nw = Math.max(MIN_W, i.sp.width + dx);
            b.right = i.sp.right - (nw - i.sp.width);
            b.width = nw;
        }
        if (edge.includes('s')) b.height = Math.max(MIN_H, i.sp.height + dy);
        if (edge.includes('n')) {
            const nh = Math.max(MIN_H, i.sp.height - dy);
            b.top = i.sp.top + i.sp.height - nh;
            b.height = nh;
        }

        // Viewport clamp
        b.right = Math.max(0, b.right);
        b.top = Math.max(0, b.top);
        b.width = Math.max(MIN_W, Math.min(b.width, window.innerWidth - 20));
        b.height = Math.max(MIN_H, Math.min(b.height, window.innerHeight - b.top - 20));

        pos.current = b;
        applyPos();
    }, [applyPos]);

    const onResizeEnd = useCallback(() => { interaction.current = null; }, []);

    const toggleMinimize = useCallback(() => {
        setMinimized(prev => {
            if (!prev) savedHeight.current = pos.current.height;
            else pos.current.height = savedHeight.current;
            return !prev;
        });
    }, []);

    // --- Widget state sync ---

    const allKeys = useRef([]);
    useEffect(() => {
        DEV && console.info(`[WidgetPanel] Descriptors updated — ${descriptors.length} descriptor(s):`, descriptors.map(d => d.type + (d.key ? ':' + d.key : '')));
        const keys = [];
        const defaults = {};
        const walk = (descs) => {
            for (const d of descs) {
                if (d.key) { keys.push(d.key); if (d.default !== undefined) defaults[d.key] = d.default; }
                // Custom composite widgets (e.g. ClippingControl) declare
                // multiple keys + defaults in bulk via `keys` / `defaults`.
                if (d.keys) { for (const k of d.keys) if (!keys.includes(k)) keys.push(k); }
                if (d.defaults) Object.assign(defaults, d.defaults);
                if (d.gradient_key) keys.push(d.gradient_key);
                if (d.state_key) keys.push(d.state_key);
                if (d.disabled_when?.key && !keys.includes(d.disabled_when.key)) keys.push(d.disabled_when.key);
                if (d.set_on_drag && !keys.includes(d.set_on_drag)) keys.push(d.set_on_drag);
                if (d.children) walk(d.children);
            }
        };
        walk(descriptors);
        allKeys.current = keys;
        DEV && console.info(`[WidgetPanel] Keys extracted (${keys.length}):`, keys, '| defaults:', defaults);
        setWidgetState(prev => {
            const next = { ...defaults };
            for (const k of keys) if (k in prev) next[k] = prev[k];
            return next;
        });
    }, [descriptors]);

    // Push only the changed key to trame (no batch sync)
    const setValue = useCallback((key, val, extra) => {
        setWidgetState(prev => {
            const next = { ...prev, [key]: val };
            if (extra) Object.assign(next, extra);
            return next;
        });
        const comm = communicatorRef?.current;
        if (comm) {
            const update = { [prefix + key]: val };
            if (extra) {
                for (const [k, v] of Object.entries(extra)) {
                    update[prefix + k] = v;
                }
            }
            comm.state.update(update);
        }
    }, [communicatorRef, prefix]);

    // Watch trame → local (skip echoes)
    useEffect(() => {
        const comm = communicatorRef?.current;
        if (!comm?.state || !allKeys.current.length) {
            DEV && console.warn('[WidgetPanel] Watch skipped —', !comm?.state ? 'communicator not ready' : 'no keys to watch');
            return;
        }

        const prefixedKeys = allKeys.current.map(k => prefix + k);
        DEV && console.info(`[WidgetPanel] Watching ${prefixedKeys.length} key(s):`, prefixedKeys);
        const unwatch = comm.state.watch(prefixedKeys, (...values) => {
            setWidgetState(prev => {
                const next = { ...prev };
                let changed = false;
                const updates = {};
                allKeys.current.forEach((k, i) => {
                    const v = values[i];
                    if (v === undefined) return;
                    const pv = prev[k];
                    if (typeof v === 'number' && typeof pv === 'number' && v === pv) return;
                    if (v === pv) return;
                    if (typeof v === 'object' && typeof pv === 'object'
                        && JSON.stringify(v) === JSON.stringify(pv)) return;
                    next[k] = v;
                    updates[k] = v;
                    changed = true;
                });
                if (changed) DEV && console.info('[WidgetPanel] Trame → local state update:', updates);
                return changed ? next : prev;
            });
        });
        return () => { if (typeof unwatch === 'function') unwatch(); };
    }, [communicatorRef?.current, descriptors, prefix]);

    const getValue = useCallback((key) => widgetState[key], [widgetState]);

    // Sync PlotTheme + PlotThemeItems from trame on mount
    useEffect(() => {
        const comm = communicatorRef?.current;
        if (!comm?.state) return;
        const themeKey = prefix + 'PlotTheme';
        const itemsKey = prefix + 'PlotThemeItems';
        const initialTheme = comm.state.get?.(themeKey);
        if (initialTheme !== undefined) setPlotTheme(initialTheme);
        const initialItems = comm.state.get?.(itemsKey);
        if (Array.isArray(initialItems)) setPlotThemeItems(initialItems);
        const unwatchTheme = comm.state.watch([themeKey], (val) => {
            if (val !== undefined) setPlotTheme(val);
        });
        const unwatchItems = comm.state.watch([itemsKey], (val) => {
            if (Array.isArray(val)) setPlotThemeItems(val);
        });
        return () => {
            if (typeof unwatchTheme === 'function') unwatchTheme();
            if (typeof unwatchItems === 'function') unwatchItems();
        };
    }, [communicatorRef?.current, prefix]);

    // Toggle a global class on <html> when the plot theme has a light background,
    // so overlay chrome (bottom bar, pinned widget panel) can swap to opaque-dark
    // fills that stay legible. Cleared on unmount so the class doesn't leak.
    useEffect(() => {
        const isLight = plotTheme === 'white' || plotTheme === 'paper';
        document.documentElement.classList.toggle('viz-light', isLight);
        return () => { document.documentElement.classList.remove('viz-light'); };
    }, [plotTheme]);

    // Expose the pinned rail's collapsed width via a global class so the bottom
    // bar can offset its viewport-centered alignment (the rail eats space on the
    // right). Hover-expanded width is intentionally not tracked.
    useEffect(() => {
        const isPinned = mode === 'pinned' && descriptors.length > 0;
        document.documentElement.classList.toggle('viz-rail-pinned', isPinned);
        return () => { document.documentElement.classList.remove('viz-rail-pinned'); };
    }, [mode, descriptors.length]);

    const onThemeChange = useCallback((val) => {
        if (val == null) return;
        setPlotTheme(val);
        const comm = communicatorRef?.current;
        if (comm) comm.state.update({ [prefix + 'PlotTheme']: val });
    }, [communicatorRef, prefix]);

    const themeOptions = useMemo(
        () => plotThemeItems.map(it => ({ value: it.value, label: it.title })),
        [plotThemeItems]
    );
    const selectedThemeOption = themeOptions.find(o => o.value === plotTheme) || null;

    // Persist mode and notify parent
    useEffect(() => {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ mode })); }
        catch { console.log("ca marche toujours pas"); /* ignore */ }
        onModeChange?.(mode);
    }, [mode, onModeChange]);

    // Collect icons from top-level descriptors for the collapsed rail — one
    // rail entry per top-level widget so sections from different marks
    // (e.g. two "info" cards, one per mark) are both represented.
    const railIcons = useMemo(() => {
        const icons = [];
        for (const d of descriptors) {
            const icon = d.icon || (d.type === 'info' ? 'info' : null);
            if (icon) icons.push(icon);
        }
        return icons;
    }, [descriptors]);

    if (!descriptors.length) return null;

    const isFloating = mode === 'floating';

    // ── Header actions (shared between modes) ──
    const headerActions = (
        <div className={styles.headerActions}>
            {isFloating ? (
                <>
                    <button className={styles.actionBtn} onClick={toggleMinimize}
                        data-tooltip={minimized ? 'Expand' : 'Minimize'}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            {minimized ? <polyline points="17 11 12 6 7 11" /> : <line x1="5" y1="12" x2="19" y2="12" />}
                        </svg>
                    </button>
                    <button className={styles.actionBtn} onClick={() => { setHovered(true); setMinimized(false); setMode('pinned'); }} data-tooltip="Dock to sidebar">
                        <MdViewSidebar size={14} />
                    </button>
                </>
            ) : (
                <button className={styles.actionBtn}
                    onClick={() => { pos.current = { ...FLOAT_DEFAULTS }; setMinimized(false); setMode('floating'); }}
                    data-tooltip="Undock">
                    <MdOpenInNew size={14} />
                </button>
            )}
            <button className={styles.actionBtn} onClick={() => setMode('hidden')} data-tooltip="Hide">
                <MdClose size={14} />
            </button>
        </div>
    );

    // ── Hidden mode: just a small floating button to re-open ──
    if (mode === 'hidden') {
        return (
            <button className={styles.showBtn} onClick={() => setMode('pinned')} data-tooltip="Show controls">
                <MdTune size={18} />
            </button>
        );
    }

    const exportDialog = showExport && (
        <ExportDialog communicatorRef={communicatorRef} onClose={() => setShowExport(false)} />
    );

    const bottomActions = (
        <div className={styles.bottomActions}>
            <div className={styles.themeSelect}>
                <MdPalette size={16} />
                <Select
                    options={themeOptions}
                    value={selectedThemeOption}
                    onChange={opt => onThemeChange(opt ? opt.value : null)}
                    menuPlacement="top"
                    theme={darkSelectTheme}
                    styles={themeSelectStyles}
                    isSearchable={false}
                />
            </div>
            <button className={styles.exportBtn} onClick={() => setShowExport(true)}>
                <MdFileDownload size={16} />
                <span>{t('widgets.Export')}</span>
            </button>
        </div>
    );

    // ── Floating mode (like chat) ──
    if (isFloating) {
        return (
            <><div key="floating" className={styles.floating} ref={floatingRef}>
                <div className={styles.floatingHeader}
                    onPointerDown={onDragStart}
                    onPointerMove={onDragMove}
                    onPointerUp={onDragEnd}
                    onDoubleClick={toggleMinimize}
                >
                    <MdTune className={styles.headerIcon} size={16} />
                    <span className={styles.headerTitle}>Controls</span>
                    {headerActions}
                </div>
                <div className={styles.body} ref={bodyRef}>
                    <WidgetRenderer descriptors={descriptors} getValue={getValue} setValue={setValue} />
                </div>
                {bottomActions}
                {!minimized && ['n','s','e','w','ne','nw','se','sw'].map(edge => (
                    <div
                        key={edge}
                        className={styles['resize' + edge[0].toUpperCase() + edge.slice(1)]}
                        onPointerDown={e => onResizeStart(edge, e)}
                        onPointerMove={onResizeMove}
                        onPointerUp={onResizeEnd}
                    />
                ))}
            </div>{exportDialog}</>
        );
    }

    // ── Pinned mode: hoverable rail ──
    return (
        <><div
            key="pinned"
            className={`${styles.pinned} ${hovered ? styles.pinnedExpanded : ''}`}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
        >
            {/* Rail icons (always visible in collapsed state) */}
            <div className={styles.railIcons}>
                <div className={styles.railIcon}>
                    <MdTune size={26} />
                </div>
                {railIcons.map((iconName, i) => (
                    <div key={`${i}-${iconName}`} className={styles.railIcon}>
                        {getIcon(iconName, 24)}
                    </div>
                ))}
                <div className={styles.railSpacer} />
                <div className={styles.railIcon} onClick={() => setShowExport(true)} style={{ cursor: 'pointer' }}>
                    <MdFileDownload size={24} />
                </div>
            </div>

            {/* Expanded content (visible on hover via CSS) */}
            <div className={styles.pinnedContent}>
                <div className={styles.pinnedHeader}>
                    <MdTune className={styles.headerIcon} size={16} />
                    <span className={styles.headerTitle}>Controls</span>
                    {headerActions}
                </div>
                <div className={styles.body}>
                    <WidgetRenderer descriptors={descriptors} getValue={getValue} setValue={setValue} />
                </div>
                {bottomActions}
            </div>
        </div>{exportDialog}</>
    );
}
