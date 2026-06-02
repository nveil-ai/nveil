# Database Models

SQLAlchemy ORM models in `server_service/database/models/`.

## User

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `email` | String | Unique, indexed |
| `name` | String | Display name |
| `_password` | String | bcrypt hash |
| `country` | String | User's country |
| `profession` | String | User's profession |
| `created_at` | DateTime | Registration timestamp |

## Room

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `owner_id` | UUID FK | Room creator |
| `name` | String | Room display name |
| `type` | Enum | `CHAT` or `DASHBOARD` |
| `token` | String | Unique auth token for viz access |
| `host` | String | Viz container hostname (nullable) |
| `cmd_port` | Integer | Viz command port (nullable) |
| `viz_port` | Integer | Viz WebSocket port (nullable) |

## RoomMember

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | Primary key |
| `room_id` | UUID FK | Room reference |
| `user_id` | UUID FK | User reference |
| `role` | String | `OWNER` or `MEMBER` |

## Message

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | Primary key |
| `room_id` | UUID FK | Room reference |
| `user_id` | UUID FK | Sender (null = bot) |
| `text` | Text | Message content |
| `created_at` | DateTime | Timestamp |

## UserFile

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `owner_id` | UUID FK | File owner |
| `original_name` | String | Original filename |
| `size` | BigInteger | File size in bytes |
| `companion_files` | JSON | Associated files (e.g., `.zraw` for `.mhd`) |

## RoomDataRef

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | Primary key |
| `room_id` | UUID FK | Room reference |
| `file_id` | UUID FK | File reference |
| `panel_id` | String | Dashboard panel ID (nullable) |

## DashboardPanel

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | Primary key |
| `room_id` | UUID FK | Parent room |
| `name` | String | Panel display name |
| `layout` | JSON | Grid position/size |
| `config` | JSON | Panel configuration |

## ApiKey

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | Primary key |
| `user_id` | UUID FK | Key owner |
| `key_hash` | String | SHA-256 hash of the key |
| `last_used` | DateTime | Last usage timestamp |

## RefreshToken

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | Primary key |
| `user_id` | UUID FK | Token owner |
| `token_hash` | String | SHA-256 hash |
| `expires_at` | DateTime | Expiration |

## License / LicenseCatalog / LicenseSeat

Subscription management models for SaaS licensing. See `license.py`, `license_catalog.py`, `license_seat.py`.
