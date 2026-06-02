// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Guillaume Franque
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../Auth/AuthContext';
import { useRoom } from '../Room/RoomContext';
import { useWebSocket } from '../Chat/WebSocketContext';
import { Responsive, useContainerWidth } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import SEO from '../Components/SEO';
import styles from './DashboardView.module.css';
import {
    MdArrowBack, MdRefresh, MdAdd, MdInsertChart,
    MdFullscreen, MdFullscreenExit, MdClose, MdPalette,
} from 'react-icons/md';

// ---------------------------------------------------------------------------
// Constants & Helpers
// ---------------------------------------------------------------------------

const DASHBOARD_THEMES = [
    { id: 'default', label: 'Dark' },
    { id: 'clean', label: 'Clean' },
    { id: 'paper', label: 'Paper' },
];

const BREAKPOINTS = { lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 };
const COLS = { lg: 36, md: 30, sm: 18, xs: 12, xxs: 6 };
const ROW_HEIGHT = 40;
const LAYOUT_VERSION = 3;
const DEFAULT_ITEM = { w: 18, h: 12, minW: 9, minH: 6 };

/** Migrate a v2 layout (12-col / 120px row) to v3 (36-col / 40px row). */
function migrateV2Layout(savedData) {
    const layouts = savedData.layouts || {};
    const migrated = {};
    for (const [bp, items] of Object.entries(layouts)) {
        if (!Array.isArray(items)) continue;
        migrated[bp] = items.map(item => ({
            ...item,
            x: item.x * 3,
            y: item.y * 3,
            w: item.w * 3,
            h: item.h * 3,
            ...(item.minW != null ? { minW: item.minW * 3 } : {}),
            ...(item.minH != null ? { minH: item.minH * 3 } : {}),
        }));
    }
    return { version: LAYOUT_VERSION, layouts: migrated };
}

/** Build a default RGL layouts object with panels in a 2-column grid. */
function buildDefaultRGLLayout(panels) {
    const lg = panels.map((p, i) => ({
        i: p.panel_id,
        x: (i % 2) * DEFAULT_ITEM.w,
        y: Math.floor(i / 2) * DEFAULT_ITEM.h,
        ...DEFAULT_ITEM,
    }));
    return { version: LAYOUT_VERSION, layouts: { lg } };
}

/** Collect all panel IDs from all breakpoint layouts. */
function collectPanelIdsFromLayouts(layouts) {
    const ids = new Set();
    for (const bp of Object.values(layouts)) {
        if (Array.isArray(bp)) {
            for (const item of bp) ids.add(item.i);
        }
    }
    return ids;
}

/** Merge missing panels into saved RGL layout data. */
function mergeNewPanelsRGL(savedData, panelList) {
    const layouts = savedData.layouts || {};
    const existingIds = collectPanelIdsFromLayouts(layouts);
    const missing = panelList.filter(p => !existingIds.has(p.panel_id));
    if (missing.length === 0) return savedData;

    const lgLayout = layouts.lg || [];
    let maxY = 0;
    for (const item of lgLayout) {
        const bottom = item.y + item.h;
        if (bottom > maxY) maxY = bottom;
    }

    for (let idx = 0; idx < missing.length; idx++) {
        lgLayout.push({
            i: missing[idx].panel_id,
            x: (idx % 2) * DEFAULT_ITEM.w,
            y: maxY + Math.floor(idx / 2) * DEFAULT_ITEM.h,
            ...DEFAULT_ITEM,
        });
    }

    return { ...savedData, layouts: { ...layouts, lg: lgLayout } };
}

// ---------------------------------------------------------------------------
// PanelHeader — drag handle + editable title + maximize/close buttons
// ---------------------------------------------------------------------------

function PanelHeader({ title, isMaximized, onMaximize, onRestore, onClose, onRename, t, isGuest }) {
    const [editing, setEditing] = useState(false);
    const [editValue, setEditValue] = useState(title);
    const inputRef = useRef(null);

    useEffect(() => { setEditValue(title); }, [title]);
    useEffect(() => { if (editing && inputRef.current) inputRef.current.select(); }, [editing]);

    const commitRename = () => {
        setEditing(false);
        const trimmed = editValue.trim();
        if (trimmed && trimmed !== title && onRename) onRename(trimmed);
        else setEditValue(title);
    };

    const headerClass = isMaximized
        ? styles.panelHeader
        : `${styles.panelHeader} grid-drag-handle`;

    return (
        <div className={headerClass}>
            {editing ? (
                <input
                    ref={inputRef}
                    className={`${styles.panelTitleInput} grid-cancel-drag`}
                    value={editValue}
                    onChange={e => setEditValue(e.target.value)}
                    onBlur={commitRename}
                    onKeyDown={e => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') { setEditValue(title); setEditing(false); } }}
                />
            ) : (
                <span
                    className={styles.panelTitle}
                    onDoubleClick={() => { if (onRename && !isGuest) setEditing(true); }}
                >
                    {title}
                </span>
            )}
            <span className={`${styles.panelActions} grid-cancel-drag`}>
                <button
                    className={styles.panelActionBtn}
                    onClick={isMaximized ? onRestore : onMaximize}
                    data-tooltip={isMaximized ? t('dashboard.restore') : t('dashboard.maximize')}
                >
                    {isMaximized ? <MdFullscreenExit /> : <MdFullscreen />}
                </button>
                {!isGuest && (
                    <button
                        className={styles.panelActionBtn}
                        onClick={onClose}
                        data-tooltip={t('dashboard.delete')}
                    >
                        <MdClose />
                    </button>
                )}
            </span>
        </div>
    );
}

// ---------------------------------------------------------------------------
// DashboardView — main component
// ---------------------------------------------------------------------------

export default function DashboardView() {
    const { dashboardToken } = useParams();
    const { t } = useTranslation();
    const navigate = useNavigate();
    const { secureRequest, isAuthenticated, isGuest, loading: authLoading } = useAuth();
    const { switchRoom } = useRoom();
    const switchRoomRef = useRef(switchRoom);
    switchRoomRef.current = switchRoom;
    const { subscribe } = useWebSocket();

    const [layouts, setLayouts] = useState(null);
    const [panels, setPanels] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);
    const [refreshing, setRefreshing] = useState(false);
    const [refreshStatus, setRefreshStatus] = useState(null);
    const [refreshInterval, setRefreshInterval] = useState(null);
    const [dashboardId, setDashboardId] = useState(null);
    const [dashboardName, setDashboardName] = useState('');
    const [maximizedPanel, setMaximizedPanel] = useState(null);

    const [themeIndex, setThemeIndex] = useState(0);

    // Add Panel popover state
    const [showAddPanel, setShowAddPanel] = useState(false);
    const [availablePanels, setAvailablePanels] = useState([]);
    const addPanelRef = useRef(null);

    const gridRef = useRef(null);
    const timeoutRef = useRef(null);
    const saveTimeoutRef = useRef(null);
    const layoutsRef = useRef(null);
    const statusTimeoutRef = useRef(null);

    // RGL v2: useContainerWidth for responsive width
    const { width, containerRef, mounted } = useContainerWidth();

    // -----------------------------------------------------------------------
    // Start dashboard — resolve token, hit /start, get panels + layout
    // -----------------------------------------------------------------------
    useEffect(() => {
        if (!authLoading && !isAuthenticated) navigate('/');
    }, [authLoading, isAuthenticated, navigate]);

    const startDashboard = useCallback(async () => {
        if (!isAuthenticated || !dashboardToken) {
            setIsLoading(false);
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            const listRes = await secureRequest('/server/dashboards/list');
            if (!listRes.ok) throw new Error('Failed to fetch dashboards');
            const dashboards = await listRes.json();
            const dashboard = dashboards.find(d => d.token === dashboardToken);
            if (!dashboard) throw new Error('Dashboard not found');

            setDashboardId(dashboard.id);
            setDashboardName(dashboard.name || '');

            // Guests aren't members of the shared dashboard room, so the
            // switch endpoint would 403.  The guest path in start_dashboard
            // already handles pod assignment via the guest's own room.
            if (!isGuest) {
                await switchRoomRef.current(dashboardToken, false);
            }

            const startRes = await secureRequest(`/server/dashboards/${dashboard.id}/start`, { method: 'POST' });
            if (!startRes.ok) throw new Error('Failed to start dashboard');
            const data = await startRes.json();

            const panelList = data.panels || [];
            setPanels(panelList);

            if (panelList.length > 0) {
                let rglData;
                if (data.saved_layout) {
                    let parsed = JSON.parse(data.saved_layout);
                    if (parsed.version === 2) {
                        parsed = migrateV2Layout(parsed);
                    }
                    if (parsed.version === LAYOUT_VERSION) {
                        rglData = mergeNewPanelsRGL(parsed, panelList);
                    } else {
                        rglData = buildDefaultRGLLayout(panelList);
                    }
                } else {
                    rglData = buildDefaultRGLLayout(panelList);
                }
                layoutsRef.current = rglData.layouts;
                setLayouts(rglData.layouts);
            }

            if (data.status === 'room_ready') {
                setIsLoading(false);
            }
        } catch (e) {
            console.error('Dashboard start error:', e);
            setError(e.message || t('dashboard.startError'));
            setIsLoading(false);
        }
    }, [isAuthenticated, isGuest, dashboardToken, secureRequest, t]);

    useEffect(() => {
        startDashboard();
        return () => {
            if (timeoutRef.current) clearTimeout(timeoutRef.current);
            if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
            if (statusTimeoutRef.current) clearTimeout(statusTimeoutRef.current);
        };
    }, [startDashboard]);

    // Cancel auto-refresh on unmount (leaving the dashboard)
    useEffect(() => {
        return () => {
            fetch('/viz/set_refresh_interval', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ interval: 0 }),
                credentials: 'include',
            }).catch(() => {});
        };
    }, []);

    // Listen for viz_ready event
    useEffect(() => {
        if (!dashboardToken) return;
        const unsub = subscribe('viz_ready', (data) => {
            if (data.room_token === dashboardToken) {
                if (timeoutRef.current) clearTimeout(timeoutRef.current);
                setIsLoading(false);
            }
        });
        return () => unsub();
    }, [dashboardToken, subscribe]);

    // Close popover on outside click or Escape key
    useEffect(() => {
        if (!showAddPanel) return;
        const handleClick = (e) => {
            if (addPanelRef.current && !addPanelRef.current.contains(e.target)) {
                setShowAddPanel(false);
            }
        };
        const handleKeyDown = (e) => {
            if (e.key === 'Escape') setShowAddPanel(false);
        };
        document.addEventListener('mousedown', handleClick);
        document.addEventListener('keydown', handleKeyDown);
        return () => {
            document.removeEventListener('mousedown', handleClick);
            document.removeEventListener('keydown', handleKeyDown);
        };
    }, [showAddPanel]);

    // -----------------------------------------------------------------------
    // Layout persistence (debounced)
    // -----------------------------------------------------------------------
    const handleLayoutChange = useCallback((_currentLayout, allLayouts) => {
        layoutsRef.current = allLayouts;
    }, []);

    const handleInteractionStop = useCallback(() => {
        // Unfreeze all iframes — they snap to their new container size
        const container = gridRef.current;
        if (container) {
            for (const iframe of container.querySelectorAll('iframe')) {
                iframe.style.pointerEvents = '';
                iframe.style.width = '';
                iframe.style.height = '';
                iframe.style.flex = '';
            }
        }

        const allLayouts = layoutsRef.current;
        if (!allLayouts || !dashboardId || isGuest) return;
        if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
        saveTimeoutRef.current = setTimeout(async () => {
            try {
                await secureRequest(`/server/dashboards/${dashboardId}/layout`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ layout: JSON.stringify({ version: LAYOUT_VERSION, layouts: allLayouts }) }),
                });
            } catch (e) {
                console.error('Layout save failed:', e);
            }
        }, 2000);
    }, [dashboardId, secureRequest, isGuest]);

    // -----------------------------------------------------------------------
    // Panel close
    // -----------------------------------------------------------------------
    const handleClosePanel = useCallback(async (panelId) => {
        setPanels(prev => prev.filter(p => p.panel_id !== panelId));
        setLayouts(prev => {
            const base = layoutsRef.current || prev;
            if (!base) return base;
            const next = {};
            for (const [bp, items] of Object.entries(base)) {
                next[bp] = Array.isArray(items) ? items.filter(it => it.i !== panelId) : items;
            }
            layoutsRef.current = next;
            return next;
        });
        if (maximizedPanel === panelId) setMaximizedPanel(null);

        if (dashboardId) {
            try {
                await secureRequest(`/server/dashboards/${dashboardId}/panels/${panelId}`, {
                    method: 'DELETE',
                });
            } catch (e) {
                console.error('Panel delete failed:', e);
            }
        }
    }, [dashboardId, maximizedPanel, secureRequest]);

    // -----------------------------------------------------------------------
    // Add Panel (in-place)
    // -----------------------------------------------------------------------
    const handleOpenAddPanel = async () => {
        if (!dashboardId) return;
        try {
            const res = await secureRequest(`/server/dashboards/${dashboardId}/panels`);
            if (!res.ok) return;
            const serverPanels = await res.json();
            const current = layoutsRef.current || layouts;
            const layoutIds = current ? collectPanelIdsFromLayouts(current) : new Set();
            const missing = serverPanels.filter(p => !layoutIds.has(p.panel_id));
            setAvailablePanels(missing);
            setShowAddPanel(true);
        } catch (e) {
            console.error('Failed to fetch panels:', e);
        }
    };

    const handleAddPanel = useCallback(async (panel) => {
        setShowAddPanel(false);

        const current = layoutsRef.current || layouts;
        // Calculate bottom of existing lg layout
        const lgLayout = (current && current.lg) || [];
        let maxY = 0;
        for (const item of lgLayout) {
            const bottom = item.y + item.h;
            if (bottom > maxY) maxY = bottom;
        }

        const newItem = { i: panel.panel_id, x: 0, y: maxY, ...DEFAULT_ITEM };

        setLayouts(prev => {
            const base = layoutsRef.current || prev;
            if (!base) return { lg: [newItem] };
            const next = { ...base };
            for (const bp of Object.keys(next)) {
                next[bp] = Array.isArray(next[bp]) ? [...next[bp], newItem] : [newItem];
            }
            if (!next.lg) next.lg = [newItem];
            layoutsRef.current = next;
            return next;
        });

        setPanels(prev => [...prev, panel]);

        // Trigger save
        if (dashboardId && saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
        saveTimeoutRef.current = setTimeout(async () => {
            try {
                const updatedLayouts = layoutsRef.current;
                await secureRequest(`/server/dashboards/${dashboardId}/layout`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ layout: JSON.stringify({ version: LAYOUT_VERSION, layouts: updatedLayouts }) }),
                });
            } catch (e) {
                console.error('Layout save failed:', e);
            }
        }, 500);
    }, [layouts, dashboardId, secureRequest]);

    // -----------------------------------------------------------------------
    // Refresh all
    // -----------------------------------------------------------------------
    const handleRefreshAll = async () => {
        if (refreshing || !panels.length) return;
        setRefreshing(true);
        setRefreshStatus(null);
        if (statusTimeoutRef.current) clearTimeout(statusTimeoutRef.current);

        try {
            const res = await secureRequest('/viz/refresh_all', { method: 'POST' });
            if (!res.ok) {
                setRefreshStatus(t('dashboard.refreshError', 'Refresh failed'));
                setRefreshing(false);
                statusTimeoutRef.current = setTimeout(() => setRefreshStatus(null), 4000);
                return;
            }
            const data = await res.json();
            const panelResults = data.panels || {};
            const refreshedCount = Object.values(panelResults).filter(v => v.startsWith('ok')).length;

            if (refreshedCount > 0) {
                setRefreshStatus(t('dashboard.refreshResult', { count: refreshedCount }));
            } else {
                setRefreshStatus(t('dashboard.noUrlSources'));
            }
        } catch (e) {
            console.error('Refresh failed:', e);
            setRefreshStatus(t('dashboard.refreshError', 'Refresh failed'));
        }
        setRefreshing(false);
        statusTimeoutRef.current = setTimeout(() => setRefreshStatus(null), 4000);
    };

    const handleRefreshIntervalChange = async (e) => {
        const val = e.target.value;
        const interval = val === '' ? null : Number(val);
        setRefreshInterval(interval);
        try {
            await secureRequest('/viz/set_refresh_interval', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ interval: interval || 0 }),
            });
        } catch (e) {
            console.error('Set refresh interval failed:', e);
        }
    };

    // -----------------------------------------------------------------------
    // Rename panel
    // -----------------------------------------------------------------------
    const handleRenamePanel = useCallback(async (panelId, newTitle) => {
        setPanels(prev => prev.map(p => p.panel_id === panelId ? { ...p, title: newTitle } : p));
        if (dashboardId) {
            try {
                await secureRequest(`/server/dashboards/${dashboardId}/panels/${panelId}/rename`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: newTitle }),
                });
            } catch (e) {
                console.error('Panel rename failed:', e);
            }
        }
    }, [dashboardId, secureRequest]);

    // -----------------------------------------------------------------------
    // Theme cycling
    // -----------------------------------------------------------------------
    const currentTheme = DASHBOARD_THEMES[themeIndex];

    const handleCycleTheme = useCallback(async () => {
        const nextIndex = (themeIndex + 1) % DASHBOARD_THEMES.length;
        setThemeIndex(nextIndex);
        const nextTheme = DASHBOARD_THEMES[nextIndex];
        try {
            await secureRequest('/viz/set_plot_theme', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ theme: nextTheme.id }),
            });
        } catch (e) {
            console.error('Theme switch failed:', e);
        }
    }, [themeIndex, secureRequest]);

    // -----------------------------------------------------------------------
    // Drag/resize: freeze all iframes to prevent Plotly relayout storms
    // Direct DOM mutations — no React re-renders during interaction.
    // -----------------------------------------------------------------------
    const handleInteractionStart = useCallback(() => {
        const container = gridRef.current;
        if (!container) return;
        for (const iframe of container.querySelectorAll('iframe')) {
            iframe.style.pointerEvents = 'none';
            iframe.style.width = iframe.offsetWidth + 'px';
            iframe.style.height = iframe.offsetHeight + 'px';
            iframe.style.flex = 'none';
        }
    }, []);

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------
    const maximizedPanelData = maximizedPanel ? panels.find(p => p.panel_id === maximizedPanel) : null;

    return (
        <>
            <SEO
                title={t('seo.dashboardViewTitle')}
                description={t('seo.dashboardDescription')}
                robots="noindex, nofollow"
            />
            <main className={`${styles.page} ${styles[`theme_${currentTheme.id}`] || ''}`}>
                <div className={styles.backdrop}>
                    <div className={styles.toolbar}>
                        <button className={styles.backBtn} onClick={() => navigate('/dashboards')}>
                            <MdArrowBack />
                            <span>{t('dashboard.backToList')}</span>
                        </button>
                        {dashboardName && (
                            <span className={styles.dashboardTitle}>{dashboardName}</span>
                        )}
                        <div className={styles.toolbarActions}>
                            <span className={styles.refreshHint}>{t('dashboard.refreshHint')}</span>
                            {refreshStatus && (
                                <span className={styles.refreshStatus}>{refreshStatus}</span>
                            )}
                            <button
                                className={`${styles.refreshBtn} ${refreshing ? styles.refreshing : ''}`}
                                onClick={handleRefreshAll}
                                disabled={refreshing || !panels.length}
                            >
                                <MdRefresh />
                                <span>{refreshing ? t('dashboard.refreshing') : t('dashboard.refreshAll')}</span>
                            </button>
                            
                            <select
                                className={styles.refreshIntervalSelect}
                                value={refreshInterval ?? ''}
                                onChange={handleRefreshIntervalChange}
                                disabled={!panels.length}
                            >
                                <option value="">{t('dashboard.autoRefresh')}: {t('dashboard.refreshOff', 'Off')}</option>
                                <option value="5">5s</option>
                                <option value="10">10s</option>
                                <option value="30">30s</option>
                                <option value="60">1 min</option>
                                <option value="300">5 min</option>
                                <option value="600">10 min</option>
                            </select>

                            {/* Theme toggle */}
                            <button
                                className={styles.themeBtn}
                                onClick={handleCycleTheme}
                                disabled={isLoading || !panels.length}
                                data-tooltip={currentTheme.label}
                            >
                                <MdPalette />
                                <span>{currentTheme.label}</span>
                            </button>

                            {/* Add Panel button */}
                            {!isGuest && (
                            <div className={styles.addPanelWrapper} ref={addPanelRef}>
                                <button
                                    className={styles.addPanelBtn}
                                    onClick={handleOpenAddPanel}
                                    disabled={isLoading}
                                >
                                    <MdAdd />
                                    <span>{t('dashboard.addPanel', 'Add Panel')}</span>
                                    {availablePanels.length > 0 && (
                                        <span className={`${styles.addPanelBadge} ${styles.glow}`}>
                                            {availablePanels.length}
                                        </span>
                                    )}
                                </button>

                                {showAddPanel && (
                                    <div className={styles.addPanelPopover}>
                                        {availablePanels.length > 0 ? (
                                            availablePanels.map(p => (
                                                <button
                                                    key={p.panel_id}
                                                    className={styles.addPanelItem}
                                                    onClick={() => handleAddPanel(p)}
                                                >
                                                    <MdInsertChart />
                                                    <span>{p.title}</span>
                                                </button>
                                            ))
                                        ) : (
                                            <div className={styles.addPanelEmpty}>
                                                {t('dashboard.noPanelsAvailable', 'No new panels available')}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                            )}
                        </div>
                    </div>

                    <div className={styles.viewer} ref={containerRef}>
                        {isLoading && (
                            <div className={styles.loadingOverlay}>
                                <div className={styles.spinner} />
                                <span className={styles.loadingText}>{t('dashboard.starting')}</span>
                            </div>
                        )}

                        {error && !isLoading && (
                            <div className={styles.errorOverlay}>
                                <span className={styles.errorText}>{error}</span>
                                <button className={styles.retryBtn} onClick={startDashboard}>
                                    {t('dashboard.retry')}
                                </button>
                            </div>
                        )}

                        {!isLoading && !error && layouts && (
                            <>
                                {maximizedPanelData && (
                                    <div className={styles.maximizedOverlay}>
                                        <PanelHeader
                                            title={maximizedPanelData.title}
                                            isMaximized
                                            onRestore={() => setMaximizedPanel(null)}
                                            onClose={() => handleClosePanel(maximizedPanelData.panel_id)}
                                            onRename={(newTitle) => handleRenamePanel(maximizedPanelData.panel_id, newTitle)}
                                            t={t}
                                            isGuest={isGuest}
                                        />
                                        <iframe
                                            src={`/viz/app/?room=${dashboardToken}&ui=dock_${maximizedPanelData.panel_id}`}
                                            title={maximizedPanelData.panel_id}
                                            className={styles.panelIframe}
                                        />
                                    </div>
                                )}
                                <div ref={gridRef} style={{ display: maximizedPanel ? 'none' : 'block' }}>
                                    {mounted && (
                                        <Responsive
                                            width={width}
                                            layouts={layouts}
                                            breakpoints={BREAKPOINTS}
                                            cols={COLS}
                                            rowHeight={ROW_HEIGHT}
                                            margin={[60, 30]}
                                            containerPadding={[40, 15]}
                                            draggableHandle=".grid-drag-handle"
                                            draggableCancel=".grid-cancel-drag"
                                            resizeConfig={{ handles: ['s', 'w', 'e', 'n', 'sw', 'nw', 'se', 'ne'] }}
                                            onLayoutChange={handleLayoutChange}
                                            onDragStart={handleInteractionStart}
                                            onDragStop={handleInteractionStop}
                                            onResizeStart={handleInteractionStart}
                                            onResizeStop={handleInteractionStop}
                                            useCSSTransforms
                                        >
                                            {panels.map(p => (
                                                <div key={p.panel_id} className={styles.gridItem}>
                                                    <PanelHeader
                                                        title={p.title}
                                                        isMaximized={false}
                                                        onMaximize={() => setMaximizedPanel(p.panel_id)}
                                                        onClose={() => handleClosePanel(p.panel_id)}
                                                        onRename={(newTitle) => handleRenamePanel(p.panel_id, newTitle)}
                                                        t={t}
                                                        isGuest={isGuest}
                                                    />
                                                    <iframe
                                                        src={`/viz/app/?room=${dashboardToken}&ui=dock_${p.panel_id}`}
                                                        title={p.panel_id}
                                                        className={styles.panelIframe}
                                                    />
                                                </div>
                                            ))}
                                        </Responsive>
                                    )}
                                </div>
                            </>
                        )}
                    </div>
                </div>
            </main>
        </>
    );
}
