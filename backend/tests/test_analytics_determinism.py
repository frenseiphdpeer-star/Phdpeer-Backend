"""
Test for deterministic behavior of AnalyticsEngine.aggregate().

Verifies:
- Output JSON is identical across multiple runs
- No timestamps or random ordering leaks into the output
"""
import sys
import os

# Set environment variables FIRST
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")

# Monkey-patch UUID type BEFORE any SQLAlchemy model imports
import uuid as uuid_module
from sqlalchemy import TypeDecorator, CHAR, create_engine
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects import postgresql


class GUID(TypeDecorator):
    """Platform-independent GUID type."""
    impl = CHAR
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_UUID())
        return dialect.type_descriptor(CHAR(32))
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        if not isinstance(value, uuid_module.UUID):
            return "%.32x" % uuid_module.UUID(value).int
        return "%.32x" % value.int
    
    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid_module.UUID):
            value = uuid_module.UUID(value)
        return value


# Store original UUID class
_original_uuid = postgresql.UUID

# Replace with GUID
def _create_guid(*args, **kwargs):
    kwargs = {k: v for k, v in kwargs.items() if k != 'as_uuid'}
    return GUID(*args, **kwargs)

postgresql.UUID = _create_guid

# NOW import models
import pytest
import json
from datetime import date, timedelta
from uuid import uuid4
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.user import User
from app.models.baseline import Baseline
from app.models.committed_timeline import CommittedTimeline
from app.models.timeline_stage import TimelineStage
from app.models.timeline_milestone import TimelineMilestone
from app.models.progress_event import ProgressEvent
from app.models.journey_assessment import JourneyAssessment
from app.services.analytics_engine import AnalyticsEngine

# Setup test database
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    """Create test database session."""
    Base.metadata.create_all(bind=engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(db):
    """Create a test user."""
    user = User(
        email="test@example.com",
        hashed_password="hashed_password",
        full_name="Test User",
        institution="Test University",
        field_of_study="Computer Science",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_analytics_engine_aggregate_is_deterministic(db, test_user):
    """
    Test: AnalyticsEngine.aggregate() produces identical output for identical inputs.
    
    Verifies:
    - Output JSON is identical across multiple runs with same inputs
    - No timestamps leak into the output (except generated_at date)
    - No random ordering in lists or dictionaries
    """
    # Create baseline
    baseline = Baseline(
        user_id=test_user.id,
        program_name="PhD in Computer Science",
        institution="Test University",
        field_of_study="Computer Science",
        start_date=date.today() - timedelta(days=90),
        total_duration_months=48,
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    
    # Create committed timeline
    timeline = CommittedTimeline(
        user_id=test_user.id,
        baseline_id=baseline.id,
        title="My PhD Timeline",
        committed_date=date.today() - timedelta(days=60),
        target_completion_date=date.today() + timedelta(days=300),
    )
    db.add(timeline)
    db.commit()
    db.refresh(timeline)
    
    # Create stages
    stage1 = TimelineStage(
        committed_timeline_id=timeline.id,
        title="Literature Review",
        stage_order=1,
        status="in_progress",
    )
    stage2 = TimelineStage(
        committed_timeline_id=timeline.id,
        title="Research Phase",
        stage_order=2,
        status="not_started",
    )
    db.add_all([stage1, stage2])
    db.commit()
    db.refresh(stage1)
    db.refresh(stage2)
    
    # Create milestones
    today = date.today()
    milestone1 = TimelineMilestone(
        timeline_stage_id=stage1.id,
        title="Complete literature review",
        milestone_order=1,
        target_date=today - timedelta(days=20),
        is_critical=True,
        is_completed=True,
        actual_completion_date=today - timedelta(days=10),
    )
    milestone2 = TimelineMilestone(
        timeline_stage_id=stage1.id,
        title="Identify research gaps",
        milestone_order=2,
        target_date=today - timedelta(days=10),
        is_critical=False,
        is_completed=False,
    )
    milestone3 = TimelineMilestone(
        timeline_stage_id=stage2.id,
        title="Design experiments",
        milestone_order=1,
        target_date=today + timedelta(days=30),
        is_critical=True,
        is_completed=False,
    )
    db.add_all([milestone1, milestone2, milestone3])
    db.commit()
    db.refresh(milestone1)
    db.refresh(milestone2)
    db.refresh(milestone3)
    
    # Create progress events
    event1 = ProgressEvent(
        user_id=test_user.id,
        milestone_id=milestone1.id,
        event_type="milestone_completed",
        title="Completed literature review",
        description="Finished literature review with delay",
        event_date=milestone1.actual_completion_date,
        impact_level="medium",
    )
    event2 = ProgressEvent(
        user_id=test_user.id,
        milestone_id=milestone2.id,
        event_type="milestone_delayed",
        title="Research gaps milestone delayed",
        description="Delayed due to additional sources",
        event_date=today - timedelta(days=5),
        impact_level="low",
    )
    db.add_all([event1, event2])
    db.commit()
    db.refresh(event1)
    db.refresh(event2)
    
    # Create journey assessment
    assessment = JourneyAssessment(
        user_id=test_user.id,
        submission_text="Making good progress",
        assessment_date=today - timedelta(days=7),
        assessment_type="self_reflection",
        overall_progress_rating=7,
        research_quality_rating=8,
        timeline_adherence_rating=6,
        challenges_identified="Time management",
        confidence_level="high",
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    
    # Load progress events
    progress_events = db.query(ProgressEvent).filter(
        ProgressEvent.user_id == test_user.id,
        ProgressEvent.milestone_id.in_([milestone1.id, milestone2.id, milestone3.id])
    ).all()
    
    # Initialize AnalyticsEngine
    engine = AnalyticsEngine(db)
    
    # Call aggregate() multiple times with identical inputs
    results = []
    for i in range(5):
        summary = engine.aggregate(
            committed_timeline=timeline,
            progress_events=progress_events,
            latest_assessment=assessment
        )
        
        # Convert to dict for comparison (excluding generated_at which uses date.today())
        result_dict = {
            "timeline_id": str(summary.timeline_id),
            "user_id": str(summary.user_id),
            "timeline_status": summary.timeline_status,
            "milestone_completion_percentage": summary.milestone_completion_percentage,
            "total_milestones": summary.total_milestones,
            "completed_milestones": summary.completed_milestones,
            "pending_milestones": summary.pending_milestones,
            "total_delays": summary.total_delays,
            "overdue_milestones": summary.overdue_milestones,
            "overdue_critical_milestones": summary.overdue_critical_milestones,
            "average_delay_days": summary.average_delay_days,
            "max_delay_days": summary.max_delay_days,
            "latest_health_score": summary.latest_health_score,
            "health_dimensions": summary.health_dimensions,
            "longitudinal_summary": summary.longitudinal_summary,
        }
        results.append(result_dict)
    
    # Verify all 5 results are identical
    first_result = results[0]
    for i, result in enumerate(results[1:], start=2):
        # Convert to JSON strings for deep comparison
        first_json = json.dumps(first_result, sort_keys=True, indent=2)
        result_json = json.dumps(result, sort_keys=True, indent=2)
        
        assert first_json == result_json, (
            f"Run {i} produced different output than run 1:\n"
            f"First result:\n{first_json}\n\n"
            f"Run {i} result:\n{result_json}"
        )
    
    # Verify expected values
    assert first_result["timeline_status"] in ["on_track", "delayed", "completed"]
    assert isinstance(first_result["milestone_completion_percentage"], (int, float))
    assert first_result["total_milestones"] == 3
    assert first_result["completed_milestones"] == 1
    assert first_result["pending_milestones"] == 2
    
    # Verify numeric values are consistent
    assert first_result["milestone_completion_percentage"] >= 0
    assert first_result["milestone_completion_percentage"] <= 100
    assert isinstance(first_result["total_delays"], int)
    assert isinstance(first_result["overdue_milestones"], int)
    assert isinstance(first_result["average_delay_days"], (int, float))
    assert isinstance(first_result["max_delay_days"], int)
    
    # Verify health dimensions
    assert first_result["latest_health_score"] is not None
    assert isinstance(first_result["health_dimensions"], dict)
    
    # Verify longitudinal summary structure
    longitudinal = first_result["longitudinal_summary"]
    assert isinstance(longitudinal, dict)
    
    # Check event counts are consistent across runs
    if "event_counts_by_type" in longitudinal:
        event_counts = longitudinal["event_counts_by_type"]
        assert isinstance(event_counts, dict)
        for result in results[1:]:
            assert result["longitudinal_summary"]["event_counts_by_type"] == event_counts
    
    print("✓ AnalyticsEngine.aggregate() is deterministic")
    print(f"✓ All {len(results)} runs produced identical output")
    print(f"✓ No timestamps or random ordering detected")
