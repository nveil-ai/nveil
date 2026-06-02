# Services

Business logic layer in `server_service/database/services/`. Each service composes one or more repositories and encapsulates domain logic.

## UserService

```python
create_user(name, email, password) -> User
get_by_email(email) -> User | None
get_by_id(user_id) -> User | None
verify_password(email, password) -> bool
update_user_profile(user_id, **kwargs) -> User
```

## RoomService

```python
create_room(owner_id, name=None, type="CHAT") -> Room
get_user_rooms(user_id) -> list[Room]
get_room_by_id(room_id) -> Room | None
get_room_by_token(token) -> Room | None
delete_room(room_id) -> None
add_member(room_id, user_id, role="MEMBER") -> RoomMember
send_message(room_id, user_id, text) -> Message
get_messages(room_id, limit=50) -> list[Message]
```

## TokenService

```python
create_tokens(user_id) -> tuple[str, str]  # (access_token, refresh_token)
verify_token(token) -> dict | None          # JWT payload
create_refresh_token(user_id, token) -> RefreshToken
rotate_refresh_token(old_token) -> tuple[str, str] | None
```

## DashboardService

```python
create_dashboard(owner_id, name) -> Room
list_dashboards(owner_id) -> list[Room]
add_panel(room_id, panel_config) -> DashboardPanel
remove_panel(room_id, panel_id) -> None
update_layout(dashboard_id, layout) -> None
delete_dashboard(dashboard_id) -> None
```

## FileService

```python
get_rooms_for_file(file_id) -> list[Room]  # For reupload WS notifications
```

## ApiKeyService

```python
generate_key(user_id) -> tuple[str, ApiKey]  # (plaintext, record)
validate_key(key) -> User | None
revoke_key(key_id, user_id) -> None
list_keys(user_id) -> list[ApiKey]
```

## EmailService

SendGrid integration for transactional emails:

```python
send_password_reset(email, token) -> None
send_welcome(email, name) -> None
```

## LicenseService / LicenseCatalogService / LicenseSeatService

SaaS subscription management: license validation, seat allocation, tier pricing.

## Repository pattern

Each service uses repositories (`server_service/database/repository/`) for data access. Repositories inherit from `BaseRepository` and provide typed CRUD operations over SQLAlchemy models.
