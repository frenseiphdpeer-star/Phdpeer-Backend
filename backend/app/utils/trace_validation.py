"""
Validation utility for DecisionTrace completeness and state mutation tracking.

Ensures every orchestrator execution produces a complete DecisionTrace with:
- Orchestrator name
- Step order
- Input/output hashes
- Failure reasons (if applicable)

Fails if any orchestrator mutates state without a corresponding trace.
"""
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.models.idempotency import DecisionTrace, IdempotencyKey
from app.models.baseline import Baseline
from app.models.draft_timeline import DraftTimeline
from app.models.committed_timeline import CommittedTimeline


class TraceValidationError(Exception):
    """Raised when trace validation fails."""
    pass


class StateChangeWithoutTraceError(TraceValidationError):
    """Raised when state is mutated without a corresponding trace."""
    pass


class IncompleteTraceError(TraceValidationError):
    """Raised when a trace is missing required fields."""
    pass


def validate_trace_completeness(trace: DecisionTrace) -> None:
    """
    Validate that a DecisionTrace has all required fields.
    
    Required fields:
    - orchestrator_name: str
    - request_id: str
    - execution_steps: list with proper order
    - input_hash: str
    - output_hash: str (if successful)
    - error_message: str (if failed)
    
    Args:
        trace: DecisionTrace to validate
        
    Raises:
        IncompleteTraceError: If any required field is missing or invalid
    """
    errors = []
    
    # Check orchestrator name
    if not trace.orchestrator_name or not isinstance(trace.orchestrator_name, str):
        errors.append("Missing or invalid orchestrator_name")
    
    # Check request_id
    if not trace.request_id or not isinstance(trace.request_id, str):
        errors.append("Missing or invalid request_id")
    
    # Check execution steps
    if not trace.execution_steps:
        errors.append("Missing execution_steps")
    elif not isinstance(trace.execution_steps, list):
        errors.append("execution_steps must be a list")
    else:
        # Validate step order
        for i, step in enumerate(trace.execution_steps, start=1):
            if not isinstance(step, dict):
                errors.append(f"Step {i} is not a dictionary")
                continue
            
            if "step_number" not in step:
                errors.append(f"Step {i} missing step_number")
            elif step["step_number"] != i:
                errors.append(f"Step {i} has incorrect step_number: {step['step_number']}")
            
            if "action" not in step:
                errors.append(f"Step {i} missing action")
            
            if "status" not in step:
                errors.append(f"Step {i} missing status")
    
    # Check input hash
    if not trace.input_hash or not isinstance(trace.input_hash, str):
        errors.append("Missing or invalid input_hash")
    
    # Check output hash or error message
    if trace.status == "COMPLETED":
        if not trace.output_hash or not isinstance(trace.output_hash, str):
            errors.append("Completed trace missing output_hash")
    elif trace.status == "FAILED":
        if not trace.error_message or not isinstance(trace.error_message, str):
            errors.append("Failed trace missing error_message")
    
    # Check timestamps
    if not trace.started_at:
        errors.append("Missing started_at timestamp")
    
    if trace.status in ("COMPLETED", "FAILED") and not trace.completed_at:
        errors.append(f"{trace.status} trace missing completed_at timestamp")
    
    # Check duration for completed/failed traces
    if trace.status in ("COMPLETED", "FAILED"):
        if trace.duration_ms is None or trace.duration_ms < 0:
            errors.append("Missing or invalid duration_ms")
    
    if errors:
        raise IncompleteTraceError(
            f"DecisionTrace validation failed for {trace.request_id}:\n" +
            "\n".join(f"  - {error}" for error in errors)
        )


def validate_trace_for_request(
    db: Session,
    request_id: str,
    orchestrator_name: str
) -> DecisionTrace:
    """
    Validate that a DecisionTrace exists for a specific request.
    
    Args:
        db: Database session
        request_id: Request identifier
        orchestrator_name: Name of the orchestrator
        
    Returns:
        The validated DecisionTrace
        
    Raises:
        TraceValidationError: If trace doesn't exist or is incomplete
    """
    trace = db.query(DecisionTrace).filter(
        and_(
            DecisionTrace.request_id == request_id,
            DecisionTrace.orchestrator_name == orchestrator_name
        )
    ).first()
    
    if not trace:
        raise TraceValidationError(
            f"No DecisionTrace found for request_id={request_id}, "
            f"orchestrator={orchestrator_name}"
        )
    
    validate_trace_completeness(trace)
    return trace


def get_recent_state_changes(
    db: Session,
    since: datetime,
    model_class: type
) -> List[Any]:
    """
    Get all state changes (record creations) since a specific time.
    
    Args:
        db: Database session
        since: Timestamp to check from
        model_class: Model class to check (Baseline, DraftTimeline, etc.)
        
    Returns:
        List of records created since the timestamp
    """
    return db.query(model_class).filter(
        model_class.created_at >= since
    ).all()


def validate_state_changes_have_traces(
    db: Session,
    since: datetime,
    models_to_check: Optional[List[type]] = None
) -> Dict[str, Any]:
    """
    Validate that all state changes since a timestamp have corresponding traces.
    
    This ensures that no orchestrator mutated state without creating a trace.
    
    Args:
        db: Database session
        since: Timestamp to check from
        models_to_check: List of model classes to validate (default: all major models)
        
    Returns:
        Dictionary with validation results
        
    Raises:
        StateChangeWithoutTraceError: If any state change lacks a trace
    """
    if models_to_check is None:
        models_to_check = [Baseline, DraftTimeline, CommittedTimeline]
    
    results = {
        "timestamp": since,
        "models_checked": [],
        "violations": [],
        "summary": {}
    }
    
    # Get all traces since the timestamp
    all_traces = db.query(DecisionTrace).filter(
        DecisionTrace.started_at >= since
    ).all()
    
    trace_request_ids = {trace.request_id for trace in all_traces}
    
    # Check each model for state changes
    for model_class in models_to_check:
        model_name = model_class.__tablename__
        results["models_checked"].append(model_name)
        
        # Get all records created since timestamp
        recent_records = get_recent_state_changes(db, since, model_class)
        
        results["summary"][model_name] = {
            "total_records": len(recent_records),
            "records_without_traces": 0
        }
        
        # For each record, verify there's a corresponding IdempotencyKey/trace
        for record in recent_records:
            # Check if there's an IdempotencyKey that could have created this
            # Note: We check IdempotencyKey because it's created before state changes
            idempotency_keys = db.query(IdempotencyKey).filter(
                and_(
                    IdempotencyKey.user_id == record.user_id,
                    IdempotencyKey.created_at <= record.created_at,
                    IdempotencyKey.status.in_(["COMPLETED", "FAILED"])
                )
            ).order_by(desc(IdempotencyKey.created_at)).all()
            
            # Check if any of these keys have a corresponding trace
            found_trace = False
            for key in idempotency_keys:
                if key.request_id in trace_request_ids:
                    # Verify the trace is complete
                    try:
                        validate_trace_for_request(
                            db,
                            key.request_id,
                            key.orchestrator_name
                        )
                        found_trace = True
                        break
                    except TraceValidationError:
                        # Trace exists but is incomplete
                        pass
            
            if not found_trace:
                violation = {
                    "model": model_name,
                    "record_id": str(record.id),
                    "created_at": record.created_at.isoformat(),
                    "user_id": str(record.user_id)
                }
                results["violations"].append(violation)
                results["summary"][model_name]["records_without_traces"] += 1
    
    # Raise error if violations found
    if results["violations"]:
        violation_summary = "\n".join(
            f"  - {v['model']} record {v['record_id']} (created {v['created_at']})"
            for v in results["violations"]
        )
        raise StateChangeWithoutTraceError(
            f"Found {len(results['violations'])} state changes without traces:\n"
            f"{violation_summary}"
        )
    
    return results


def validate_all_traces_complete(
    db: Session,
    orchestrator_name: Optional[str] = None,
    since: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Validate that all DecisionTraces in the database are complete.
    
    Args:
        db: Database session
        orchestrator_name: Optional filter by orchestrator name
        since: Optional filter by timestamp
        
    Returns:
        Dictionary with validation results
        
    Raises:
        IncompleteTraceError: If any trace is incomplete
    """
    query = db.query(DecisionTrace)
    
    if orchestrator_name:
        query = query.filter(DecisionTrace.orchestrator_name == orchestrator_name)
    
    if since:
        query = query.filter(DecisionTrace.started_at >= since)
    
    traces = query.all()
    
    results = {
        "total_traces": len(traces),
        "incomplete_traces": [],
        "errors": {}
    }
    
    for trace in traces:
        try:
            validate_trace_completeness(trace)
        except IncompleteTraceError as e:
            results["incomplete_traces"].append(trace.request_id)
            results["errors"][trace.request_id] = str(e)
    
    if results["incomplete_traces"]:
        error_details = "\n\n".join(
            f"Request ID: {req_id}\n{results['errors'][req_id]}"
            for req_id in results["incomplete_traces"]
        )
        raise IncompleteTraceError(
            f"Found {len(results['incomplete_traces'])} incomplete traces:\n\n"
            f"{error_details}"
        )
    
    return results


def validate_step_order(execution_steps: List[Dict[str, Any]]) -> None:
    """
    Validate that execution steps have proper sequential ordering.
    
    Args:
        execution_steps: List of execution step dictionaries
        
    Raises:
        TraceValidationError: If step order is invalid
    """
    if not execution_steps:
        raise TraceValidationError("execution_steps is empty")
    
    expected_step = 1
    for step in execution_steps:
        if "step_number" not in step:
            raise TraceValidationError(f"Step missing step_number: {step}")
        
        if step["step_number"] != expected_step:
            raise TraceValidationError(
                f"Step order violation: expected step {expected_step}, "
                f"found step {step['step_number']}"
            )
        
        expected_step += 1


def validate_hash_consistency(
    input_data: Dict[str, Any],
    stored_input_hash: str
) -> None:
    """
    Validate that stored input hash matches computed hash.
    
    Args:
        input_data: Original input data
        stored_input_hash: Hash stored in DecisionTrace
        
    Raises:
        TraceValidationError: If hashes don't match
    """
    import hashlib
    import json
    
    # Compute hash of input data
    input_json = json.dumps(input_data, sort_keys=True, default=str)
    computed_hash = hashlib.sha256(input_json.encode()).hexdigest()
    
    if computed_hash != stored_input_hash:
        raise TraceValidationError(
            f"Input hash mismatch: stored={stored_input_hash}, "
            f"computed={computed_hash}"
        )


def get_orchestrator_execution_summary(
    db: Session,
    orchestrator_name: str,
    since: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Get summary of orchestrator executions with trace validation.
    
    Args:
        db: Database session
        orchestrator_name: Name of the orchestrator
        since: Optional timestamp filter
        
    Returns:
        Summary dictionary with execution statistics
    """
    query = db.query(DecisionTrace).filter(
        DecisionTrace.orchestrator_name == orchestrator_name
    )
    
    if since:
        query = query.filter(DecisionTrace.started_at >= since)
    
    traces = query.all()
    
    summary = {
        "orchestrator": orchestrator_name,
        "total_executions": len(traces),
        "completed": 0,
        "failed": 0,
        "processing": 0,
        "avg_duration_ms": 0,
        "incomplete_traces": 0,
        "traces_with_errors": []
    }
    
    durations = []
    
    for trace in traces:
        if trace.status == "COMPLETED":
            summary["completed"] += 1
        elif trace.status == "FAILED":
            summary["failed"] += 1
        elif trace.status == "PROCESSING":
            summary["processing"] += 1
        
        if trace.duration_ms:
            durations.append(trace.duration_ms)
        
        # Check trace completeness
        try:
            validate_trace_completeness(trace)
        except IncompleteTraceError as e:
            summary["incomplete_traces"] += 1
            summary["traces_with_errors"].append({
                "request_id": trace.request_id,
                "error": str(e)
            })
    
    if durations:
        summary["avg_duration_ms"] = sum(durations) / len(durations)
    
    return summary


# Convenience function for test usage
def assert_execution_has_complete_trace(
    db: Session,
    request_id: str,
    orchestrator_name: str
) -> DecisionTrace:
    """
    Assert that an execution has a complete trace. Use in tests.
    
    Args:
        db: Database session
        request_id: Request identifier
        orchestrator_name: Orchestrator name
        
    Returns:
        Validated DecisionTrace
        
    Raises:
        AssertionError: If trace is missing or incomplete
    """
    try:
        trace = validate_trace_for_request(db, request_id, orchestrator_name)
        return trace
    except TraceValidationError as e:
        raise AssertionError(f"Trace validation failed: {e}") from e


# Convenience function for runtime checks
def ensure_no_untraced_mutations(
    db: Session,
    since: datetime,
    models: Optional[List[type]] = None
) -> None:
    """
    Ensure no state mutations occurred without traces. Use in production monitoring.
    
    Args:
        db: Database session
        since: Timestamp to check from
        models: Optional list of models to check
        
    Raises:
        StateChangeWithoutTraceError: If untraced mutations found
    """
    validate_state_changes_have_traces(db, since, models)
