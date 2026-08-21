import asyncio

from app.cache import HotCache


def test_memory_rate_limit_counter_increments():
    cache = HotCache()

    async def run():
        assert await cache.increment("rate:test", ttl=60) == 1
        assert await cache.increment("rate:test", ttl=60) == 2

    asyncio.run(run())
