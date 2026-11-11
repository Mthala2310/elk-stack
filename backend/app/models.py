from datetime import datetime
from pydantic import (
    BaseModel,
    Field,
    model_validator,
)
from app.config import get_settings


class TimeRange(BaseModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError(
                "start dan end wajib memiliki timezone."
            )
        if self.start >= self.end:
            raise ValueError(
                "start harus lebih kecil dari end."
            )
        
        max_hours = get_settings().tool_max_lookback_hours
        duration_hours = (
            self.end - self.start
        ).total_seconds() / 3600
        
        if duration_hours > max_hours:
            raise ValueError(
                f"Time range maksimal {max_hours} jam."
            )
        return self


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=4000
    )
    index: str | None = None
