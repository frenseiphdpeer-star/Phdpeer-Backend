"""AnalyticsSnapshot model."""
from sqlalchemy import Column, String, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import BaseModel


class AnalyticsSnapshot(Base, BaseModel):
    """
    AnalyticsSnapshot model for storing analytics reports.
    
    Snapshots capture aggregated analytics data at a point in time,
    including time-series summaries and status indicators.
    
    Attributes:
        user_id: Reference to the user
        timeline_id: Optional reference to committed timeline
        snapshot_date: Date when snapshot was generated
        analytics_data: Complete analytics report as JSON
        snapshot_type: Type of snapshot (daily, weekly, on_demand)
    """
    
    __tablename__ = "analytics_snapshots"
    
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    timeline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("committed_timelines.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    snapshot_date = Column(Date, nullable=False, index=True)
    analytics_data = Column(JSONB, nullable=False)
    snapshot_type = Column(String(50), nullable=False, default="on_demand")  # "daily", "weekly", "on_demand"
    
    # Relationships
    user = relationship("User", back_populates="analytics_snapshots")
    timeline = relationship("CommittedTimeline")
