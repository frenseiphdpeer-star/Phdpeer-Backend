"""
Idempotency Models

Models for handling idempotent operations and request deduplication.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, Float, ForeignKey
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
import enum

from app.database import Base


class RequestStatus(str, enum.Enum):
    """Status of an idempotent request"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class IdempotencyKey(Base):
    """
    Tracks idempotent requests to prevent duplicate operations.
    
    When an orchestrator receives a request with a request_id, it checks this table:
    - If request_id exists and status is COMPLETED: return cached response
    - If request_id exists and status is PROCESSING: wait or reject (duplicate in-flight)
    - If request_id exists and status is FAILED: allow retry
    - If request_id doesn't exist: proceed with operation
    """
    __tablename__ = "idempotency_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Unique request identifier provided by client
    request_id = Column(String(255), unique=True, nullable=False, index=True)
    
    # Orchestrator that processed this request
    orchestrator_name = Column(String(100), nullable=False, index=True)
    
    # User who made the request
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    
    # Request status
    status = Column(
        SQLEnum(RequestStatus, name="request_status"),
        nullable=False,
        default=RequestStatus.PENDING,
        index=True
    )
    
    # Request payload (for audit and debugging)
    request_payload = Column(JSONB, nullable=True)
    
    # Response data (cached for duplicate requests)
    response_data = Column(JSONB, nullable=True)
    
    # Error information if failed
    error_message = Column(Text, nullable=True)
    error_details = Column(JSONB, nullable=True)
    
    # Timing information
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Reference to the created resource (if applicable)
    result_resource_type = Column(String(50), nullable=True)
    result_resource_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    
    # TTL for cleanup (optional)
    expires_at = Column(DateTime, nullable=True, index=True)

    def __repr__(self):
        return f"<IdempotencyKey(request_id='{self.request_id}', status='{self.status}')>"


class DecisionTrace(Base):
    """
    Audit trail of orchestration execution.
    
    Stores step-by-step execution logs as structured JSON in trace_json.
    Pure structured storage - no UI formatting.
    """
    __tablename__ = "decision_traces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Request identifier (idempotency key)
    request_id = Column(String(255), nullable=False, index=True)
    
    # Orchestrator that created this trace
    orchestrator_name = Column(String(100), nullable=False, index=True)
    
    # Complete execution trace as structured JSON
    trace_json = Column(JSONB, nullable=False)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<DecisionTrace(request_id='{self.request_id}', orchestrator='{self.orchestrator_name}')>"


class EvidenceBundle(Base):
    """
    Evidence used during orchestration.
    
    Stores evidence snippets as structured JSON in evidence_json.
    Linked to DecisionTrace via foreign key.
    Pure structured storage - no UI formatting.
    """
    __tablename__ = "evidence_bundles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Foreign key to DecisionTrace
    decision_trace_id = Column(UUID(as_uuid=True), ForeignKey('decision_traces.id'), nullable=False, index=True)
    
    # Complete evidence bundle as structured JSON
    evidence_json = Column(JSONB, nullable=False)

    def __repr__(self):
        return f"<EvidenceBundle(decision_trace_id='{self.decision_trace_id}')>"
