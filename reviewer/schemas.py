"""Validated request models for the local reviewer API."""

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SaveRequest(StrictModel):
    record_ids: list[str] = Field(min_length=1)
    revision: int
    reviewed: dict[str, str] = Field(default_factory=dict)


class ReviewRequest(StrictModel):
    revision: int
    reviewed: dict[str, str]


class MappingRequest(StrictModel):
    revision: int
    columns: dict[int, str]


class ActivationRequest(StrictModel):
    reference_id: str


class CheckRequest(StrictModel):
    record_ids: list[str] = Field(min_length=1)


class ReviewDetails(StrictModel):
    contractor: str = Field(default="", max_length=300)
    classification: str = Field(default="", max_length=300)
    work_start: str = ""
    work_end: str = ""


class ClassificationAlias(StrictModel):
    contractor: str = Field(min_length=1, max_length=300)
    source_label: str = Field(min_length=1, max_length=300)
    target_position: str = Field(min_length=1, max_length=500)


class BulkDetails(StrictModel):
    records: dict[str, ReviewDetails] = Field(min_length=1, max_length=10000)
