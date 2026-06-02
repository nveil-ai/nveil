// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Guillaume Franque
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import styles from "./Viz.module.css"
import { useEffect, useState, useRef, useMemo, useCallback } from 'react';

const DEV = import.meta.env.VITE_DEV;
import { useNavigate } from 'react-router-dom';
import { TrameIframeApp } from '@kitware/trame-react';
import { useAuth } from "../Auth/AuthContext"
import { useRoom } from "../Room/RoomContext"
import { useWebSocket } from "../Chat/WebSocketContext"
import { WidgetPanel } from "./widgets";
import TimelineControl from "./widgets/controls/TimelineControl";
// CSS imports kept for potential local overrides
import './kedro.styles.min.css';
import './kedro.custom.css';
import { Tabs, TabList, Tab } from 'react-aria-components';
import { MdNavigateBefore, MdNavigateNext } from 'react-icons/md';
import { useTranslation } from 'react-i18next';

function HistoryIndexInput({ className, currentIndex, count, onCommit, tooltip }) {
    const [draft, setDraft] = useState(String(currentIndex + 1));
    const lastCommitted = useRef(currentIndex);

    // Sync draft when the authoritative index changes externally (e.g. prev/next button).
    useEffect(() => {
        if (currentIndex !== lastCommitted.current) {
            setDraft(String(currentIndex + 1));
            lastCommitted.current = currentIndex;
        }
    }, [currentIndex]);

    const commit = () => {
        const n = parseInt(draft, 10);
        if (Number.isNaN(n)) {
            setDraft(String(currentIndex + 1));
            return;
        }
        const clamped = Math.max(1, Math.min(count, n));
        setDraft(String(clamped));
        if (clamped - 1 !== currentIndex) {
            lastCommitted.current = clamped - 1;
            onCommit(clamped - 1);
        }
    };

    return (
        <input
            type="number"
            className={className}
            min={1}
            max={count}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
                if (e.key === 'Enter') { e.currentTarget.blur(); }
                else if (e.key === 'Escape') { setDraft(String(currentIndex + 1)); e.currentTarget.blur(); }
            }}
            data-tooltip={tooltip}
        />
    );
}

export default function Viz({ roomToken, shouldStart, onStart, mobileTab, onMobileTabChange }) {
    const isMobile = Boolean(onMobileTabChange);
    const navigate = useNavigate();
    const [isProcessing, setIsProcessing] = useState(false);
    const [isWaitingForViz, setIsWaitingForViz] = useState(false);
    const [loadError, setLoadError] = useState(false);
    const [iframeError, setIframeError] = useState(false);
    const { user, isAuthenticated, isGuest } = useAuth();
    const { currentRoom } = useRoom();
    const { subscribe } = useWebSocket();
    const [iframeKey, setIframeKey] = useState(0);
    const [iframeSrc, setIframeSrc] = useState(null);
    const { t } = useTranslation();
    // Kedro Viz readiness is signaled via WebSocket event
    const [kedroVizReady, setKedroVizReady] = useState(false);
    const kedroIframeRef = useRef(null);
    const [_selectedTab, _setSelectedTab] = useState("viz");
    // On mobile, Home owns the tab state (chat/pipeline/viz); on desktop, local state
    const selectedTab = isMobile ? (mobileTab === 'chat' ? 'viz' : mobileTab) : _selectedTab;
    const setSelectedTab = isMobile ? onMobileTabChange : _setSelectedTab;
    const communicatorRef = useRef(null);
    const restartTrameRef = useRef(null);
    const unwatchDescriptors = useRef(null);
    const readHistoryTimeoutRef = useRef(null);

    // Room idle state — only set via room_idle WebSocket event
    const [roomIdle, setRoomIdle] = useState(false);

    // Data stale state — set when a linked file is re-uploaded
    const [dataStale, setDataStale] = useState(null); // { file_name }


    // Dashboard export state
    const [showExportModal, setShowExportModal] = useState(false);
    const [dashboards, setDashboards] = useState([]);
    const [exporting, setExporting] = useState(false);
    const [exportSuccess, setExportSuccess] = useState(null);
    const [exportError, setExportError] = useState(null);
    const pendingExportSpecRef = useRef(null);
    const [newDashboardName, setNewDashboardName] = useState('');
    const [showNewDashboardInput, setShowNewDashboardInput] = useState(false);

    // Reset viz state on room switch — clears old iframe to prevent stale proxy requests
    useEffect(() => {
        setIframeSrc(null);
        setIframeKey(prev => prev + 1); // Force full TrameIframeApp remount
        setKedroVizReady(false);
        setIsWaitingForViz(false);
        setIsProcessing(false);
        setLoadError(false);
        setIframeError(false);
        setRoomIdle(false);
        setDataStale(null);
        setWidgetDescriptors([]);
        // Drop the stale communicator — its iframe is about to unmount, so any
        // subsequent watch() call on it would postMessage to a null contentWindow.
        if (unwatchDescriptors.current) {
            unwatchDescriptors.current();
            unwatchDescriptors.current = null;
        }
        if (readHistoryTimeoutRef.current) {
            clearTimeout(readHistoryTimeoutRef.current);
            readHistoryTimeoutRef.current = null;
        }
        communicatorRef.current = null;
    }, [roomToken]);

    // Pod restart state
    const [restartCountdown, setRestartCountdown] = useState(null);
    const restartTimerRef = useRef(null);

    // Subscribe to WebSocket events directly (no CustomEvent bridge needed)
    // Note: viz_ready WS removed — synchronous fetch replaces it for chat rooms.
    useEffect(() => {
        const unsubKedroReady = subscribe('kedro_viz_ready', () => {
            setKedroVizReady(true);
        });

        const unsubTrameState = subscribe('trame_state_update', (data) => {
            if (data.details?.state === "processing") {
                setIsProcessing(true);
            }
        });

        const unsubVizLoaded = subscribe('viz_loaded', (data) => {
            performance.mark('viz:loaded');
            try {
                const buildMs = Math.round(performance.measure('viz:server-build', 'viz:build-start', 'viz:loaded').duration);
                DEV && console.info(`[Viz] Server build: ${buildMs}ms`);
            } catch { /* no build-start mark — viz triggered manually, not via loadVizFile */ }

            // Widget descriptors delivered via WebSocket payload (nested in details).
            // Always overwrite (even with an empty array) so widgets from the
            // previous viz clear out when switching to a viz that has no sliders
            // — e.g., replaying a point scatter after a heatmap.
            const wd = data?.details?.widget_descriptors || data?.widget_descriptors;
            if (wd !== undefined) {
                try {
                    const parsed = typeof wd === 'string' ? JSON.parse(wd) : wd;
                    if (Array.isArray(parsed)) {
                        DEV && console.info(`[Widgets/viz_loaded] ${parsed.length} descriptor(s) from WS payload`);
                        setWidgetDescriptors(parsed);
                    }
                } catch (e) {
                    console.error('[Widgets/viz_loaded] JSON parse error:', e);
                }
            }

            setIsProcessing(false);
            setSelectedTab("viz");
        });

        // Pod restart warning — show countdown toast
        const unsubPodRestart = subscribe('pod_restart_scheduled', (data) => {
            let remaining = data.countdown || 60;
            setRestartCountdown(remaining);
            if (restartTimerRef.current) clearInterval(restartTimerRef.current);
            restartTimerRef.current = setInterval(() => {
                remaining -= 1;
                if (remaining <= 0) {
                    clearInterval(restartTimerRef.current);
                    restartTimerRef.current = null;
                    setRestartCountdown(null);
                } else {
                    setRestartCountdown(remaining);
                }
            }, 1000);
        });

        // Pod restarted — auto-restart room
        const unsubPodRestarted = subscribe('pod_restarted', () => {
            setRestartCountdown(null);
            if (restartTimerRef.current) {
                clearInterval(restartTimerRef.current);
                restartTimerRef.current = null;
            }
            // Auto-restart the room
            if (roomToken && shouldStart) {
                startRoom();
            }
        });

        // Room went idle (pod still alive, but room context cleared)
        const unsubRoomIdle = subscribe('room_idle', () => {
            setIframeSrc(null);
            setKedroVizReady(false);
            setRoomIdle(true);
            communicatorRef.current = null;
        });

        // Data stale — a linked file was re-uploaded via Data Manager
        const unsubDataStale = subscribe('data_stale', (data) => {
            setDataStale({ file_name: data.file_name || 'unknown' });
        });

        return () => {
            unsubKedroReady();
            unsubTrameState();
            unsubVizLoaded();
            unsubPodRestart();
            unsubPodRestarted();
            unsubRoomIdle();
            unsubDataStale();
            if (restartTimerRef.current) clearInterval(restartTimerRef.current);
        };
    }, [roomToken, subscribe, shouldStart]);

    // Widget descriptors from HTTP response (reliable channel for initial delivery)
    useEffect(() => {
        const onWidgetDescriptors = (e) => {
            try {
                const parsed = typeof e.detail === 'string' ? JSON.parse(e.detail) : e.detail;
                if (Array.isArray(parsed) && parsed.length > 0) {
                    DEV && console.info(`[widget-descriptors] ${parsed.length} descriptor(s) from HTTP response`);
                    setWidgetDescriptors(parsed);
                }
            } catch (err) {
                console.error('[widget-descriptors] parse error:', err);
            }
        };
        window.addEventListener('widget-descriptors', onWidgetDescriptors);
        return () => window.removeEventListener('widget-descriptors', onWidgetDescriptors);
    }, []);

    // Listen for export modal trigger from chat message buttons
    useEffect(() => {
        const handleOpenExportEvent = (e) => {
            pendingExportSpecRef.current = e.detail?.specFilename || null;
            handleOpenExport();
        };
        window.addEventListener('openExportModal', handleOpenExportEvent);
        return () => window.removeEventListener('openExportModal', handleOpenExportEvent);
    }, []);

    // Check if Kedro Viz is already running (e.g., after page refresh)
    const checkKedroVizHealth = async () => {
        try {
            const response = await fetch('/api/main', {
                method: 'GET',
                credentials: 'include'
            });
            if (response.ok) {
                setTimeout(() => {
                    setKedroVizReady(true);
                }, 1000);
                return true;
            }
        } catch (e) {
            // Not ready yet, that's fine
        }
        return false;
    };

    // Kedro Viz polling fallback — if the WebSocket event is missed,
    // keep checking health every 5s until ready or component unmounts.
    useEffect(() => {
        if (kedroVizReady || !iframeSrc) return;
        const interval = setInterval(async () => {
            const ready = await checkKedroVizHealth();
            if (ready) clearInterval(interval);
        }, 5000);
        return () => clearInterval(interval);
    }, [kedroVizReady, iframeSrc]);

    // Fonction pour démarrer la room
    const startRoom = async () => {
        performance.mark('trame:room-start');
        setIframeSrc(null);
        setIframeKey(prev => prev + 1);
        setKedroVizReady(false);
        setLoadError(false);
        setIframeError(false);
        setRoomIdle(false);
        setIsWaitingForViz(true);

        try {
            const response = await fetch('/server/room/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ room_token: roomToken }),
                credentials: 'include',
            });
            performance.mark('trame:pod-ready');
            if (response.ok) {
                // Always "room_ready" now — fetch blocks until pod is ready
                setIframeSrc(`${window.location.origin}/viz/app/?room=${roomToken}`);
                await checkKedroVizHealth();
                performance.mark('trame:ready');
                const podMs = Math.round(performance.measure('trame:pod-wait', 'trame:room-start', 'trame:pod-ready').duration);
                const healthMs = Math.round(performance.measure('trame:health-check', 'trame:pod-ready', 'trame:ready').duration);
                DEV && console.info(`[Trame] pod: ${podMs}ms | health check: ${healthMs}ms | total: ${podMs + healthMs}ms`);
                window.dispatchEvent(new CustomEvent('trame-ready'));
            } else {
                setLoadError(true);
                console.error("Failed to start Viz room.");
            }
        } catch (error) {
            setLoadError(true);
            console.error("Error starting Viz room.", error);
        } finally {
            setIsWaitingForViz(false);
        }
    };

    // Start room when all conditions are met.
    // roomToken is passed explicitly in the request body (not just the cookie)
    // to guard against stale cookies after dashboard navigation.
    useEffect(() => {
        if (user && roomToken && shouldStart) {
            startRoom();
        } else {
            setIframeSrc(null);
            setKedroVizReady(false);
            setIsWaitingForViz(false);
        }
    }, [user, roomToken, shouldStart]);



    const restartTrame = async () => {
        setIsProcessing(true);
        setIsWaitingForViz(true);
        setIframeError(false);
        setLoadError(false);

        try {
            const response = await fetch('/server/room/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ room_token: roomToken }),
                credentials: 'include',
            });
            if (response.ok) {
                setIframeSrc(`${window.location.origin}/viz/app/?room=${roomToken}`);
                setIframeKey(prev => prev + 1);
            } else {
                setLoadError(true);
            }
        } catch (error) {
            setLoadError(true);
            console.error("restartTrame error:", error);
        } finally {
            setIsWaitingForViz(false);
            setIsProcessing(false);
        }
    };

    // Keep ref updated so window.restartTrame always calls the latest closure
    restartTrameRef.current = restartTrame;

    useEffect(() => {
        window.restartTrame = (...args) => restartTrameRef.current?.(...args);
        window.reloadTrameButton = setIsProcessing;

        return () => {
            delete window.restartTrame;
            delete window.reloadTrameButton;
        };
    }, []);

    const [widgetDescriptors, setWidgetDescriptors] = useState([]);
    const [widgetMode, setWidgetMode] = useState('pinned');

    // Timeline state (extracted from widget descriptors)
    const [timelineDesc, setTimelineDesc] = useState(null);
    const [timelineCurrent, setTimelineCurrent] = useState(0);
    const [timelinePlaying, setTimelinePlaying] = useState(false);
    const [timelineFps, setTimelineFps] = useState(2);

    // History navigation state (from Trame)
    const [historyCount, setHistoryCount] = useState(0);
    const [historyIndex, setHistoryIndex] = useState(-1);

    // Extract timeline descriptor from widget descriptors
    const nonTimelineDescriptors = useMemo(
        () => widgetDescriptors.filter(d => d.type !== 'timeline'),
        [widgetDescriptors]
    );

    useEffect(() => {
        const tl = widgetDescriptors.find(d => d.type === 'timeline');
        setTimelineDesc(tl || null);
        if (tl) setTimelineCurrent(0);
    }, [widgetDescriptors]);

    // Sync timeline state with Trame
    const setTimelineValue = useCallback((key, val) => {
        const comm = communicatorRef?.current;
        if (comm) comm.state.update({ [key]: val });
    }, []);

    // Watch trame → local for timeline keys
    useEffect(() => {
        const comm = communicatorRef?.current;
        if (!comm?.state || !timelineDesc) return;
        const keys = [timelineDesc.key, timelineDesc.playing_key, timelineDesc.fps_key];
        const unwatch = comm.state.watch(keys, (current, playing, fps) => {
            if (current !== undefined) setTimelineCurrent(current);
            if (playing !== undefined) setTimelinePlaying(playing);
            if (fps !== undefined) setTimelineFps(fps);
        });
        return () => { if (typeof unwatch === 'function') unwatch(); };
    }, [communicatorRef?.current, timelineDesc]);

    // Watch history state from Trame
    useEffect(() => {
        const comm = communicatorRef?.current;
        if (!comm?.state) return;
        const unwatch = comm.state.watch(['history_files', 'current_history_index'], (files, idx) => {
            if (files !== undefined) setHistoryCount(Array.isArray(files) ? files.length : 0);
            if (idx !== undefined) setHistoryIndex(idx);
        });
        return () => { if (typeof unwatch === 'function') unwatch(); };
    }, [communicatorRef?.current]);

    // Dispatch the TARGET index rather than a prev/next pulse. Rapid clicks
    // all carry the same target (local historyIndex hasn't updated yet) and
    // collapse to a single backend call via trame's @state.change dedup.
    const triggerHistoryJump = useCallback((idx) => {
        const comm = communicatorRef?.current;
        if (!comm) return;
        comm.state.update({ trigger_history_jump: idx });
    }, []);

    const onCommunicatorReady = (comm) => {
        performance.mark('viz:communicator-ready');
        try {
            const commMs = Math.round(performance.measure('viz:build-to-comm', 'viz:build-start', 'viz:communicator-ready').duration);
            DEV && console.info(`[Widgets/comm] Communicator ready: ${commMs}ms after build-start`);
        } catch {
            DEV && console.info('[Widgets/comm] Communicator ready (no build-start mark — reload or manual trigger)');
        }
        communicatorRef.current = comm;
        setIframeError(false);

        // Watch widget_descriptors via event-driven API (comm.state.get() hangs — do not use it).
        // The watcher fires immediately if the value is already set, or when the viz builds.
        if (comm?.state) {
            // Cancel any watcher from a previous communicator instance
            if (unwatchDescriptors.current) {
                unwatchDescriptors.current();
                unwatchDescriptors.current = null;
                DEV && console.info('[Widgets/comm] Previous widget_descriptors watcher cancelled');
            }

            DEV && console.info('[Widgets/comm] Setting up widget_descriptors watcher');
            const unwatch = comm.state.watch(['widget_descriptors'], (raw) => {
                DEV && console.info('[Widgets/comm] widget_descriptors received:', raw);
                try {
                    const parsed = raw ? (typeof raw === 'string' ? JSON.parse(raw) : raw) : [];
                    const arr = Array.isArray(parsed) ? parsed : [];
                    const nonTimeline = arr.filter(d => d.type !== 'timeline');
                    DEV && console.info(`[Widgets/comm] ${arr.length} descriptor(s), ${nonTimeline.length} non-timeline`);
                    setWidgetDescriptors(arr);
                    if (arr.length > 0) {
                        performance.mark('viz:widgets-ready');
                        try {
                            const widgetsMs = Math.round(performance.measure('viz:build-to-widgets', 'viz:build-start', 'viz:widgets-ready').duration);
                            DEV && console.info(`[Viz] Widgets ready: ${widgetsMs}ms (${arr.length} descriptor(s))`);
                        } catch { /* no build-start mark */ }
                    }
                } catch (e) {
                    console.error('[Widgets/comm] JSON parse error:', e);
                }
            });
            unwatchDescriptors.current = unwatch;

            // Read history state on connect
            const readHistory = () => {
                if (communicatorRef.current !== comm) return;
                comm.state.get().then((fullState) => {
                    const files = fullState?.history_files;
                    const idx = fullState?.current_history_index;
                    if (Array.isArray(files)) setHistoryCount(files.length);
                    if (typeof idx === 'number') setHistoryIndex(idx);
                }).catch(() => {});
            };
            readHistory();
            readHistoryTimeoutRef.current = setTimeout(readHistory, 2000);
        }
    };

    // Dashboard export handlers
    const handleOpenExport = async () => {
        setExportSuccess(null);
        setExportError(null);
        setShowNewDashboardInput(false);
        setNewDashboardName('');
        setShowExportModal(true);
        try {
            const res = await fetch('/server/dashboards/list', { credentials: 'include' });
            if (res.ok) {
                setDashboards(await res.json());
            }
        } catch (e) {
            console.error('Failed to fetch dashboards:', e);
        }
    };

    const handleExportToDashboard = async (dashboardId, dashboardToken) => {
        if (exporting || !currentRoom) return;
        setExporting(true);
        setExportError(null);
        const title = currentRoom?.name || 'Panel';
        const specFilename = pendingExportSpecRef.current;
        try {
            const res = await fetch(`/server/dashboards/${dashboardId}/export-panel`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    source_room_id: currentRoom.id,
                    title,
                    ...(specFilename && { spec_filename: specFilename }),
                }),
            });
            if (res.ok) {
                setExportSuccess({ dashboardId, token: dashboardToken });
            } else {
                setExportError(t('dashboard.exportError'));
            }
        } catch (e) {
            console.error('Export failed:', e);
            setExportError(t('dashboard.exportError'));
        }
        setExporting(false);
    };

    const handleCreateAndExport = async (name) => {
        if (exporting || !currentRoom) return;
        setExporting(true);
        setExportError(null);
        const dashName = name?.trim() || null;
        try {
            const createRes = await fetch('/server/dashboards/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ name: dashName }),
            });
            if (createRes.ok) {
                const newDash = await createRes.json();
                setDashboards(prev => [...prev, { ...newDash, panel_count: 1 }]);
                await handleExportToDashboard(newDash.id, newDash.token);
            } else {
                setExportError(t('dashboard.exportError'));
            }
        } catch (e) {
            console.error('Create & export failed:', e);
            setExportError(t('dashboard.exportError'));
        }
        setExporting(false);
    };

    if (roomIdle && onStart) {
        return (
            <div className={styles.iframeContainer} style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', backgroundColor: '#1e1e1e' }}>
                <button
                    onClick={startRoom}
                    className={styles.btnResume}
                    style={{
                        padding: '12px 24px',
                        color: 'white',
                        borderRadius: '40px',
                        cursor: 'pointer',
                        fontSize: '0.9rem',
                    }}
                >
                    {t('viz.resumeSession')}
                </button>
            </div>
        );
    }

    return (
        <div className={`${styles.iframeContainer} ${isMobile ? styles.iframeContainerMobile : ''}`}>
            {/* Pod restart countdown toast */}
            {restartCountdown !== null && (
                <div style={{
                    position: 'absolute',
                    top: '12px',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    zIndex: 100,
                    backgroundColor: 'rgba(255, 152, 0, 0.95)',
                    color: '#fff',
                    padding: '10px 24px',
                    borderRadius: '8px',
                    fontSize: '0.85rem',
                    fontWeight: 500,
                    boxShadow: '0 2px 12px rgba(0,0,0,0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                }}>
                    <span>{t('viz.sessionReloadWarning', { seconds: restartCountdown })}</span>
                </div>
            )}
            {/* Data stale banner — file was re-uploaded */}
            {dataStale && (
                <div style={{
                    position: 'absolute',
                    top: restartCountdown !== null ? '56px' : '12px',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    zIndex: 100,
                    backgroundColor: 'rgba(73, 252, 179, 0.92)',
                    color: '#0a0a0c',
                    padding: '8px 20px',
                    borderRadius: '8px',
                    fontSize: '0.82rem',
                    fontWeight: 500,
                    boxShadow: '0 2px 12px rgba(0,0,0,0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                }}>
                    <span>{t('data.staleNotice', { fileName: dataStale.file_name })}</span>
                    <button
                        onClick={() => { setDataStale(null); restartTrame(); }}
                        style={{
                            padding: '4px 14px',
                            background: 'rgba(0,0,0,0.15)',
                            border: '1px solid rgba(0,0,0,0.2)',
                            borderRadius: '6px',
                            color: '#0a0a0c',
                            fontWeight: 600,
                            cursor: 'pointer',
                            fontSize: '0.78rem',
                        }}
                    >
                        {t('data.refresh')}
                    </button>
                    <button
                        onClick={() => setDataStale(null)}
                        style={{
                            background: 'none',
                            border: 'none',
                            color: 'rgba(0,0,0,0.4)',
                            cursor: 'pointer',
                            fontSize: '1rem',
                            padding: '0 4px',
                        }}
                    >
                        &times;
                    </button>
                </div>
            )}
                <div className={styles.tabPanel} style={{
                    height: '100%',
                    position: selectedTab === 'viz' ? 'relative' : 'absolute',
                    visibility: selectedTab === 'viz' ? 'visible' : 'hidden',
                    top: 0, left: 0, width: '100%',
                    pointerEvents: selectedTab === 'viz' ? 'auto' : 'none',
                }}>
                    {(isProcessing || isWaitingForViz) && !iframeError && !loadError && (
                        <div className={styles.loadingOverlay}>
                            <div className={styles.spinner} />
                        </div>
                    )}

                    {(loadError || iframeError) && (
                        <div style={{
                            position: 'absolute',
                            top: 0,
                            left: 0,
                            right: 0,
                            bottom: 0,
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'center',
                            alignItems: 'center',
                            backgroundColor: '#1e1e1e',
                            color: '#999',
                            gap: '16px',
                            zIndex: 10
                        }}>
                            <span style={{ fontSize: '1rem' }}>
                                {iframeError ? 'Visualization failed to load' : 'Something went wrong, please reload'}
                            </span>
                            <button
                                onClick={restartTrame}
                                style={{
                                    padding: '10px 20px',
                                    backgroundColor: '#333',
                                    color: 'white',
                                    border: '1px solid #555',
                                    borderRadius: '20px',
                                    cursor: 'pointer',
                                    fontSize: '0.85rem'
                                }}
                            >
                                Reload
                            </button>
                        </div>
                    )}

                    {iframeSrc && (
                        <div style={{
                            width: (nonTimelineDescriptors.length > 0 && widgetMode === 'pinned') ? 'calc(100% - 48px)' : '100%',
                            height: '100%',
                            transition: 'width 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                        }}>
                            <TrameIframeApp
                                key={iframeKey}
                                url={iframeSrc}
                                style={{ width: '100%', height: '100%', border: 'none' }}
                                onCommunicatorReady={onCommunicatorReady}
                                iframeId="trame-iframe"
                            />
                        </div>
                    )}

                    {/* React widget panel */}
                    {nonTimelineDescriptors.length > 0 && (
                        <WidgetPanel
                            communicatorRef={communicatorRef}
                            descriptors={nonTimelineDescriptors}
                            onModeChange={setWidgetMode}
                        />
                    )}

                </div>

                <div className={styles.tabPanel} style={{
                    height: '100%',
                    position: selectedTab === 'pipeline' ? 'relative' : 'absolute',
                    visibility: selectedTab === 'pipeline' ? 'visible' : 'hidden',
                    top: 0, left: 0, width: '100%',
                    pointerEvents: selectedTab === 'pipeline' ? 'auto' : 'none',
                }}>
                    {kedroVizReady ? (
                        <iframe
                            ref={kedroIframeRef}
                            src="/kedro-viz/"
                            style={{ width: '100%', height: '100%', border: 'none' }}
                            title="Kedro Pipeline Visualization"
                            id="kedro-viz-iframe"
                        />
                    ) : (
                        <div style={{
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'center',
                            alignItems: 'center',
                            height: '100%',
                            color: '#999',
                            gap: '16px'
                        }}>
                            {isWaitingForViz ? (
                                <>
                                    <div className={styles.spinnerSmall} />
                                    <span>{t('nav.startingPipeline')}</span>
                                </>
                            ) : (
                                <span>{t('nav.waitingPipelineData')}</span>
                            )}
                        </div>
                    )}
                </div>

                {/* Export to Dashboard Modal */}
                {showExportModal && (
                    <div
                        className={styles.exportModalOverlay}
                        onClick={() => setShowExportModal(false)}
                        onKeyDown={e => { if (e.key === 'Escape') setShowExportModal(false); }}
                    >
                        <div className={styles.exportModal} onClick={e => e.stopPropagation()}>
                            <h3 className={styles.exportModalTitle}>{t('dashboard.exportTitle')}</h3>

                            {exportError && (
                                <p className={styles.exportError}>{exportError}</p>
                            )}

                            {isGuest && (
                                <p className={styles.exportEmpty} style={{ color: '#ffb74d' }}>
                                    {t('dashboard.guestExportDisabled')}
                                </p>
                            )}

                            {exportSuccess ? (
                                <div className={styles.exportSuccessActions}>
                                    <button
                                        className={styles.exportCreateBtn}
                                        onClick={() => navigate(`/dashboard/${exportSuccess.token}`)}
                                    >
                                        {t('dashboard.viewDashboard')}
                                    </button>
                                    <button className={styles.exportCancelBtn} onClick={() => setShowExportModal(false)}>
                                        {t('cancel')}
                                    </button>
                                </div>
                            ) : (
                                <>
                                    {dashboards.length > 0 ? (
                                        <div className={styles.exportList}>
                                            {dashboards.map(d => (
                                                <button
                                                    key={d.id}
                                                    className={styles.exportItem}
                                                    onClick={() => handleExportToDashboard(d.id, d.token)}
                                                    disabled={exporting || isGuest}
                                                >
                                                    <span>{d.name || 'Dashboard'} — {d.panel_count} {t('dashboard.panels')}</span>
                                                </button>
                                            ))}
                                        </div>
                                    ) : (
                                        !isGuest && <p className={styles.exportEmpty}>{t('dashboard.noDashboards')}</p>
                                    )}
                                    {showNewDashboardInput ? (
                                        <>
                                            <input
                                                className={styles.exportTitleInput}
                                                type="text"
                                                placeholder={t('dashboard.newDashboardName')}
                                                value={newDashboardName}
                                                onChange={e => setNewDashboardName(e.target.value)}
                                                onKeyDown={e => {
                                                    if (e.key === 'Enter' && newDashboardName.trim()) handleCreateAndExport(newDashboardName);
                                                    if (e.key === 'Escape') setShowNewDashboardInput(false);
                                                }}
                                                autoFocus
                                                disabled={exporting}
                                            />
                                            <button
                                                className={styles.exportCreateBtn}
                                                onClick={() => handleCreateAndExport(newDashboardName)}
                                                disabled={exporting || !newDashboardName.trim()}
                                            >
                                                {exporting ? t('dashboard.exporting') : t('dashboard.createAndExport')}
                                            </button>
                                            <button className={styles.exportCancelBtn} onClick={() => setShowNewDashboardInput(false)}>
                                                {t('cancel')}
                                            </button>
                                        </>
                                    ) : (
                                        <>
                                            <button
                                                className={styles.exportCreateBtn}
                                                onClick={() => { setShowNewDashboardInput(true); setNewDashboardName(''); }}
                                                disabled={exporting || isGuest}
                                            >
                                                {t('dashboard.createAndExport')}
                                            </button>
                                            <button className={styles.exportCancelBtn} onClick={() => setShowExportModal(false)}>
                                                {t('cancel')}
                                            </button>
                                        </>
                                    )}
                                </>
                            )}
                        </div>
                    </div>
                )}

                {/* Unified bottom bar — tabs + timeline */}
                {!isMobile && (
                    <div className={styles.bottomBar}>
                        <Tabs selectedKey={selectedTab} onSelectionChange={setSelectedTab} className={styles.tabsContainer}>
                            <TabList aria-label="Visualization Tabs" className={styles.tabList}>
                                <Tab id="pipeline" className={styles.tab} data-tooltip={t('nav.pipelineTooltip')}>{t('nav.pipeline')}</Tab>
                                <Tab id="viz" className={styles.tab} data-tooltip={t('nav.visualizationTooltip')}>{t('nav.visualization')}</Tab>
                            </TabList>
                        </Tabs>
                        {historyCount > 1 && selectedTab === 'viz' && (
                            <>
                                <div className={styles.bottomBarDivider} />
                                <div className={styles.historyControls}>
                                    <button
                                        className={styles.historyBtn}
                                        onClick={() => triggerHistoryJump(historyIndex - 1)}
                                        disabled={historyIndex <= 0}
                                        data-tooltip={t('nav.previousViz', 'Previous visualization')}
                                    >
                                        <MdNavigateBefore />
                                    </button>
                                    <span className={styles.historyLabel}>
                                        <HistoryIndexInput
                                            className={styles.historyIndexInput}
                                            currentIndex={historyIndex}
                                            count={historyCount}
                                            onCommit={(idx) => triggerHistoryJump(idx)}
                                            tooltip={t('nav.jumpToViz', 'Jump to visualization')}
                                        />
                                        /{historyCount}
                                    </span>
                                    <button
                                        className={styles.historyBtn}
                                        onClick={() => triggerHistoryJump(historyIndex + 1)}
                                        disabled={historyIndex >= historyCount - 1}
                                        data-tooltip={t('nav.nextViz', 'Next visualization')}
                                    >
                                        <MdNavigateNext />
                                    </button>
                                </div>
                            </>
                        )}
                        {timelineDesc && selectedTab === 'viz' && (
                            <>
                                <div className={styles.bottomBarDivider} />
                                <TimelineControl
                                    count={timelineDesc.count}
                                    labels={timelineDesc.labels}
                                    current={timelineCurrent}
                                    playing={timelinePlaying}
                                    fps={timelineFps}
                                    onChange={(val) => { setTimelineCurrent(val); setTimelineValue(timelineDesc.key, val); }}
                                    onPlayToggle={(val) => { setTimelinePlaying(val); setTimelineValue(timelineDesc.playing_key, val); }}
                                    onFpsChange={(val) => { setTimelineFps(val); setTimelineValue(timelineDesc.fps_key, val); }}
                                    inline
                                />
                            </>
                        )}
                    </div>
                )}

        </div>
    );
}
