"""API request/response models."""

from __future__ import annotations

from datetime import UTC, date, datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_serializer, field_validator

from .providers import LLMConfig


class LLMConfigIn(BaseModel):
    provider: str
    model: str = ""
    api_key: SecretStr | None = None  # SecretStr keeps the key out of logs and reprs
    base_url: str | None = None

    def to_config(self) -> LLMConfig:
        key = self.api_key.get_secret_value().strip() if self.api_key else None
        return LLMConfig(self.provider, self.model.strip(), key or None, (self.base_url or "").strip() or None)


class TestConnectionIn(LLMConfigIn):
    pass


class RunCreate(BaseModel):
    app: str = Field(min_length=3, description="Play Store app ID or link")
    country: str = Field("us", min_length=2, max_length=2)
    lang: str = Field("en", min_length=2, max_length=7)
    count: int = Field(200, ge=10, le=2000)
    ratings: list[int] | None = Field(None, description="Only these star ratings, e.g. [1, 2]. Omit for all.")
    output_language: str = Field("English", max_length=32)
    llm: LLMConfigIn

    @field_validator("country", "lang")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("ratings")
    @classmethod
    def _ratings(cls, v: list[int] | None) -> list[int] | None:
        if not v:
            return None
        if any(r not in range(1, 6) for r in v):
            raise ValueError("ratings must be between 1 and 5")
        return sorted(set(v))


class EstimateIn(BaseModel):
    count: int = Field(200, ge=10, le=2000)


class AppOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    store_id: str
    title: str | None
    developer: str | None
    icon_url: str | None
    genre: str | None
    score: float | None
    ratings_count: int | None
    installs: str | None
    version: str | None
    store_url: str | None


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    stage: str | None
    progress_done: int
    progress_total: int
    message: str | None
    error: str | None
    country: str | None
    lang: str | None
    ratings: list[int] | None
    requested_count: int
    output_language: str
    provider: str
    model: str
    tag_version: int = 1
    review_count: int
    tagged_count: int
    failed_count: int
    input_tokens: int
    output_tokens: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    app: AppOut

    @field_serializer("created_at", "started_at", "finished_at")
    def _utc(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


class MetricsQueryIn(BaseModel):
    measures: list[str] = Field(min_length=1)
    dimensions: list[str] = Field(default_factory=list, max_length=3)
    filters: dict[str, list[str | int]] = Field(default_factory=dict)
    time_grain: str = "day"
    date_from: date | None = None
    date_to: date | None = None
    order_by: str | None = None
    descending: bool = True
    limit: int | None = Field(None, ge=1, le=1000)
