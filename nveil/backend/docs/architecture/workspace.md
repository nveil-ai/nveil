# Workspace Filesystem

All services share a centralized filesystem rooted at `DIVE_PATH` (default: `/root/DIVE`).

## Layout

```
{DIVE_PATH}/
├── data_store/                         # User file uploads (managed by file_service)
│   └── {owner_id}/
│       ├── {file_id}.csv
│       ├── {file_id}.json
│       └── _temporal_{stem}/           # Temporal file collections
│           ├── 0001.csv
│           └── 0002.csv
│
└── {owner_id}/
    └── workspaces/
        └── {room_id}/
            ├── choregraph.xml          # Kedro pipeline definition
            ├── specifications.xml      # Visualization spec (VisuSpec XML)
            ├── metadata.json           # Dataset metadata, active palette
            ├── data/                   # Symlinks to data_store files
            │   ├── sales.csv -> ../../data_store/{owner_id}/{file_id}.csv
            │   └── geo.json -> ../../data_store/{owner_id}/{file_id}.json
            └── pipeline/               # Choregraph intermediate outputs
```

## Key concepts

### Data store vs workspace

- **Data store** (`data_store/{owner_id}/`): Permanent file storage. One copy per uploaded file.
- **Workspace** (`{owner_id}/workspaces/{room_id}/`): Per-room working directory. Data files are **symlinked**, not copied.

This means:
- A file uploaded once can be linked to multiple rooms
- Deleting a room's workspace doesn't delete the source file
- Re-uploading a file updates all rooms that link to it

### Symlink management

The file service manages symlinks via `link_files_to_room` and `unlink_file`:

```python
# Link: creates symlink in workspace/data/
link_data_file(workspace_path, "sales.csv", "/data_store/{owner_id}/{file_id}.csv")

# Unlink: removes symlink
unlink_data_file(workspace_path, "sales.csv")
```

### Temporal collections

File-based temporal sequences (animation frames) are stored in a subdirectory:

```
data_store/{owner_id}/_temporal_weather/
├── 0001.csv    # Timestep 1
├── 0002.csv    # Timestep 2
└── 0003.csv    # Timestep 3
```

The workspace symlinks to the collection directory, and `TimestepIndex` indexes the files.

### Path helpers

All path construction goes through `shared/workspace.py`:

| Function | Returns |
|----------|---------|
| `workspace_path(owner_id, room_id)` | `{DIVE_PATH}/{owner_id}/workspaces/{room_id}/` |
| `metadata_path(owner_id, room_id)` | `.../{room_id}/metadata.json` |
| `specs_xml_path(owner_id, room_id)` | `.../{room_id}/specifications.xml` |
| `panel_workspace_path(owner_id, room_id, panel_id)` | `.../{room_id}/panels/{panel_id}/` |

### Security

`shared/security.py` provides `safe_path(base, user_path)` to prevent directory traversal attacks. All user-supplied paths are resolved and validated against the workspace base.
