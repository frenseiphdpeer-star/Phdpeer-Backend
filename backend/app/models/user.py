"""User model."""
from sqlalchemy import Column, String, Boolean
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import BaseModel


class User(Base, BaseModel):
    """
    User model representing platform users (PhD students, advisors, etc.).
    
    Attributes:
        email: Unique email address
        hashed_password: Hashed password for authentication
        full_name: User's full name
        is_active: Whether the user account is active
        is_superuser: Whether the user has admin privileges
        institution: Academic institution
        field_of_study: Research field/discipline
    """
    
    __tablename__ = "users"
    
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    institution = Column(String, nullable=True)
    field_of_study = Column(String, nullable=True)
    
    # Relationships
    document_artifacts = relationship(
        "DocumentArtifact",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    baselines = relationship(
        "Baseline",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    draft_timelines = relationship(
        "DraftTimeline",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    committed_timelines = relationship(
        "CommittedTimeline",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    progress_events = relationship(
        "ProgressEvent",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    journey_assessments = relationship(
        "JourneyAssessment",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    questionnaire_drafts = relationship(
        "QuestionnaireDraft",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    opportunity_feeds = relationship(
        "OpportunityFeedSnapshot",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    analytics_snapshots = relationship(
        "AnalyticsSnapshot",
        back_populates="user",
        cascade="all, delete-orphan"
    )