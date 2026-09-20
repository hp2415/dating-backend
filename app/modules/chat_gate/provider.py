"""Cloud IM adapter re-export — prefer app.modules.messaging.provider."""

from app.modules.messaging.provider import ImProvider, NoopImProvider, get_im_provider

__all__ = ["ImProvider", "NoopImProvider", "get_im_provider"]
