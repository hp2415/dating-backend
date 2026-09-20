"""Optional Sentry + structured logging bootstrap."""

from __future__ import annotations

import logging
import sys

from app.shared.config import settings

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    level = logging.DEBUG if settings.app_env == "development" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
        force=True,
    )
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
