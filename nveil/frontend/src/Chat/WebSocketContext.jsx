// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Guillaume Franque
// SPDX-License-Identifier: AGPL-3.0-or-later

import { createContext, useContext, useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { useAuth } from '../Auth/AuthContext';

const WebSocketContext = createContext(null);

export const useWebSocket = () => {
	const ctx = useContext(WebSocketContext);
	if (!ctx) throw new Error('useWebSocket must be used within WebSocketProvider');
	return ctx;
};

// Compute WS URL once
const { wsUrl } = (() => {
	const isLocal = Boolean(import.meta.env.VITE_LOCAL);
	const isTest = Boolean(import.meta.env.VITE_TEST);
	let host, protocol;
	if (isLocal) {
		host = import.meta.env.VITE_URL_LOCAL_APP || window.location.host;
		protocol = "wss";
	} else if (isTest) {
		host = window.location.host;
		protocol = "ws";
	} else {
		host = window.location.host;
		protocol = window.location.protocol === "https:" ? "wss" : "ws";
	}
	let h;
	try { h = new URL(host).host; } catch { h = host; }
	if (h === "") h = host;
	return { wsUrl: `${protocol}://${h}/ws/events` };
})();

const INITIAL_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 30000;

export function WebSocketProvider({ children }) {
	const { isAuthenticated, refreshUser, user } = useAuth();
	const wsRef = useRef(null);
	const subscribersRef = useRef(new Map()); // eventType -> Set<callback>
	const currentRoomRef = useRef(null);
	const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
	const reconnectTimerRef = useRef(null);
	const [connected, setConnected] = useState(false);

	const handleMessage = useCallback((event) => {
		try {
			const data = JSON.parse(event.data);
			const eventType = data.event;
			if (!eventType) return;

			// Handle license_updated event - refresh user data
			if (eventType === 'license_updated' && data.action === 'refresh_user') {
				// Only refresh if this event is for the current user
				if (user && data.user_id === user.id) {
					console.debug('[WS] License updated, refreshing user data...');
					if (refreshUser) {
						refreshUser();
					}
				}
				return;
			}

			const callbacks = subscribersRef.current.get(eventType);
			if (callbacks) {
				callbacks.forEach(cb => {
					try { cb(data); } catch (e) { console.error(`[WS] subscriber error for ${eventType}:`, e); }
				});
			}

			// Also dispatch to wildcard subscribers (listen to all events)
			const wildcardCallbacks = subscribersRef.current.get('*');
			if (wildcardCallbacks) {
				wildcardCallbacks.forEach(cb => {
					try { cb(data); } catch (e) { console.error('[WS] wildcard subscriber error:', e); }
				});
			}
		} catch (e) {
			console.error('[WS] Failed to parse message:', e);
		}
	}, [user, refreshUser]);

	const connectWs = useCallback(() => {
		if (wsRef.current && (wsRef.current.readyState === WebSocket.CONNECTING || wsRef.current.readyState === WebSocket.OPEN)) {
			return;
		}

		const ws = new WebSocket(wsUrl);

		ws.onopen = () => {
			console.debug('[WS] Session-level WebSocket connected');
			setConnected(true);
			reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;

			// Re-subscribe to current room if we had one
			if (currentRoomRef.current) {
				ws.send(JSON.stringify({ action: 'subscribe', room_token: currentRoomRef.current }));
			}
		};

		ws.onmessage = handleMessage;

		ws.onclose = (e) => {
			console.debug('[WS] WebSocket closed', e.code, e.reason);
			setConnected(false);
			wsRef.current = null;

			// Auto-reconnect with exponential backoff (only if still authenticated)
			if (isAuthenticated) {
				const delay = reconnectDelayRef.current;
				reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY);
				reconnectTimerRef.current = setTimeout(connectWs, delay);
			}
		};

		ws.onerror = () => {};

		wsRef.current = ws;
	}, [isAuthenticated, handleMessage]);

	// Connect/disconnect based on auth state
	useEffect(() => {
		if (isAuthenticated) {
			connectWs();
		} else {
			if (reconnectTimerRef.current) {
				clearTimeout(reconnectTimerRef.current);
				reconnectTimerRef.current = null;
			}
			if (wsRef.current) {
				wsRef.current.close();
				wsRef.current = null;
			}
			setConnected(false);
			currentRoomRef.current = null;
		}

		return () => {
			if (reconnectTimerRef.current) {
				clearTimeout(reconnectTimerRef.current);
				reconnectTimerRef.current = null;
			}
			if (wsRef.current) {
				wsRef.current.close();
				wsRef.current = null;
			}
		};
	}, [isAuthenticated, connectWs]);

	const subscribe = useCallback((eventType, callback) => {
		if (!subscribersRef.current.has(eventType)) {
			subscribersRef.current.set(eventType, new Set());
		}
		subscribersRef.current.get(eventType).add(callback);

		// Return unsubscribe function
		return () => {
			const callbacks = subscribersRef.current.get(eventType);
			if (callbacks) {
				callbacks.delete(callback);
				if (callbacks.size === 0) {
					subscribersRef.current.delete(eventType);
				}
			}
		};
	}, []);

	const subscribeRoom = useCallback((roomToken) => {
		currentRoomRef.current = roomToken;
		if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
			wsRef.current.send(JSON.stringify({ action: 'subscribe', room_token: roomToken }));
		}
	}, []);

	const value = useMemo(() => ({
		subscribe,
		subscribeRoom,
		connected,
		ws: wsRef,
	}), [subscribe, subscribeRoom, connected]);

	return (
		<WebSocketContext.Provider value={value}>
			{children}
		</WebSocketContext.Provider>
	);
}
