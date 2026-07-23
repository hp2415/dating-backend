"""Background workers package (ARQ / Redis Streams later)."""

import asyncio
import logging

from redis.asyncio import Redis

from app.shared.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("dating-worker")


async def run() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("Worker started. env=%s redis=%s", settings.app_env, settings.redis_url)
    try:
        while True:
            # Placeholder loop — replace with ARQ worker when task queue is wired.
            await redis.set("worker:heartbeat", "1", ex=30)
            await asyncio.sleep(10)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(run())
