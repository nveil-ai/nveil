# File Service

**Port 8200** — File CRUD and workspace management

The file service owns all file operations: upload, delete, reupload, and workspace symlink management. It provisions room workspaces with data files and triggers Choregraph builds.

## Entry point

`file_service/file_server.py` — FastAPI application.

`file_service/app_factory.py` — Mounts routers and dependencies.

## Modules

- [Routes](routes.md) — HTTP endpoints
- [FileManager](file-manager.md) — Business logic

## Supported file types

| Category | Formats |
|----------|---------|
| Tabular | CSV, TSV, JSON, Parquet, Excel (XLSX/XLS/ODS) |
| Medical | MHD + ZRAW, DICOM series |
| Image | PNG, JPG, TIFF |
| Geospatial | GeoJSON |
| 3D | GLTF, STL, VTK |
