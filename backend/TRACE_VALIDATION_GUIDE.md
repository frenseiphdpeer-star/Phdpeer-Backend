# DecisionTrace Validation Utility

## Overview

Validation utility that ensures every orchestrator execution produces a complete `DecisionTrace` with all required fields. Detects state mutations that occur without corresponding audit trails.

## Purpose

- **Audit Compliance**: Verify all operations are properly traced
- **Debugging**: Identify operations that failed to record decisions
- **Data Integrity**: Ensure state changes have corresponding evidence
- **Testing**: Validate orchestrator implementations create proper traces

## Usage

### In Tests

```python
from app.utils.trace_validation import (
    assert_execution_has_complete_trace,
    ensure_no_untraced_mutations,
    validate_trace_completeness,
)

def test_orchestrator_creates_trace(db):
    """Verify orchestrator creates complete trace."""
    orchestrator = BaselineOrchestrator(db)
    
    request_id = "test-request-123"
    result = orchestrator.execute(request_id, input_data={...})
    
    # Assert trace exists and is complete
    trace = assert_execution_has_complete_trace(
        db,
        request_id=request_id,
        orchestrator_name="baseline_orchestrator"
    )
    
    assert trace.status == "COMPLETED"
    assert trace.output_hash is not None
    assert len(trace.execution_steps) > 0
```

### In Production Monitoring

```python
from datetime import datetime, timedelta
from app.utils.trace_validation import (
    ensure_no_untraced_mutations,
    validate_all_traces_complete,
    get_orchestrator_execution_summary,
)

# Check for untraced mutations in last hour
one_hour_ago = datetime.utcnow() - timedelta(hours=1)

try:
    ensure_no_untraced_mutations(db, since=one_hour_ago)
    print("✓ All state changes properly traced")
except StateChangeWithoutTraceError as e:
    logger.error(f"Untraced mutations detected: {e}")
    alert_ops_team(e)

# Get execution summary
summary = get_orchestrator_execution_summary(
    db,
    orchestrator_name="timeline_orchestrator",
    since=one_hour_ago
)
print(f"Executions: {summary['total_executions']}")
print(f"Success rate: {summary['completed'] / summary['total_executions']:.1%}")
print(f"Avg duration: {summary['avg_duration_ms']:.0f}ms")
```

### In Integration Tests

```python
from app.utils.trace_validation import validate_state_changes_have_traces

def test_full_pipeline_tracing(db):
    """Verify entire pipeline produces traces for all state changes."""
    start_time = datetime.utcnow()
    
    # Run full pipeline
    baseline_id = create_baseline(...)
    draft_id = generate_timeline(baseline_id)
    committed_id = commit_timeline(draft_id)
    
    # Verify all state changes have traces
    result = validate_state_changes_have_traces(
        db,
        since=start_time,
        models_to_check=[Baseline, DraftTimeline, CommittedTimeline]
    )
    
    assert result["violations"] == []
    print(f"All {sum(r['total_records'] for r in result['summary'].values())} records traced")
```

## Validation Checks

### Required DecisionTrace Fields

Every `DecisionTrace` must contain:

1. **orchestrator_name** (string)
   - Name of the orchestrator that executed
   - Example: `"baseline_orchestrator"`, `"timeline_orchestrator"`

2. **request_id** (string)
   - Unique identifier for the request (idempotency key)
   - Example: `"baseline-create-abc123"`

3. **execution_steps** (list of dicts)
   - Sequential list of execution steps
   - Each step must have:
     - `step_number`: Integer starting from 1
     - `action`: Description of the step
     - `status`: "completed", "failed", etc.
   - Step numbers must be sequential (1, 2, 3, ...)

4. **input_hash** (string)
   - SHA-256 hash of input data
   - Used for cache key validation

5. **output_hash** (string, if COMPLETED)
   - SHA-256 hash of output data
   - Required for successfully completed operations

6. **error_message** (string, if FAILED)
   - Error description for failed operations
   - Required for operations with status="FAILED"

7. **started_at** (datetime)
   - Timestamp when execution started
   - Must be present for all traces

8. **completed_at** (datetime, if finished)
   - Timestamp when execution finished
   - Required for COMPLETED or FAILED status

9. **duration_ms** (integer, if finished)
   - Execution time in milliseconds
   - Required for completed/failed traces
   - Must be non-negative

### State Change Validation

The utility checks that every database record creation has a corresponding:
1. **IdempotencyKey** - Request tracking entry
2. **DecisionTrace** - Complete audit trail

Models checked by default:
- `Baseline` - Initial program assessment
- `DraftTimeline` - Generated timelines
- `CommittedTimeline` - Finalized timelines

## API Reference

### Core Validation Functions

#### `validate_trace_completeness(trace: DecisionTrace)`
Validates a single trace has all required fields.

```python
trace = db.query(DecisionTrace).filter_by(request_id="abc").first()
validate_trace_completeness(trace)  # Raises IncompleteTraceError if invalid
```

#### `validate_trace_for_request(db, request_id, orchestrator_name)`
Validates trace exists and is complete for a specific request.

```python
trace = validate_trace_for_request(
    db,
    request_id="timeline-gen-123",
    orchestrator_name="timeline_orchestrator"
)
```

#### `validate_state_changes_have_traces(db, since, models_to_check=None)`
Validates all state changes since timestamp have traces.

```python
result = validate_state_changes_have_traces(
    db,
    since=datetime.utcnow() - timedelta(hours=1),
    models_to_check=[Baseline, DraftTimeline]
)

# Returns:
# {
#     "timestamp": <datetime>,
#     "models_checked": ["baselines", "draft_timelines"],
#     "violations": [],  # Empty if all traced
#     "summary": {
#         "baselines": {"total_records": 5, "records_without_traces": 0},
#         "draft_timelines": {"total_records": 3, "records_without_traces": 0}
#     }
# }
```

#### `validate_all_traces_complete(db, orchestrator_name=None, since=None)`
Validates all traces in database are complete.

```python
result = validate_all_traces_complete(
    db,
    orchestrator_name="timeline_orchestrator",
    since=datetime.utcnow() - timedelta(days=1)
)

# Returns:
# {
#     "total_traces": 50,
#     "incomplete_traces": [],  # Empty if all complete
#     "errors": {}
# }
```

### Utility Functions

#### `validate_step_order(execution_steps: List[Dict])`
Validates step numbers are sequential.

```python
steps = [
    {"step_number": 1, "action": "validate"},
    {"step_number": 2, "action": "execute"},
    {"step_number": 3, "action": "persist"},
]
validate_step_order(steps)  # OK

steps_bad = [
    {"step_number": 1, "action": "first"},
    {"step_number": 3, "action": "skip_two"},  # ERROR: skipped 2
]
validate_step_order(steps_bad)  # Raises TraceValidationError
```

#### `validate_hash_consistency(input_data, stored_input_hash)`
Validates stored hash matches computed hash.

```python
input_data = {"baseline_id": "123", "user_id": "456"}
validate_hash_consistency(input_data, trace.input_hash)
```

#### `get_orchestrator_execution_summary(db, orchestrator_name, since=None)`
Get execution statistics with validation.

```python
summary = get_orchestrator_execution_summary(
    db,
    orchestrator_name="timeline_orchestrator"
)

# Returns:
# {
#     "orchestrator": "timeline_orchestrator",
#     "total_executions": 100,
#     "completed": 95,
#     "failed": 5,
#     "processing": 0,
#     "avg_duration_ms": 450.2,
#     "incomplete_traces": 0,
#     "traces_with_errors": []
# }
```

### Convenience Functions

#### `assert_execution_has_complete_trace(db, request_id, orchestrator_name)`
For use in tests - raises `AssertionError` if trace invalid.

```python
def test_baseline_creates_trace():
    result = orchestrator.execute(request_id="test-123", ...)
    
    # Will raise AssertionError with details if trace incomplete
    assert_execution_has_complete_trace(
        db,
        request_id="test-123",
        orchestrator_name="baseline_orchestrator"
    )
```

#### `ensure_no_untraced_mutations(db, since, models=None)`
For production monitoring - raises `StateChangeWithoutTraceError` if violations found.

```python
# In periodic monitoring job
try:
    ensure_no_untraced_mutations(db, since=last_check_time)
except StateChangeWithoutTraceError as e:
    alert_ops_team(str(e))
```

## Exception Types

### `TraceValidationError`
Base exception for all validation errors.

### `IncompleteTraceError`
Raised when a trace is missing required fields or has invalid data.

```python
# Example error message:
# DecisionTrace validation failed for request-123:
#   - Missing or invalid orchestrator_name
#   - Step 2 has incorrect step_number: 3
#   - Completed trace missing output_hash
```

### `StateChangeWithoutTraceError`
Raised when state mutations occur without corresponding traces.

```python
# Example error message:
# Found 2 state changes without traces:
#   - baselines record abc-123 (created 2026-01-31T10:30:00)
#   - draft_timelines record def-456 (created 2026-01-31T10:35:00)
```

## Integration with Orchestrators

All orchestrators extending `BaseOrchestrator` automatically create traces via:

```python
class MyOrchestrator(BaseOrchestrator):
    def _execute_pipeline(self, context):
        # Each step is automatically traced
        with self._trace_step("validate_input"):
            # validation logic
            pass
        
        with self._trace_step("execute_logic"):
            # execution logic
            pass
        
        with self._trace_step("persist_results"):
            # persistence logic
            pass
        
        # BaseOrchestrator automatically:
        # 1. Records all steps
        # 2. Computes input/output hashes
        # 3. Persists DecisionTrace
        # 4. Handles errors and records failure reasons
```

## Best Practices

### 1. Always Validate After Execution

```python
result = orchestrator.execute(request_id, input_data)
trace = assert_execution_has_complete_trace(db, request_id, orchestrator_name)
assert trace.status == "COMPLETED"
```

### 2. Use in CI/CD Pipeline

```python
# In integration test suite
@pytest.mark.integration
def test_all_traces_complete():
    """Verify all test executions produced complete traces."""
    validate_all_traces_complete(db)
```

### 3. Monitor Production Continuously

```python
# In scheduled monitoring job (every 5 minutes)
def check_trace_health():
    five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
    
    try:
        ensure_no_untraced_mutations(db, since=five_minutes_ago)
    except StateChangeWithoutTraceError as e:
        metrics.increment("untraced_mutations")
        logger.error(f"Trace validation failed: {e}")
```

### 4. Add to Pre-Deployment Checks

```bash
# In deployment script
python -m pytest tests/test_trace_validation.py -v
if [ $? -ne 0 ]; then
    echo "❌ Trace validation failed - deployment blocked"
    exit 1
fi
```

## Troubleshooting

### Incomplete Trace Errors

**Problem:** `IncompleteTraceError: Missing output_hash`

**Solution:** Ensure orchestrator properly serializes results:
```python
def _serialize_result(self, result):
    # Must return dict with all relevant fields
    return {"key": "value"}
```

**Problem:** `Step order violation: expected step 2, found step 3`

**Solution:** Ensure steps use sequential numbering:
```python
# WRONG
with self._trace_step("step1"):  # Creates step 1
    pass
# Missing step 2!
with self._trace_step("step3"):  # Tries to create step 3
    pass

# CORRECT
with self._trace_step("step1"):  # Creates step 1
    pass
with self._trace_step("step2"):  # Creates step 2
    pass
with self._trace_step("step3"):  # Creates step 3
    pass
```

### State Change Without Trace Errors

**Problem:** `StateChangeWithoutTraceError` for legitimate operations

**Cause:** Record was created outside orchestrator framework

**Solution:** Always use orchestrators for state changes:
```python
# WRONG - Direct database manipulation
baseline = Baseline(...)
db.add(baseline)
db.commit()

# CORRECT - Use orchestrator
orchestrator = BaselineOrchestrator(db)
result = orchestrator.execute(request_id, input_data)
```

## Performance Considerations

- **Batch Validation**: Use `validate_all_traces_complete()` for periodic checks, not per-request
- **Time Windows**: Limit validation to recent time windows (e.g., last hour) in production
- **Index Usage**: Ensure `DecisionTrace` and `IdempotencyKey` tables have indexes on:
  - `request_id`
  - `orchestrator_name`
  - `started_at`
  - `user_id`

## See Also

- [DecisionTrace Model](../app/models/idempotency.py)
- [BaseOrchestrator](../app/orchestrators/base.py)
- [Idempotency Testing](../tests/test_idempotency.py)
- [Trace Validation Tests](../tests/test_trace_validation.py)
