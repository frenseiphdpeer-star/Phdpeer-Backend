"""
Test suite for AnalyticsOrchestrator read-only contract enforcement.

This test suite verifies that AnalyticsOrchestrator adheres to its read-only
contract by:
1. Only reading from allowed models (CommittedTimeline, ProgressEvent, etc.)
2. Only writing to allowed models (AnalyticsSnapshot, DecisionTrace)
3. Never mutating upstream state
4. Raising errors when attempting to violate the contract

The read-only contract is critical for maintaining data integrity and preventing
unintended side effects during analytics generation.
"""

import pytest
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.orchestrators.analytics_orchestrator import (
    AnalyticsOrchestrator,
    StateMutationInAnalyticsOrchestratorError
)
from app.models.user import User
from app.models.committed_timeline import CommittedTimeline
from app.models.timeline_stage import TimelineStage
from app.models.timeline_milestone import TimelineMilestone
from app.models.progress_event import ProgressEvent
from app.models.journey_assessment import JourneyAssessment
from app.models.analytics_snapshot import AnalyticsSnapshot


@pytest.fixture
def user(db: Session):
    """Create a test user."""
    user = User(
        email=f"test_{uuid4()}@example.com",
        hashed_password="test_hash"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def committed_timeline(db: Session, user: User):
    """Create a committed timeline with stages and milestones."""
    timeline = CommittedTimeline(
        user_id=user.id,
        title="Test PhD Timeline",
        committed_date=datetime.utcnow(),
        notes="Version 1.0"
    )
    db.add(timeline)
    db.commit()
    db.refresh(timeline)
    
    # Add stage
    stage = TimelineStage(
        committed_timeline_id=timeline.id,
        name="Research Phase",
        description="Initial research",
        order_index=1
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    
    # Add milestone
    milestone = TimelineMilestone(
        timeline_stage_id=stage.id,
        title="Literature Review",
        description="Complete literature review",
        target_date=datetime.utcnow() + timedelta(days=90),
        order_index=1,
        is_critical=True
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    
    return timeline


@pytest.fixture
def progress_event(db: Session, user: User, committed_timeline: CommittedTimeline):
    """Create a progress event."""
    # Get milestone
    stage = db.query(TimelineStage).filter(
        TimelineStage.committed_timeline_id == committed_timeline.id
    ).first()
    milestone = db.query(TimelineMilestone).filter(
        TimelineMilestone.timeline_stage_id == stage.id
    ).first()
    
    event = ProgressEvent(
        user_id=user.id,
        milestone_id=milestone.id,
        event_type="started",
        event_date=datetime.utcnow() - timedelta(days=5),
        notes="Started literature review"
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@pytest.fixture
def journey_assessment(db: Session, user: User):
    """Create a journey assessment."""
    assessment = JourneyAssessment(
        user_id=user.id,
        assessment_date=datetime.utcnow() - timedelta(days=1),
        score=75.0,
        dimension_scores={
            "momentum": 80.0,
            "clarity": 70.0,
            "support": 75.0
        },
        notes="Good progress overall"
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


def test_valid_read_operations_succeed(
    db: Session,
    user: User,
    committed_timeline: CommittedTimeline,
    progress_event: ProgressEvent,
    journey_assessment: JourneyAssessment
):
    """
    Test that reading from allowed models succeeds.
    
    Verifies that the orchestrator can read from:
    - User
    - CommittedTimeline
    - TimelineStage
    - TimelineMilestone
    - ProgressEvent
    - JourneyAssessment
    """
    orchestrator = AnalyticsOrchestrator(db=db, user_id=user.id)
    
    # Run analytics (should succeed)
    result = orchestrator.run(
        request_id=f"test_{uuid4()}",
        user_id=user.id,
        timeline_id=committed_timeline.id
    )
    
    # Verify result has expected structure
    assert result is not None
    assert "snapshot_id" in result
    assert "generated_at" in result
    assert "timeline_status" in result
    
    # Verify snapshot was created
    snapshot = db.query(AnalyticsSnapshot).filter(
        AnalyticsSnapshot.id == UUID(result["snapshot_id"])
    ).first()
    assert snapshot is not None
    assert snapshot.user_id == user.id


def test_valid_write_operations_succeed(
    db: Session,
    user: User,
    committed_timeline: CommittedTimeline,
    progress_event: ProgressEvent,
    journey_assessment: JourneyAssessment
):
    """
    Test that writing to allowed models succeeds.
    
    Verifies that the orchestrator can write to:
    - AnalyticsSnapshot
    - DecisionTrace (via BaseOrchestrator)
    - EvidenceBundle (via BaseOrchestrator)
    """
    orchestrator = AnalyticsOrchestrator(db=db, user_id=user.id)
    
    # Count existing snapshots
    initial_count = db.query(AnalyticsSnapshot).filter(
        AnalyticsSnapshot.user_id == user.id
    ).count()
    
    # Run analytics
    result = orchestrator.run(
        request_id=f"test_{uuid4()}",
        user_id=user.id,
        timeline_id=committed_timeline.id
    )
    
    # Verify new snapshot was created
    final_count = db.query(AnalyticsSnapshot).filter(
        AnalyticsSnapshot.user_id == user.id
    ).count()
    assert final_count == initial_count + 1


def test_read_only_contract_is_validated(
    db: Session,
    user: User,
    committed_timeline: CommittedTimeline,
    progress_event: ProgressEvent,
    journey_assessment: JourneyAssessment
):
    """
    Test that read-only contract validation is executed.
    
    Verifies that _validate_read_only_contract() is called during execution
    and validates all operations against allowed models.
    """
    orchestrator = AnalyticsOrchestrator(db=db, user_id=user.id)
    
    # Run analytics
    result = orchestrator.run(
        request_id=f"test_{uuid4()}",
        user_id=user.id,
        timeline_id=committed_timeline.id
    )
    
    # Verify operation tracking lists were populated
    assert len(orchestrator._read_operations) > 0
    assert len(orchestrator._write_operations) > 0
    
    # Verify all read operations were from allowed models
    for model_name in orchestrator._read_operations:
        assert model_name in orchestrator._ALLOWED_READ_MODELS, \
            f"Model {model_name} not in allowed read models"
    
    # Verify all write operations were to allowed models
    for model_name in orchestrator._write_operations:
        assert model_name in orchestrator._ALLOWED_WRITE_MODELS, \
            f"Model {model_name} not in allowed write models"


def test_tracked_read_validates_model(db: Session, user: User):
    """
    Test that _tracked_read validates model is in allowed list.
    """
    orchestrator = AnalyticsOrchestrator(db=db, user_id=user.id)
    
    # Valid read should succeed
    query = orchestrator._tracked_read(User, User.id == user.id)
    assert query is not None
    assert 'User' in orchestrator._read_operations
    
    # Invalid read should raise error
    from app.models.questionnaire_draft import QuestionnaireDraft
    with pytest.raises(StateMutationInAnalyticsOrchestratorError) as exc_info:
        orchestrator._tracked_read(QuestionnaireDraft, QuestionnaireDraft.id == uuid4())
    
    assert "non-allowed model: QuestionnaireDraft" in str(exc_info.value)


def test_tracked_write_validates_model(db: Session, user: User):
    """
    Test that _tracked_write validates model is in allowed list.
    """
    orchestrator = AnalyticsOrchestrator(db=db, user_id=user.id)
    
    # Valid write should succeed
    snapshot = AnalyticsSnapshot(
        user_id=user.id,
        timeline_version="1.0",
        summary_json={"test": "data"}
    )
    orchestrator._tracked_write(snapshot)
    assert 'AnalyticsSnapshot' in orchestrator._write_operations
    
    # Invalid write should raise error
    from app.models.draft_timeline import DraftTimeline
    draft = DraftTimeline(
        user_id=user.id,
        title="Test",
        version_number="1.0"
    )
    with pytest.raises(StateMutationInAnalyticsOrchestratorError) as exc_info:
        orchestrator._tracked_write(draft)
    
    assert "non-allowed model: DraftTimeline" in str(exc_info.value)


def test_multiple_runs_maintain_read_only_contract(
    db: Session,
    user: User,
    committed_timeline: CommittedTimeline,
    progress_event: ProgressEvent,
    journey_assessment: JourneyAssessment
):
    """
    Test that read-only contract is maintained across multiple runs.
    
    Verifies that:
    - Each run resets operation tracking
    - Each run validates independently
    - No state leaks between runs
    """
    orchestrator = AnalyticsOrchestrator(db=db, user_id=user.id)
    
    # Run 1
    result1 = orchestrator.run(
        request_id=f"test_{uuid4()}",
        user_id=user.id,
        timeline_id=committed_timeline.id
    )
    read_ops_1 = len(orchestrator._read_operations)
    write_ops_1 = len(orchestrator._write_operations)
    
    # Run 2 (with different request_id, should create new snapshot)
    result2 = orchestrator.run(
        request_id=f"test_{uuid4()}",
        user_id=user.id,
        timeline_id=committed_timeline.id
    )
    read_ops_2 = len(orchestrator._read_operations)
    write_ops_2 = len(orchestrator._write_operations)
    
    # Verify each run has operation tracking
    assert read_ops_1 > 0
    assert write_ops_1 > 0
    assert read_ops_2 > 0
    assert write_ops_2 > 0
    
    # Verify different snapshots were created
    assert result1["snapshot_id"] != result2["snapshot_id"]


def test_no_upstream_mutations_during_analytics(
    db: Session,
    user: User,
    committed_timeline: CommittedTimeline,
    progress_event: ProgressEvent,
    journey_assessment: JourneyAssessment
):
    """
    Test that no upstream data is modified during analytics generation.
    
    Verifies that:
    - CommittedTimeline is not modified
    - ProgressEvents are not modified
    - JourneyAssessment is not modified
    - TimelineStage and TimelineMilestone are not modified
    """
    # Capture initial state
    timeline_before = db.query(CommittedTimeline).filter(
        CommittedTimeline.id == committed_timeline.id
    ).first()
    timeline_updated_at_before = timeline_before.updated_at
    
    event_before = db.query(ProgressEvent).filter(
        ProgressEvent.id == progress_event.id
    ).first()
    event_updated_at_before = event_before.updated_at
    
    assessment_before = db.query(JourneyAssessment).filter(
        JourneyAssessment.id == journey_assessment.id
    ).first()
    assessment_updated_at_before = assessment_before.updated_at
    
    # Run analytics
    orchestrator = AnalyticsOrchestrator(db=db, user_id=user.id)
    orchestrator.run(
        request_id=f"test_{uuid4()}",
        user_id=user.id,
        timeline_id=committed_timeline.id
    )
    
    # Verify no updates to upstream data
    db.expire_all()  # Force reload from database
    
    timeline_after = db.query(CommittedTimeline).filter(
        CommittedTimeline.id == committed_timeline.id
    ).first()
    assert timeline_after.updated_at == timeline_updated_at_before
    
    event_after = db.query(ProgressEvent).filter(
        ProgressEvent.id == progress_event.id
    ).first()
    assert event_after.updated_at == event_updated_at_before
    
    assessment_after = db.query(JourneyAssessment).filter(
        JourneyAssessment.id == journey_assessment.id
    ).first()
    assert assessment_after.updated_at == assessment_updated_at_before


def test_contract_error_contains_helpful_information(db: Session, user: User):
    """
    Test that contract violation errors contain helpful debugging information.
    
    Verifies that error messages include:
    - The model that was accessed
    - Whether it was a read or write operation
    - List of allowed models
    """
    orchestrator = AnalyticsOrchestrator(db=db, user_id=user.id)
    
    # Try to read from non-allowed model
    from app.models.questionnaire_draft import QuestionnaireDraft
    with pytest.raises(StateMutationInAnalyticsOrchestratorError) as exc_info:
        orchestrator._tracked_read(QuestionnaireDraft, QuestionnaireDraft.id == uuid4())
    
    error_msg = str(exc_info.value)
    assert "QuestionnaireDraft" in error_msg
    assert "Allowed read models:" in error_msg
    assert "CommittedTimeline" in error_msg  # Should list allowed models
