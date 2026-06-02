// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Guillaume Franque
// SPDX-License-Identifier: AGPL-3.0-or-later

import { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../Auth/AuthContext";

const RoomContext = createContext();

/**
 * Custom hook to access the room context.
 * @throws {Error} If used outside of a RoomProvider.
 * @returns {object} The room context value.
 */
export const useRoom = () => {
    const context = useContext(RoomContext);
    if (!context) throw new Error("useRoom must be used within RoomProvider");
    return context;
};

/**
 * RoomProvider component that supplies room management context to its children.
 * 
 * Handles room list state, current room selection, room creation, switching, and deletion.
 * When switching rooms, the backend closes the viz instance of the previous room.
 * 
 * @component
 * @param {Object} props
 * @param {React.ReactNode} props.children - Child components that consume the room context.
 * @returns {JSX.Element} The RoomContext provider wrapping its children.
 */
export const RoomProvider = ({ children }) => {
    const { secureRequest, isAuthenticated, isGuest } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const [rooms, setRooms] = useState([]);
    const [currentRoom, setCurrentRoom] = useState(null);
    const [loading, setLoading] = useState(true);
    const [switching, setSwitching] = useState(false);
    const currentRoomRef = useRef(currentRoom);
    currentRoomRef.current = currentRoom;
    const locationRef = useRef(location);
    locationRef.current = location;
    const prevIsGuestRef = useRef(isGuest);

    /**
     * Fetch all rooms for the current user from the backend.
     */
    const fetchRooms = useCallback(async () => {
        if (!isAuthenticated) {
            setRooms([]);
            setCurrentRoom(null);
            setLoading(false);
            return;
        }
        try {
            const res = await secureRequest("/server/rooms/list");
            if (res.ok) {
                const data = await res.json();
                setRooms(data);

                const cur = currentRoomRef.current;
                if (cur) {
                    // Update current room data from fresh list
                    const updated = data.find(r => r.id === cur.id);
                    if (updated && JSON.stringify(updated) !== JSON.stringify(cur)) {
                        setCurrentRoom(updated);
                    } else if (data.length > 0 && !updated) {
                        // Current room not in the chat-rooms list. This is expected
                        // when viewing a dashboard (dashboards are excluded from /rooms/list).
                        const path = locationRef.current.pathname;
                        if (path.startsWith('/room/') || path === '/') {
                            setCurrentRoom(data[0]);
                            navigate(`/room/${data[0].token}`);
                        }
                    }
                }
            }
        } catch (e) {
            console.error("Failed to fetch rooms:", e);
        }
        setLoading(false);
    }, [isAuthenticated, secureRequest, navigate]);

    /**
     * Create a new room and auto-switch to it.
     * @returns {Promise<Object|null>} The new room object or null on failure.
     */
    const createRoom = async () => {
        try {
            const res = await secureRequest("/server/rooms/create", { method: "POST" });
            if (res.ok) {
                const newRoom = await res.json();
                // Refresh room list
                await fetchRooms();
                // Auto-switch to new room
                navigate(`/room/${newRoom.token}`, { state: { autoStart: true } });
                return newRoom;
            }
        } catch (e) {
            console.error("Failed to create room:", e);
        }
        return null;
    };

    /**
     * Switch to a different room. The backend will close the viz of the current room.
     * @param {string} roomIdentifier - The ID or Token of the room to switch to.
     * @param {boolean} doNavigate - Whether to navigate to the room URL.
     * @returns {Promise<boolean>} True if switch was successful.
     */
    const switchRoom = async (roomIdentifier, doNavigate = true) => {
        if (switching) return false;
        // Already on this room — just navigate if needed, skip the API call
        if (currentRoom && (currentRoom.id === roomIdentifier || currentRoom.token === roomIdentifier)) {
            if (doNavigate) {
                navigate(isGuest ? '/' : `/room/${currentRoom.token}`);
            }
            return true;
        }

        setSwitching(true);
        try {
            const res = await secureRequest(`/server/rooms/${roomIdentifier}/switch`, {
                method: "POST",
            });
            if (res.ok) {
                const data = await res.json();
                // Find the target room in our list, or build a minimal object.
                // Dashboards aren't in the rooms list — the fallback includes id
                // (from room_id) so fetchRooms won't treat it as a deleted room.
                const target = rooms.find(r => r.token === data.token)
                    || { id: data.room_id, token: data.token, ...data };
                setCurrentRoom(target);
                // Dispatch event for other components (Viz, Chat) to react
                window.dispatchEvent(new CustomEvent("roomSwitched", { detail: { success: true, roomToken: data.token } }));
                
                if (doNavigate) {
                    navigate(`/room/${data.token}`);
                }
                return true;
            }
        } catch (e) {
            console.error("Failed to switch room:", e);
        } finally {
            setSwitching(false);
        }
        return false;
    };

    /**
     * Delete a room. If it's the current room, auto-switch to another.
     * @param {string} roomId - The ID of the room to delete.
     * @returns {Promise<boolean>} True if deletion was successful.
     */
    const deleteRoom = async (roomId) => {
        try {
            const res = await secureRequest(`/server/rooms/${roomId}/delete`, {
                method: "DELETE",
            });
            if (res.ok) {
                const remaining = rooms.filter(r => r.id !== roomId);
                if (remaining.length === 0) {
                    // Last chat room gone — always create a replacement
                    await createRoom();
                    return true;
                }
                if (currentRoom?.id === roomId) {
                    navigate(`/room/${remaining[0].token}`);
                }
                await fetchRooms();
                return true;
            }
        } catch (e) {
            console.error("Failed to delete room:", e);
        }
        return false;
    };

    /**
     * Get a display-friendly title for a room.
     * Uses the last user message with ellipsis truncation, or "New Chat" if no messages.
     * @param {Object} room - The room object.
     * @param {number} maxLength - Maximum length before truncation (default 30).
     * @returns {string} The display title.
     */
    const getRoomTitle = (room, maxLength = 30) => {
        if (!room) return "New Chat";
        if (room.last_message) {
            const msg = room.last_message;
            // Strip HTML tags if present
            const cleanMsg = msg.replace(/<[^>]*>/g, '');
            return cleanMsg.length > maxLength
                ? cleanMsg.substring(0, maxLength) + "..."
                : cleanMsg;
        }
        return "New Chat";
    };

    // Fetch rooms when authentication state changes (including guest → logged-in)
    useEffect(() => {
        if (prevIsGuestRef.current && !isGuest) {
            setRooms([]);
            setCurrentRoom(null);
        }
        prevIsGuestRef.current = isGuest;
        fetchRooms();
    }, [isAuthenticated, isGuest]);

    // Refresh rooms periodically (every 30 seconds) to catch updates
    useEffect(() => {
        if (!isAuthenticated) return;
        const interval = setInterval(() => {
            fetchRooms();
        }, 30 * 1000);
        return () => clearInterval(interval);
    }, [isAuthenticated, fetchRooms]);

    // Sync URL with Room (skip URL navigation for guests)
    useEffect(() => {
        if (!isAuthenticated || rooms.length === 0) return;

        const match = location.pathname.match(/\/room\/([a-zA-Z0-9-]+)/);
        const roomTokenFromUrl = match ? match[1] : null;

        if (roomTokenFromUrl) {
            // If guest is on a room URL, redirect to root without room token
            if (isGuest) {
                navigate('/', { replace: true });
                // Still switch to the room internally (without navigation)
                if (!currentRoom || currentRoom.token !== roomTokenFromUrl) {
                    switchRoom(roomTokenFromUrl, false);
                }
            } else if (!currentRoom || currentRoom.token !== roomTokenFromUrl) {
                // Regular user: Switch without navigation
                switchRoom(roomTokenFromUrl, false);
            }
        } else if (location.pathname === "/" && !isGuest) {
            // Only navigate to room URL for non-guests
            navigate(`/room/${rooms[0].token}`);
        } else if (location.pathname === "/" && isGuest && !currentRoom && rooms.length > 0) {
            // Guest at root: switch to their room internally without URL change
            switchRoom(rooms[0].token, false);
        }
    }, [location.pathname, rooms, isAuthenticated, isGuest]);

    const value = {
        rooms,
        currentRoom,
        loading,
        switching,
        createRoom,
        switchRoom,
        deleteRoom,
        refreshRooms: fetchRooms,
        getRoomTitle,
    };

    return (
        <RoomContext.Provider value={value}>
            {children}
        </RoomContext.Provider>
    );
};
