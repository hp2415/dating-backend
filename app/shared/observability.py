"""Optional Sentry + structured logging bootstrap."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.shared.config import settings

_configured = False
_ACCESS_FIELDS = ("request_id", "method", "path", "status", "duration_ms", "client_ip")


class JsonFormatter(logging.Formatter):
    """One JSON object per line so docker logs can be shipped without a parser."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _ACCESS_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def use_json_logs() -> bool:
    chosen = (settings.log_format or "").strip().lower()
    if chosen == "json":
        return True
    if chosen == "text":
        return False
    return settings.app_env != "development"


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    level = logging.DEBUG if settings.app_env == "development" else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    if use_json_logs():
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    _configured = True


def init_sentry() -> None:
    """No-op when SENTRY_DSN is empty; soft-fails if sentry-sdk missing."""
    dsn = (settings.sentry_dsn or "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        logging.getLogger(__name__).warning("sentry-sdk not installed; skipping Sentry init")
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.app_env,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        send_default_pii=False,
    )


def capture_exception(exc: BaseException) -> None:
    if not (settings.sentry_dsn or "").strip():
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001
        pass
