"""The observation envelope every source adapter normalizes to (spec 6.2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ObservationType = Literal["metric", "incident", "feedback", "update"]


class Observation(BaseModel):
    source_id: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    subject_code: str | None = None
    type: ObservationType
    value: float | None = None
    payload_ref: str | None = None
    observed_at: datetime
    period: str | None = Field(
        default=None, description="Aggregate period label; defaults to the observation date"
    )
    unit: str | None = None
    title: str | None = None
    summary: str | None = Field(
        default=None, description="Short summary only; message bodies stay out of the graph"
    )
    hints: dict[str, Any] = Field(
        default_factory=dict, description="Lane 2 hints (ticket id, link, thread, mentions)"
    )

    @model_validator(mode="after")
    def _check(self) -> Observation:
        if self.type == "metric" and self.value is None:
            raise ValueError("metric observations need a numeric value")
        if self.value is None and self.payload_ref is None and self.summary is None:
            raise ValueError("an observation needs a value, a payload_ref or a summary")
        return self

    def idempotency_key(self, tenant_id: str) -> tuple[str, str, str]:
        return (tenant_id, self.source_id, self.external_id)
