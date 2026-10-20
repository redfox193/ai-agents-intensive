from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ClickEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    link_id: int
    user_agent: str
    referrer: str
    created_at: datetime


class LinkDetailedAnalytics(BaseModel):
    short_code: str
    total_clicks: int
    unique_visitors: int
    top_referrers: list[tuple[str, int]]
    recent_events: list[ClickEventResponse]
