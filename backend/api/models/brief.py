"""
Pydantic models — Brief (Layer 8: Proactive Delivery)
"""

from datetime import datetime

from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    document_id: str
    document_type: str
    title: str
    authority_level: int = Field(..., ge=1, le=5)
    relevant_excerpt: str
    vault_url: str | None = None
    is_quarantine: bool = False


class Brief(BaseModel):
    brief_id: str
    trigger_event_id: str
    trigger_event_type: str = Field(
        ...,
        description="work_order, ptw, shift_handover, alarm, recurring_failure"
    )
    asset_id: str | None = None
    work_order_id: str | None = None
    ptw_id: str | None = None
    recipient_user_id: str
    priority: str = Field(..., description="critical, high, normal, low")

    # Brief content — designed for 30s read (field) or 2min (PTW) or 5min (shift handover)
    headline: str = Field(..., description="Key finding — first two lines")
    body: str = Field(..., description="Supporting detail")
    action_items: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    quarantine_flags: list[str] = Field(default_factory=list, description="Unverified items referenced")

    # Evidence
    sources: list[SourceCitation] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)

    # Delivery state
    delivered_at: datetime | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    requires_countersignature: bool = False  # PTW briefs require shift lead sign-off
    countersigned_by: str | None = None
    countersigned_at: datetime | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)


class BriefFeedback(BaseModel):
    rating: str = Field(..., description="accurate, missing_context, incorrect")
    notes: str | None = None
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
