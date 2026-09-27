from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

Kind = Literal['public_designated','venue_designated','informal_outdoor','venue_claim']
Status = Literal['verified_designated','community_reported','disputed','prohibited','closed']

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Point(Strict):
    lat: float = Field(ge=-90,le=90)
    lon: float = Field(ge=-180,le=180)

class Register(Strict):
    email: str = Field(min_length=5,max_length=254)
    password: str = Field(min_length=12,max_length=128)
    adult_attested: Literal[True]

class Login(Strict):
    email: str
    password: str

class Token(Strict):
    access_token: str
    token_type: Literal['bearer'] = 'bearer'

class SubmissionIn(Strict):
    intent: Literal['create','correct']
    place_id: str | None = None
    name: str = Field(min_length=2,max_length=120)
    kind: Kind
    location: Point
    access_point: Point | None = None
    address_label: str | None = Field(default=None,max_length=240)
    access_notes: str | None = Field(default=None,max_length=500)
    inside_venue: bool | None = None
    basis: str = Field(min_length=10,max_length=1000)
    @model_validator(mode='after')
    def intent_valid(self):
        if self.kind == 'venue_designated' and self.inside_venue is None:
            raise ValueError('inside_venue is required for venue_designated')
        if (self.intent == 'correct') != (self.place_id is not None):
            raise ValueError('place_id is required only for corrections')
        return self

class ConfirmationIn(Strict):
    observation: Literal['still_there','changed','gone']
    observed_at: datetime
    access_note_suggestion: str | None = Field(default=None,max_length=500)

class ReviewIn(Strict):
    stars: int = Field(ge=1,le=5)
    body: str | None = Field(default=None,max_length=1000)

class ReportIn(Strict):
    target_type: Literal['place','review']
    target_id: str
    reason: Literal['wrong_status','closed','access_notes','privacy','harassment','spam','other']
    detail: str | None = Field(default=None,max_length=1000)

class DecisionIn(Strict):
    action: Literal['publish','reject','merge','verify_designated','set_status','hide_place','restore_place','correct_place','hide_review','restore_review','resolve','approve_deletion','merge_place','hide_confirmation']
    reason: str = Field(min_length=5,max_length=1000)
    expected_version: int | None = None
    advisory_status: Status | None = None
    canonical_place_id: str | None = None
    evidence_type: Literal['signage','venue_confirmation','official_listing'] | None = None
    public_source: str | None = Field(default=None,max_length=240)
    evidence: str | None = Field(default=None,max_length=1000)
    reviewed_at: datetime | None = None
    name: str | None = Field(default=None,min_length=2,max_length=120)
    kind: Kind | None = None
    inside_venue: bool | None = None
    location: Point | None = None
    access_point: Point | None = None
    access_notes: str | None = Field(default=None,max_length=500)

class Verification(Strict):
    reviewed_at: datetime
    public_source: str

class Rating(Strict):
    average: float | None
    count: int

class Place(Strict):
    id: str
    name: str
    kind: Kind
    advisory_status: Status
    location: Point
    access_point: Point | None
    address_label: str | None
    access_notes: str | None
    inside_venue: bool | None
    verification: Verification | None
    last_confirmed_at: datetime | None
    rating: Rating
    updated_at: datetime
    version: int
    directions_allowed: bool
    freshness: Literal['fresh','stale']
    merged_into: str | None = None

class Page(Strict):
    items: list[dict]
    next_cursor: str | None

class Ack(Strict):
    id: str
    state: str

class Error(Strict):
    code: str
    message: str
    request_id: str
    field_errors: list[dict[str,str]] | None = None

class PublicReview(Strict):
    id: str
    stars: int
    body: str | None
    created_at: datetime
    updated_at: datetime

class ReviewPage(Strict):
    items: list[PublicReview]
    next_cursor: str | None

class PublicConfirmation(Strict):
    id: str
    observation: Literal['still_there','changed','gone']
    observed_at: datetime
    created_at: datetime

class ConfirmationPage(Strict):
    items: list[PublicConfirmation]
    next_cursor: str | None

class PlaceSummary(Strict):
    id: str
    name: str
    kind: Kind
    advisory_status: Status
    location: Point
    verification_reviewed_at: datetime | None
    last_confirmed_at: datetime | None
    freshness: Literal['fresh','stale']
    rating: Rating
    updated_at: datetime
    directions_allowed: bool

class PlacePage(Strict):
    items: list[PlaceSummary]
    next_cursor: str | None

class AddressSuggestion(Strict):
    label: str
    location: Point

class AddressSuggestions(Strict):
    items: list[AddressSuggestion]
    provider: Literal['geoapify'] | None = None

class Me(Strict):
    id: str
    email: str
    role: Literal['contributor','admin']
    adult_attested_at: datetime

class SubmissionStatus(Strict):
    id: str
    intent: Literal['create','correct']
    place_id: str | None
    name: str
    kind: Kind
    state: Literal['pending','published','rejected','merged']
    decision_reason: str | None
    created_at: datetime
    decided_at: datetime | None

class SubmissionList(Strict):
    items: list[SubmissionStatus]

class DecisionAck(Strict):
    id: str
    case_id: str
    state: Literal['resolved']
    target_type: str
    target_id: str
