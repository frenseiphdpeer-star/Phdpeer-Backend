"""
Base Orchestrator

Abstract base class for all orchestrators with built-in support for:
- Idempotency (prevents duplicate operations)
- Decision tracing (audit trail of decisions)
- Evidence bundling (explainability of decisions)
- Deterministic pipeline execution

All feature orchestrators should extend this class.
"""

import uuid
import time
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypeVar, Generic
from datetime import datetime, timedelta
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.idempotency import (
    IdempotencyKey,
    DecisionTrace,
    EvidenceBundle,
    RequestStatus
)
from app.utils.invariants import (
    check_no_duplicate_execution,
    validate_request_id,
    validate_orchestrator_name,
    DuplicateExecutionError
)


# Type variable for orchestrator result
T = TypeVar('T')


class ExecutionStep:
    """Represents a single execution step in the trace"""
    def __init__(self, action: str, step_number: int):
        self.step = step_number
        self.action = action
        self.status = "in_progress"
        self.started_at = datetime.utcnow().isoformat()
        self.completed_at = None
        self.duration_ms = None
        self.details = {}
        self.error = None
        self._start_time = time.time()
    
    def complete(self, status: str = "success", details: Optional[Dict[str, Any]] = None):
        """Mark step as completed"""
        self.status = status
        self.completed_at = datetime.utcnow().isoformat()
        self.duration_ms = int((time.time() - self._start_time) * 1000)
        if details:
            self.details = details
    
    def fail(self, error: str, details: Optional[Dict[str, Any]] = None):
        """Mark step as failed"""
        self.status = "failed"
        self.completed_at = datetime.utcnow().isoformat()
        self.duration_ms = int((time.time() - self._start_time) * 1000)
        self.error = error
        if details:
            self.details = details
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "step": self.step,
            "action": self.action,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
        }
        if self.details:
            result["details"] = self.details
        if self.error:
            result["error"] = self.error
        return result


class EvidenceCollector:
    """Collects evidence during orchestration"""
    def __init__(self, event_id: str, orchestrator_name: str):
        self.event_id = event_id
        self.orchestrator_name = orchestrator_name
        self.evidence_items = []
        self.metadata = {}
    
    def add(
        self,
        evidence_type: str,
        data: Any,
        source: Optional[str] = None,
        confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Add an evidence item"""
        evidence_item = {
            "type": evidence_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        if source:
            evidence_item["source"] = source
        if confidence is not None:
            evidence_item["confidence"] = confidence
        if metadata:
            evidence_item["metadata"] = metadata
        
        self.evidence_items.append(evidence_item)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "evidence": self.evidence_items,
            "metadata": self.metadata
        }


class OrchestrationError(Exception):
    """Base exception for orchestration errors"""
    pass


class DuplicateRequestError(OrchestrationError):
    """Raised when a duplicate request is detected and still processing"""
    pass


class BaseOrchestrator(ABC, Generic[T]):
    """
    Abstract base orchestrator with idempotency and traceability.
    
    Subclasses must implement:
    - orchestrator_name: str property
    - _execute_pipeline(context: Dict[str, Any]) -> T method
    
    Usage:
        class MyOrchestrator(BaseOrchestrator[MyResult]):
            @property
            def orchestrator_name(self) -> str:
                return "my_orchestrator"
            
            def _execute_pipeline(self, context: Dict[str, Any]) -> MyResult:
                # Implementation here
                return result
        
        orchestrator = MyOrchestrator(db, user_id)
        result = orchestrator.execute(request_id, input_data)
    """
    
    def __init__(self, db: Session, user_id: Optional[uuid.UUID] = None):
        """
        Initialize base orchestrator.
        
        Args:
            db: Database session
            user_id: Optional user ID for this operation
        """
        self.db = db
        self.user_id = user_id
        self._start_time = None
        self._current_request_id = None
        self._execution_steps: List[ExecutionStep] = []
        self._evidence_collector: Optional[EvidenceCollector] = None
        self._step_counter = 0
    
    @property
    @abstractmethod
    def orchestrator_name(self) -> str:
        """
        Name of this orchestrator (must be unique across all orchestrators).
        
        Returns:
            Orchestrator name (e.g., "baseline_orchestrator")
        """
        pass
    
    @abstractmethod
    def _execute_pipeline(self, context: Dict[str, Any]) -> T:
        """
        Execute the orchestration pipeline.
        
        This method contains the core business logic of the orchestrator.
        It should be deterministic and idempotent.
        
        Args:
            context: Execution context with input data and configuration
        
        Returns:
            Result of the orchestration
        
        Raises:
            OrchestrationError: If orchestration fails
        """
        pass
    
    def execute(
        self,
        request_id: str,
        input_data: Dict[str, Any],
        ttl_hours: int = 24
    ) -> T:
        """
        Execute the orchestration with idempotency guarantees.
        
        Executes steps in a fixed, explicit order:
        1. Check idempotency key in database
        2. If duplicate completed request: return cached response
        3. If duplicate in-flight request: raise error
        4. Create new idempotency key record
        5. Mark as processing
        6. Execute pipeline with step-by-step tracing
        7. Serialize result
        8. Persist DecisionTrace (structured JSON)
        9. Mark as completed and cache response
        
        Args:
            request_id: Unique request identifier (idempotency key)
            input_data: Input data for the orchestration
            ttl_hours: Time-to-live for cached response (hours)
        
        Returns:
            Result of the orchestration
        
        Raises:
            DuplicateRequestError: If request is already being processed
            OrchestrationError: If orchestration fails
        """
        # Validate inputs (fail fast)
        try:
            validate_request_id(request_id)
            validate_orchestrator_name(self.orchestrator_name)
        except ValueError as e:
            raise OrchestrationError(f"Invalid input: {str(e)}") from e
        
        self._current_request_id = request_id
        self._start_time = time.time()
        self._execution_steps = []
        self._evidence_collector = EvidenceCollector(request_id, self.orchestrator_name)
        self._step_counter = 0
        
        try:
            # Step 1: Check idempotency key in database
            with self._trace_step("check_idempotency"):
                existing_key = self._get_idempotency_key(request_id)
                
                if existing_key:
                    # Handle duplicate request based on status
                    cached_result = self._handle_duplicate_request(existing_key)
                    if cached_result is not None:
                        # Return cached result (COMPLETED case)
                        return cached_result
                    # If None, failed record was deleted and we proceed with new execution
                
                # Step 1b: Global invariant check - No duplicate execution (for in-flight only)
                # This ensures no PROCESSING duplicates slip through
                if not existing_key or existing_key.status != RequestStatus.COMPLETED:
                    try:
                        check_no_duplicate_execution(
                            db=self.db,
                            request_id=request_id,
                            orchestrator_name=self.orchestrator_name,
                            allow_completed=False  # Fail on PROCESSING duplicates
                        )
                    except DuplicateExecutionError as e:
                        # Fail fast with explicit error
                        raise OrchestrationError(f"Duplicate execution prevented: {str(e)}") from e
            
            # Step 3: Create new idempotency key record
            with self._trace_step("create_idempotency_key"):
                idempotency_key = self._create_idempotency_key(
                    request_id=request_id,
                    input_data=input_data,
                    ttl_hours=ttl_hours
                )
            
            # Step 4: Mark as processing
            with self._trace_step("mark_processing"):
                self._update_status(idempotency_key, RequestStatus.PROCESSING)
            
            try:
                # Step 5: Prepare execution context
                with self._trace_step("prepare_context"):
                    context = self._prepare_context(input_data)
                
                # Step 6: Execute the pipeline
                with self._trace_step("execute_pipeline"):
                    result = self._execute_pipeline(context)
                
                # Step 7: Serialize result for caching
                with self._trace_step("serialize_result"):
                    response_data = self._serialize_result(result)
                
                # Step 8: Persist DecisionTrace (structured JSON)
                with self._trace_step("persist_trace"):
                    self._persist_trace_and_evidence()
                
                # Step 9: Mark as completed and cache response
                with self._trace_step("complete_request"):
                    self._complete_request(
                        idempotency_key=idempotency_key,
                        response_data=response_data,
                        result=result
                    )
                
                self.db.commit()
                return result
                
            except Exception as e:
                # Mark as failed and persist trace
                with self._trace_step("handle_error"):
                    self._persist_trace_and_evidence(error=str(e))
                    self._fail_request(idempotency_key, e)
                
                self.db.commit()
                raise
        
        except DuplicateRequestError:
            # Don't rollback for duplicate requests
            raise
        except Exception as e:
            self.db.rollback()
            raise OrchestrationError(f"Orchestration failed: {str(e)}") from e
    
    def _get_idempotency_key(self, request_id: str) -> Optional[IdempotencyKey]:
        """Get existing idempotency key if it exists"""
        return self.db.query(IdempotencyKey).filter(
            and_(
                IdempotencyKey.request_id == request_id,
                IdempotencyKey.orchestrator_name == self.orchestrator_name
            )
        ).first()
    
    def _handle_duplicate_request(self, existing_key: IdempotencyKey) -> Optional[T]:
        """
        Handle duplicate request based on current status.
        
        - COMPLETED: Return cached response
        - PROCESSING: Raise error (duplicate in-flight)
        - FAILED: Delete failed record and return None to allow retry
        - PENDING: Should not happen, raise error
        
        Returns:
            Cached result if COMPLETED, None if FAILED (allows retry), raises error otherwise
        """
        if existing_key.status == RequestStatus.COMPLETED:
            # Return cached response
            if existing_key.response_data:
                return self._deserialize_result(existing_key.response_data)
            else:
                raise OrchestrationError("Completed request has no cached response")
        
        elif existing_key.status == RequestStatus.PROCESSING:
            # Duplicate in-flight request
            raise DuplicateRequestError(
                f"Request {existing_key.request_id} is already being processed"
            )
        
        elif existing_key.status == RequestStatus.FAILED:
            # Allow retry by deleting the failed record
            self.db.delete(existing_key)
            self.db.flush()
            # Return None to indicate we should proceed with new execution
            return None
        
        else:
            # Pending status should not exist for long
            raise OrchestrationError(
                f"Request {existing_key.request_id} is in unexpected state: {existing_key.status}"
            )
    
    def _create_idempotency_key(
        self,
        request_id: str,
        input_data: Dict[str, Any],
        ttl_hours: int
    ) -> IdempotencyKey:
        """Create new idempotency key record"""
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
        
        idempotency_key = IdempotencyKey(
            request_id=request_id,
            orchestrator_name=self.orchestrator_name,
            user_id=self.user_id,
            status=RequestStatus.PENDING,
            request_payload=input_data,
            expires_at=expires_at,
            created_at=datetime.utcnow()
        )
        
        self.db.add(idempotency_key)
        self.db.flush()
        
        return idempotency_key
    
    def _update_status(self, idempotency_key: IdempotencyKey, status: RequestStatus):
        """Update idempotency key status"""
        idempotency_key.status = status
        
        if status == RequestStatus.PROCESSING:
            idempotency_key.started_at = datetime.utcnow()
        elif status in (RequestStatus.COMPLETED, RequestStatus.FAILED):
            idempotency_key.completed_at = datetime.utcnow()
        
        self.db.flush()
    
    def _complete_request(
        self,
        idempotency_key: IdempotencyKey,
        response_data: Dict[str, Any],
        result: T
    ):
        """Mark request as completed and cache response"""
        self._update_status(idempotency_key, RequestStatus.COMPLETED)
        
        idempotency_key.response_data = response_data
        
        # Store reference to created resource if result has an ID
        if hasattr(result, 'id'):
            idempotency_key.result_resource_id = result.id
            idempotency_key.result_resource_type = result.__class__.__name__
        
        self.db.flush()
    
    def _fail_request(self, idempotency_key: IdempotencyKey, error: Exception):
        """Mark request as failed"""
        self._update_status(idempotency_key, RequestStatus.FAILED)
        
        idempotency_key.error_message = str(error)
        idempotency_key.error_details = {
            'error_type': type(error).__name__,
            'error_message': str(error)
        }
        
        self.db.flush()
    
    def _prepare_context(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare execution context.
        
        Subclasses can override to add custom context preparation.
        """
        return {
            'input': input_data,
            'user_id': self.user_id,
            'request_id': self._current_request_id,
            'orchestrator': self.orchestrator_name
        }
    
    def _serialize_result(self, result: T) -> Dict[str, Any]:
        """
        Serialize result for caching.
        
        Subclasses should override for custom serialization.
        Default implementation works for objects with __dict__.
        """
        if hasattr(result, '__dict__'):
            # Simple serialization for SQLAlchemy models and dataclasses
            serialized = {}
            for key, value in result.__dict__.items():
                if key.startswith('_'):
                    continue
                if isinstance(value, (str, int, float, bool, type(None))):
                    serialized[key] = value
                elif isinstance(value, uuid.UUID):
                    serialized[key] = str(value)
                elif isinstance(value, datetime):
                    serialized[key] = value.isoformat()
            return serialized
        elif isinstance(result, dict):
            return result
        else:
            return {'result': str(result)}
    
    def _deserialize_result(self, response_data: Dict[str, Any]) -> T:
        """
        Deserialize cached result.
        
        Subclasses should override for custom deserialization.
        Default implementation returns the dict as-is.
        """
        return response_data  # type: ignore
    
    # Execution Tracing Methods
    
    @contextmanager
    def _trace_step(self, action: str):
        """
        Context manager for automatic step tracing.
        
        Usage:
            with self._trace_step("validate_input"):
                # do validation
                pass
        """
        self._step_counter += 1
        step = ExecutionStep(action, self._step_counter)
        self._execution_steps.append(step)
        
        try:
            yield step
            step.complete()
        except Exception as e:
            step.fail(str(e))
            raise
    
    def log_step(
        self,
        action: str,
        status: str = "success",
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Manually log an execution step.
        
        Args:
            action: Description of the action
            status: Status of the step (success, failed, skipped, etc.)
            details: Additional details about the step
        """
        self._step_counter += 1
        step = ExecutionStep(action, self._step_counter)
        step.complete(status, details)
        self._execution_steps.append(step)
    
    def add_evidence(
        self,
        evidence_type: str,
        data: Any,
        source: Optional[str] = None,
        confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Add evidence to the evidence collector.
        
        Args:
            evidence_type: Type of evidence (e.g., "document_text", "analysis_result")
            data: The evidence data (will be JSON serialized)
            source: Source of the evidence (e.g., "DocumentArtifact:uuid")
            confidence: Confidence score (0.0 to 1.0)
            metadata: Additional metadata
        """
        if self._evidence_collector:
            self._evidence_collector.add(evidence_type, data, source, confidence, metadata)
    
    def _persist_trace_and_evidence(self, error: Optional[str] = None):
        """
        Persist execution trace and evidence to database.
        
        Automatically writes DecisionTrace and EvidenceBundle records.
        Pure structured storage - no UI formatting.
        
        Args:
            error: Error message if execution failed
        """
        # Build trace JSON (pure structured data)
        trace_json = {
            "started_at": datetime.fromtimestamp(self._start_time).isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "duration_ms": self.get_elapsed_time_ms(),
            "steps": [step.to_dict() for step in self._execution_steps],
            "result": "failed" if error else "success",
            "metadata": {
                "user_id": str(self.user_id) if self.user_id else None,
                "total_steps": len(self._execution_steps)
            }
        }
        
        if error:
            trace_json["error"] = error
        
        # Create DecisionTrace record
        decision_trace = DecisionTrace(
            request_id=self._current_request_id,
            orchestrator_name=self.orchestrator_name,
            trace_json=trace_json,
            created_at=datetime.utcnow()
        )
        self.db.add(decision_trace)
        self.db.flush()  # Flush to get the ID
        
        # Create EvidenceBundle record if there's evidence
        if self._evidence_collector and self._evidence_collector.evidence_items:
            evidence_bundle = EvidenceBundle(
                decision_trace_id=decision_trace.id,
                evidence_json=self._evidence_collector.to_dict()
            )
            self.db.add(evidence_bundle)
        
        self.db.flush()
    
    # Utility Methods
    
    def get_elapsed_time_ms(self) -> int:
        """Get elapsed time since orchestration started in milliseconds"""
        if self._start_time:
            return int((time.time() - self._start_time) * 1000)
        return 0
