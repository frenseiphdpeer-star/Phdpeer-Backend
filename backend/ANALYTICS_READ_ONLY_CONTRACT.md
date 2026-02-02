# AnalyticsOrchestrator Read-Only Contract

## Overview

The `AnalyticsOrchestrator` enforces a strict **read-only contract** that prevents unintended mutations to upstream state during analytics generation. This ensures data integrity and maintains clear boundaries between analytics generation and state modification.

## Core Principles

### 1. **Analytics is Read-Only**
Analytics generation should never modify the data it analyzes. The orchestrator only reads from source data and writes to new analytics snapshots.

### 2. **Explicit Allowed Models**
The orchestrator explicitly defines which models it can read from and write to, with runtime validation to prevent violations.

### 3. **Operation Tracking**
Every database operation is tracked and validated against the allowed model lists.

### 4. **Automatic Validation**
The read-only contract is automatically validated at the end of every execution pipeline.

## Allowed Operations

### Read Operations (Allowed Models)
The orchestrator can READ from these models only:
- **User**: For user validation
- **CommittedTimeline**: Source timeline data
- **TimelineStage**: Timeline structure
- **TimelineMilestone**: Milestone data
- **ProgressEvent**: User progress events
- **JourneyAssessment**: Health assessments
- **DraftTimeline**: For version extraction

### Write Operations (Allowed Models)
The orchestrator can WRITE to these models only:
- **AnalyticsSnapshot**: New analytics snapshots (never updates existing)
- **DecisionTrace**: Automatic via BaseOrchestrator
- **EvidenceBundle**: Automatic via BaseOrchestrator

### Forbidden Operations
- ❌ Updating any upstream model (CommittedTimeline, ProgressEvent, etc.)
- ❌ Deleting any data
- ❌ Reading from non-analytics models (e.g., QuestionnaireDraft, Opportunity)
- ❌ Writing to upstream models

## Implementation

### Tracked Operations

All database operations go through tracked methods:

```python
# Tracked read - validates and logs the operation
user = orchestrator._tracked_read(User, User.id == user_id).first()

# Tracked write - validates and logs the operation
snapshot = AnalyticsSnapshot(...)
orchestrator._tracked_write(snapshot)
```

### Validation Methods

Three validation methods enforce the contract:

```python
def _validate_read_operation(self, model_name: str):
    """Validate a read operation is allowed."""
    if model_name not in self._ALLOWED_READ_MODELS:
        raise StateMutationInAnalyticsOrchestratorError(...)

def _validate_write_operation(self, model_name: str):
    """Validate a write operation is allowed."""
    if model_name not in self._ALLOWED_WRITE_MODELS:
        raise StateMutationInAnalyticsOrchestratorError(...)

def _validate_read_only_contract(self):
    """Final validation at end of pipeline."""
    # Checks all tracked operations
    # Raises error if any violations detected
```

### Pipeline Integration

The validation is integrated into the execution pipeline:

```python
def _execute_pipeline(self, context: Dict[str, Any]) -> Dict[str, Any]:
    # Reset operation tracking
    self._read_operations = []
    self._write_operations = []
    
    # Step 1-4: Execute pipeline with tracked operations
    ...
    
    # Step 5: Validate read-only contract
    self._validate_read_only_contract()
    
    return result
```

## Error Handling

### StateMutationInAnalyticsOrchestratorError

This exception is raised when the read-only contract is violated:

```python
class StateMutationInAnalyticsOrchestratorError(Exception):
    """
    Exception raised when AnalyticsOrchestrator violates read-only contract.
    
    This indicates the orchestrator attempted to mutate upstream state,
    which violates the analytics-only constraint.
    """
    pass
```

### Error Messages

Error messages include helpful debugging information:

```
AnalyticsOrchestrator attempted to read from non-allowed model: QuestionnaireDraft.
Allowed read models: CommittedTimeline, DraftTimeline, JourneyAssessment, ProgressEvent, TimelineMilestone, TimelineStage, User
```

## Testing

### Test Suite

The test suite in `test_analytics_read_only_contract.py` verifies:

1. **Valid Operations Succeed**: Reading from allowed models works
2. **Invalid Operations Fail**: Reading from non-allowed models raises errors
3. **Write Validation**: Only allowed models can be written to
4. **No Upstream Mutations**: Upstream data is never modified
5. **Multiple Runs**: Contract is maintained across multiple executions
6. **Error Messages**: Violations include helpful information

### Running Tests

```bash
# Run read-only contract tests
pytest tests/test_analytics_read_only_contract.py -v

# Run with coverage
pytest tests/test_analytics_read_only_contract.py --cov=app.orchestrators.analytics_orchestrator -v
```

## Best Practices

### DO ✅

- **Use tracked operations**: Always use `_tracked_read()` and `_tracked_write()`
- **Read from source data**: Freely read from CommittedTimeline, ProgressEvent, etc.
- **Create new snapshots**: Write new AnalyticsSnapshot records only
- **Trust the validation**: Let the automatic validation catch violations

### DON'T ❌

- **Bypass tracked operations**: Never use `db.query()` or `db.add()` directly
- **Update upstream data**: Never modify source data during analytics
- **Add unauthorized models**: Don't add models to allowed lists without review
- **Suppress validation**: Don't try to skip or disable validation

## Common Scenarios

### Adding a New Read Model

If analytics needs to read from a new model:

1. Add the model to `_ALLOWED_READ_MODELS`:
   ```python
   _ALLOWED_READ_MODELS = {
       'User',
       'CommittedTimeline',
       # ... existing models ...
       'NewModel',  # Add here
   }
   ```

2. Update the docstring to document the new model

3. Add tests to verify the model can be read

### Adding a New Write Model

If analytics needs to write to a new model:

1. **Carefully evaluate**: Should analytics really write to this model?
2. Add to `_ALLOWED_WRITE_MODELS` if justified
3. Update documentation and tests
4. Consider: Does this violate the read-only principle?

### Debugging Contract Violations

When you see `StateMutationInAnalyticsOrchestratorError`:

1. **Check the error message**: It tells you which model was accessed
2. **Verify it's intentional**: Is this read/write necessary?
3. **Add to allowed list**: If justified, add to appropriate set
4. **Consider refactoring**: Maybe this operation belongs elsewhere

## Architecture Notes

### Why Explicit Validation?

1. **Data Integrity**: Prevents accidental mutations during analytics
2. **Clear Boundaries**: Makes orchestrator responsibilities explicit
3. **Debugging**: Easy to identify when/where violations occur
4. **Documentation**: Self-documenting code through allowed model lists

### Relationship to Snapshot Immutability

This contract complements AnalyticsSnapshot immutability:
- **Snapshot Immutability**: Individual snapshots can't be modified after creation
- **Read-Only Contract**: The entire analytics pipeline can't modify source data

Together, they ensure:
- Source data remains untouched during analytics
- Analytics snapshots remain immutable after creation
- Clear audit trail of what analytics read and wrote

### Future Enhancements

Potential improvements to the contract enforcement:

1. **Query Analysis**: Parse SQL queries to detect mutations
2. **Transaction Isolation**: Use read-only transactions
3. **Database Triggers**: Database-level prevention of mutations
4. **Metrics**: Track operation counts for monitoring
5. **Caching**: Cache allowed model checks for performance

## Related Documentation

- [ANALYTICS_SNAPSHOT_IMMUTABILITY.md](ANALYTICS_SNAPSHOT_IMMUTABILITY.md): Snapshot immutability rules
- [BASE_ORCHESTRATOR_GUIDE.md](BASE_ORCHESTRATOR_GUIDE.md): Base orchestrator patterns
- [TRACE_PERSISTENCE_GUIDE.md](TRACE_PERSISTENCE_GUIDE.md): Decision tracing

## Summary

The read-only contract is a critical architectural constraint that:
- ✅ Prevents unintended state mutations during analytics
- ✅ Makes data flow explicit and auditable
- ✅ Provides clear error messages when violated
- ✅ Is automatically validated on every execution
- ✅ Is thoroughly tested with comprehensive test suite

**Key Takeaway**: Analytics should NEVER modify the data it analyzes. The read-only contract enforces this principle at runtime.
