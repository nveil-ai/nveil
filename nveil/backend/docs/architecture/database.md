# Database Schema

All services share a single PostgreSQL instance. The server and file services use the main schema; the AI service uses a separate state schema.

## Server / File schema

```mermaid
erDiagram
    users ||--o{ rooms : owns
    users ||--o{ room_members : member_of
    users ||--o{ messages : sends
    users ||--o{ user_files : uploads
    users ||--o{ api_keys : has
    users ||--o{ refresh_tokens : has
    users ||--o{ connection_logs : logged
    users ||--o{ licenses : holds
    rooms ||--o{ room_members : has
    rooms ||--o{ messages : contains
    rooms ||--o{ room_data_refs : links
    rooms ||--o{ dashboard_panels : contains
    user_files ||--o{ room_data_refs : referenced_by
    licenses ||--o{ license_seats : allocates

    users {
        uuid id PK
        string email UK
        string name
        string _password
        string country
        string profession
        datetime created_at
    }

    rooms {
        uuid id PK
        uuid owner_id FK
        string name
        string type
        string token UK
        string host
        int cmd_port
        int viz_port
    }

    room_members {
        int id PK
        uuid room_id FK
        uuid user_id FK
        string role
    }

    messages {
        int id PK
        uuid room_id FK
        uuid user_id FK
        text text
        datetime created_at
    }

    user_files {
        uuid id PK
        uuid owner_id FK
        string original_name
        bigint size
        json companion_files
    }

    room_data_refs {
        int id PK
        uuid room_id FK
        uuid file_id FK
        string panel_id
    }

    dashboard_panels {
        int id PK
        uuid room_id FK
        string name
        json layout
        json config
    }

    api_keys {
        int id PK
        uuid user_id FK
        string key_hash
        datetime last_used
    }

    refresh_tokens {
        int id PK
        uuid user_id FK
        string token_hash
        datetime expires_at
    }

    connection_logs {
        int id PK
        uuid user_id FK
        string ip_address
        string action
        datetime created_at
    }

    licenses {
        int id PK
        uuid owner_id FK
        string key
        string tier
        int seats
        datetime expires_at
    }

    license_seats {
        int id PK
        int license_id FK
        uuid user_id FK
    }
```

## AI state schema

| Table | Columns | Purpose |
|-------|---------|---------|
| `turn_metrics_record` | id, room_id, user_id, turn_number, input_tokens, output_tokens, cached_tokens, latency_ms, classification, timestamp | Per-turn LLM metrics |
| `user_properties` | id, user_id, tone, additional_info | User preferences for AI responses |

## Migrations

Alembic manages schema migrations from `server_service/database/models/alembic/`. One migration system for the shared database — the file service does not run its own migrations.
