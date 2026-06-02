# Service Client

`shared/service_client.py` — Async HTTP client for inter-service communication.

## ServiceClient

Wraps `httpx.AsyncClient` with:

- Configurable timeouts
- Uniform response format (`ServiceResponse`)
- Error handling and logging

## Usage

```python
from shared.service_client import ServiceClient

client = ServiceClient()

# POST to another service
response = await client.post(
    "https://ai-service:8100/ai/process_user_message",
    json={"message": "...", "room_id": "..."},
    timeout=60.0,
)

if response.ok:
    data = response.data
else:
    error = response.error

await client.close()
```

## ServiceResponse

| Attribute | Type | Description |
|-----------|------|-------------|
| `ok` | bool | Whether the request succeeded (2xx) |
| `status_code` | int | HTTP status code |
| `data` | dict | Parsed JSON response body |
| `error` | str | Error message (if not ok) |
