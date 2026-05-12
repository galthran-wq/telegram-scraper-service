from pydantic import BaseModel


class SessionInfo(BaseModel):
    name: str
    connected: bool


class EvictionEvent(BaseModel):
    ts: str
    session: str
    reason: str


class PoolStatusResponse(BaseModel):
    alive: int
    configured: int
    sessions: list[SessionInfo]
    recent_evictions: list[EvictionEvent]
    rescan_interval: int
