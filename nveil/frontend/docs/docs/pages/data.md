# Data Manager

`Data/DataManager.jsx` — File upload, management, and room linking.

## Upload flow

1. User selects files via `UploadPanel`
2. Files uploaded to `POST /server/data/upload` (proxied to file service)
3. File metadata returned (id, name, size, companions)
4. User selects files and clicks "Link to Room"
5. `POST /server/rooms/{roomId}/link-files` creates workspace symlinks

## Features

- **Multi-file upload**: Drag-and-drop or file picker
- **Companion files**: MHD+ZRAW, DICOM series handled automatically
- **Temporal collections**: Upload multiple files as a time series
- **Re-upload**: Replace existing file (notifies linked rooms via WebSocket)
- **Delete**: Remove file from data store

## Supported formats

| Category | Formats |
|----------|---------|
| Tabular | CSV, TSV, JSON, Parquet, Excel (XLSX/XLS/ODS) |
| Medical | MHD + ZRAW, DICOM |
| Biosignal | EDF/EDF+ (EEG, ECG, PSG) |
| Image | PNG, JPG, TIFF |
| Geospatial | GeoJSON |
| 3D | GLTF, STL, VTK |
