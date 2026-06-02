// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Guillaume Franque
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useRef, useEffect, useLayoutEffect, useState, lazy, Suspense, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { useParams, useLocation } from 'react-router-dom';
import { useRoom } from "../Room/RoomContext";
import { useAuth } from "../Auth/AuthContext";
const Chat = lazy(() => import("../Chat/Chat"));
import ErrorBoundary from '../Components/ErrorBoundary';
import SEO from '../Components/SEO';
import { useTranslation } from 'react-i18next';
import Landing from './Landing';
import useFloatingWindow from './useFloatingWindow';
import styles from "./Home.module.css";
import './resizable-panels.css';

// Lazy load the heavy Visualization component (Trame, VTK)
const Viz = lazy(() => import("../Viz/Viz"));

/**
 * Home component renders the main application interface, including navigation, chat, and an iframe for the Trame server.
 * 
 * Features:
 * - Provides a button to restart the Trame server via a POST request to `/viz/restart`.
 * - Reloads the Trame iframe after a successful restart.
 * - Exposes `window.restartTrame` and `window.reloadTrameButton` for external control.
 * - Cleans up global window properties on unmount.
 * 
 * @component
 * @returns {JSX.Element} The rendered Home component.
 */
export default function Home(props) {
    const { roomToken } = useParams();
    const location = useLocation();
    const { isAuthenticated, loading } = useAuth();

    // Show the SEO landing page to unauthenticated visitors on "/"
    if (!roomToken && !isAuthenticated) {
        return <Landing />;
    }

    return <HomeContent roomToken={roomToken} locationState={location.state} {...props} />;
}

function HomeContent({ roomToken, locationState }) {
    const { t } = useTranslation();
    const { currentRoom, rooms } = useRoom();
    const activeRoomToken = roomToken || currentRoom?.token;

    const [shouldStartViz, setShouldStartViz] = useState(locationState?.autoStart || (rooms && rooms.length > 0));
    const [isMobile, setIsMobile] = useState(window.innerWidth < 1000);
    const [mobileTab, setMobileTab] = useState('chat'); // 'chat' | 'pipeline' | 'viz'
    const [chatDocked, setChatDocked] = useState(() => {
        try { return localStorage.getItem('nveil_chatDocked') !== 'false'; }
        catch { return true; }
    });
    const rightPanelRef = useRef(null);
    const leftPanelRef = useRef(null);
    const panelGroupRef = useRef(null);
    const floatingRef = useRef(null);
    const floatingSlotRef = useRef(null);
    const prevRoomTokenRef = useRef(activeRoomToken);

    const {
        minimized: chatMinimized,
        toggleMinimize,
        dragHandlers,
        onResizeStart, onResizeMove, onResizeEnd,
        reset: resetFloating,
    } = useFloatingWindow(floatingRef, floatingSlotRef);

    const toggleDock = useCallback(() => {
        setChatDocked(prev => {
            const next = !prev;
            if (!next) resetFloating();
            try { localStorage.setItem('nveil_chatDocked', String(next)); } catch {}
            return next;
        });
    }, [resetFloating]);

    useEffect(() => {
        if (rooms && rooms.length > 0 && !shouldStartViz) {
            setShouldStartViz(true);
        }
    }, [rooms]);

    if (prevRoomTokenRef.current !== activeRoomToken && activeRoomToken != null) {
        prevRoomTokenRef.current = activeRoomToken;
        setShouldStartViz(true);
    }

    // HomeContent only renders for authenticated users (including guests),
    // who will always have rooms. Default to true to prevent CLS from
    // panels shifting from 100/0 → 30/70 when rooms load async.
    const isVizPanelVisible = true;
    const isMobileWithViz = isMobile && (activeRoomToken != null || (rooms && rooms.length > 0));
    // Desktop non-docked: chat is floating
    const isFloating = !isMobile && !chatDocked;

    useEffect(() => {
        if (activeRoomToken && rightPanelRef.current) {
            if (rightPanelRef.current.isCollapsed()) {
                rightPanelRef.current.resize(isFloating ? 100 : 70);
            }
        }
    }, [activeRoomToken, isFloating]);

    // Collapse/expand chat panel based on floating state
    useEffect(() => {
        if (!leftPanelRef.current) return;
        if (isFloating) {
            leftPanelRef.current.collapse();
        } else if (leftPanelRef.current.isCollapsed()) {
            leftPanelRef.current.expand();
        }
    }, [isFloating]);

    useEffect(() => {
        const handleResize = () => setIsMobile(window.innerWidth < 1000);
        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    const handleStartViz = () => setShouldStartViz(true);

    // Stable DOM node that hosts Chat — survives docked/floating transitions
    const chatHostRef = useRef(null);
    if (!chatHostRef.current) {
        chatHostRef.current = document.createElement('div');
        chatHostRef.current.style.cssText = 'width:100%;height:100%;';
    }

    // Reparent the stable chat host into whichever container is active (layout effect to avoid flash)
    const dockedSlotRef = useRef(null);
    useLayoutEffect(() => {
        const host = chatHostRef.current;
        const target = isFloating ? floatingSlotRef.current : dockedSlotRef.current;
        if (target && host.parentNode !== target) {
            target.appendChild(host);
        }
    });

    return (
        <>
            <SEO
                title={t('seo.homeTitle')}
                description={t('seo.homeDescription')}
                robots={roomToken ? "noindex, nofollow" : "index, follow"}
                url={roomToken ? "https://app.nveil.com/" : undefined}
            />
            {/* Chat rendered once into stable portal target — never remounts */}
            {createPortal(
                <ErrorBoundary fallbackMessage="Chat failed to load">
                    <Suspense fallback={null}>
                        <Chat
                            roomToken={activeRoomToken}
                            isRoomReady={shouldStartViz}
                        />
                    </Suspense>
                </ErrorBoundary>,
                chatHostRef.current
            )}
            <main className={styles.homeContainer} role="main">
                <div className={`${styles.content} ${isMobileWithViz ? styles.mobileContent : ''}`}>
                    <PanelGroup
                        direction="horizontal"
                        className={`panelGroup ${isMobileWithViz ? styles.mobileLayout : ''}`}
                        ref={panelGroupRef}
                    >
                        <Panel
                            defaultSize={isVizPanelVisible ? 30 : 100}
                            collapsible
                            collapsedSize={0}
                            minSize={isMobileWithViz ? 0 : 20}
                            ref={leftPanelRef}
                            className={`${styles.panelLeft} ${isMobileWithViz ? (mobileTab === 'chat' ? styles.mobileChatActive : styles.mobileChatHidden) : ''}`}
                            id="chat-panel"
                        >
                            <div className={styles.chatPanelWrapper}>
                                {!isFloating && !isMobile && (
                                    <button
                                        className={styles.undockButton}
                                        onClick={toggleDock}
                                        data-tooltip="Pop out chat"
                                    >
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                            <polyline points="15 3 21 3 21 9" />
                                            <line x1="10" y1="14" x2="21" y2="3" />
                                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                                        </svg>
                                    </button>
                                )}
                                {/* Slot where stable chat host gets reparented when docked */}
                                <div ref={dockedSlotRef} style={{ width: '100%', height: '100%' }} />
                            </div>
                        </Panel>
                        <PanelResizeHandle
                            className="resize-handle"
                            style={{ display: isFloating || isMobileWithViz ? "none" : "flex" }}
                        >
                            <svg className="OG5fOa_Icon AzW8qW_ResizeHandleThumb" viewBox="0 0 24 24" data-direction="horizontal">
                                <path fill="currentColor" d="M11 18c0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2 2 .9 2 2m-2-8c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2m0-6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2m6 4c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2m0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2m0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2"></path>
                            </svg>
                        </PanelResizeHandle>
                        <Panel
                            collapsible
                            collapsedSize={0}
                            ref={rightPanelRef}
                            defaultSize={isVizPanelVisible ? 70 : 0}
                            minSize={isMobileWithViz ? 0 : 20}
                            className={`${styles.panelRight} ${isFloating ? styles.panelFull : ''} ${isMobileWithViz ? styles.mobileVizPanel : ''}`}
                            id="viz-panel"
                        >
                            <ErrorBoundary key={activeRoomToken} fallbackMessage="Visualization failed to load">
                                <Suspense fallback={<div style={{ width: '100%', height: '100%', background: 'black' }} />}>
                                    <Viz
                                        roomToken={activeRoomToken}
                                        shouldStart={shouldStartViz}
                                        onStart={handleStartViz}
                                        mobileTab={isMobileWithViz ? mobileTab : undefined}
                                        onMobileTabChange={isMobileWithViz ? setMobileTab : undefined}
                                    />
                                </Suspense>
                            </ErrorBoundary>
                        </Panel>
                    </PanelGroup>
                    {isMobileWithViz && (
                        <div className={styles.mobileTabBar}>
                            <button
                                className={`${styles.mobileTabButton} ${mobileTab === 'chat' ? styles.mobileTabActive : ''}`}
                                onClick={() => setMobileTab('chat')}
                            >
                                {t('home.chatTab', 'Chat')}
                            </button>
                            <button
                                className={`${styles.mobileTabButton} ${mobileTab === 'pipeline' ? styles.mobileTabActive : ''}`}
                                onClick={() => setMobileTab('pipeline')}
                            >
                                {t('nav.pipeline')}
                            </button>
                            <button
                                className={`${styles.mobileTabButton} ${mobileTab === 'viz' ? styles.mobileTabActive : ''}`}
                                onClick={() => setMobileTab('viz')}
                            >
                                {t('nav.visualization')}
                            </button>
                        </div>
                    )}
                </div>
                {isFloating && (
                    <div className={styles.floatingChat} ref={floatingRef}>
                        <div
                            className={styles.floatingChatHeader}
                            onPointerDown={dragHandlers.onPointerDown}
                            onPointerMove={dragHandlers.onPointerMove}
                            onPointerUp={dragHandlers.onPointerUp}
                            onDoubleClick={toggleMinimize}
                        >
                            <span className={styles.floatingChatTitle}>Chat</span>
                            <div className={styles.headerButtons}>
                                <button
                                    className={styles.minimizeButton}
                                    onClick={toggleMinimize}
                                    data-tooltip={chatMinimized ? "Expand chat" : "Minimize chat"}
                                >
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                        {chatMinimized
                                            ? <polyline points="17 11 12 6 7 11" />
                                            : <line x1="5" y1="12" x2="19" y2="12" />
                                        }
                                    </svg>
                                </button>
                                <button
                                    className={styles.dockButton}
                                    onClick={toggleDock}
                                    data-tooltip="Dock chat"
                                >
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                                        <line x1="9" y1="3" x2="9" y2="21" />
                                    </svg>
                                </button>
                            </div>
                        </div>
                        {/* Slot where stable chat host gets reparented when floating */}
                        <div ref={floatingSlotRef} className={styles.floatingChatBody} />
                        {/* Resize handles — all edges and corners */}
                        {!chatMinimized && ['n','s','e','w','ne','nw','se','sw'].map(edge => (
                            <div
                                key={edge}
                                className={styles['resize' + edge[0].toUpperCase() + edge.slice(1)]}
                                onPointerDown={e => onResizeStart(edge, e)}
                                onPointerMove={onResizeMove}
                                onPointerUp={onResizeEnd}
                            />
                        ))}
                    </div>
                )}
            </main>
        </>
    );
}
