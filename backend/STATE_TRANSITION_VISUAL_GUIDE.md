# State Transition Validation - Visual Guide

## State Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    PhD TRACKING STATE MACHINE                     │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐
│   S0: Raw    │  Initial data collection
│    Input     │  (Questionnaire, Documents)
└──────┬───────┘
       │ ✅ ALLOWED: Create baseline
       │ Validation: Required fields present
       ▼
┌──────────────┐
│ S1: Baseline │  Structured PhD profile
│    Profile   │  (Program, Institution, Duration)
└──────┬───────┘
       │ ✅ ALLOWED: Generate draft timeline
       │ Validation: Baseline exists and valid
       ▼
┌──────────────┐
│  S2: Draft   │  Editable timeline
│   Timeline   │  (Stages, Milestones)
└──────┬───────┘
       │ ✅ ALLOWED: Commit timeline
       │ Validation: Has stages, milestones, ownership
       │ ❌ BLOCKED: Double commit (immutability)
       │ ❌ BLOCKED: Commit empty/incomplete timeline
       │ ❌ BLOCKED: Track progress (skip S3)
       ▼
┌──────────────┐
│S3: Committed │  Immutable frozen timeline
│   Timeline   │  (Production state)
└──────┬───────┘
       │ ✅ ALLOWED: Track progress
       │ Validation: Milestone belongs to this timeline
       │ ❌ BLOCKED: Edit timeline (immutable)
       │ ❌ BLOCKED: Uncommit
       ▼
┌──────────────┐
│S4: Progress  │  Active tracking
│   Tracking   │  (Milestone completion events)
└──────────────┘
```

## Transition Validation Matrix

```
         │ S0 │ S1 │ S2 │ S3 │ S4 │ Analytics │
─────────┼────┼────┼────┼────┼────┼───────────┤
FROM S0  │  - │ ✅ │ ❌ │ ❌ │ ❌ │    ❌     │
FROM S1  │  - │  - │ ✅ │ ❌ │ ❌ │    ❌     │
FROM S2  │  - │  - │  - │ ✅ │ ❌ │    ❌     │
FROM S3  │  - │  - │  - │ ❌ │ ✅ │    ✅     │
FROM S4  │  - │  - │  - │  - │  - │    ✅     │

Legend:
✅ = Allowed transition
❌ = Blocked transition (fails with clear error)
-  = Not applicable
```

## Error Types by Transition

```
┌─────────────────────────────────────────────────────────────────┐
│                    DISALLOWED TRANSITIONS                        │
└─────────────────────────────────────────────────────────────────┘

❌ S2 → S4 (Skip commit)
   ├─ Error: ProgressEventWithoutMilestoneError
   ├─ Message: "Milestone not in CommittedTimeline"
   └─ Fix: Commit timeline first (S2 → S3), then track progress

❌ S0/S1 → S3 (Skip draft)
   ├─ Error: CommittedTimelineWithoutDraftError
   ├─ Message: "DraftTimeline not found"
   └─ Fix: Create draft timeline first (S1 → S2)

❌ S2 → S3 → S3 (Double commit)
   ├─ Error: CommittedTimelineWithoutDraftError
   ├─ Message: "DraftTimeline already committed"
   └─ Fix: Use existing committed timeline or create new draft

❌ Any → Analytics (No committed timeline)
   ├─ Error: AnalyticsOrchestratorError
   ├─ Message: "No committed timeline found"
   └─ Fix: Commit a timeline first (S2 → S3)

❌ S2 (empty) → S3 (Incomplete timeline)
   ├─ Error: TimelineOrchestratorError
   ├─ Message: "No stages found"
   └─ Fix: Add stages and milestones to draft

❌ S2 (no milestones) → S3 (Missing milestones)
   ├─ Error: TimelineOrchestratorError
   ├─ Message: "No milestones found for stage"
   └─ Fix: Add at least one milestone per stage

❌ Other User's S2 → S3 (Ownership violation)
   ├─ Error: CommittedTimelineWithoutDraftError
   ├─ Message: "Not owned by user"
   └─ Fix: Users can only commit their own timelines
```

## Validation Checkpoints

```
┌─────────────────────────────────────────────────────────────────┐
│               VALIDATION AT EACH TRANSITION                      │
└─────────────────────────────────────────────────────────────────┘

S0 → S1 (Create Baseline)
├─ ✓ User exists
├─ ✓ Required fields present
│   ├─ program_name
│   ├─ institution
│   ├─ field_of_study
│   └─ start_date
└─ ✓ Dates are valid

S1 → S2 (Create Draft)
├─ ✓ Baseline exists
├─ ✓ Baseline belongs to user
├─ ✓ User owns baseline
└─ → Draft timeline created (editable)

S2 → S3 (Commit Timeline)
├─ ✓ Draft exists
├─ ✓ Draft belongs to user
├─ ✓ Draft not already committed
├─ ✓ Has at least one stage
├─ ✓ Each stage has at least one milestone
├─ ✓ All data valid
├─ → CommittedTimeline created (immutable)
├─ → Draft marked inactive
└─ → DecisionTrace recorded

S3 → S4 (Track Progress)
├─ ✓ Milestone exists
├─ ✓ Milestone belongs to stage
├─ ✓ Stage belongs to COMMITTED timeline
├─ ✓ Timeline belongs to user
├─ ✓ Milestone not already completed
├─ → ProgressEvent created (append-only)
├─ → Milestone marked completed
└─ → DecisionTrace recorded

S3 → Analytics
├─ ✓ CommittedTimeline exists
├─ ✓ Timeline belongs to user
├─ → AnalyticsSnapshot created
└─ → DecisionTrace recorded
```

## Immutability Enforcement

```
┌─────────────────────────────────────────────────────────────────┐
│                    IMMUTABILITY GUARANTEES                       │
└─────────────────────────────────────────────────────────────────┘

STATE: S3 (Committed Timeline)
─────────────────────────────────────────────────────────────
  🔒 IMMUTABLE - Cannot be modified after creation
  
  Enforcement mechanisms:
  ├─ Draft marked inactive (is_active = False)
  ├─ No update methods in TimelineOrchestrator
  ├─ UI shows read-only interface
  ├─ To make changes: Create new draft → commit
  └─ Original timeline preserved for audit trail

STATE: S4 (Progress Events)
─────────────────────────────────────────────────────────────
  🔒 APPEND-ONLY - Never updated or deleted
  
  Enforcement mechanisms:
  ├─ ProgressEvent has no update() method
  ├─ ProgressService only has create methods
  ├─ UI does not allow editing completed milestones
  └─ Audit trail preserved forever

LINEAGE: Draft → Committed
─────────────────────────────────────────────────────────────
  📜 AUDIT TRAIL - Full history preserved
  
  Tracking:
  ├─ CommittedTimeline.draft_timeline_id → original draft
  ├─ TimelineEditHistory → all edits before commit
  ├─ DecisionTrace → step-by-step validation
  └─ EvidenceBundle → supporting data
```

## Code Integration Points

```
┌─────────────────────────────────────────────────────────────────┐
│                 VALIDATION IMPLEMENTATION MAP                     │
└─────────────────────────────────────────────────────────────────┘

Core Validation Layer
├─ app/utils/invariants.py
│   ├─ check_committed_timeline_has_draft()
│   ├─ check_progress_event_has_milestone()
│   └─ check_analytics_has_committed_timeline()

Orchestrator Layer
├─ app/orchestrators/timeline_orchestrator.py
│   ├─ create_draft_timeline()  [S1 → S2]
│   └─ commit_timeline()        [S2 → S3]
├─ app/orchestrators/analytics_orchestrator.py
│   └─ run()                    [S3 → Analytics]

Service Layer
├─ app/services/progress_service.py
│   └─ mark_milestone_completed()  [S3 → S4]

Frontend Validation
├─ frontend/VALIDATION_GUIDE.md
│   ├─ State transition matrix
│   ├─ Guardrails by flow
│   └─ Immutability enforcement

Test Suite
└─ backend/tests/test_state_transitions_validation.py
    ├─ TestAllowedTransitions      [✅ paths]
    ├─ TestDisallowedTransitions   [❌ paths]
    ├─ TestImmutabilityEnforcement [🔒 guarantees]
    └─ TestErrorMessagesClarity    [📝 quality]
```

## Decision Trace Flow

```
Every state transition creates an audit trail:

┌─────────────┐
│   Request   │ User initiates state transition
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Orchestrator│ Coordinates transition
└──────┬──────┘
       │ Creates DecisionTrace with:
       │ ├─ Operation name
       │ ├─ Input parameters
       │ ├─ Timestamp
       │ └─ Request ID (idempotency)
       ▼
┌─────────────┐
│  Validate   │ Check invariants
└──────┬──────┘
       │ Records validation steps:
       │ ├─ What was checked
       │ ├─ What was found
       │ └─ Pass/fail status
       ▼
┌─────────────┐
│   Execute   │ Perform state mutation
└──────┬──────┘
       │ Records execution steps:
       │ ├─ Database operations
       │ ├─ Side effects
       │ └─ Results
       ▼
┌─────────────┐
│Evidence     │ Collect supporting data
│Bundle       │
└──────┬──────┘
       │ Attaches:
       │ ├─ Entity snapshots
       │ ├─ Validation results
       │ └─ Computed values
       ▼
┌─────────────┐
│   Persist   │ Write DecisionTrace to DB
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Response  │ Return result to user
└─────────────┘
```

## Error Propagation

```
┌─────────────────────────────────────────────────────────────────┐
│                     ERROR HANDLING FLOW                          │
└─────────────────────────────────────────────────────────────────┘

Frontend Request
  │
  ▼
API Endpoint
  │ Validates request format
  ├─ ✅ Valid → proceed
  └─ ❌ Invalid → 400 Bad Request
      │
      ▼
Orchestrator
  │ Calls invariant checks
  ├─ ✅ Valid → proceed
  └─ ❌ Invalid → InvariantViolationError
      │ ├─ CommittedTimelineWithoutDraftError
      │ ├─ ProgressEventWithoutMilestoneError
      │ └─ AnalyticsWithoutCommittedTimelineError
      │
      ▼
Error Handler
  │ Formats error for API response
  ├─ HTTP status code (400, 404, 409)
  ├─ Error message (user-friendly)
  ├─ Error details (context)
  └─ Hint (how to fix)
      │
      ▼
Frontend
  │ Displays error to user
  ├─ Error message
  ├─ Suggested action
  └─ Option to retry or go back
```

## Testing Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                        TEST COVERAGE                             │
└─────────────────────────────────────────────────────────────────┘

✅ Happy Path Tests (All transitions work)
├─ test_s0_to_s1_raw_input_to_baseline()
├─ test_s1_to_s2_baseline_to_draft_timeline()
├─ test_s2_to_s3_draft_to_committed_timeline()
├─ test_s3_to_s4_committed_to_progress_tracking()
└─ test_complete_allowed_pipeline_s0_to_s4()

❌ Sad Path Tests (Invalid transitions fail)
├─ test_progress_without_committed_timeline_fails()
├─ test_commit_without_draft_fails()
├─ test_double_commit_fails()
├─ test_analytics_without_committed_timeline_fails()
├─ test_commit_empty_timeline_fails()
├─ test_commit_timeline_without_milestones_fails()
└─ test_commit_someone_elses_timeline_fails()

🔒 Immutability Tests
├─ test_committed_timeline_is_immutable()
└─ test_draft_inactive_after_commit()

📝 Error Quality Tests
└─ test_error_messages_are_informative()

Coverage: 100% of state transitions validated
```

---

## Quick Reference

### ✅ Do This
- Always use orchestrators for state transitions
- Check invariants before expensive operations
- Provide clear error context
- Test both happy and sad paths
- Use DecisionTrace for audit trail

### ❌ Don't Do This
- Don't bypass orchestrators
- Don't modify committed timelines
- Don't update/delete progress events
- Don't skip validation checks
- Don't use generic error messages

### 🔍 When Debugging
1. Check DecisionTrace for audit trail
2. Verify current state in database
3. Check error message and details
4. Review state transition rules
5. Use validation checkpoints guide
