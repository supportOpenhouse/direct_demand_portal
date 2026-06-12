import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["admin", "cm", "rm"]
Source = Literal["meta", "gads", "99acres", "magicbricks", "youtube", "whatsapp", "api", "webhook", "sheets"]
Stage = Literal[
    "new", "contacted", "visit_scheduled", "visit_feedback", "negotiation",
    "won", "lost", "future_prospect", "timepass",
]
PlanToBuy = Literal["within_30_days", "1_3_months", "3_6_months", "just_exploring"]
Purpose = Literal["self_use", "investment"]
OfficeWilling = Literal["yes", "no", "maybe"]
ReminderType = Literal["follow_up", "visit_schedule", "visit_feedback", "negotiation"]
Segment = Literal["new", "qualified", "pipeline", "converted"]


class GoogleAuthRequest(BaseModel):
    credential: str


class DevLoginRequest(BaseModel):
    email: str


class IngestLeadRequest(BaseModel):
    name: str = Field(min_length=1)
    phone: str = Field(min_length=4)
    source: Source
    city: str | None = None
    society: str | None = None
    configuration: str | None = None
    budget_band: str | None = None
    budget_min_lacs: float | None = None
    budget_max_lacs: float | None = None
    plan_to_buy: PlanToBuy | None = None


class SourceDataPatch(BaseModel):
    budget_band: str | None = None
    budget_min_lacs: float | None = None
    budget_max_lacs: float | None = None
    city: str | None = None
    society: str | None = None
    configuration: str | None = None
    plan_to_buy: PlanToBuy | None = None


class ConfirmRequest(BaseModel):
    # All optional at the schema level: the endpoint validates Q1/Q2/Q3/Q6 itself so
    # the 422 carries a per-field map for EVERY missing mandatory field at once.
    purpose: Purpose | None = None
    budget_value_lacs: float | None = None
    configuration: str | None = None
    shortlist_societies: list[str] = Field(default_factory=list)
    preferred_localities: list[str] = Field(default_factory=list)
    office_willing: OfficeWilling | None = None
    office_preferred_date: date | None = None
    remark: str | None = None


class StageRequest(BaseModel):
    to_stage: Stage
    remark: str | None = None


class HotRequest(BaseModel):
    is_hot: bool


class ReminderCreate(BaseModel):
    lead_id: uuid.UUID
    type: ReminderType
    note: str | None = None
    due_at: datetime


class ReminderPatch(BaseModel):
    done: bool | None = None


class VisitStopIn(BaseModel):
    inventory_id: uuid.UUID
    seq: int


class VisitCreate(BaseModel):
    trip_date: date
    stops: list[VisitStopIn] = Field(min_length=1)
    total_km: float = 0.0
    total_min: float = 0.0
    route_source: Literal["est", "google"] = "est"


class RecordingCreate(BaseModel):
    file_ref: str = Field(min_length=1)
    duration_sec: int = 0


class InterestCreate(BaseModel):
    note: str | None = None
    lead_id: uuid.UUID | None = None


class BroadcastRequest(BaseModel):
    mode: Literal["whatsapp", "call_list"]


class InsightCreate(BaseModel):
    society: str = Field(min_length=1)
    city: str = Field(min_length=1)
    note: str = Field(min_length=1)


class UserCreate(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    phone: str | None = None
    role: Role
    team_id: uuid.UUID | None = None


class IntegrationPatch(BaseModel):
    key: str
    enabled: bool


class AssignmentPatch(BaseModel):
    method: str = Field(min_length=1)
