"""
Tests for DecisionTrace validation utility.

Validates that:
1. Every orchestrator execution produces a DecisionTrace
2. DecisionTrace contains all required fields
3. No state mutations occur without traces
"""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.user import User
from app.models.baseline import Baseline
from app.models.draft_timeline import DraftTimeline
from app.models.idempotency import DecisionTrace, IdempotencyKey
from app.utils.trace_validation import (
    validate_trace_completeness,
    validate_trace_for_request,
    validate_state_changes_have_traces,
    validate_all_traces_complete,
    validate_step_order,
    validate_hash_consistency,
    get_orchestrator_execution_summary,
    assert_execution_has_complete_trace,
    ensure_no_untraced_mutations,
    TraceValidationError,
    StateChangeWithoutTraceError,
    IncompleteTraceError,
)


# Use in-memory SQLite for fast tests
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
        email="test@test.com",
        hashed_password="hashed",
        full_name="Test User",
        institution="Test Uni",
        field_of_study="CS",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def complete_trace(db, test_user):
    """Create a complete DecisionTrace."""
    trace = DecisionTrace(
        request_id=f"test-{uuid4()}",
        orchestrator_name="test_orchestrator",
        user_id=test_user.id,
        status="COMPLETED",
        input_hash="abc123",
        output_hash="def456",
        execution_steps=[
            {"step_number": 1, "action": "validate", "status": "completed"},
            {"step_number": 2, "action": "execute", "status": "completed"},
            {"step_number": 3, "action": "persist", "status": "completed"},
        ],
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        duration_ms=100,
        evidence_json={"test": "data"},
    )
    db.add(trace)
    db.commit()
    db.refresh(trace)
    return trace


class TestTraceCompletenessValidation:
    """Test trace completeness validation."""
    
    def test_valid_complete_trace(self, db, complete_trace):
        """Valid trace passes validation."""
        # Should not raise
        validate_trace_completeness(complete_trace)
    
    def test_missing_orchestrator_name(self, db, test_user):
        """Trace without orchestrator_name fails validation."""
        trace = DecisionTrace(
            request_id=f"test-{uuid4()}",
            orchestrator_name=None,  # Missing
            user_id=test_user.id,
            status="COMPLETED",
            input_hash="abc",
            output_hash="def",
            execution_steps=[{"step_number": 1, "action": "test", "status": "completed"}],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        db.add(trace)
        db.commit()
        
        with pytest.raises(IncompleteTraceError, match="orchestrator_name"):
            validate_trace_completeness(trace)
    
    def test_missing_request_id(self, db, test_user):
        """Trace without request_id fails validation."""
        trace = DecisionTrace(
            request_id=None,  # Missing
            orchestrator_name="test",
            user_id=test_user.id,
            status="COMPLETED",
            input_hash="abc",
            output_hash="def",
            execution_steps=[{"step_number": 1, "action": "test", "status": "completed"}],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        db.add(trace)
        db.commit()
        
        with pytest.raises(IncompleteTraceError, match="request_id"):
            validate_trace_completeness(trace)
    
    def test_missing_execution_steps(self, db, test_user):
        """Trace without execution_steps fails validation."""
        trace = DecisionTrace(
            request_id=f"test-{uuid4()}",
            orchestrator_name="test",
            user_id=test_user.id,
            status="COMPLETED",
            input_hash="abc",
            output_hash="def",
            execution_steps=None,  # Missing
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        db.add(trace)
        db.commit()
        
        with pytest.raises(IncompleteTraceError, match="execution_steps"):
            validate_trace_completeness(trace)
    
    def test_invalid_step_order(self, db, test_user):
        """Trace with incorrect step numbers fails validation."""
        trace = DecisionTrace(
            request_id=f"test-{uuid4()}",
            orchestrator_name="test",
            user_id=test_user.id,
            status="COMPLETED",
            input_hash="abc",
            output_hash="def",
            execution_steps=[
                {"step_number": 1, "action": "first", "status": "completed"},
                {"step_number": 3, "action": "skip_two", "status": "completed"},  # Wrong!
            ],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        db.add(trace)
        db.commit()
        
        with pytest.raises(IncompleteTraceError, match="incorrect step_number"):
            validate_trace_completeness(trace)
    
    def test_completed_trace_missing_output_hash(self, db, test_user):
        """Completed trace without output_hash fails validation."""
        trace = DecisionTrace(
            request_id=f"test-{uuid4()}",
            orchestrator_name="test",
            user_id=test_user.id,
            status="COMPLETED",
            input_hash="abc",
            output_hash=None,  # Missing for completed
            execution_steps=[{"step_number": 1, "action": "test", "status": "completed"}],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        db.add(trace)
        db.commit()
        
        with pytest.raises(IncompleteTraceError, match="output_hash"):
            validate_trace_completeness(trace)
    
    def test_failed_trace_missing_error_message(self, db, test_user):
        """Failed trace without error_message fails validation."""
        trace = DecisionTrace(
            request_id=f"test-{uuid4()}",
            orchestrator_name="test",
            user_id=test_user.id,
            status="FAILED",
            input_hash="abc",
            error_message=None,  # Missing for failed
            execution_steps=[{"step_number": 1, "action": "test", "status": "failed"}],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        db.add(trace)
        db.commit()
        
        with pytest.raises(IncompleteTraceError, match="error_message"):
            validate_trace_completeness(trace)
    
    def test_missing_timestamps(self, db, test_user):
        """Trace without timestamps fails validation."""
        trace = DecisionTrace(
            request_id=f"test-{uuid4()}",
            orchestrator_name="test",
            user_id=test_user.id,
            status="COMPLETED",
            input_hash="abc",
            output_hash="def",
            execution_steps=[{"step_number": 1, "action": "test", "status": "completed"}],
            started_at=None,  # Missing
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        db.add(trace)
        db.commit()
        
        with pytest.raises(IncompleteTraceError, match="started_at"):
            validate_trace_completeness(trace)


class TestStateChangesWithTraces:
    """Test validation of state changes with corresponding traces."""
    
    def test_baseline_creation_with_trace(self, db, test_user):
        """Baseline created with corresponding trace passes validation."""
        now = datetime.utcnow()
        
        # Create baseline
        baseline = Baseline(
            user_id=test_user.id,
            program_name="PhD",
            institution="Test",
            field_of_study="CS",
            start_date=datetime.now().date(),
            total_duration_months=48,
        )
        db.add(baseline)
        db.commit()
        
        # Create idempotency key
        request_id = f"baseline-{uuid4()}"
        key = IdempotencyKey(
            request_id=request_id,
            orchestrator_name="baseline_orchestrator",
            user_id=test_user.id,
            status="COMPLETED",
            request_payload={"test": "data"},
            response_data={"baseline_id": str(baseline.id)},
        )
        db.add(key)
        db.commit()
        
        # Create trace
        trace = DecisionTrace(
            request_id=request_id,
            orchestrator_name="baseline_orchestrator",
            user_id=test_user.id,
            status="COMPLETED",
            input_hash="abc",
            output_hash="def",
            execution_steps=[{"step_number": 1, "action": "create", "status": "completed"}],
            started_at=now,
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        db.add(trace)
        db.commit()
        
        # Should not raise
        result = validate_state_changes_have_traces(db, now)
        assert result["violations"] == []
    
    def test_baseline_without_trace_fails(self, db, test_user):
        """Baseline created without trace fails validation."""
        now = datetime.utcnow()
        
        # Create baseline WITHOUT trace
        baseline = Baseline(
            user_id=test_user.id,
            program_name="PhD",
            institution="Test",
            field_of_study="CS",
            start_date=datetime.now().date(),
            total_duration_months=48,
        )
        db.add(baseline)
        db.commit()
        
        # Should raise StateChangeWithoutTraceError
        with pytest.raises(StateChangeWithoutTraceError, match="state changes without traces"):
            validate_state_changes_have_traces(db, now)
    
    def test_multiple_models_validation(self, db, test_user):
        """Validation checks multiple model types."""
        now = datetime.utcnow()
        
        # Create baseline
        baseline = Baseline(
            user_id=test_user.id,
            program_name="PhD",
            institution="Test",
            field_of_study="CS",
            start_date=datetime.now().date(),
            total_duration_months=48,
        )
        db.add(baseline)
        
        # Create draft timeline
        draft = DraftTimeline(
            user_id=test_user.id,
            baseline_id=baseline.id,
            title="Test",
            version_number="1.0",
            is_active=True,
        )
        db.add(draft)
        db.commit()
        
        # Both without traces - should detect both violations
        with pytest.raises(StateChangeWithoutTraceError) as exc_info:
            validate_state_changes_have_traces(db, now)
        
        error_msg = str(exc_info.value)
        assert "baselines" in error_msg
        assert "draft_timelines" in error_msg


class TestValidateTraceForRequest:
    """Test validation of trace for specific request."""
    
    def test_valid_trace_for_request(self, db, complete_trace):
        """Finding and validating existing trace succeeds."""
        trace = validate_trace_for_request(
            db,
            complete_trace.request_id,
            complete_trace.orchestrator_name
        )
        assert trace.request_id == complete_trace.request_id
    
    def test_missing_trace_for_request(self, db):
        """Missing trace for request raises error."""
        with pytest.raises(TraceValidationError, match="No DecisionTrace found"):
            validate_trace_for_request(db, "nonexistent", "test_orchestrator")
    
    def test_incomplete_trace_for_request(self, db, test_user):
        """Incomplete trace for request raises error."""
        request_id = f"test-{uuid4()}"
        trace = DecisionTrace(
            request_id=request_id,
            orchestrator_name="test",
            user_id=test_user.id,
            status="COMPLETED",
            input_hash="abc",
            output_hash=None,  # Missing - makes it incomplete
            execution_steps=[{"step_number": 1, "action": "test", "status": "completed"}],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        db.add(trace)
        db.commit()
        
        with pytest.raises(IncompleteTraceError):
            validate_trace_for_request(db, request_id, "test")


class TestValidateAllTracesComplete:
    """Test validation of all traces in database."""
    
    def test_all_complete_traces(self, db, complete_trace):
        """Database with only complete traces passes validation."""
        result = validate_all_traces_complete(db)
        assert result["total_traces"] == 1
        assert result["incomplete_traces"] == []
    
    def test_mixed_complete_incomplete(self, db, test_user, complete_trace):
        """Database with incomplete traces fails validation."""
        # Add incomplete trace
        incomplete = DecisionTrace(
            request_id=f"incomplete-{uuid4()}",
            orchestrator_name="test",
            user_id=test_user.id,
            status="COMPLETED",
            input_hash="abc",
            output_hash=None,  # Missing
            execution_steps=[{"step_number": 1, "action": "test", "status": "completed"}],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        db.add(incomplete)
        db.commit()
        
        with pytest.raises(IncompleteTraceError, match="incomplete traces"):
            validate_all_traces_complete(db)
    
    def test_filter_by_orchestrator(self, db, test_user, complete_trace):
        """Can filter validation by orchestrator name."""
        # Add trace for different orchestrator
        other_trace = DecisionTrace(
            request_id=f"other-{uuid4()}",
            orchestrator_name="other_orchestrator",
            user_id=test_user.id,
            status="COMPLETED",
            input_hash="abc",
            output_hash=None,  # Incomplete, but different orchestrator
            execution_steps=[{"step_number": 1, "action": "test", "status": "completed"}],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        db.add(other_trace)
        db.commit()
        
        # Should pass when filtering by complete_trace orchestrator
        result = validate_all_traces_complete(
            db,
            orchestrator_name=complete_trace.orchestrator_name
        )
        assert result["total_traces"] == 1


class TestStepOrderValidation:
    """Test step order validation."""
    
    def test_valid_step_order(self):
        """Sequential step numbers pass validation."""
        steps = [
            {"step_number": 1, "action": "first"},
            {"step_number": 2, "action": "second"},
            {"step_number": 3, "action": "third"},
        ]
        validate_step_order(steps)  # Should not raise
    
    def test_missing_step_number(self):
        """Steps without step_number fail validation."""
        steps = [
            {"action": "first"},  # Missing step_number
        ]
        with pytest.raises(TraceValidationError, match="missing step_number"):
            validate_step_order(steps)
    
    def test_skipped_step_number(self):
        """Non-sequential step numbers fail validation."""
        steps = [
            {"step_number": 1, "action": "first"},
            {"step_number": 3, "action": "skip_two"},
        ]
        with pytest.raises(TraceValidationError, match="Step order violation"):
            validate_step_order(steps)
    
    def test_empty_steps(self):
        """Empty steps list fails validation."""
        with pytest.raises(TraceValidationError, match="empty"):
            validate_step_order([])


class TestHashConsistency:
    """Test hash consistency validation."""
    
    def test_matching_hash(self):
        """Matching hashes pass validation."""
        import hashlib
        import json
        
        input_data = {"key": "value", "number": 123}
        input_json = json.dumps(input_data, sort_keys=True, default=str)
        expected_hash = hashlib.sha256(input_json.encode()).hexdigest()
        
        validate_hash_consistency(input_data, expected_hash)  # Should not raise
    
    def test_mismatched_hash(self):
        """Mismatched hashes fail validation."""
        input_data = {"key": "value"}
        wrong_hash = "0" * 64
        
        with pytest.raises(TraceValidationError, match="hash mismatch"):
            validate_hash_consistency(input_data, wrong_hash)


class TestExecutionSummary:
    """Test orchestrator execution summary."""
    
    def test_execution_summary(self, db, test_user):
        """Summary includes execution statistics."""
        orchestrator = "test_orchestrator"
        
        # Create completed trace
        trace1 = DecisionTrace(
            request_id=f"test1-{uuid4()}",
            orchestrator_name=orchestrator,
            user_id=test_user.id,
            status="COMPLETED",
            input_hash="abc",
            output_hash="def",
            execution_steps=[{"step_number": 1, "action": "test", "status": "completed"}],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        
        # Create failed trace
        trace2 = DecisionTrace(
            request_id=f"test2-{uuid4()}",
            orchestrator_name=orchestrator,
            user_id=test_user.id,
            status="FAILED",
            input_hash="abc",
            error_message="Test error",
            execution_steps=[{"step_number": 1, "action": "test", "status": "failed"}],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=50,
        )
        
        db.add_all([trace1, trace2])
        db.commit()
        
        summary = get_orchestrator_execution_summary(db, orchestrator)
        
        assert summary["orchestrator"] == orchestrator
        assert summary["total_executions"] == 2
        assert summary["completed"] == 1
        assert summary["failed"] == 1
        assert summary["avg_duration_ms"] == 75.0  # (100 + 50) / 2
        assert summary["incomplete_traces"] == 0


class TestConvenienceFunctions:
    """Test convenience functions for common use cases."""
    
    def test_assert_execution_has_complete_trace(self, db, complete_trace):
        """Assert function succeeds with complete trace."""
        trace = assert_execution_has_complete_trace(
            db,
            complete_trace.request_id,
            complete_trace.orchestrator_name
        )
        assert trace.request_id == complete_trace.request_id
    
    def test_assert_execution_fails_for_incomplete(self, db, test_user):
        """Assert function raises AssertionError for incomplete trace."""
        request_id = f"test-{uuid4()}"
        trace = DecisionTrace(
            request_id=request_id,
            orchestrator_name="test",
            user_id=test_user.id,
            status="COMPLETED",
            input_hash="abc",
            output_hash=None,  # Incomplete
            execution_steps=[{"step_number": 1, "action": "test", "status": "completed"}],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        db.add(trace)
        db.commit()
        
        with pytest.raises(AssertionError, match="Trace validation failed"):
            assert_execution_has_complete_trace(db, request_id, "test")
    
    def test_ensure_no_untraced_mutations(self, db, test_user):
        """Ensure function succeeds with properly traced mutations."""
        now = datetime.utcnow()
        
        # Create baseline with trace
        baseline = Baseline(
            user_id=test_user.id,
            program_name="PhD",
            institution="Test",
            field_of_study="CS",
            start_date=datetime.now().date(),
            total_duration_months=48,
        )
        db.add(baseline)
        db.commit()
        
        # Create trace
        request_id = f"test-{uuid4()}"
        key = IdempotencyKey(
            request_id=request_id,
            orchestrator_name="baseline_orchestrator",
            user_id=test_user.id,
            status="COMPLETED",
            request_payload={},
            response_data={},
        )
        trace = DecisionTrace(
            request_id=request_id,
            orchestrator_name="baseline_orchestrator",
            user_id=test_user.id,
            status="COMPLETED",
            input_hash="abc",
            output_hash="def",
            execution_steps=[{"step_number": 1, "action": "test", "status": "completed"}],
            started_at=now,
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        db.add_all([key, trace])
        db.commit()
        
        # Should not raise
        ensure_no_untraced_mutations(db, now)
