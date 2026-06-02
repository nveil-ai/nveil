# Logger

`tools/logger/` — Structured logging utility used by all services.

## Usage

```python
from logger import logger, INFO, ERROR, WARNING, DEBUG, SUCCESS

# Initialize (once per service)
log = logger(service="SERVER", service_id="MAIN")

# Log messages
log.info("Server started on port 8000")
log.debug("Processing request", extra={"room_id": "abc"})
log.warning("Slow query detected")
log.error("Database connection failed")
log.success("Migration complete")
```

## Log levels

| Level | Color (local) | Usage |
|-------|--------------|-------|
| `DEBUG` | Yellow | Detailed diagnostic info |
| `INFO` | White | General operational messages |
| `WARNING` | Orange | Non-critical issues |
| `ERROR` | Red | Failures requiring attention |
| `SUCCESS` | Green | Completed operations |

## Environment modes

- **Local** (`LOCAL=1`): Colored console output with service name prefix
- **GCP** (`GCP=1`): Structured logfmt output for Cloud Logging ingestion

## Singleton pattern

`logger()` returns the same instance when called with the same `service` name. Multiple calls with the same service name return the existing logger.
