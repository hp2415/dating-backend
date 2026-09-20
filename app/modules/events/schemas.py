from pydantic import BaseModel, Field


class EnqueueEventRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    aggregate_kind: str = Field(default="ops", min_length=1, max_length=32)
    aggregate_id: str = Field(default="manual", min_length=1, max_length=64)
    payload: dict = Field(default_factory=dict)
