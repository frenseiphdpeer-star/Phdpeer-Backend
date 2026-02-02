"""
System invariants and validation utilities.

Enforces critical system constraints:
1. No duplicate execution for same request_id (global)
2. No state mutation outside orchestrators
3. No committed timeline without draft
4. No PhD Doctor score without submission
5. No progress event without committed milestone
6. No analytics without committed timeline
7. No state mutation inside AnalyticsOrchestrator

Fail fast with explicit errors.
"""

from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session
from datetime import datetime


class InvariantViolationError(Exception):
    """Base exception for invariant violations."""
    
    def __init__(self, invariant_name: str, message: str, details: dict = None):
        self.invariant_name = invariant_name
        self.details = details or {}
        super().__init__(f"[INVARIANT VIOLATION: {invariant_name}] {message}")


class CommittedTimelineWithoutDraftError(InvariantViolationError):
    """Raised when attempting to create CommittedTimeline without DraftTimeline."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__("committed_timeline_without_draft", message, details)


class AssessmentWithoutSubmissionError(InvariantViolationError):
    """Raised when JourneyAssessment created without proper submission."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__("assessment_without_submission", message, details)


class ProgressEventWithoutMilestoneError(InvariantViolationError):
    """Raised when ProgressEvent references non-existent milestone."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__("progress_event_without_milestone", message, details)


class DuplicateIdempotentActionError(InvariantViolationError):
    """Raised when attempting duplicate idempotent action."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__("duplicate_idempotent_action", message, details)


class DuplicateExecutionError(InvariantViolationError):
    """Raised when duplicate execution detected for same request_id."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__("duplicate_execution", message, details)


class StateMutationOutsideOrchestratorError(InvariantViolationError):
    """Raised when state mutation attempted outside orchestrator."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__("state_mutation_outside_orchestrator", message, details)


class AnalyticsWithoutCommittedTimelineError(InvariantViolationError):
    """Raised when attempting analytics without committed timeline."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__("analytics_without_committed_timeline", message, details)


class StateMutationInAnalyticsOrchestratorError(InvariantViolationError):
    """Raised when state mutation attempted inside AnalyticsOrchestrator."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__("state_mutation_in_analytics_orchestrator", message, details)


class AnalyticsSnapshotMutationError(InvariantViolationError):
    """Raised when attempting to modify an immutable AnalyticsSnapshot."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__("analytics_snapshot_mutation", message, details)


class AnalyticsSnapshotDeletionError(InvariantViolationError):
    """Raised when attempting to delete an AnalyticsSnapshot."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__("analytics_snapshot_deletion", message, details)


class InvariantChecker:
    """
    Central invariant checker for system-wide validation.
    
    Usage:
        checker = InvariantChecker(db)
        checker.check_all(operation="commit_timeline", context={...})
    """
    
    def __init__(self, db: Session):
        """
        Initialize invariant checker.
        
        Args:
            db: Database session
        """
        self.db = db
    
    def check_committed_timeline_has_draft(
        self,
        draft_timeline_id: Optional[UUID],
        user_id: UUID
    ) -> None:
        """
        Invariant: No committed timeline without draft.
        
        Every CommittedTimeline must originate from a DraftTimeline.
        This ensures proper workflow and auditability.
        
        Args:
            draft_timeline_id: Draft timeline ID
            user_id: User ID
            
        Raises:
            CommittedTimelineWithoutDraftError: If draft doesn't exist
        """
        if draft_timeline_id is None:
            raise CommittedTimelineWithoutDraftError(
                "Cannot commit timeline: no draft_timeline_id provided",
                details={
                    "user_id": str(user_id),
                    "draft_timeline_id": None
                }
            )
        
        from app.models.draft_timeline import DraftTimeline
        
        draft = self.db.query(DraftTimeline).filter(
            DraftTimeline.id == draft_timeline_id,
            DraftTimeline.user_id == user_id
        ).first()
        
        if not draft:
            raise CommittedTimelineWithoutDraftError(
                f"Cannot commit timeline: DraftTimeline {draft_timeline_id} not found or not owned by user {user_id}",
                details={
                    "user_id": str(user_id),
                    "draft_timeline_id": str(draft_timeline_id),
                    "exists": False
                }
            )
        
        # Check if draft is already committed
        from app.models.committed_timeline import CommittedTimeline
        
        existing_commit = self.db.query(CommittedTimeline).filter(
            CommittedTimeline.draft_timeline_id == draft_timeline_id
        ).first()
        
        if existing_commit:
            raise CommittedTimelineWithoutDraftError(
                f"Cannot commit timeline: DraftTimeline {draft_timeline_id} already committed as {existing_commit.id}",
                details={
                    "user_id": str(user_id),
                    "draft_timeline_id": str(draft_timeline_id),
                    "existing_committed_id": str(existing_commit.id),
                    "already_committed": True
                }
            )
    
    def check_assessment_has_submission(
        self,
        user_id: UUID,
        responses_count: int,
        is_explicit_submission: bool = True
    ) -> None:
        """
        Invariant: No PhD Doctor score without submission.
        
        JourneyAssessment records must only be created through explicit
        submission (via PhDDoctorOrchestrator.submit()), not directly.
        
        Args:
            user_id: User ID
            responses_count: Number of responses
            is_explicit_submission: Whether this is an explicit submission
            
        Raises:
            AssessmentWithoutSubmissionError: If not explicit submission
        """
        if not is_explicit_submission:
            raise AssessmentWithoutSubmissionError(
                "Cannot create JourneyAssessment: must use PhDDoctorOrchestrator.submit()",
                details={
                    "user_id": str(user_id),
                    "is_explicit_submission": False,
                    "hint": "Use PhDDoctorOrchestrator.submit() instead of creating JourneyAssessment directly"
                }
            )
        
        # Check minimum responses
        if responses_count < 5:
            raise AssessmentWithoutSubmissionError(
                f"Cannot create JourneyAssessment: insufficient responses (got {responses_count}, need at least 5)",
                details={
                    "user_id": str(user_id),
                    "responses_count": responses_count,
                    "minimum_required": 5
                }
            )
    
    def check_progress_event_has_milestone(
        self,
        milestone_id: UUID,
        user_id: UUID
    ) -> None:
        """
        Invariant: No progress event without committed milestone.
        
        Every ProgressEvent must reference a valid milestone in a
        CommittedTimeline. This ensures progress tracking integrity.
        
        Args:
            milestone_id: Milestone ID
            user_id: User ID
            
        Raises:
            ProgressEventWithoutMilestoneError: If milestone doesn't exist
        """
        from app.models.timeline_milestone import TimelineMilestone
        from app.models.timeline_stage import TimelineStage
        from app.models.committed_timeline import CommittedTimeline
        
        # Check milestone exists
        milestone = self.db.query(TimelineMilestone).filter(
            TimelineMilestone.id == milestone_id
        ).first()
        
        if not milestone:
            raise ProgressEventWithoutMilestoneError(
                f"Cannot create ProgressEvent: TimelineMilestone {milestone_id} not found",
                details={
                    "user_id": str(user_id),
                    "milestone_id": str(milestone_id),
                    "exists": False
                }
            )
        
        # Check milestone belongs to a stage
        stage = self.db.query(TimelineStage).filter(
            TimelineStage.id == milestone.timeline_stage_id
        ).first()
        
        if not stage:
            raise ProgressEventWithoutMilestoneError(
                f"Cannot create ProgressEvent: Milestone {milestone_id} has no associated stage",
                details={
                    "user_id": str(user_id),
                    "milestone_id": str(milestone_id),
                    "stage_id": milestone.timeline_stage_id,
                    "stage_exists": False
                }
            )
        
        # Check stage belongs to a committed timeline
        if stage.committed_timeline_id:
            timeline = self.db.query(CommittedTimeline).filter(
                CommittedTimeline.id == stage.committed_timeline_id
            ).first()
        else:
            timeline = None
        
        if not timeline:
            raise ProgressEventWithoutMilestoneError(
                f"Cannot create ProgressEvent: Milestone {milestone_id} not in CommittedTimeline",
                details={
                    "user_id": str(user_id),
                    "milestone_id": str(milestone_id),
                    "stage_id": milestone.timeline_stage_id,
                    "committed_timeline_id": stage.committed_timeline_id,
                    "hint": "Progress can only be tracked on committed timelines"
                }
            )
        
        # Verify timeline belongs to user
        if timeline.user_id != user_id:
            raise ProgressEventWithoutMilestoneError(
                f"Cannot create ProgressEvent: Timeline {timeline.id} does not belong to user {user_id}",
                details={
                    "user_id": str(user_id),
                    "milestone_id": str(milestone_id),
                    "timeline_user_id": str(timeline.user_id),
                    "ownership_mismatch": True
                }
            )
    
    def check_no_duplicate_execution(
        self,
        request_id: str,
        orchestrator_name: str,
        allow_completed: bool = False
    ) -> None:
        """
        Global invariant: No duplicate execution for same request_id.
        
        Prevents duplicate execution across all orchestrators.
        This is a global check that enforces idempotency at the system level.
        
        Args:
            request_id: Request identifier (idempotency key)
            orchestrator_name: Orchestrator name
            allow_completed: If True, allow completed requests (they return cached results)
            
        Raises:
            DuplicateExecutionError: If duplicate execution detected
        """
        from app.models.idempotency import IdempotencyKey, RequestStatus
        from sqlalchemy import and_
        
        existing = self.db.query(IdempotencyKey).filter(
            and_(
                IdempotencyKey.request_id == request_id,
                IdempotencyKey.orchestrator_name == orchestrator_name
            )
        ).first()
        
        if not existing:
            return  # No duplicate found
        
        if existing.status == RequestStatus.PROCESSING:
            raise DuplicateExecutionError(
                f"Duplicate execution detected: request_id '{request_id}' is already being processed by '{orchestrator_name}'",
                details={
                    "request_id": request_id,
                    "orchestrator_name": orchestrator_name,
                    "status": existing.status.value,
                    "started_at": existing.started_at.isoformat() if existing.started_at else None,
                    "hint": "Wait for operation to complete or use a different request_id"
                }
            )
        
        if existing.status == RequestStatus.COMPLETED and not allow_completed:
            raise DuplicateExecutionError(
                f"Duplicate execution detected: request_id '{request_id}' was already completed by '{orchestrator_name}'",
                details={
                    "request_id": request_id,
                    "orchestrator_name": orchestrator_name,
                    "status": existing.status.value,
                    "completed_at": existing.completed_at.isoformat() if existing.completed_at else None,
                    "hint": "Use the cached result or use a different request_id"
                }
            )
    
    def check_idempotency_key_unique(
        self,
        request_id: str,
        orchestrator_name: str,
        allow_completed: bool = True
    ) -> Optional[dict]:
        """
        Invariant: No duplicate idempotent actions.
        
        Idempotency keys must be unique per orchestrator to prevent
        duplicate execution. Returns existing result if key exists and completed.
        
        Args:
            request_id: Request identifier (idempotency key)
            orchestrator_name: Orchestrator name
            allow_completed: If True, return cached result for completed operations
            
        Returns:
            Cached result if key exists and completed, None otherwise
            
        Raises:
            DuplicateIdempotentActionError: If key exists but not completed
        """
        from app.models.idempotency import IdempotencyKey, RequestStatus
        from sqlalchemy import and_
        
        existing = self.db.query(IdempotencyKey).filter(
            and_(
                IdempotencyKey.request_id == request_id,
                IdempotencyKey.orchestrator_name == orchestrator_name
            )
        ).first()
        
        if not existing:
            return None
        
        # If completed and allowed, return cached result
        if existing.status == RequestStatus.COMPLETED and allow_completed:
            return existing.response_data
        
        # If in progress, fail
        if existing.status == RequestStatus.PROCESSING:
            raise DuplicateIdempotentActionError(
                f"Operation with request_id '{request_id}' is already in progress",
                details={
                    "request_id": request_id,
                    "orchestrator_name": orchestrator_name,
                    "status": existing.status.value,
                    "started_at": existing.started_at.isoformat() if existing.started_at else None,
                    "hint": "Wait for operation to complete or use a different request_id"
                }
            )
        
        # If failed, allow retry with same key
        if existing.status == RequestStatus.FAILED:
            # Delete failed attempt to allow retry
            self.db.delete(existing)
            self.db.flush()
            return None
        
        # Other statuses - treat as error
        raise DuplicateIdempotentActionError(
            f"Operation with request_id '{request_id}' exists with unexpected status: {existing.status.value}",
            details={
                "request_id": request_id,
                "orchestrator_name": orchestrator_name,
                "status": existing.status.value
            }
        )
    
    def check_all(
        self,
        operation: str,
        context: dict
    ) -> None:
        """
        Check all relevant invariants for an operation.
        
        Args:
            operation: Operation name (e.g., "commit_timeline", "create_assessment")
            context: Operation context with required fields
            
        Raises:
            InvariantViolationError: If any invariant is violated
        """
        if operation == "commit_timeline":
            self.check_committed_timeline_has_draft(
                draft_timeline_id=context.get("draft_timeline_id"),
                user_id=context["user_id"]
            )
        
        elif operation == "create_assessment":
            self.check_assessment_has_submission(
                user_id=context["user_id"],
                responses_count=context.get("responses_count", 0),
                is_explicit_submission=context.get("is_explicit_submission", False)
            )
        
        elif operation == "create_progress_event":
            self.check_progress_event_has_milestone(
                milestone_id=context["milestone_id"],
                user_id=context["user_id"]
            )
        
        elif operation == "check_idempotency":
            result = self.check_idempotency_key_unique(
                request_id=context["request_id"],
                orchestrator_name=context["orchestrator_name"],
                allow_completed=context.get("allow_completed", True)
            )
            return result
        
        elif operation == "check_duplicate_execution":
            self.check_no_duplicate_execution(
                request_id=context["request_id"],
                orchestrator_name=context["orchestrator_name"]
            )
        
        elif operation == "check_state_mutation":
            self.check_no_state_mutation_outside_orchestrator(
                operation=context["operation"],
                caller_context=context.get("caller_context", {})
            )
        
        elif operation == "run_analytics":
            self.check_analytics_has_committed_timeline(
                user_id=context["user_id"],
                timeline_id=context.get("timeline_id")
            )
        
        elif operation == "check_analytics_state_mutation":
            self.check_no_state_mutation_in_analytics_orchestrator(
                operation=context["operation"],
                caller_context=context.get("caller_context", {})
            )
        
        else:
            # Unknown operation - no checks
            pass
    
    def check_no_state_mutation_outside_orchestrator(
        self,
        operation: str,
        caller_context: dict
    ) -> None:
        """
        Invariant: No state mutation outside orchestrators.
        
        Ensures that state-changing operations (create, update, delete)
        are only performed through orchestrators, not directly.
        
        Args:
            operation: Operation name (e.g., "create_baseline", "update_timeline")
            caller_context: Context about the caller (stack trace, module, etc.)
            
        Raises:
            StateMutationOutsideOrchestratorError: If mutation attempted outside orchestrator
        """
        import inspect
        import traceback
        
        # Get the call stack
        stack = inspect.stack()
        
        # Check if we're being called from an orchestrator
        is_orchestrator = False
        caller_module = None
        caller_function = None
        
        for frame_info in stack[2:6]:  # Skip current frame and immediate caller
            frame = frame_info.frame
            module_name = frame.f_globals.get('__name__', '')
            function_name = frame_info.function
            
            if 'orchestrator' in module_name.lower() or 'orchestrator' in function_name.lower():
                is_orchestrator = True
                caller_module = module_name
                caller_function = function_name
                break
        
        if not is_orchestrator:
            # Get more context about the caller
            caller_frame = stack[2] if len(stack) > 2 else None
            if caller_frame:
                caller_module = caller_frame.frame.f_globals.get('__name__', 'unknown')
                caller_function = caller_frame.function
            
            raise StateMutationOutsideOrchestratorError(
                f"State mutation '{operation}' attempted outside orchestrator",
                details={
                    "operation": operation,
                    "caller_module": caller_module,
                    "caller_function": caller_function,
                    "hint": f"Use an orchestrator to perform '{operation}' instead of direct database access",
                    "context": caller_context
                }
            )
    
    def check_analytics_has_committed_timeline(
        self,
        user_id: UUID,
        timeline_id: Optional[UUID] = None
    ) -> None:
        """
        Invariant: No analytics without committed timeline.
        
        Analytics can only be generated for CommittedTimeline records.
        This ensures analytics are based on immutable, committed data.
        
        Args:
            user_id: User ID
            timeline_id: Optional timeline ID (checks latest if not provided)
            
        Raises:
            AnalyticsWithoutCommittedTimelineError: If no committed timeline exists
        """
        from app.models.committed_timeline import CommittedTimeline
        
        if timeline_id:
            timeline = self.db.query(CommittedTimeline).filter(
                CommittedTimeline.id == timeline_id,
                CommittedTimeline.user_id == user_id
            ).first()
            
            if not timeline:
                raise AnalyticsWithoutCommittedTimelineError(
                    f"Cannot generate analytics: CommittedTimeline {timeline_id} not found or not owned by user {user_id}",
                    details={
                        "user_id": str(user_id),
                        "timeline_id": str(timeline_id),
                        "exists": False,
                        "hint": "Analytics can only be generated for committed timelines"
                    }
                )
        else:
            # Check if user has any committed timeline
            timeline = self.db.query(CommittedTimeline).filter(
                CommittedTimeline.user_id == user_id
            ).order_by(CommittedTimeline.committed_date.desc()).first()
            
            if not timeline:
                raise AnalyticsWithoutCommittedTimelineError(
                    f"Cannot generate analytics: No CommittedTimeline found for user {user_id}",
                    details={
                        "user_id": str(user_id),
                        "timeline_id": None,
                        "has_committed_timeline": False,
                        "hint": "Commit a timeline before generating analytics"
                    }
                )
    
    def check_no_state_mutation_in_analytics_orchestrator(
        self,
        operation: str,
        caller_context: dict
    ) -> None:
        """
        Invariant: No state mutation inside AnalyticsOrchestrator.
        
        AnalyticsOrchestrator must be read-only. It should only:
        - Read data (CommittedTimeline, ProgressEvents, JourneyAssessment)
        - Create AnalyticsSnapshot (immutable snapshot, not mutation)
        
        It must NOT:
        - Update any upstream models
        - Delete any records
        - Modify timeline, progress, or assessment data
        
        Args:
            operation: Operation name (e.g., "update_timeline", "delete_event")
            caller_context: Context about the caller
            
        Raises:
            StateMutationInAnalyticsOrchestratorError: If mutation attempted
        """
        import inspect
        
        # Get the call stack
        stack = inspect.stack()
        
        # Check if we're being called from AnalyticsOrchestrator
        is_analytics_orchestrator = False
        caller_module = None
        caller_function = None
        
        for frame_info in stack[2:8]:  # Check deeper stack for AnalyticsOrchestrator
            frame = frame_info.frame
            module_name = frame.f_globals.get('__name__', '')
            function_name = frame_info.function
            
            if 'analytics_orchestrator' in module_name.lower():
                is_analytics_orchestrator = True
                caller_module = module_name
                caller_function = function_name
                break
        
        if is_analytics_orchestrator:
            # Check if operation is a mutation (not allowed)
            mutation_operations = [
                'update', 'delete', 'modify', 'change', 'edit',
                'set', 'remove', 'clear', 'reset'
            ]
            
            operation_lower = operation.lower()
            is_mutation = any(mut_op in operation_lower for mut_op in mutation_operations)
            
            # Allow creating AnalyticsSnapshot (it's an immutable snapshot, not a mutation)
            if 'create' in operation_lower and 'analytics_snapshot' in operation_lower:
                is_mutation = False
            
            if is_mutation:
                raise StateMutationInAnalyticsOrchestratorError(
                    f"State mutation '{operation}' attempted inside AnalyticsOrchestrator",
                    details={
                        "operation": operation,
                        "caller_module": caller_module,
                        "caller_function": caller_function,
                        "hint": "AnalyticsOrchestrator is read-only. It can only read data and create immutable snapshots.",
                        "context": caller_context
                    }
                )


    def check_analytics_snapshot_not_modified(
        self,
        snapshot_id: UUID
    ) -> None:
        """
        Invariant: AnalyticsSnapshot records are immutable.
        
        AnalyticsSnapshots must never be modified after creation.
        They serve as immutable historical records of analytics state.
        
        Args:
            snapshot_id: ID of snapshot being checked
            
        Raises:
            AnalyticsSnapshotMutationError: If snapshot modification attempted
        """
        from app.models.analytics_snapshot import AnalyticsSnapshot
        
        # Check if snapshot exists
        snapshot = self.db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.id == snapshot_id
        ).first()
        
        if not snapshot:
            # Snapshot doesn't exist, no mutation check needed
            return
        
        # This method exists as a documentation of the invariant
        # In practice, application code should never call update/delete on snapshots
        # Database-level constraints or triggers would be ideal for enforcement
        
        raise AnalyticsSnapshotMutationError(
            f"Attempted to modify immutable AnalyticsSnapshot {snapshot_id}",
            details={
                "snapshot_id": str(snapshot_id),
                "hint": "AnalyticsSnapshots are immutable. Create a new snapshot instead.",
                "action": "Create new snapshot with updated data rather than modifying existing"
            }
        )
    
    def check_analytics_snapshot_not_deleted(
        self,
        snapshot_id: UUID
    ) -> None:
        """
        Invariant: AnalyticsSnapshot records must not be deleted.
        
        Snapshots are historical records and should be preserved.
        If cleanup is needed, use soft deletion or archival processes.
        
        Args:
            snapshot_id: ID of snapshot being checked
            
        Raises:
            AnalyticsSnapshotDeletionError: If snapshot deletion attempted
        """
        from app.models.analytics_snapshot import AnalyticsSnapshot
        
        # Check if snapshot exists
        snapshot = self.db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.id == snapshot_id
        ).first()
        
        if not snapshot:
            # Snapshot doesn't exist, might have been deleted
            # or never existed
            return
        
        raise AnalyticsSnapshotDeletionError(
            f"Attempted to delete immutable AnalyticsSnapshot {snapshot_id}",
            details={
                "snapshot_id": str(snapshot_id),
                "hint": "AnalyticsSnapshots should not be deleted. They are historical records.",
                "action": "Use soft deletion or archival process if cleanup is needed"
            }
        )


# Convenience functions for direct usage

def check_committed_timeline_has_draft(
    db: Session,
    draft_timeline_id: Optional[UUID],
    user_id: UUID
) -> None:
    """Check committed timeline has draft invariant."""
    checker = InvariantChecker(db)
    checker.check_committed_timeline_has_draft(draft_timeline_id, user_id)


def check_assessment_has_submission(
    db: Session,
    user_id: UUID,
    responses_count: int,
    is_explicit_submission: bool = True
) -> None:
    """Check assessment has submission invariant."""
    checker = InvariantChecker(db)
    checker.check_assessment_has_submission(user_id, responses_count, is_explicit_submission)


def check_progress_event_has_milestone(
    db: Session,
    milestone_id: UUID,
    user_id: UUID
) -> None:
    """Check progress event has milestone invariant."""
    checker = InvariantChecker(db)
    checker.check_progress_event_has_milestone(milestone_id, user_id)


def check_idempotency_key_unique(
    db: Session,
    request_id: str,
    orchestrator_name: str,
    allow_completed: bool = True
) -> Optional[dict]:
    """Check idempotency key unique invariant."""
    checker = InvariantChecker(db)
    return checker.check_idempotency_key_unique(request_id, orchestrator_name, allow_completed)


def check_no_duplicate_execution(
    db: Session,
    request_id: str,
    orchestrator_name: str,
    allow_completed: bool = False
) -> None:
    """
    Global invariant: No duplicate execution for same request_id.
    
    Utility helper for checking duplicate execution across orchestrators.
    Fail fast with explicit error.
    
    Args:
        db: Database session
        request_id: Request identifier
        orchestrator_name: Orchestrator name
        allow_completed: If True, allow completed requests (they return cached results)
        
    Raises:
        DuplicateExecutionError: If duplicate execution detected
    """
    checker = InvariantChecker(db)
    checker.check_no_duplicate_execution(request_id, orchestrator_name, allow_completed)


def check_no_state_mutation_outside_orchestrator(
    db: Session,
    operation: str,
    caller_context: dict = None
) -> None:
    """
    Invariant: No state mutation outside orchestrators.
    
    Utility helper for ensuring state mutations only happen in orchestrators.
    Fail fast with explicit error.
    
    Args:
        db: Database session
        operation: Operation name
        caller_context: Optional context about the caller
        
    Raises:
        StateMutationOutsideOrchestratorError: If mutation attempted outside orchestrator
    """
    checker = InvariantChecker(db)
    checker.check_no_state_mutation_outside_orchestrator(
        operation,
        caller_context or {}
    )


def validate_request_id(request_id: str) -> None:
    """
    Utility helper: Validate request_id format.
    
    Args:
        request_id: Request identifier to validate
        
    Raises:
        ValueError: If request_id is invalid
    """
    if not request_id:
        raise ValueError("request_id cannot be empty")
    
    if not isinstance(request_id, str):
        raise ValueError(f"request_id must be a string, got {type(request_id)}")
    
    if len(request_id) > 255:
        raise ValueError(f"request_id too long (max 255 chars, got {len(request_id)})")
    
    if len(request_id) < 1:
        raise ValueError("request_id must be at least 1 character")


def validate_orchestrator_name(orchestrator_name: str) -> None:
    """
    Utility helper: Validate orchestrator name format.
    
    Args:
        orchestrator_name: Orchestrator name to validate
        
    Raises:
        ValueError: If orchestrator_name is invalid
    """
    if not orchestrator_name:
        raise ValueError("orchestrator_name cannot be empty")
    
    if not isinstance(orchestrator_name, str):
        raise ValueError(f"orchestrator_name must be a string, got {type(orchestrator_name)}")
    
    if len(orchestrator_name) > 100:
        raise ValueError(f"orchestrator_name too long (max 100 chars, got {len(orchestrator_name)})")
    
    if not orchestrator_name.replace('_', '').isalnum():
        raise ValueError("orchestrator_name must contain only alphanumeric characters and underscores")


def check_analytics_has_committed_timeline(
    db: Session,
    user_id: UUID,
    timeline_id: Optional[UUID] = None
) -> None:
    """
    Invariant: No analytics without committed timeline.
    
    Utility helper for ensuring analytics only run on committed timelines.
    Fail fast with explicit error.
    
    Args:
        db: Database session
        user_id: User ID
        timeline_id: Optional timeline ID (checks latest if not provided)
        
    Raises:
        AnalyticsWithoutCommittedTimelineError: If no committed timeline exists
    """
    checker = InvariantChecker(db)
    checker.check_analytics_has_committed_timeline(user_id, timeline_id)


def check_no_state_mutation_in_analytics_orchestrator(
    db: Session,
    operation: str,
    caller_context: dict = None
) -> None:
    """
    Invariant: No state mutation inside AnalyticsOrchestrator.
    
    Utility helper for ensuring AnalyticsOrchestrator is read-only.
    Fail fast with explicit error.
    
    Args:
        db: Database session
        operation: Operation name
        caller_context: Optional context about the caller
        
    Raises:
        StateMutationInAnalyticsOrchestratorError: If mutation attempted
    """
    checker = InvariantChecker(db)
    checker.check_no_state_mutation_in_analytics_orchestrator(
        operation,
        caller_context or {}
    )


def check_analytics_snapshot_not_modified(
    db: Session,
    snapshot_id: UUID
) -> None:
    """
    Invariant: AnalyticsSnapshot records are immutable.
    
    Utility helper for preventing snapshot modifications.
    Fail fast with explicit error.
    
    Args:
        db: Database session
        snapshot_id: ID of snapshot to check
        
    Raises:
        AnalyticsSnapshotMutationError: If snapshot modification attempted
    """
    checker = InvariantChecker(db)
    checker.check_analytics_snapshot_not_modified(snapshot_id)


def check_analytics_snapshot_not_deleted(
    db: Session,
    snapshot_id: UUID
) -> None:
    """
    Invariant: AnalyticsSnapshot records must not be deleted.
    
    Utility helper for preventing snapshot deletions.
    Fail fast with explicit error.
    
    Args:
        db: Database session
        snapshot_id: ID of snapshot to check
        
    Raises:
        AnalyticsSnapshotDeletionError: If snapshot deletion attempted
    """
    checker = InvariantChecker(db)
    checker.check_analytics_snapshot_not_deleted(snapshot_id)

