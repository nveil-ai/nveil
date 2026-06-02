# Security

`shared/security.py` — Path validation and filename sanitization to prevent directory traversal and injection attacks.

## Path validation

```python
safe_path(base: Path, user_supplied: str) -> Path
```

Resolves `user_supplied` relative to `base` and validates the result is within `base`. Raises `ValueError` if the resolved path escapes the base directory (e.g., via `../`).

```python
# Safe
safe_path(Path("/data/user1"), "file.csv")
# -> /data/user1/file.csv

# Raises ValueError
safe_path(Path("/data/user1"), "../../etc/passwd")
```

## Filename sanitization

```python
sanitize_filename(name: str) -> str
```

Strips dangerous characters, keeping only alphanumeric, `.`, `-`, `_`. Prevents injection via filenames.

```python
sanitize_file_path(path: str, allowed_base: Path) -> Path
```

Combines sanitization with path validation.
