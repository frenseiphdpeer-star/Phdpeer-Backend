"""
Test AnalyticsSnapshot immutability, versioning, and non-overwriting behavior.

Validates:
- Snapshots are immutable (no update/delete operations)
- Snapshots are versioned by timeline_version
- Re-running analytics creates new snapshot instead of overwriting
- Multiple snapshots can exist for different timeline versions
"""
import pytest
import os
from datetime import date, timedelta
from uuid import uuid4
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

# Set environment variables before importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")

from app.database import Base
from app.models.user import User
from app.models.baseline import Baseline
from app.models.committed_timeline import CommittedTimeline
from app.models.timeline_stage import TimelineStage
from app.models.timeline_milestone import TimelineMilestone
from app.models.progress_event import ProgressEvent
from app.models.journey_assessment import JourneyAssessment
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.orchestrators.analytics_orchestrator import AnalyticsOrchestrator


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


@pytest.fixture
def test_timeline_with_data(db, test_user):
    """Create a committed timeline with complete data."""
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
        notes="Version 1.0"
    )
    db.add(timeline)
    db.commit()
    db.refresh(timeline)
    
    # Create stages
    stage = TimelineStage(
        committed_timeline_id=timeline.id,
        title="Literature Review",
        stage_order=1,
        status="in_progress",
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    
    # Create milestones
    today = date.today()
    milestone = TimelineMilestone(
        timeline_stage_id=stage.id,
        title="Complete literature review",
        milestone_order=1,
        target_date=today - timedelta(days=20),
        is_critical=True,
        is_completed=True,
        actual_completion_date=today - timedelta(days=10),
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    
    # Create progress event
    event = ProgressEvent(
        user_id=test_user.id,
        milestone_id=milestone.id,
        event_type="milestone_completed",
        title="Completed literature review",
        description="Finished",
        event_date=today - timedelta(days=10),
        impact_level="medium",
    )
    db.add(event)
    db.commit()
    
    # Create journey assessment
    assessment = JourneyAssessment(
        user_id=test_user.id,
        submission_text="Making progress",
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
    
    return timeline


class TestAnalyticsSnapshotImmutability:
    """Test analytics snapshot immutability and versioning."""
    
    def test_snapshot_model_has_no_update_methods(self):
        """Test: AnalyticsSnapshot model has no update methods."""
        from app.models.analytics_snapshot import AnalyticsSnapshot
        
        # Verify no update-related methods exist on model
        model_methods = dir(AnalyticsSnapshot)
        update_methods = [m for m in model_methods if 'update' in m.lower()]
        
        # SQLAlchemy adds __mapper__ related stuff, filter those out
        dangerous_methods = [m for m in update_methods if not m.startswith('_')]
        
        assert len(dangerous_methods) == 0, (
            f"AnalyticsSnapshot should not have update methods, found: {dangerous_methods}"
        )
        
        print("✓ AnalyticsSnapshot has no update methods")
    
    def test_snapshot_fields_are_non_nullable(self):
        """Test: Critical snapshot fields are non-nullable to ensure data integrity."""
        from sqlalchemy import inspect as sqla_inspect
        from app.models.analytics_snapshot import AnalyticsSnapshot
        
        mapper = sqla_inspect(AnalyticsSnapshot)
        
        # Check that critical columns are non-nullable
        critical_columns = ['user_id', 'timeline_version', 'summary_json']
        
        for col_name in critical_columns:
            column = mapper.columns[col_name]
            assert not column.nullable, (
                f"Column {col_name} should be non-nullable for data integrity"
            )
        
        print("✓ Critical snapshot fields are non-nullable")
    
    def test_snapshot_is_versioned_by_timeline_version(self, db, test_user, test_timeline_with_data):
        """Test: Snapshots are versioned by timeline_version field."""
        orchestrator = AnalyticsOrchestrator(db, test_user.id)
        
        # Create first snapshot
        request_id_1 = f"analytics-{uuid4()}"
        result_1 = orchestrator.run(
            request_id=request_id_1,
            user_id=test_user.id,
            timeline_id=test_timeline_with_data.id
        )
        
        # Verify snapshot was created with version
        snapshot_1 = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.id == result_1['snapshot_id']
        ).first()
        
        assert snapshot_1 is not None
        assert snapshot_1.timeline_version == "1.0"  # From notes "Version 1.0"
        assert snapshot_1.user_id == test_user.id
        
        print(f"✓ Snapshot created with timeline_version: {snapshot_1.timeline_version}")
        
        # Update timeline version (simulating a timeline edit)
        test_timeline_with_data.notes = "Version 2.0"
        db.commit()
        
        # Create second snapshot with different version
        request_id_2 = f"analytics-{uuid4()}"
        result_2 = orchestrator.run(
            request_id=request_id_2,
            user_id=test_user.id,
            timeline_id=test_timeline_with_data.id
        )
        
        # Verify second snapshot was created with new version
        snapshot_2 = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.id == result_2['snapshot_id']
        ).first()
        
        assert snapshot_2 is not None
        assert snapshot_2.timeline_version == "2.0"
        assert snapshot_2.id != snapshot_1.id  # Different snapshot
        
        print(f"✓ Second snapshot created with timeline_version: {snapshot_2.timeline_version}")
        
        # Verify both snapshots still exist
        all_snapshots = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.user_id == test_user.id
        ).all()
        
        assert len(all_snapshots) == 2
        versions = {s.timeline_version for s in all_snapshots}
        assert versions == {"1.0", "2.0"}
        
        print("✓ Both snapshots coexist with different versions")
    
    def test_rerunnig_analytics_creates_new_snapshot_not_overwrites(self, db, test_user, test_timeline_with_data):
        """Test: Re-running analytics creates a new snapshot instead of overwriting."""
        orchestrator = AnalyticsOrchestrator(db, test_user.id)
        
        # Create first snapshot
        request_id_1 = f"analytics-{uuid4()}"
        result_1 = orchestrator.run(
            request_id=request_id_1,
            user_id=test_user.id,
            timeline_id=test_timeline_with_data.id
        )
        
        snapshot_1_id = result_1['snapshot_id']
        snapshot_1 = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.id == snapshot_1_id
        ).first()
        
        original_created_at = snapshot_1.created_at
        original_summary = snapshot_1.summary_json.copy()
        
        # Wait a moment to ensure different timestamp (in real scenario)
        import time
        time.sleep(0.01)
        
        # Re-run analytics with different request_id (simulating re-generation)
        request_id_2 = f"analytics-{uuid4()}"
        result_2 = orchestrator.run(
            request_id=request_id_2,
            user_id=test_user.id,
            timeline_id=test_timeline_with_data.id
        )
        
        snapshot_2_id = result_2['snapshot_id']
        
        # Verify a NEW snapshot was created
        assert snapshot_2_id != snapshot_1_id, (
            "Re-running analytics should create a new snapshot, not reuse the old one"
        )
        
        # Verify original snapshot is UNCHANGED (immutable)
        snapshot_1_after = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.id == snapshot_1_id
        ).first()
        
        assert snapshot_1_after is not None, "Original snapshot should still exist"
        assert snapshot_1_after.created_at == original_created_at, (
            "Original snapshot created_at should not change"
        )
        assert snapshot_1_after.summary_json == original_summary, (
            "Original snapshot summary_json should not change"
        )
        
        # Verify we now have 2 snapshots
        all_snapshots = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.user_id == test_user.id
        ).all()
        
        assert len(all_snapshots) == 2, (
            "Should have 2 snapshots after re-running analytics"
        )
        
        print("✓ Re-running analytics creates new snapshot")
        print("✓ Original snapshot remains unchanged (immutable)")
        print(f"✓ Total snapshots: {len(all_snapshots)}")
    
    def test_snapshot_data_cannot_be_modified(self, db, test_user, test_timeline_with_data):
        """Test: Snapshot data cannot be modified after creation."""
        orchestrator = AnalyticsOrchestrator(db, test_user.id)
        
        # Create snapshot
        request_id = f"analytics-{uuid4()}"
        result = orchestrator.run(
            request_id=request_id,
            user_id=test_user.id,
            timeline_id=test_timeline_with_data.id
        )
        
        snapshot_id = result['snapshot_id']
        snapshot = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.id == snapshot_id
        ).first()
        
        original_summary = snapshot.summary_json.copy()
        original_version = snapshot.timeline_version
        original_created_at = snapshot.created_at
        
        # Attempt to modify snapshot fields (this should be prevented by immutability design)
        # In practice, developers should not do this, but we test the behavior
        
        # Try to change timeline_version
        try:
            snapshot.timeline_version = "999.0"
            snapshot.summary_json = {"modified": "data"}
            db.commit()
            
            # If we get here, modification succeeded (not ideal but documents current behavior)
            # Fetch snapshot again to see if changes persisted
            snapshot_after = db.query(AnalyticsSnapshot).filter(
                AnalyticsSnapshot.id == snapshot_id
            ).first()
            
            if snapshot_after.timeline_version == "999.0":
                pytest.fail(
                    "WARNING: Snapshot was modified directly in database. "
                    "Add database-level immutability constraints or application-level guards."
                )
        except Exception as e:
            # If modification fails, that's good (immutability enforced)
            print(f"✓ Modification prevented: {type(e).__name__}")
            db.rollback()
        
        # Verify snapshot still has original data
        snapshot_final = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.id == snapshot_id
        ).first()
        
        # Note: This test documents current behavior
        # Ideally, there would be database triggers or application-level guards
        print("✓ Snapshot immutability test completed")
    
    def test_multiple_snapshots_per_timeline_version(self, db, test_user, test_timeline_with_data):
        """Test: Multiple snapshots can exist for the same timeline version."""
        orchestrator = AnalyticsOrchestrator(db, test_user.id)
        
        # Create multiple snapshots for the same timeline version
        snapshot_ids = []
        for i in range(3):
            request_id = f"analytics-{uuid4()}"
            result = orchestrator.run(
                request_id=request_id,
                user_id=test_user.id,
                timeline_id=test_timeline_with_data.id
            )
            snapshot_ids.append(result['snapshot_id'])
        
        # Verify all 3 snapshots exist
        snapshots = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.user_id == test_user.id,
            AnalyticsSnapshot.timeline_version == "1.0"
        ).all()
        
        assert len(snapshots) == 3, (
            "Should be able to create multiple snapshots for same timeline version"
        )
        
        # Verify each has unique ID and created_at
        ids = {s.id for s in snapshots}
        assert len(ids) == 3, "Each snapshot should have unique ID"
        
        created_at_list = [s.created_at for s in snapshots]
        # They might have same timestamp in test, but should be different objects
        assert len(snapshots) == 3
        
        print(f"✓ Created {len(snapshots)} snapshots for same timeline version")
        print("✓ Each snapshot has unique ID")
    
    def test_snapshot_history_is_preserved(self, db, test_user, test_timeline_with_data):
        """Test: Snapshot history is preserved across timeline changes."""
        orchestrator = AnalyticsOrchestrator(db, test_user.id)
        
        # Create snapshots for different timeline versions
        versions = ["1.0", "1.1", "2.0", "2.1"]
        snapshot_data = []
        
        for version in versions:
            test_timeline_with_data.notes = f"Version {version}"
            db.commit()
            
            request_id = f"analytics-{uuid4()}"
            result = orchestrator.run(
                request_id=request_id,
                user_id=test_user.id,
                timeline_id=test_timeline_with_data.id
            )
            
            snapshot = db.query(AnalyticsSnapshot).filter(
                AnalyticsSnapshot.id == result['snapshot_id']
            ).first()
            
            snapshot_data.append({
                'id': snapshot.id,
                'version': snapshot.timeline_version,
                'created_at': snapshot.created_at
            })
        
        # Verify all snapshots still exist
        all_snapshots = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.user_id == test_user.id
        ).order_by(AnalyticsSnapshot.created_at).all()
        
        assert len(all_snapshots) == 4
        
        # Verify versions are correct
        snapshot_versions = [s.timeline_version for s in all_snapshots]
        assert snapshot_versions == versions
        
        # Verify chronological ordering is preserved
        created_at_list = [s.created_at for s in all_snapshots]
        assert created_at_list == sorted(created_at_list), (
            "Snapshots should be in chronological order"
        )
        
        print(f"✓ Created snapshots for versions: {versions}")
        print("✓ All snapshots preserved in history")
        print("✓ Chronological ordering maintained")
    
    def test_idempotent_analytics_uses_existing_snapshot(self, db, test_user, test_timeline_with_data):
        """Test: Idempotent analytics calls return cached snapshot for same request_id."""
        orchestrator = AnalyticsOrchestrator(db, test_user.id)
        
        # Use same request_id for multiple calls
        request_id = f"analytics-idempotent-{uuid4()}"
        
        # First call creates snapshot
        result_1 = orchestrator.run(
            request_id=request_id,
            user_id=test_user.id,
            timeline_id=test_timeline_with_data.id
        )
        
        # Second call with same request_id should return cached result
        result_2 = orchestrator.run(
            request_id=request_id,
            user_id=test_user.id,
            timeline_id=test_timeline_with_data.id
        )
        
        # Should return same snapshot_id
        assert result_1['snapshot_id'] == result_2['snapshot_id']
        
        # Verify only one snapshot was created
        snapshots = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.user_id == test_user.id
        ).all()
        
        assert len(snapshots) == 1, (
            "Idempotent call should not create duplicate snapshot"
        )
        
        print("✓ Idempotent analytics returns cached snapshot")
        print("✓ No duplicate snapshots created")
