from src.core.session_pool import SessionPool

_pool: SessionPool | None = None


async def init_session_pool() -> None:
    global _pool  # noqa: PLW0603
    _pool = SessionPool()
    await _pool.init()


async def close_session_pool() -> None:
    global _pool  # noqa: PLW0603
    if _pool:
        await _pool.close()
        _pool = None


async def get_session_pool() -> SessionPool:
    if _pool is None:
        raise RuntimeError("Session pool not initialized")
    return _pool
