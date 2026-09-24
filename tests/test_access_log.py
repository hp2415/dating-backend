import json
import logging

from app.shared.observability import JsonFormatter


def test_json_formatter_keeps_access_fields():
    record = logging.LogRecord(
        name="dating.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="%s %s %s %dms",
        args=("GET", "/api/v1/posts", 200, 12),
        exc_info=None,
    )
    record.request_id = "abc"
    record.method = "GET"
    record.path = "/api/v1/posts"
    record.status = 200
    record.duration_ms = 12
    record.client_ip = "1.2.3.4"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["logger"] == "dating.access"
    assert payload["message"] == "GET /api/v1/posts 200 12ms"
    assert payload["request_id"] == "abc"
    assert payload["status"] == 200
    assert payload["duration_ms"] == 12
    assert "exception" not in payload
