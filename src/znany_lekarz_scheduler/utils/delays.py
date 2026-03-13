from __future__ import annotations

import asyncio
import random


async def human_delay(base_seconds: float = 2.0, jitter: float = 0.5) -> None:
    delay = base_seconds + random.uniform(-jitter, jitter)
    await asyncio.sleep(max(0.5, delay))


async def between_doctors_delay() -> None:
    await asyncio.sleep(random.uniform(30, 90))


async def post_login_delay() -> None:
    await asyncio.sleep(random.uniform(3, 8))


async def page_load_delay() -> None:
    await asyncio.sleep(random.uniform(2, 5))
