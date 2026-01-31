# Failure Path Testing Guide

## Overview

The failure path test suite (`test_failure_paths.py`) deliberately breaks the system to verify that error handling, atomicity, and audit trails work correctly. These tests are **critical** for ensuring data integrity and system reliability.

## What Gets Tested

### 1. Atomicity (No Partial Writes)
Every test verifies that when an operation fails, **NO partial data** is written to the database:
- Failed timeline commits don't create partial `CommittedTimeline` records
- Failed progress tracking doesn't create orphaned `ProgressEvent` records
- Failed analytics don't create incomplete snapshots

### 2. Loud Failures (No Silent Errors)
Every test verifies that errors are **raised explicitly** and not silently ignored:
- Invalid operations throw clear exceptions
- Error messages contain actionable information
- No operations return `None` or empty results on failure

### 3. Audit Trail Preservation
Tests verify that `DecisionTrace` records are written **even when operations fail**:
- Failed attempts are logged for debugging
- Evidence bundles capture what went wrong
- Audit trail remains complete

### 4. Database Rollback
Tests verify that database transactions **rollback completely** on failure:
- First successful operation is preserved
- Second failing operation doesn't corrupt first
- System remains in consistent state

## Test Categories

### TestCommitFailures (3 tests)
Deliberately attempts invalid timeline commits:
- **test_commit_without_draft_no_partial_writes**: Tries to commit non-existent draft
- **test_commit_empty_timeline_no_partial_writes**: Tries to commit timeline without stages
- **test_double_commit_preserves_first_commit**: Tries to commit same timeline twice

**Verifies**: No `CommittedTimeline` created, no stages copied, original draft unchanged

### TestTimelineGenerationFailures (2 tests)
Deliberately breaks timeline generation:
- **test_generate_timeline_without_baseline**: Tries to create timeline for non-existent baseline
- **test_generate_timeline_wrong_user**: Tries to create timeline for another user's baseline

**Verifies**: No `DraftTimeline` created, no stages/milestones created

### TestProgressTrackingFailures (3 tests)
Deliberately breaks progress tracking:
- **test_mark_progress_on_nonexistent_milestone**: Tries to complete non-existent milestone
- **test_mark_progress_on_draft_milestone**: Tries to complete milestone from draft (not committed)
- **test_mark_progress_wrong_user**: Tries to complete another user's milestone

**Verifies**: No `ProgressEvent` created, milestone state unchanged

### TestAnalyticsFailures (2 tests)
Deliberately breaks analytics generation:
- **test_analytics_without_committed_timeline**: Tries to run analytics with no timeline
- **test_analytics_with_invalid_timeline_id**: Tries to run analytics with fake timeline ID

**Verifies**: No `AnalyticsSnapshot` created, clear error message

### TestQuestionnaireFailures (2 tests)
Deliberately breaks PhD Doctor questionnaire:
- **test_submit_questionnaire_twice_same_request_id**: Submits same questionnaire twice (tests idempotency)
- **test_submit_incomplete_questionnaire**: Submits insufficient responses

**Verifies**: Idempotency works (no duplicate assessments), validation catches incomplete data

### TestDecisionTraceOnFailure (2 tests)
Verifies audit trail on failures:
- **test_decision_trace_written_on_commit_failure**: Checks trace written even when commit fails
- **test_decision_trace_written_on_progress_failure**: Checks service-level operations (no trace by design)

**Verifies**: DecisionTrace audit trail preserved for orchestrator operations

### TestAtomicityAndRollback (2 tests)
Verifies database transaction behavior:
- **test_partial_timeline_commit_rolls_back**: Simulates partial commit and verifies rollback
- **test_progress_tracking_atomicity**: Verifies milestone update and event creation are atomic

**Verifies**: Database transactions are all-or-nothing

### TestSilentFailurePrevention (3 tests)
Verifies no silent failures:
- **test_no_silent_failure_on_invalid_baseline**: Invalid baseline must raise error
- **test_no_silent_failure_on_invalid_user**: Invalid user must raise error
- **test_no_silent_failure_on_missing_data**: Missing required data must raise error

**Verifies**: All failures raise exceptions (no silent failures)

## Running the Tests

### Prerequisites

**IMPORTANT**: These tests require PostgreSQL. SQLite **cannot** be used due to UUID type incompatibility.

### Option 1: Using docker-compose (Recommended)

```bash
# Start PostgreSQL
cd /path/to/Phdpeer-Backend
docker-compose up -d postgres

# Set environment variables
export DATABASE_URL='postgresql://phdpeer:phdpeer123@localhost:5432/phdpeer_db'
export SECRET_KEY='your-secret-key'

# Run tests using the provided script
cd backend
./run_failure_path_tests.sh
```

### Option 2: Using existing PostgreSQL

```bash
# Set your PostgreSQL connection
export DATABASE_URL='postgresql://user:password@host:port/database'
export SECRET_KEY='your-secret-key'

# Run tests
cd backend
./run_failure_path_tests.sh
```

### Option 3: Direct pytest command

```bash
# Set environment variables
export DATABASE_URL='postgresql://user:password@host:port/database'
export SECRET_KEY='your-secret-key'

# Run with pytest
python -m pytest tests/test_failure_paths.py -v -s
```

### Running Specific Test Categories

```bash
# Run only commit failures
python -m pytest tests/test_failure_paths.py::TestCommitFailures -v

# Run only progress tracking failures
python -m pytest tests/test_failure_paths.py::TestProgressTrackingFailures -v

# Run only atomicity tests
python -m pytest tests/test_failure_paths.py::TestAtomicityAndRollback -v

# Run a single test
python -m pytest tests/test_failure_paths.py::TestCommitFailures::test_commit_without_draft_no_partial_writes -v
```

## What Success Looks Like

When all tests pass, you should see output like:

```
╔════════════════════════════════════════════════════════════════════════════╗
║                    FAILURE PATH TEST SUITE                                 ║
║                                                                            ║
║  Tests that deliberately break the system to verify:                      ║
║  • No partial writes occur (atomicity)                                    ║
║  • No silent failures (errors are raised loudly)                          ║
║  • DecisionTrace audit trail preserved even on failures                   ║
║  • Database rollback happens correctly                                    ║
╚════════════════════════════════════════════════════════════════════════════╝

✓ PostgreSQL DATABASE_URL detected
✓ Environment configured

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Running failure path tests...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

tests/test_failure_paths.py::TestCommitFailures::test_commit_without_draft_no_partial_writes PASSED
✅ VERIFIED: No partial writes on commit failure

tests/test_failure_paths.py::TestCommitFailures::test_commit_empty_timeline_no_partial_writes PASSED
✅ VERIFIED: No partial writes on empty timeline commit

... [more tests] ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ ALL FAILURE PATH TESTS PASSED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Verified:
  ✓ No partial writes on failures
  ✓ All errors raised loudly (no silent failures)
  ✓ DecisionTrace audit trail preserved
  ✓ Database rollback working correctly
  ✓ System remains consistent after failures
```

## Understanding Test Patterns

Each test follows this pattern:

```python
def test_some_failure_case(self, db, test_user):
    """
    FAILURE PATH: Describe what we're breaking
    
    Verify:
    - What should NOT happen
    - What error should be raised
    - What state should be preserved
    """
    # 1. Get baseline state (count records, capture values)
    count_before = db.query(SomeModel).count()
    
    # 2. Attempt invalid operation
    with pytest.raises(SpecificError) as exc_info:
        service.do_something_invalid(...)
    
    # 3. Verify error message is clear
    assert "expected keyword" in str(exc_info.value).lower()
    
    # 4. Verify NO changes occurred
    count_after = db.query(SomeModel).count()
    assert count_before == count_after, "No records should be created"
    
    print("✅ VERIFIED: Specific guarantee holds")
```

## Key Assertions

### No Partial Writes
```python
committed_count_before = db.query(CommittedTimeline).count()
# ... attempt operation ...
committed_count_after = db.query(CommittedTimeline).count()
assert committed_count_before == committed_count_after, \
    "No CommittedTimeline should be created on failure"
```

### Error Messages Are Clear
```python
with pytest.raises(SomeError) as exc_info:
    # ... attempt operation ...

error_msg = str(exc_info.value).lower()
assert "timeline" in error_msg or "committed" in error_msg, \
    "Error message should mention timeline"
```

### Atomicity Verification
```python
# Both operations should succeed together or fail together
milestone_completed_before = milestone.is_completed
progress_count_before = db.query(ProgressEvent).count()

# ... mark milestone completed (should be atomic) ...

db.refresh(milestone)
progress_count_after = db.query(ProgressEvent).count()

# BOTH should have changed
assert milestone.is_completed is True
assert progress_count_after == progress_count_before + 1
```

## Troubleshooting

### Test fails with "CompileError: can't render element of type UUID"
**Problem**: You're using SQLite instead of PostgreSQL

**Solution**: 
1. Start PostgreSQL: `docker-compose up -d postgres`
2. Set DATABASE_URL: `export DATABASE_URL='postgresql://...'`
3. Run tests again

### Test fails with "ValidationError: DATABASE_URL Field required"
**Problem**: DATABASE_URL environment variable not set

**Solution**: Export DATABASE_URL before running tests

### Test fails with connection error
**Problem**: PostgreSQL not running or wrong credentials

**Solution**: 
1. Check PostgreSQL is running: `docker-compose ps`
2. Verify connection string is correct
3. Test connection: `psql $DATABASE_URL -c "SELECT 1"`

### All tests pass but one specific test fails
**Problem**: Possible race condition or database state issue

**Solution**:
1. Run that test in isolation: `pytest tests/test_failure_paths.py::TestClass::test_method -v`
2. Check if test is cleaning up properly (using fixture rollback)
3. Verify test doesn't depend on specific database state

## Integration with CI/CD

Add to your CI pipeline:

```yaml
# .github/workflows/test.yml or similar
test-failure-paths:
  runs-on: ubuntu-latest
  services:
    postgres:
      image: postgres:15-alpine
      env:
        POSTGRES_USER: test
        POSTGRES_PASSWORD: test
        POSTGRES_DB: testdb
      options: >-
        --health-cmd pg_isready
        --health-interval 10s
        --health-timeout 5s
        --health-retries 5
  steps:
    - uses: actions/checkout@v3
    - name: Run failure path tests
      env:
        DATABASE_URL: postgresql://test:test@localhost:5432/testdb
        SECRET_KEY: test-secret-key
      run: |
        cd backend
        python -m pytest tests/test_failure_paths.py -v
```

## Why These Tests Matter

1. **Data Integrity**: Ensures no corrupt or partial data in database
2. **Debugging**: Clear errors make issues easy to diagnose
3. **Audit Trail**: DecisionTrace provides complete history even for failures
4. **Confidence**: Knowing system fails safely enables faster development
5. **Compliance**: Audit trail may be required for research data

## Related Documentation

- [State Transition Validation Guide](STATE_TRANSITION_VALIDATION_GUIDE.md) - Validation of allowed state transitions
- [State Transition Visual Guide](STATE_TRANSITION_VISUAL_GUIDE.md) - Visual diagrams of state flow
- [Base Orchestrator Guide](BASE_ORCHESTRATOR_GUIDE.md) - How orchestrators handle errors
- [Trace Persistence Guide](TRACE_PERSISTENCE_GUIDE.md) - How DecisionTrace works

## Maintenance

### Adding New Failure Tests

When adding new features, add corresponding failure tests:

```python
class TestNewFeatureFailures:
    """Test failures for new feature."""
    
    def test_new_feature_invalid_input(self, db, test_user):
        """
        FAILURE PATH: Invalid input to new feature
        
        Verify:
        - Clear error raised
        - No partial writes
        - Audit trail preserved
        """
        # Get baseline state
        count_before = db.query(NewModel).count()
        
        # Attempt invalid operation
        with pytest.raises(NewFeatureError) as exc_info:
            new_feature_service.do_something(invalid_data)
        
        # Verify error
        assert "expected message" in str(exc_info.value).lower()
        
        # Verify no changes
        count_after = db.query(NewModel).count()
        assert count_before == count_after
        
        print("✅ VERIFIED: New feature fails safely")
```

### Updating Tests

When modifying error handling:
1. Update test to match new error types
2. Verify error messages are still clear
3. Ensure atomicity guarantees still hold
4. Update this documentation

## Summary

The failure path tests are your **safety net**. They ensure that when things go wrong (and they will), the system:
- ✅ Fails cleanly without data corruption
- ✅ Raises clear errors for debugging
- ✅ Preserves audit trail for analysis
- ✅ Maintains database consistency

Run these tests regularly and especially before deploying changes to error handling logic.
