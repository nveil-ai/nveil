# Workspace

`shared/workspace.py` — Centralized path construction for the workspace filesystem.

All services use these helpers to build consistent paths. The root is configured via `DIVE_PATH` env var (default: `/root/DIVE`).

## Path helpers

| Function | Returns |
|----------|---------|
| `workspace_path(owner_id, room_id)` | `{DIVE_PATH}/{owner_id}/workspaces/{room_id}/` |
| `metadata_path(owner_id, room_id)` | `.../{room_id}/metadata.json` |
| `specs_xml_path(owner_id, room_id)` | `.../{room_id}/specifications.xml` |
| `panel_workspace_path(owner_id, room_id, panel_id)` | `.../{room_id}/panels/{panel_id}/` |

## Metadata operations

```python
read_metadata(owner_id, room_id) -> dict
```
Reads `metadata.json` from the workspace. Returns empty dict if file doesn't exist.

```python
write_metadata(owner_id, room_id, data) -> None
```
Writes `metadata.json` to the workspace.

## Symlink operations

```python
link_data_file(workspace: Path, filename: str, source: Path) -> None
```
Creates a symlink in `workspace/data/{filename}` pointing to `source`.

```python
unlink_data_file(workspace: Path, filename: str) -> None
```
Removes the symlink.
