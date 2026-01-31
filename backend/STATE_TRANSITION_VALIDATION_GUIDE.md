# State Transition Validation Guide

## Overview

This document describes the comprehensive state transition validation system for the PhD tracking platform. The system ensures data integrity by validating all allowed state transitions and preventing disallowed ones with clear error messages.

## State Definitions

The system operates on a five-state lifecycle:

- **S0: Raw Input** - Initial data collection (questionnaire responses, document uploads)
- **S1: Baseline** - Structured PhD profile with program requirements  
- **S2: Draft Timeline** - Ed

itable timeline with stages and milestones
- **S3: Committed Timeline** - Immutable, frozen timeline (production state)
- **S4: Progress Tracking** - Active milestone completion and progress events

## State Transition Matrix

### ✅ Allowed Transitions

| From | To | Description | Validation |
|------|----|-----------|-----------| 
| S0 | S1 | Raw input → Baseline | All required fields provided |
| S1 | S2 | Baseline → Draft timeline | Baseline exists and valid |
| S2 | S3 | Draft → Committed timeline | Has stages, milestones, ownership |
| S3 | S4 | Committed → Progress tracking | Milestone belongs to committed timeline |

### ❌ Disallowed Transitions

| From | To | Description | Error Type |
|------|----|-----------| -----------|
| S2 | S4 | Progress without commit | `ProgressEventWithoutMilestoneError` |
| S0/S1 | S3 | Commit without draft | `CommittedTimelineWithoutDraftError` |
| S2 | S3 (x2) | Double commit | `CommittedTimelineWithoutDraftError` |
| Any | Analytics | Analytics without committed timeline | `AnalyticsOrchestratorError` |
| S2 (empty) | S3 | Commit empty timeline | `TimelineOrchestratorError` |
| S2 (no milestones) | S3 | Commit without milestones | `TimelineOrchestratorError` |
| Other user's S2 | S3 | Cross-user commit | `CommittedTimelineWithoutDraftError` |

## Validation Locations

### 1. Progress Tracking Validation
**File**: [app/utils/invariants.py](app/utils/invariants.py#L207)

```python
def check_progress_event_has_milestone(
    db: Session,
    milestone_id: UUID,
    user_id: UUID
) -> None:
    """
    Invariant: No progress event without committed milestone.
    
    Ensures milestone belongs to a CommittedTimeline before
    allowing progress tracking.
    """
```

**Error Message**:
```
Cannot create ProgressEvent: Milestone {milestone_id} not in CommittedTimeline
Hint: Progress can only be tracked on committed timelines
```

### 2. Timeline Commitment Validation
**File**: [app/utils/invariants.py](app/utils/invariants.py#L110)

```python
def check_committed_timeline_has_draft(
    db: Session,
    draft_timeline_id: Optional[UUID],
    user_id: UUID
) -> None:
    """
    Invariant: No committed timeline without draft.
    
    Every CommittedTimeline must originate from a DraftTimeline.
    """
```

**Error Messages**:
- Missing draft: `"Cannot commit timeline: DraftTimeline {id} not found or not owned by user"`
- Already committed: `"Cannot commit timeline: DraftTimeline {id} already committed as {committed_id}"`

### 3. Analytics Generation Validation
**File**: [app/orchestrators/analytics_orchestrator.py](app/orchestrators/analytics_orchestrator.py#L168)

```python
# Invariant check: No analytics without committed timeline
from app.utils.invariants import check_analytics_has_committed_timeline
check_analytics_has_committed_timeline(
    db=self.db,
    user_id=user_id,
    timeline_id=timeline_id
)
```

**Error Message**:
```
No committed timeline found for user {user_id}
```

### 4. Timeline Completeness Validation
**File**: [app/orchestrators/timeline_orchestrator.py](app/orchestrators/timeline_orchestrator.py#L889)

```python
# Validate stages exist
draft_stages = self.db.query(TimelineStage).filter(
    TimelineStage.draft_timeline_id == draft_timeline_id
).all()

if not draft_stages:
    raise TimelineOrchestratorError(
        f"Cannot commit timeline: no stages found for draft timeline {draft_timeline_id}"
    )

# Validate milestones exist
for stage in draft_stages:
    milestones = self.db.query(TimelineMilestone).filter(
        TimelineMilestone.timeline_stage_id == stage.id
    ).all()
    
    if not milestones:
        raise TimelineOrchestratorError(
            f"Cannot commit timeline: no milestones found for stage {stage.title}"
        )
```

## Test Suite

### File: [tests/test_state_transitions_validation.py](tests/test_state_transitions_validation.py)

The test suite provides comprehensive validation of all state transitions:

#### Test Classes

1. **TestAllowedTransitions**
   - `test_s0_to_s1_raw_input_to_baseline()` - Validates baseline creation
   - `test_s1_to_s2_baseline_to_draft_timeline()` - Validates draft creation
   - `test_s2_to_s3_draft_to_committed_timeline()` - Validates timeline commitment
   - `test_s3_to_s4_committed_to_progress_tracking()` - Validates progress tracking
   - `test_complete_allowed_pipeline_s0_to_s4()` - End-to-end valid pipeline

2. **TestDisallowedTransitions**
   - `test_progress_without_committed_timeline_fails()` - S2 → S4 blocked
   - `test_commit_without_draft_fails()` - S0/S1 → S3 blocked
   - `test_double_commit_fails()` - Immutability enforced
   - `test_analytics_without_committed_timeline_fails()` - Analytics blocked
   - `test_commit_empty_timeline_fails()` - Empty timeline blocked
   - `test_commit_timeline_without_milestones_fails()` - Incomplete timeline blocked
   - `test_commit_someone_elses_timeline_fails()` - Ownership enforced

3. **TestImmutabilityEnforcement**
   - `test_committed_timeline_is_immutable()` - No edit methods exist
   - `test_draft_inactive_after_commit()` - Draft marked inactive

4. **TestErrorMessagesClarity**
   - `test_error_messages_are_informative()` - All errors are clear and actionable

### Running Tests

**Note**: Tests require PostgreSQL (not SQLite) due to UUID type requirements.

```bash
# Set environment variables
export DATABASE_URL="postgresql://user:password@localhost/test_db"
export SECRET_KEY="test-secret-key"

# Run all state transition tests
cd backend
python -m pytest tests/test_state_transitions_validation.py -v

# Run specific test class
python -m pytest tests/test_state_transitions_validation.py::TestAllowedTransitions -v

# Run specific test
python -m pytest tests/test_state_transitions_validation.py::TestDisallowedTransitions::test_double_commit_fails -v
```

## Error Handling Standards

### Error Message Format

All state transition errors follow this format:

```
[OPERATION]: [WHAT_WENT_WRONG]
Details: {context_dict}
Hint: [HOW_TO_FIX]
```

### Example Error Messages

1. **Progress without committed timeline**:
   ```python
   ProgressEventWithoutMilestoneError(
       "Cannot create ProgressEvent: Milestone {id} not in CommittedTimeline",
       details={
           "user_id": str(user_id),
           "milestone_id": str(milestone_id),
           "hint": "Progress can only be tracked on committed timelines"
       }
   )
   ```

2. **Commit without draft**:
   ```python
   CommittedTimelineWithoutDraftError(
       "Cannot commit timeline: DraftTimeline {id} not found or not owned by user {user_id}",
       details={
           "user_id": str(user_id),
           "draft_timeline_id": str(draft_timeline_id),
           "exists": False
       }
   )
   ```

3. **Double commit**:
   ```python
   CommittedTimelineWithoutDraftError(
       "Cannot commit timeline: DraftTimeline {id} already committed as {committed_id}",
       details={
           "user_id": str(user_id),
           "draft_timeline_id": str(draft_timeline_id),
           "existing_committed_id": str(existing_commit.id),
           "already_committed": True
       }
   )
   ```

## Immutability Guarantees

### Committed Timeline Immutability

Once a timeline transitions from S2 (draft) to S3 (committed), it becomes immutable:

1. **Draft marked inactive**:
   ```python
   draft_timeline.is_active = False
   ```

2. **No update methods**:
   - `TimelineOrchestrator` has no `update_committed_timeline()` method
   - UI prevents editing of committed timelines
   - All edits must create new draft → commit flow

3. **Audit trail preserved**:
   - Original draft timeline retained
   - `CommittedTimeline.draft_timeline_id` maintains lineage
   - `TimelineEditHistory` table tracks all changes

### Progress Event Immutability

Progress events are append-only:

```python
# ProgressEvent is NEVER updated or deleted
# Only new events are created
progress_event = ProgressEvent(
    user_id=user_id,
    milestone_id=milestone_id,
    event_type="milestone_completed",
    # ... immutable from creation
)
db.add(progress_event)  # Append only
```

## Integration Points

### 1. Timeline Orchestrator
**File**: [app/orchestrators/timeline_orchestrator.py](app/orchestrators/timeline_orchestrator.py)

- `create_draft_timeline()` - S1 → S2 transition
- `commit_timeline()` - S2 → S3 transition with full validation

### 2. Progress Service
**File**: [app/services/progress_service.py](app/services/progress_service.py)

- `mark_milestone_completed()` - S3 → S4 transition with invariant checks

### 3. Analytics Orchestrator
**File**: [app/orchestrators/analytics_orchestrator.py](app/orchestrators/analytics_orchestrator.py)

- `run()` - Requires S3 (committed timeline) before generating analytics
- `generate()` - Same requirement with additional date range parameters

### 4. Invariant Checker
**File**: [app/utils/invariants.py](app/utils/invariants.py)

Central validation logic for all state transitions:
- `check_committed_timeline_has_draft()`
- `check_progress_event_has_milestone()`
- `check_analytics_has_committed_timeline()`

## Frontend Validation

### File: [frontend/VALIDATION_GUIDE.md](../frontend/VALIDATION_GUIDE.md)

The frontend implements complementary validation:

1. **State Transition Matrix** (page 492)
   - Visual representation of allowed/disallowed transitions
   - UI-level guardrails prevent invalid actions

2. **Guardrails by Flow** (pages 143-171)
   - Timeline Commit: Cannot commit empty, must have stages/milestones
   - Progress Tracking: Can only mark milestones from committed timelines
   - Analytics: Requires committed timeline

3. **Immutability Enforcement** (page 510)
   - Committed timelines show read-only UI
   - No edit buttons on committed content
   - New version requires new draft → commit flow

## Monitoring & Observability

### Decision Traces

All state transitions create `DecisionTrace` records:

```python
class DecisionTrace(Base):
    """Audit trail for all orchestrator decisions."""
    orchestrator_name = Column(String)  # Which orchestrator
    operation = Column(String)          # What operation
    input_data = Column(JSON)           # Input parameters
    output_data = Column(JSON)          # Result
    steps = Column(JSON)                # Step-by-step trace
    evidence_bundle = Column(JSON)      # Supporting evidence
```

### Evidence Bundles

Each transition collects evidence:

```python
# Example: Timeline commitment evidence
{
    "draft_timeline_data": {
        "id": "uuid",
        "title": "PhD Timeline",
        "baseline_id": "uuid",
        "is_active": true
    },
    "validation_results": {
        "has_stages": true,
        "has_milestones": true,
        "stage_count": 4,
        "milestone_count": 12
    }
}
```

## Best Practices

### 1. Always Use Orchestrators

✅ **Correct**:
```python
orchestrator = TimelineOrchestrator(db=db, user_id=user_id)
committed_id = orchestrator.commit_timeline(draft_id, user_id)
```

❌ **Incorrect**:
```python
# Don't bypass orchestrator
committed = CommittedTimeline(draft_timeline_id=draft_id, ...)
db.add(committed)
```

### 2. Check Invariants Early

```python
# Validate state before expensive operations
check_committed_timeline_has_draft(db, draft_id, user_id)

# Then proceed with operation
result = expensive_operation()
```

### 3. Provide Clear Error Context

```python
raise StateTransitionError(
    "Cannot perform X because Y",
    details={
        "current_state": state,
        "attempted_transition": transition,
        "reason": reason,
        "hint": "How to fix this"
    }
)
```

### 4. Test Both Happy and Sad Paths

```python
def test_allowed_transition():
    """Test S2 → S3 works when valid."""
    result = orchestrator.commit_timeline(draft_id, user_id)
    assert result is not None

def test_disallowed_transition():
    """Test S2 → S3 fails when invalid."""
    with pytest.raises(CommittedTimelineWithoutDraftError) as exc:
        orchestrator.commit_timeline(fake_id, user_id)
    
    assert "not found" in str(exc.value)
```

## Debugging State Transition Issues

### 1. Check Decision Traces

```sql
SELECT * FROM decision_traces 
WHERE orchestrator_name = 'timeline_orchestrator'
  AND operation = 'commit_timeline'
ORDER BY created_at DESC 
LIMIT 10;
```

### 2. Verify State

```python
# Check draft exists and is active
draft = db.query(DraftTimeline).get(draft_id)
print(f"Draft active: {draft.is_active}")

# Check if already committed
existing = db.query(CommittedTimeline).filter(
    CommittedTimeline.draft_timeline_id == draft_id
).first()
print(f"Already committed: {existing is not None}")

# Check milestone's timeline
milestone = db.query(TimelineMilestone).get(milestone_id)
stage = db.query(TimelineStage).get(milestone.timeline_stage_id)
print(f"Milestone in committed timeline: {stage.committed_timeline_id is not None}")
```

### 3. Common Issues

| Issue | Symptom | Solution |
|-------|---------|----------|
| Progress fails | `ProgressEventWithoutMilestoneError` | Ensure milestone is in committed timeline, not draft |
| Double commit | `already committed` error | Check if draft was previously committed |
| Empty timeline | `no stages found` error | Add stages and milestones before committing |
| Wrong user | `not found or not owned` error | Verify user_id matches draft owner |

## Summary

The state transition validation system ensures:

1. **Data Integrity**: All transitions follow S0 → S1 → S2 → S3 → S4 flow
2. **Clear Errors**: Every invalid transition has specific, actionable error message
3. **Immutability**: Committed timelines and progress events are append-only
4. **Audit Trail**: All transitions logged in DecisionTrace with evidence
5. **Defense in Depth**: Validation at multiple layers (invariants, orchestrators, services, frontend)

The system makes invalid states **impossible**, not just **hard**.
