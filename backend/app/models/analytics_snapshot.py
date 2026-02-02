"""AnalyticsSnapshot model."""
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import BaseModel


class AnalyticsSnapshot(Base, BaseModel):
    """
    AnalyticsSnapshot model for storing immutable analytics snapshots.
    
    **IMMUTABILITY RULES:**
    - Snapshots are IMMUTABLE once created
    - NEVER update fields after creation
    - NEVER delete snapshots (they are historical records)
    - To "update" analytics, create a NEW snapshot
    
    **VERSIONING:**
    - Snapshots are versioned by timeline_version
    - Multiple snapshots can exist for the same timeline_version
    - Each snapshot has unique ID and created_at timestamp
    - Snapshots form a historical audit trail
    
    Snapshots persist the output of AnalyticsEngine.aggregate() as
    an immutable record for historical tracking and analysis.
    
    Attributes:
        user_id: Reference to the user
        timeline_version: Version string of the timeline (e.g., "1.0", "2.0")
        summary_json: Complete AnalyticsSummary output as JSON
        created_at: Timestamp when snapshot was created (from BaseModel)
        
    Guards:
        - check_analytics_snapshot_not_modified() - prevents updates
        - check_analytics_snapshot_not_deleted() - prevents deletions
    """
    
    __tablename__ = "analytics_snapshots"
    
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    timeline_version = Column(
        String(50),
        nullable=False,
        index=True
    )
    summary_json = Column(
        JSONB,
        nullable=False
    )
    
    # Relationships
    user = relationship("User", back_populates="analytics_snapshots")
