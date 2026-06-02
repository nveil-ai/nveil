# API Layer

The frontend communicates with the backend via HTTP (fetch) and WebSocket. All API calls go through the Vite dev proxy in development and directly to the server in production.

## Proxy configuration (development)

Defined in `vite.config.js`:

| Prefix | Target | Description |
|--------|--------|-------------|
| `/server` | `https://localhost:8000` | Server service API |
| `/api` | `https://localhost:8000` | REST API (keys, specs) |
| `/oauth` | `https://localhost:8000` | OAuth callbacks |
| `/viz` | `https://localhost:8000` | Viz proxy (Trame WS) |
| `/assets` | `https://localhost:8000` | Static assets |

## Secure requests

All authenticated API calls use `secureRequest()` from `AuthContext`:

```javascript
const { secureRequest } = useAuth();

// GET
const data = await secureRequest("/server/rooms/list");

// POST with body
const result = await secureRequest("/server/rooms/create", {
  method: "POST",
  body: JSON.stringify({ name: "My Room" }),
});
```

### What `secureRequest` handles

1. Checks JWT expiry — refreshes if within 2 minutes
2. Attaches CSRF token header
3. Sets `Content-Type: application/json`
4. Returns parsed JSON response

## WebSocket

Single persistent connection at `wss://{host}/ws/events`:

```javascript
const { subscribe, subscribeRoom } = useWebSocket();

// Listen for events
subscribe("file_reupload", (data) => {
  console.log(`File ${data.file_id} was re-uploaded`);
});

// Subscribe to room events
subscribeRoom(roomToken);
```

## Key API endpoints

### Rooms
- `GET /server/rooms/list`
- `POST /server/rooms/create`
- `POST /server/rooms/{id}/switch`
- `DELETE /server/rooms/{id}/delete`

### Chat
- `POST /ai/sendUserMessage`
- `GET /server/get_history`

### Data
- `GET /server/data/list`
- `POST /server/data/upload`
- `POST /server/rooms/{roomId}/link-files`

### Auth
- `POST /server/auth/login`
- `POST /server/auth/register`
- `POST /server/auth/refresh`
- `POST /server/auth/logout`
