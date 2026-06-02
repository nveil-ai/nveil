# State Management

State is managed through React Context (no Redux or Zustand). Three core providers handle authentication, WebSocket connectivity, and room lifecycle.

## AuthContext

`Auth/AuthContext.jsx` — User session and secure API calls.

### State

| Field | Type | Description |
|-------|------|-------------|
| `user` | object | Current user (id, email, name, etc.) |
| `isGuest` | boolean | Guest mode active |
| `loading` | boolean | Auth state loading |
| `showAuthModal` | boolean | Show login/signup modal |
| `profileComplete` | boolean | All required fields filled |

### Key methods

```javascript
// CSRF-protected fetch with auto token refresh
const response = await secureRequest("/server/rooms/list");

// Auth actions
await login(email, password);
await logout();
await refetchUser();
```

### Token handling

- JWT stored in `access_token` HTTP-only cookie
- Auto-refresh when token expires within 2 minutes
- Proactive refresh every 30 minutes as fallback
- CSRF token managed automatically by `secureRequest()`

---

## WebSocketContext

`Chat/WebSocketContext.jsx` — Persistent WebSocket connection for real-time events.

### Usage

```javascript
const { connected, subscribe, subscribeRoom } = useWebSocket();

// Subscribe to all events
const unsub = subscribe("*", (data) => console.log(data));

// Subscribe to room-specific events
subscribeRoom(roomToken);
```

### Features

- Auto-reconnect with exponential backoff (1s → 30s max)
- Pub/sub pattern with event type filtering
- Room-specific subscriptions
- License update listener (auto-refreshes user data)

---

## RoomContext

`Room/RoomContext.jsx` — Room lifecycle and navigation.

### State

| Field | Type | Description |
|-------|------|-------------|
| `rooms` | array | User's rooms |
| `currentRoom` | object | Active room |
| `loading` | boolean | Rooms loading |
| `switching` | boolean | Room switch in progress |

### Key methods

```javascript
const { createRoom, switchRoom, deleteRoom, refreshRooms } = useRoom();

await createRoom();                    // Create new room
await switchRoom(roomIdentifier);      // Switch by ID or token
await deleteRoom(roomId);              // Delete with fallback
```

### Features

- URL sync: room token in URL (`/room/:roomToken`)
- Guest mode: guests stay at `/` (no tokens in URL)
- Periodic sync: re-fetches rooms every 30 seconds
- Viz cleanup: closes previous room's viz on switch
- Custom event: dispatches `roomSwitched` for cross-component coordination
