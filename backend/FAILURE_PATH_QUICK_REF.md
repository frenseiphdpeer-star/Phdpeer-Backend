# Failure Path Tests - Quick Reference

## 🎯 Purpose
Deliberately break the system to verify proper error handling, atomicity, and audit trails.

## 📊 Test Coverage

| Scenario | Test | Verifies |
|----------|------|----------|
| **Commit without draft** | `TestCommitFailures::test_commit_without_draft_no_partial_writes` | No CommittedTimeline created |
| **Commit empty timeline** | `TestCommitFailures::test_commit_empty_timeline_no_partial_writes` | Error before any writes |
| **Double commit** | `TestCommitFailures::test_double_commit_preserves_first_commit` | First commit preserved |
| **Generate without baseline** | `TestTimelineGenerationFailures::test_generate_timeline_without_baseline` | No DraftTimeline created |
| **Generate wrong user** | `TestTimelineGenerationFailures::test_generate_timeline_wrong_user` | Cross-user prevented |
| **Mark non-existent milestone** | `TestProgressTrackingFailures::test_mark_progress_on_nonexistent_milestone` | No ProgressEvent created |
| **Mark draft milestone** | `TestProgressTrackingFailures::test_mark_progress_on_draft_milestone` | Committed-only enforced |
| **Mark wrong user milestone** | `TestProgressTrackingFailures::test_mark_progress_wrong_user` | Ownership enforced |
| **Analytics without timeline** | `TestAnalyticsFailures::test_analytics_without_committed_timeline` | Clear error raised |
| **Analytics invalid ID** | `TestAnalyticsFailures::test_analytics_with_invalid_timeline_id` | No snapshot created |
| **Submit questionnaire twice** | `TestQuestionnaireFailures::test_submit_questionnaire_twice_same_request_id` | **Idempotency works** |
| **Submit incomplete** | `TestQuestionnaireFailures::test_submit_incomplete_questionnaire` | Validation catches |
| **Trace on failure** | `TestDecisionTraceOnFailure::test_decision_trace_written_on_commit_failure` | **Audit trail preserved** |
| **Rollback verification** | `TestAtomicityAndRollback::test_partial_timeline_commit_rolls_back` | **Complete rollback** |
| **Atomicity check** | `TestAtomicityAndRollback::test_progress_tracking_atomicity` | **All-or-nothing** |
| **Silent failure check** | `TestSilentFailurePrevention::test_no_silent_failure_on_*` | **All errors raised** |

**Total: 19 tests across 8 categories**

## ⚡ Quick Start

### One Command (requires docker-compose)
```bash
cd backend
./quick_test_failures.sh
```

### Manual Run
```bash
# 1. Start PostgreSQL
docker-compose up -d postgres

# 2. Set environment
export DATABASE_URL='postgresql://postgres:password@localhost:5432/phd_timeline_db'
export SECRET_KEY='test-secret-key'

# 3. Run tests
cd backend
python -m pytest tests/test_failure_paths.py -v
```

## ⚠️ Requirements

**MUST USE POSTGRESQL** - SQLite incompatible (UUID types)

If you see:
```
CompileError: Compiler can't render element of type UUID
```
→ You're using SQLite. Switch to PostgreSQL.

## 🔍 What Gets Verified

Every test checks:

✅ **No Partial Writes**
```python
count_before = db.query(Model).count()
# ... attempt operation ...
count_after = db.query(Model).count()
assert count_before == count_after  # Nothing created!
```

✅ **Loud Failures**
```python
with pytest.raises(SpecificError) as exc_info:
    service.do_something_invalid(...)
assert "expected keyword" in str(exc_info.value).lower()
```

✅ **DecisionTrace Preserved**
```python
# Even on failure, audit trail is written
traces = db.query(DecisionTrace).all()
# Traces contain error information
```

✅ **Atomicity**
```python
# Both succeed together or both fail
milestone.is_completed  # Updated
progress_event  # Created
# Or both unchanged on failure
```

## 📝 Running Specific Tests

```bash
# Single test class
pytest tests/test_failure_paths.py::TestCommitFailures -v

# Single test
pytest tests/test_failure_paths.py::TestCommitFailures::test_commit_without_draft_no_partial_writes -v

# Stop on first failure
pytest tests/test_failure_paths.py -v -x

# Extra verbose
pytest tests/test_failure_paths.py -v -s --tb=long
```

## 🐛 Troubleshooting

| Error | Solution |
|-------|----------|
| `CompileError: can't render UUID` | Using SQLite → switch to PostgreSQL |
| `ValidationError: DATABASE_URL required` | Set: `export DATABASE_URL='postgresql://...'` |
| Connection refused | Start PostgreSQL: `docker-compose up -d postgres` |
| Wrong password | Check credentials in docker-compose.yml |
| Tests hang | Check PostgreSQL is healthy: `docker-compose ps` |

## 📁 Files

| File | Purpose |
|------|---------|
| `tests/test_failure_paths.py` | Main test suite (920+ lines) |
| `run_failure_path_tests.sh` | Test runner with validation |
| `quick_test_failures.sh` | One-command setup + run |
| `FAILURE_PATH_TESTING_GUIDE.md` | Comprehensive documentation |
| `FAILURE_PATH_TESTS_SUMMARY.md` | Detailed summary |

## 🎨 Success Output

```
╔════════════════════════════════════════════════════════════════════════════╗
║                    FAILURE PATH TEST SUITE                                 ║
╚════════════════════════════════════════════════════════════════════════════╝

✓ PostgreSQL DATABASE_URL detected
✓ Environment configured

tests/test_failure_paths.py::TestCommitFailures::... PASSED
✅ VERIFIED: No partial writes on commit failure

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ ALL FAILURE PATH TESTS PASSED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Verified:
  ✓ No partial writes on failures
  ✓ All errors raised loudly
  ✓ DecisionTrace audit trail preserved
  ✓ Database rollback working
  ✓ System remains consistent
```

## 🔗 Related

- [tests/test_state_transitions_validation.py](tests/test_state_transitions_validation.py) - Allowed transitions
- [app/utils/invariants.py](app/utils/invariants.py) - Core validation
- [STATE_TRANSITION_VALIDATION_GUIDE.md](STATE_TRANSITION_VALIDATION_GUIDE.md) - State flow

## 💡 Key Insight

These tests are your **safety net** - they prove the system fails cleanly without data corruption or silent errors. Essential for research data integrity.
