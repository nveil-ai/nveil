# FileManager

Business logic for file operations in `file_service/services/file_manager.py`.

## Key methods

### File CRUD

```python
await upload_file(owner_id, file: UploadFile, collection=None) -> UserFile
```
Stores file in `data_store/{owner_id}/`, creates `UserFile` DB record. For temporal collections, stores in `_temporal_{stem}/` subdirectory.

```python
await delete_file(file_id) -> None
```
Removes file from data store and DB. Cleans up symlinks in all linked rooms.

```python
await reupload_file(file_id, file: UploadFile) -> UserFile
```
Replaces file content. Returns list of affected rooms for WebSocket notification.

```python
await get_user_files(owner_id) -> list[UserFile]
```
Lists all files with their room reference counts.

### Workspace management

```python
await link_files_to_room(room_id, file_ids: list[UUID]) -> None
```
Creates symlinks in the room workspace and `RoomDataRef` records. Additive — does not remove existing links.

```python
await apply_files_to_room(room_id) -> None
```
Writes `specifications.xml` and `metadata.json` from linked files. Triggers Choregraph build if a pipeline definition exists.

```python
await unlink_file(room_id, file_id) -> None
```
Removes symlink and `RoomDataRef` record.

### Helpers

```python
linkable_filenames(user_file: UserFile) -> list[str]
```
Returns filenames that should be symlinked (main file + companions).

```python
temporal_subdir(user_file: UserFile) -> str
```
Returns the temporal collection subdirectory name, if applicable.

## Per-room locking

Link/unlink/apply operations acquire an async lock per `room_id` to prevent concurrent workspace modifications.
