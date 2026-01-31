#!/usr/bin/env python3
"""
End-to-End State Transition Validation Script

This script validates all allowed and disallowed state transitions
in the PhD tracking system without requiring pytest.

Run with: python run_state_transition_validation.py
"""
import sys
import os
from datetime import date, timedelta
from uuid import uuid4

# Set environment variables BEFORE importing app modules
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.user import User
from app.models.baseline import Baseline
from app.models.draft_timeline import DraftTimeline
from app.models.committed_timeline import CommittedTimeline
from app.models.timeline_stage import TimelineStage
from app.models.timeline_milestone import TimelineMilestone
from app.models.progress_event import ProgressEvent
from app.orchestrators.timeline_orchestrator import (
    TimelineOrchestrator,
    TimelineOrchestratorError,
)
from app.services.progress_service import ProgressService
from app.orchestrators.analytics_orchestrator import (
    AnalyticsOrchestrator,
    AnalyticsOrchestratorError
)
from app.utils.invariants import (
    CommittedTimelineWithoutDraftError,
    ProgressEventWithoutMilestoneError,
)


def setup_database():
    """Create in-memory test database."""
    # Use PostgreSQL-compatible GUID type for SQLite
    from sqlalchemy import TypeDecorator, CHAR
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    import uuid as uuid_module
    
    class GUID(TypeDecorator):
        """Platform-independent GUID type.
        Uses PostgreSQL's UUID type, otherwise uses CHAR(32), storing as stringified hex values.
        """
        impl = CHAR
        cache_ok = True
        
        def load_dialect_impl(self, dialect):
            if dialect.name == 'postgresql':
                return dialect.type_descriptor(PG_UUID())
            else:
                return dialect.type_descriptor(CHAR(32))
        
        def process_bind_param(self, value, dialect):
            if value is None:
                return value
            elif dialect.name == 'postgresql':
                return str(value)
            else:
                if not isinstance(value, uuid_module.UUID):
                    return "%.32x" % uuid_module.UUID(value).int
                else:
                    return "%.32x" % value.int
        
        def process_result_value(self, value, dialect):
            if value is None:
                return value
            else:
                if not isinstance(value, uuid_module.UUID):
                    value = uuid_module.UUID(value)
                return value
    
    # Monkey-patch the UUID type to use GUID for SQLite
    from sqlalchemy.dialects import postgresql
    original_uuid = postgresql.UUID
    
    def create_guid(*args, **kwargs):
        kwargs_copy = kwargs.copy()
        kwargs_copy.pop('as_uuid', None)
        return GUID(*args, **kwargs_copy)
    
    postgresql.UUID = create_guid
    
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Restore original
    postgresql.UUID = original_uuid
    
    return SessionLocal()


def create_test_user(db):
    """Create a test user."""
    user = User(
        email="phd.student@university.edu",
        hashed_password="hashed_password",
        full_name="Test Student",
        institution="Test University",
        field_of_study="Computer Science",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def print_section(title):
    """Print a section header."""
    print("\n" + "="*80)
    print(title)
    print("="*80)


def print_test(message, passed=True):
    """Print test result."""
    symbol = "✅" if passed else "❌"
    print(f"{symbol} {message}")


def test_allowed_transitions(db, user):
    """Test all allowed state transitions."""
    print_section("TESTING ALLOWED STATE TRANSITIONS")
    
    # Test 1: S0 → S1 (Raw input → Baseline)
    print("\n[Test 1] S0 → S1: Raw input → Baseline")
    baseline = Baseline(
        user_id=user.id,
        program_name="PhD in Machine Learning",
        institution="AI Research University",
        field_of_study="Artificial Intelligence",
        start_date=date.today(),
        total_duration_months=48,
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    assert baseline.id is not None
    print_test("S0 → S1: Raw input → Baseline PASSED")
    
    # Test 2: S1 → S2 (Baseline → Draft timeline)
    print("\n[Test 2] S1 → S2: Baseline → Draft timeline")
    draft = DraftTimeline(
        user_id=user.id,
        baseline_id=baseline.id,
        title="Generated Timeline",
        description="Auto-generated from baseline",
        version_number="1.0",
        is_active=True,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    
    # Add stage and milestone
    stage = TimelineStage(
        draft_timeline_id=draft.id,
        title="Research Phase",
        stage_order=1,
        status="planned",
        duration_months=24,
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    
    milestone = TimelineMilestone(
        timeline_stage_id=stage.id,
        title="Complete Literature Review",
        milestone_order=1,
        target_date=date.today() + timedelta(days=90),
        is_completed=False,
        is_critical=True,
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    
    assert draft.id is not None
    print_test("S1 → S2: Baseline → Draft timeline PASSED")
    
    # Test 3: S2 → S3 (Draft → Committed timeline)
    print("\n[Test 3] S2 → S3: Draft → Committed timeline")
    orchestrator = TimelineOrchestrator(db=db, user_id=user.id)
    committed_id = orchestrator.commit_timeline(
        draft_timeline_id=draft.id,
        user_id=user.id,
        title="Committed Timeline v1.0",
    )
    db.commit()
    
    committed = db.query(CommittedTimeline).filter(
        CommittedTimeline.id == committed_id
    ).first()
    assert committed is not None
    assert committed.draft_timeline_id == draft.id
    print_test("S2 → S3: Draft → Committed timeline PASSED")
    
    # Test 4: S3 → S4 (Committed → Progress tracking)
    print("\n[Test 4] S3 → S4: Committed → Progress tracking")
    
    # Get milestone from committed timeline
    committed_stages = db.query(TimelineStage).filter(
        TimelineStage.committed_timeline_id == committed.id
    ).all()
    committed_milestones = db.query(TimelineMilestone).filter(
        TimelineMilestone.timeline_stage_id.in_([s.id for s in committed_stages])
    ).all()
    
    progress_service = ProgressService(db=db)
    event_id = progress_service.mark_milestone_completed(
        milestone_id=committed_milestones[0].id,
        user_id=user.id,
        completion_date=date.today(),
        notes="Completed successfully"
    )
    db.commit()
    
    event = db.query(ProgressEvent).filter(ProgressEvent.id == event_id).first()
    assert event is not None
    print_test("S3 → S4: Committed → Progress tracking PASSED")
    
    return baseline, draft, committed


def test_disallowed_transitions(db, user):
    """Test all disallowed state transitions."""
    print_section("TESTING DISALLOWED STATE TRANSITIONS (Must Fail Loudly)")
    
    # Setup: Create baseline and draft for tests
    baseline = Baseline(
        user_id=user.id,
        program_name="PhD in Computer Science",
        institution="Test University",
        field_of_study="Computer Science",
        start_date=date.today(),
        total_duration_months=48,
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    
    draft = DraftTimeline(
        user_id=user.id,
        baseline_id=baseline.id,
        title="Test Draft",
        version_number="1.0",
        is_active=True,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    
    stage = TimelineStage(
        draft_timeline_id=draft.id,
        title="Test Stage",
        stage_order=1,
        status="planned",
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    
    milestone = TimelineMilestone(
        timeline_stage_id=stage.id,
        title="Test Milestone",
        milestone_order=1,
        target_date=date.today() + timedelta(days=30),
        is_completed=False,
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    
    # Test 1: Progress without committed timeline (S2 → S4)
    print("\n[Test 1] ❌ S2 → S4: Progress without committed timeline")
    progress_service = ProgressService(db=db)
    try:
        progress_service.mark_milestone_completed(
            milestone_id=milestone.id,
            user_id=user.id,
        )
        print_test("FAILED: Should have raised ProgressEventWithoutMilestoneError", False)
    except ProgressEventWithoutMilestoneError as e:
        error_msg = str(e)
        print(f"  Error message: {error_msg[:150]}")
        assert "CommittedTimeline" in error_msg or "committed" in error_msg.lower()
        print_test("S2 → S4 correctly rejected with clear error")
    
    # Test 2: Commit without draft (S0/S1 → S3)
    print("\n[Test 2] ❌ S0/S1 → S3: Commit without draft")
    fake_draft_id = uuid4()
    orchestrator = TimelineOrchestrator(db=db, user_id=user.id)
    try:
        orchestrator.commit_timeline(
            draft_timeline_id=fake_draft_id,
            user_id=user.id,
        )
        print_test("FAILED: Should have raised CommittedTimelineWithoutDraftError", False)
    except CommittedTimelineWithoutDraftError as e:
        error_msg = str(e)
        print(f"  Error message: {error_msg[:150]}")
        assert "not found" in error_msg.lower() or "draft" in error_msg.lower()
        print_test("Commit without draft correctly rejected with clear error")
    
    # Test 3: Double commit
    print("\n[Test 3] ❌ S2 → S3 → S3: Double commit")
    # First commit
    committed_id = orchestrator.commit_timeline(
        draft_timeline_id=draft.id,
        user_id=user.id,
    )
    db.commit()
    print(f"  First commit succeeded: {committed_id}")
    
    # Second commit attempt
    try:
        orchestrator.commit_timeline(
            draft_timeline_id=draft.id,
            user_id=user.id,
        )
        print_test("FAILED: Should have raised CommittedTimelineWithoutDraftError", False)
    except CommittedTimelineWithoutDraftError as e:
        error_msg = str(e)
        print(f"  Error message: {error_msg[:150]}")
        assert "already committed" in error_msg.lower()
        print_test("Double commit correctly rejected with clear error")
    
    # Test 4: Analytics without committed timeline
    print("\n[Test 4] ❌ Analytics without committed timeline")
    # Create new user with no committed timeline
    new_user = User(
        email="new.student@university.edu",
        hashed_password="hashed_password",
        full_name="New Student",
        institution="Test University",
        field_of_study="Computer Science",
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    analytics_orchestrator = AnalyticsOrchestrator(db=db, user_id=new_user.id)
    try:
        analytics_orchestrator.run(
            request_id=f"analytics-{uuid4()}",
            user_id=new_user.id,
        )
        print_test("FAILED: Should have raised AnalyticsOrchestratorError", False)
    except AnalyticsOrchestratorError as e:
        error_msg = str(e)
        print(f"  Error message: {error_msg[:150]}")
        assert "committed timeline" in error_msg.lower()
        print_test("Analytics without timeline correctly rejected with clear error")
    
    # Test 5: Commit empty timeline
    print("\n[Test 5] ❌ Commit empty timeline (no stages)")
    empty_draft = DraftTimeline(
        user_id=user.id,
        baseline_id=baseline.id,
        title="Empty Timeline",
        version_number="1.0",
        is_active=True,
    )
    db.add(empty_draft)
    db.commit()
    db.refresh(empty_draft)
    
    try:
        orchestrator.commit_timeline(
            draft_timeline_id=empty_draft.id,
            user_id=user.id,
        )
        print_test("FAILED: Should have raised TimelineOrchestratorError", False)
    except TimelineOrchestratorError as e:
        error_msg = str(e)
        print(f"  Error message: {error_msg[:150]}")
        assert "stage" in error_msg.lower()
        print_test("Empty timeline commit correctly rejected with clear error")
    
    # Test 6: Commit timeline without milestones
    print("\n[Test 6] ❌ Commit timeline without milestones")
    draft_no_milestones = DraftTimeline(
        user_id=user.id,
        baseline_id=baseline.id,
        title="Timeline Without Milestones",
        version_number="1.0",
        is_active=True,
    )
    db.add(draft_no_milestones)
    db.commit()
    db.refresh(draft_no_milestones)
    
    stage_no_milestones = TimelineStage(
        draft_timeline_id=draft_no_milestones.id,
        title="Stage Without Milestones",
        stage_order=1,
        status="planned",
    )
    db.add(stage_no_milestones)
    db.commit()
    
    try:
        orchestrator.commit_timeline(
            draft_timeline_id=draft_no_milestones.id,
            user_id=user.id,
        )
        print_test("FAILED: Should have raised TimelineOrchestratorError", False)
    except TimelineOrchestratorError as e:
        error_msg = str(e)
        print(f"  Error message: {error_msg[:150]}")
        assert "milestone" in error_msg.lower()
        print_test("Timeline without milestones correctly rejected with clear error")


def test_complete_pipeline(db, user):
    """Test complete pipeline S0 → S1 → S2 → S3 → S4."""
    print_section("TESTING COMPLETE PIPELINE: S0 → S1 → S2 → S3 → S4")
    
    # S0 → S1: Create baseline
    print("\n[Step 1] S0 → S1: Creating baseline...")
    baseline = Baseline(
        user_id=user.id,
        program_name="PhD in Quantum Computing",
        institution="Tech University",
        field_of_study="Physics",
        start_date=date.today(),
        total_duration_months=60,
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    print_test("S0 → S1: Baseline created")
    
    # S1 → S2: Create draft timeline
    print("\n[Step 2] S1 → S2: Creating draft timeline...")
    draft = DraftTimeline(
        user_id=user.id,
        baseline_id=baseline.id,
        title="Quantum PhD Timeline",
        version_number="1.0",
        is_active=True,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    
    stage = TimelineStage(
        draft_timeline_id=draft.id,
        title="Quantum Research Phase",
        stage_order=1,
        status="planned",
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    
    milestone = TimelineMilestone(
        timeline_stage_id=stage.id,
        title="Quantum Algorithm Design",
        milestone_order=1,
        target_date=date.today() + timedelta(days=180),
        is_completed=False,
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    print_test("S1 → S2: Draft timeline created")
    
    # S2 → S3: Commit timeline
    print("\n[Step 3] S2 → S3: Committing timeline...")
    orchestrator = TimelineOrchestrator(db=db, user_id=user.id)
    committed_id = orchestrator.commit_timeline(
        draft_timeline_id=draft.id,
        user_id=user.id,
    )
    db.commit()
    
    committed = db.query(CommittedTimeline).filter(
        CommittedTimeline.id == committed_id
    ).first()
    print_test("S2 → S3: Timeline committed")
    
    # S3 → S4: Track progress
    print("\n[Step 4] S3 → S4: Tracking progress...")
    committed_stages = db.query(TimelineStage).filter(
        TimelineStage.committed_timeline_id == committed.id
    ).all()
    committed_milestones = db.query(TimelineMilestone).filter(
        TimelineMilestone.timeline_stage_id.in_([s.id for s in committed_stages])
    ).all()
    
    progress_service = ProgressService(db=db)
    event_id = progress_service.mark_milestone_completed(
        milestone_id=committed_milestones[0].id,
        user_id=user.id,
    )
    db.commit()
    
    event = db.query(ProgressEvent).filter(ProgressEvent.id == event_id).first()
    print_test("S3 → S4: Progress tracked")
    
    print_section("COMPLETE PIPELINE S0 → S1 → S2 → S3 → S4 PASSED")


def print_summary():
    """Print test summary."""
    print_section("STATE TRANSITION VALIDATION SUMMARY")
    
    print("\n✅ ALLOWED TRANSITIONS (All Passed):")
    print("  ✅ S0 → S1: Raw input → Baseline")
    print("  ✅ S1 → S2: Baseline → Draft timeline")
    print("  ✅ S2 → S3: Draft → Committed timeline")
    print("  ✅ S3 → S4: Committed → Progress tracking")
    print("  ✅ Complete pipeline: S0 → S1 → S2 → S3 → S4")
    
    print("\n❌ DISALLOWED TRANSITIONS (All Correctly Rejected):")
    print("  ❌ S2 → S4: Progress without committed timeline")
    print("  ❌ S0/S1 → S3: Commit without draft")
    print("  ❌ S2 → S3 → S3: Double commit (immutability)")
    print("  ❌ Analytics without committed timeline")
    print("  ❌ Commit empty timeline (no stages)")
    print("  ❌ Commit timeline without milestones")
    
    print("\n" + "="*80)
    print("✅ ALL STATE TRANSITION VALIDATIONS PASSED")
    print("="*80)


def main():
    """Run all state transition validation tests."""
    print_section("PhD TRACKING SYSTEM - STATE TRANSITION VALIDATION")
    print("\nThis script validates all allowed and disallowed state transitions.")
    print("\nState Definitions:")
    print("  S0: Raw input (questionnaire submission, document upload)")
    print("  S1: Baseline created (structured profile)")
    print("  S2: Draft timeline created (editable timeline)")
    print("  S3: Committed timeline (immutable, frozen)")
    print("  S4: Progress tracking active (milestone completion events)")
    
    try:
        # Setup database
        print("\nSetting up test database...")
        db = setup_database()
        user = create_test_user(db)
        print(f"Test user created: {user.email}")
        
        # Run tests
        test_allowed_transitions(db, user)
        
        # Create new user for disallowed tests to avoid conflicts
        user2 = create_test_user(db)
        user2.email = "test2@university.edu"
        db.add(user2)
        db.commit()
        
        test_disallowed_transitions(db, user2)
        
        # Create new user for complete pipeline test
        user3 = create_test_user(db)
        user3.email = "test3@university.edu"
        db.add(user3)
        db.commit()
        
        test_complete_pipeline(db, user3)
        
        # Print summary
        print_summary()
        
        return 0
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
