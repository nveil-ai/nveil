# Server Routes

## Authentication (`/server/auth/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/server/auth/register` | Create user account |
| POST | `/server/auth/login` | JWT + refresh token login |
| POST | `/server/auth/refresh` | Rotate refresh token |
| POST | `/server/auth/logout` | Invalidate tokens |
| POST | `/server/auth/forgot-password` | Send password reset email |
| POST | `/server/auth/reset-password` | Reset password with token |
| GET | `/server/auth/oauth/{provider}` | OAuth2 redirect |
| GET | `/server/auth/oauth/{provider}/callback` | OAuth2 callback |

## Rooms (`/server/rooms/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/server/rooms/create` | Create a new room |
| GET | `/server/rooms/list` | List user's rooms |
| DELETE | `/server/rooms/{room_id}/delete` | Delete room and workspace |
| GET | `/server/room/status` | Check viz container status |
| POST | `/server/rooms/{room_id}/members` | Add room member |

## Data (`/server/data/`)

Proxied to the file service:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/server/data/list` | List user's uploaded files |
| POST | `/server/data/upload` | Upload file (multipart) |
| DELETE | `/server/data/{file_id}` | Delete file |
| POST | `/server/data/{file_id}/reupload` | Replace file |
| POST | `/server/rooms/{room_id}/link-files` | Link files to room workspace |

## Chat (`/server/chat/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ai/sendUserMessage` | Send message to AI (proxied to AI service) |
| GET | `/server/get_history` | Get chat history for room |
| POST | `/server/chat/messages` | Store a message |

## Dashboards (`/dashboards/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/dashboards` | List user's dashboards |
| POST | `/dashboards/create` | Create dashboard |
| PUT | `/dashboards/{id}/layout` | Update dashboard layout |
| POST | `/dashboards/{id}/add-panel` | Add panel to dashboard |
| DELETE | `/dashboards/{id}/remove-panel/{panel_id}` | Remove panel |
| POST | `/dashboards/{id}/start` | Start dashboard viz containers |
| DELETE | `/dashboards/{id}` | Delete dashboard |

## Settings

| Method | Path | Description |
|--------|------|-------------|
| GET | `/server/user/settings` | Get user preferences |
| POST | `/server/user/settings` | Update user preferences |

## API Keys (`/api/v1/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/keys` | Generate API key |
| GET | `/api/v1/keys` | List API keys |
| DELETE | `/api/v1/keys/{id}` | Revoke API key |

## API Specifications (`/api/v1/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/sdk/process` | Unified SDK endpoint (fresh call or resume, polymorphic on `session_id`) |

## Viz Proxy (`/viz/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/viz/send` | Forward command to viz container |
| POST | `/viz/refresh_all` | Refresh all viz data |
| WebSocket | `/viz/app/ws` | Trame WebSocket proxy |
| GET | `/kedro-viz/*` | Kedro Viz static proxy |

## WebSocket

| Path | Description |
|------|-------------|
| `/ws/events` | Room event hub (chat messages, viz updates, notifications) |
