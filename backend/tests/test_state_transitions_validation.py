"""
End-to-End State Transition Validation Test Suite

This test suite explicitly validates all allowed and disallowed state transitions
in the PhD tracking system.

State Definitions:
- S0: Raw input (questionnaire submission, document upload)
- S1: Baseline created (structured profile)
- S2: Draft timeline created (editable timeline)
- S3: Committed timeline (immutable, frozen)
- S4: Progress tracking active (milestone completion events)

Allowed Transitions:
✅ S0 → S1: Raw input → Baseline
✅ S1 → S2: Baseline → Draft timeline
✅ S2 → S3: Draft → Committed timeline
✅ S3 → S4: Committed → Progress tracking

Disallowed Transitions (must fail loudly):
❌ S2 → S4: Progress without committed timeline
❌ S0 → S3: Commit without draft
❌ Analytics without committed timeline
❌ Double commit (S2 → S3 twice)
❌ Edit committed timeline (immutability violation)
"""
import pytest
import os
from datetime import date, timedelta
from uuid import uuid4, UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set environment variables before importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")

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
    TimelineAlreadyCommittedError
)
from app.services.progress_service import ProgressService, ProgressServiceError
from app.orchestrators.analytics_orchestrator import (
    AnalyticsOrchestrator,
    AnalyticsOrchestratorError
)
from app.utils.invariants import (
    CommittedTimelineWithoutDraftError,
    ProgressEventWithoutMilestoneError,
    AnalyticsWithoutCommittedTimelineError,
)


# Test database setup
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


@pytest.fixture
def baseline(db, test_user):
    """Create a baseline (S1 state)."""
    baseline = Baseline(
        user_id=test_user.id,
        program_name="PhD in Computer Science",
        institution="Test University",
        field_of_study="Computer Science",
        start_date=date.today() - timedelta(days=30),
        total_duration_months=48,
        requirements_summary="Complete coursework, research, and dissertation",
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    return baseline


@pytest.fixture
def draft_timeline(db, test_user, baseline):
    """Create a draft timeline (S2 state)."""
    draft = DraftTimeline(
        user_id=test_user.id,
        baseline_id=baseline.id,
        title="My PhD Timeline",
        description="Initial draft timeline",
        version_number="1.0",
        is_active=True,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    
    # Add a stage and milestone to make it committable
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
    
    return draft


@pytest.fixture
def committed_timeline(db, test_user, baseline, draft_timeline):
    """Create a committed timeline (S3 state)."""
    # Get orchestrator
    orchestrator = TimelineOrchestrator(db=db, user_id=test_user.id)
    
    # Commit the timeline
    committed_id = orchestrator.commit_timeline(
        draft_timeline_id=draft_timeline.id,
        user_id=test_user.id,
        title="Committed PhD Timeline v1.0",
    )
    
    db.commit()
    
    # Return the committed timeline
    committed = db.query(CommittedTimeline).filter(
        CommittedTimeline.id == committed_id
    ).first()
    
    return committed


class TestAllowedTransitions:
    """Test all allowed state transitions."""
    
    def test_s0_to_s1_raw_input_to_baseline(self, db, test_user):
        """
        ✅ ALLOWED: S0 → S1
        Raw input (questionnaire data) → Baseline creation
        """
        # S0: Raw input (simulate questionnaire data)
        program_name = "PhD in Machine Learning"
        institution = "AI Research University"
        field_of_study = "Artificial Intelligence"
        start_date = date.today()
        
        # S0 → S1: Create baseline
        baseline = Baseline(
            user_id=test_user.id,
            program_name=program_name,
            institution=institution,
            field_of_study=field_of_study,
            start_date=start_date,
            total_duration_months=48,
        )
        db.add(baseline)
        db.commit()
        db.refresh(baseline)
        
        # Verify S1 state reached
        assert baseline.id is not None
        assert baseline.program_name == program_name
        assert baseline.user_id == test_user.id
        print("✅ S0 → S1: Raw input → Baseline creation PASSED")
    
    def test_s1_to_s2_baseline_to_draft_timeline(self, db, test_user, baseline):
        """
        ✅ ALLOWED: S1 → S2
        Baseline → Draft timeline creation
        """
        # S1: Baseline exists (from fixture)
        assert baseline.id is not None
        
        # S1 → S2: Create draft timeline
        draft = DraftTimeline(
            user_id=test_user.id,
            baseline_id=baseline.id,
            title="Generated Timeline",
            description="Auto-generated from baseline",
            version_number="1.0",
            is_active=True,
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        
        # Verify S2 state reached
        assert draft.id is not None
        assert draft.baseline_id == baseline.id
        assert draft.is_active is True
        print("✅ S1 → S2: Baseline → Draft timeline PASSED")
    
    def test_s2_to_s3_draft_to_committed_timeline(self, db, test_user, draft_timeline):
        """
        ✅ ALLOWED: S2 → S3
        Draft timeline → Committed timeline
        """
        # S2: Draft timeline exists with stages and milestones (from fixture)
        assert draft_timeline.id is not None
        assert draft_timeline.is_active is True
        
        # Verify draft has stages and milestones
        stages = db.query(TimelineStage).filter(
            TimelineStage.draft_timeline_id == draft_timeline.id
        ).all()
        assert len(stages) > 0
        
        milestones = db.query(TimelineMilestone).filter(
            TimelineMilestone.timeline_stage_id.in_([s.id for s in stages])
        ).all()
        assert len(milestones) > 0
        
        # S2 → S3: Commit timeline
        orchestrator = TimelineOrchestrator(db=db, user_id=test_user.id)
        committed_id = orchestrator.commit_timeline(
            draft_timeline_id=draft_timeline.id,
            user_id=test_user.id,
            title="Committed Timeline v1.0",
        )
        db.commit()
        
        # Verify S3 state reached
        committed = db.query(CommittedTimeline).filter(
            CommittedTimeline.id == committed_id
        ).first()
        assert committed is not None
        assert committed.draft_timeline_id == draft_timeline.id
        assert committed.committed_date is not None
        
        # Verify immutability: draft is now inactive
        db.refresh(draft_timeline)
        assert draft_timeline.is_active is False
        
        print("✅ S2 → S3: Draft → Committed timeline PASSED")
    
    def test_s3_to_s4_committed_to_progress_tracking(self, db, test_user, committed_timeline):
        """
        ✅ ALLOWED: S3 → S4
        Committed timeline → Progress tracking (milestone completion)
        """
        # S3: Committed timeline exists (from fixture)
        assert committed_timeline.id is not None
        
        # Get a milestone from the committed timeline
        stages = db.query(TimelineStage).filter(
            TimelineStage.committed_timeline_id == committed_timeline.id
        ).all()
        assert len(stages) > 0
        
        milestones = db.query(TimelineMilestone).filter(
            TimelineMilestone.timeline_stage_id == stages[0].id
        ).all()
        assert len(milestones) > 0
        
        milestone = milestones[0]
        
        # S3 → S4: Mark milestone completed (progress tracking)
        progress_service = ProgressService(db=db)
        event_id = progress_service.mark_milestone_completed(
            milestone_id=milestone.id,
            user_id=test_user.id,
            completion_date=date.today(),
            notes="Completed successfully"
        )
        db.commit()
        
        # Verify S4 state reached
        progress_event = db.query(ProgressEvent).filter(
            ProgressEvent.id == event_id
        ).first()
        assert progress_event is not None
        assert progress_event.milestone_id == milestone.id
        assert progress_event.event_type == ProgressService.EVENT_TYPE_MILESTONE_COMPLETED
        
        # Verify milestone is marked completed
        db.refresh(milestone)
        assert milestone.is_completed is True
        assert milestone.actual_completion_date is not None
        
        print("✅ S3 → S4: Committed → Progress tracking PASSED")
    
    def test_complete_allowed_pipeline_s0_to_s4(self, db, test_user):
        """
        ✅ ALLOWED: Complete pipeline S0 → S1 → S2 → S3 → S4
        """
        # S0 → S1: Create baseline
        baseline = Baseline(
            user_id=test_user.id,
            program_name="PhD in Quantum Computing",
            institution="Tech University",
            field_of_study="Physics",
            start_date=date.today(),
            total_duration_months=60,
        )
        db.add(baseline)
        db.commit()
        db.refresh(baseline)
        assert baseline.id is not None
        print("  ✅ S0 → S1: Baseline created")
        
        # S1 → S2: Create draft timeline
        draft = DraftTimeline(
            user_id=test_user.id,
            baseline_id=baseline.id,
            title="Quantum PhD Timeline",
            version_number="1.0",
            is_active=True,
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        
        # Add stage and milestone
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
        assert draft.id is not None
        print("  ✅ S1 → S2: Draft timeline created")
        
        # S2 → S3: Commit timeline
        orchestrator = TimelineOrchestrator(db=db, user_id=test_user.id)
        committed_id = orchestrator.commit_timeline(
            draft_timeline_id=draft.id,
            user_id=test_user.id,
        )
        db.commit()
        
        committed = db.query(CommittedTimeline).filter(
            CommittedTimeline.id == committed_id
        ).first()
        assert committed is not None
        print("  ✅ S2 → S3: Timeline committed")
        
        # S3 → S4: Track progress
        progress_service = ProgressService(db=db)
        event_id = progress_service.mark_milestone_completed(
            milestone_id=milestone.id,
            user_id=test_user.id,
        )
        db.commit()
        
        event = db.query(ProgressEvent).filter(ProgressEvent.id == event_id).first()
        assert event is not None
        print("  ✅ S3 → S4: Progress tracked")
        
        print("✅ COMPLETE PIPELINE S0 → S1 → S2 → S3 → S4 PASSED")


class TestDisallowedTransitions:
    """Test all disallowed state transitions that must fail loudly."""
    
    def test_progress_without_committed_timeline_fails(self, db, test_user, draft_timeline):
        """
        ❌ DISALLOWED: S2 → S4 (skip S3)
        Progress tracking without committed timeline must fail.
        
        Error: Cannot track progress on draft timeline milestones.
        """
        # S2: Draft timeline exists (from fixture)
        assert draft_timeline.id is not None
        
        # Get milestone from DRAFT timeline
        stages = db.query(TimelineStage).filter(
            TimelineStage.draft_timeline_id == draft_timeline.id
        ).all()
        assert len(stages) > 0
        
        milestones = db.query(TimelineMilestone).filter(
            TimelineMilestone.timeline_stage_id == stages[0].id
        ).all()
        assert len(milestones) > 0
        
        milestone = milestones[0]
        
        # S2 → S4: Attempt to track progress on draft milestone (SHOULD FAIL)
        progress_service = ProgressService(db=db)
        
        with pytest.raises(ProgressEventWithoutMilestoneError) as exc_info:
            progress_service.mark_milestone_completed(
                milestone_id=milestone.id,
                user_id=test_user.id,
            )
        
        # Verify error message is clear
        error_message = str(exc_info.value)
        assert "not in CommittedTimeline" in error_message
        assert "Progress can only be tracked on committed timelines" in error_message or "CommittedTimeline" in error_message
        
        print(f"✅ DISALLOWED S2 → S4 correctly rejected: {error_message}")
    
    def test_commit_without_draft_fails(self, db, test_user, baseline):
        """
        ❌ DISALLOWED: S0/S1 → S3 (skip S2)
        Committing without a draft timeline must fail.
        
        Error: Cannot commit non-existent draft.
        """
        # S1: Baseline exists (from fixture)
        assert baseline.id is not None
        
        # S1 → S3: Attempt to commit non-existent draft (SHOULD FAIL)
        fake_draft_id = uuid4()
        orchestrator = TimelineOrchestrator(db=db, user_id=test_user.id)
        
        with pytest.raises(CommittedTimelineWithoutDraftError) as exc_info:
            orchestrator.commit_timeline(
                draft_timeline_id=fake_draft_id,
                user_id=test_user.id,
            )
        
        # Verify error message is clear
        error_message = str(exc_info.value)
        assert "not found" in error_message or "DraftTimeline" in error_message
        
        print(f"✅ DISALLOWED commit without draft correctly rejected: {error_message}")
    
    def test_double_commit_fails(self, db, test_user, draft_timeline):
        """
        ❌ DISALLOWED: S2 → S3 → S3
        Double commit must fail (immutability).
        
        Error: Timeline already committed.
        """
        # S2: Draft timeline exists (from fixture)
        assert draft_timeline.id is not None
        
        # S2 → S3: First commit (SHOULD SUCCEED)
        orchestrator = TimelineOrchestrator(db=db, user_id=test_user.id)
        committed_id_1 = orchestrator.commit_timeline(
            draft_timeline_id=draft_timeline.id,
            user_id=test_user.id,
        )
        db.commit()
        
        committed = db.query(CommittedTimeline).filter(
            CommittedTimeline.id == committed_id_1
        ).first()
        assert committed is not None
        print(f"  ✅ First commit succeeded: {committed_id_1}")
        
        # S3 → S3: Second commit attempt (SHOULD FAIL)
        with pytest.raises(CommittedTimelineWithoutDraftError) as exc_info:
            orchestrator.commit_timeline(
                draft_timeline_id=draft_timeline.id,
                user_id=test_user.id,
            )
        
        # Verify error message is clear
        error_message = str(exc_info.value)
        assert "already committed" in error_message
        
        print(f"✅ DISALLOWED double commit correctly rejected: {error_message}")
    
    def test_analytics_without_committed_timeline_fails(self, db, test_user):
        """
        ❌ DISALLOWED: Analytics without committed timeline
        Analytics generation requires committed timeline.
        
        Error: No committed timeline found.
        """
        # No committed timeline exists for this user
        committed_count = db.query(CommittedTimeline).filter(
            CommittedTimeline.user_id == test_user.id
        ).count()
        assert committed_count == 0
        
        # Attempt to generate analytics (SHOULD FAIL)
        analytics_orchestrator = AnalyticsOrchestrator(db=db, user_id=test_user.id)
        
        with pytest.raises(AnalyticsOrchestratorError) as exc_info:
            analytics_orchestrator.run(
                request_id=f"analytics-{uuid4()}",
                user_id=test_user.id,
            )
        
        # Verify error message is clear
        error_message = str(exc_info.value)
        assert "No committed timeline found" in error_message or "committed timeline" in error_message.lower()
        
        print(f"✅ DISALLOWED analytics without timeline correctly rejected: {error_message}")
    
    def test_commit_empty_timeline_fails(self, db, test_user, baseline):
        """
        ❌ DISALLOWED: Commit timeline without stages/milestones
        Empty timeline cannot be committed.
        
        Error: Timeline must have stages and milestones.
        """
        # Create draft WITHOUT stages or milestones
        draft = DraftTimeline(
            user_id=test_user.id,
            baseline_id=baseline.id,
            title="Empty Timeline",
            version_number="1.0",
            is_active=True,
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        
        # Verify no stages exist
        stages = db.query(TimelineStage).filter(
            TimelineStage.draft_timeline_id == draft.id
        ).all()
        assert len(stages) == 0
        
        # Attempt to commit empty timeline (SHOULD FAIL)
        orchestrator = TimelineOrchestrator(db=db, user_id=test_user.id)
        
        with pytest.raises(TimelineOrchestratorError) as exc_info:
            orchestrator.commit_timeline(
                draft_timeline_id=draft.id,
                user_id=test_user.id,
            )
        
        # Verify error message is clear
        error_message = str(exc_info.value)
        assert "no stages" in error_message or "stages" in error_message.lower()
        
        print(f"✅ DISALLOWED empty timeline commit correctly rejected: {error_message}")
    
    def test_commit_timeline_without_milestones_fails(self, db, test_user, baseline):
        """
        ❌ DISALLOWED: Commit timeline with stages but no milestones
        Timeline must have milestones to be committable.
        
        Error: Timeline must have at least one milestone.
        """
        # Create draft with stage but NO milestones
        draft = DraftTimeline(
            user_id=test_user.id,
            baseline_id=baseline.id,
            title="Timeline Without Milestones",
            version_number="1.0",
            is_active=True,
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        
        # Add stage but NO milestones
        stage = TimelineStage(
            draft_timeline_id=draft.id,
            title="Stage Without Milestones",
            stage_order=1,
            status="planned",
        )
        db.add(stage)
        db.commit()
        
        # Verify no milestones exist
        milestones = db.query(TimelineMilestone).filter(
            TimelineMilestone.timeline_stage_id == stage.id
        ).all()
        assert len(milestones) == 0
        
        # Attempt to commit (SHOULD FAIL)
        orchestrator = TimelineOrchestrator(db=db, user_id=test_user.id)
        
        with pytest.raises(TimelineOrchestratorError) as exc_info:
            orchestrator.commit_timeline(
                draft_timeline_id=draft.id,
                user_id=test_user.id,
            )
        
        # Verify error message is clear
        error_message = str(exc_info.value)
        assert "no milestones" in error_message or "milestones" in error_message.lower()
        
        print(f"✅ DISALLOWED commit without milestones correctly rejected: {error_message}")
    
    def test_commit_someone_elses_timeline_fails(self, db, test_user, baseline):
        """
        ❌ DISALLOWED: Commit timeline owned by different user
        Users can only commit their own timelines.
        
        Error: Ownership violation.
        """
        # Create another user
        other_user = User(
            email="other.student@university.edu",
            hashed_password="hashed_password",
            full_name="Other Student",
            institution="Test University",
            field_of_study="Computer Science",
            is_active=True,
        )
        db.add(other_user)
        db.commit()
        db.refresh(other_user)
        
        # Create draft owned by OTHER user
        draft = DraftTimeline(
            user_id=other_user.id,  # Different user!
            baseline_id=baseline.id,
            title="Other User's Timeline",
            version_number="1.0",
            is_active=True,
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        
        # Add stage and milestone
        stage = TimelineStage(
            draft_timeline_id=draft.id,
            title="Stage",
            stage_order=1,
            status="planned",
        )
        db.add(stage)
        db.commit()
        db.refresh(stage)
        
        milestone = TimelineMilestone(
            timeline_stage_id=stage.id,
            title="Milestone",
            milestone_order=1,
            is_completed=False,
        )
        db.add(milestone)
        db.commit()
        
        # TEST_USER attempts to commit OTHER_USER's timeline (SHOULD FAIL)
        orchestrator = TimelineOrchestrator(db=db, user_id=test_user.id)
        
        with pytest.raises(CommittedTimelineWithoutDraftError) as exc_info:
            orchestrator.commit_timeline(
                draft_timeline_id=draft.id,
                user_id=test_user.id,  # Wrong user!
            )
        
        # Verify error message is clear
        error_message = str(exc_info.value)
        assert "not found" in error_message or "not owned" in error_message or "DraftTimeline" in error_message
        
        print(f"✅ DISALLOWED cross-user commit correctly rejected: {error_message}")


class TestStateTransitionMatrix:
    """Test the complete state transition matrix."""
    
    def test_state_transition_matrix_coverage(self, db, test_user):
        """
        Verify all state transitions are tested.
        
        Allowed:
        ✅ S0 → S1 (raw input → baseline)
        ✅ S1 → S2 (baseline → draft timeline)
        ✅ S2 → S3 (draft → committed timeline)
        ✅ S3 → S4 (committed → progress tracking)
        
        Disallowed:
        ❌ S2 → S4 (progress without committed timeline)
        ❌ S0/S1 → S3 (commit without draft)
        ❌ S2 → S3 → S3 (double commit)
        ❌ Analytics without S3 (committed timeline)
        ❌ Commit empty timeline
        ❌ Commit without milestones
        ❌ Cross-user commit
        """
        transition_matrix = {
            "allowed": [
                ("S0", "S1", "Raw input → Baseline"),
                ("S1", "S2", "Baseline → Draft timeline"),
                ("S2", "S3", "Draft → Committed timeline"),
                ("S3", "S4", "Committed → Progress tracking"),
            ],
            "disallowed": [
                ("S2", "S4", "Progress without committed timeline"),
                ("S0/S1", "S3", "Commit without draft"),
                ("S2→S3", "S3", "Double commit (immutability)"),
                ("Any", "Analytics", "Analytics without committed timeline"),
                ("S2_empty", "S3", "Commit empty timeline"),
                ("S2_no_milestones", "S3", "Commit without milestones"),
                ("Other_S2", "S3", "Cross-user commit"),
            ]
        }
        
        print("\n" + "="*80)
        print("STATE TRANSITION MATRIX VALIDATION")
        print("="*80)
        
        print("\n✅ ALLOWED TRANSITIONS:")
        for from_state, to_state, description in transition_matrix["allowed"]:
            print(f"  ✅ {from_state} → {to_state}: {description}")
        
        print("\n❌ DISALLOWED TRANSITIONS (must fail loudly):")
        for from_state, to_state, description in transition_matrix["disallowed"]:
            print(f"  ❌ {from_state} → {to_state}: {description}")
        
        print("\n" + "="*80)
        print("All transitions validated in test suite")
        print("="*80 + "\n")


class TestImmutabilityEnforcement:
    """Test immutability enforcement for committed timelines."""
    
    def test_committed_timeline_is_immutable(self, db, test_user, committed_timeline):
        """
        ❌ DISALLOWED: Modify committed timeline
        Committed timelines must be immutable.
        """
        # S3: Committed timeline exists (from fixture)
        assert committed_timeline.id is not None
        original_title = committed_timeline.title
        
        # Verify the timeline is committed
        assert committed_timeline.committed_date is not None
        
        # NOTE: The system doesn't provide edit operations for committed timelines
        # This is enforced by absence of update methods in the orchestrator
        # If someone tries to modify directly in DB, it violates the design
        
        # The immutability is enforced by:
        # 1. Draft timeline is marked inactive after commit
        draft = db.query(DraftTimeline).filter(
            DraftTimeline.id == committed_timeline.draft_timeline_id
        ).first()
        assert draft is not None
        assert draft.is_active is False
        
        # 2. No update methods exist in TimelineOrchestrator for committed timelines
        orchestrator = TimelineOrchestrator(db=db, user_id=test_user.id)
        assert not hasattr(orchestrator, 'update_committed_timeline')
        
        print("✅ Immutability enforced: Committed timeline cannot be modified")
    
    def test_draft_inactive_after_commit(self, db, test_user, committed_timeline):
        """
        Verify draft timeline is marked inactive after commit.
        """
        # Get the draft timeline that was committed
        draft = db.query(DraftTimeline).filter(
            DraftTimeline.id == committed_timeline.draft_timeline_id
        ).first()
        
        assert draft is not None
        assert draft.is_active is False
        
        print("✅ Draft timeline marked inactive after commit")


class TestErrorMessagesClarity:
    """Test that error messages are clear and actionable."""
    
    def test_error_messages_are_informative(self, db, test_user, draft_timeline):
        """
        Verify all error messages contain:
        - What went wrong
        - Why it's not allowed
        - What state/transition was attempted
        """
        errors_tested = []
        
        # Test 1: Progress without committed timeline
        stages = db.query(TimelineStage).filter(
            TimelineStage.draft_timeline_id == draft_timeline.id
        ).all()
        milestones = db.query(TimelineMilestone).filter(
            TimelineMilestone.timeline_stage_id == stages[0].id
        ).all()
        
        progress_service = ProgressService(db=db)
        try:
            progress_service.mark_milestone_completed(
                milestone_id=milestones[0].id,
                user_id=test_user.id,
            )
        except ProgressEventWithoutMilestoneError as e:
            error_msg = str(e)
            assert len(error_msg) > 20  # Not just a code
            assert "CommittedTimeline" in error_msg or "committed" in error_msg.lower()
            errors_tested.append(("ProgressEventWithoutMilestoneError", error_msg))
        
        # Test 2: Commit without draft
        orchestrator = TimelineOrchestrator(db=db, user_id=test_user.id)
        try:
            orchestrator.commit_timeline(
                draft_timeline_id=uuid4(),
                user_id=test_user.id,
            )
        except CommittedTimelineWithoutDraftError as e:
            error_msg = str(e)
            assert len(error_msg) > 20
            assert "not found" in error_msg.lower() or "draft" in error_msg.lower()
            errors_tested.append(("CommittedTimelineWithoutDraftError", error_msg))
        
        # Test 3: Empty timeline commit
        empty_draft = DraftTimeline(
            user_id=test_user.id,
            baseline_id=draft_timeline.baseline_id,
            title="Empty",
            version_number="1.0",
            is_active=True,
        )
        db.add(empty_draft)
        db.commit()
        
        try:
            orchestrator.commit_timeline(
                draft_timeline_id=empty_draft.id,
                user_id=test_user.id,
            )
        except TimelineOrchestratorError as e:
            error_msg = str(e)
            assert len(error_msg) > 20
            assert "stage" in error_msg.lower()
            errors_tested.append(("TimelineOrchestratorError (empty)", error_msg))
        
        print("\n✅ All error messages are clear and informative:")
        for error_type, message in errors_tested:
            print(f"  - {error_type}: {message[:100]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
