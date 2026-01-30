"""Baseline orchestrator for creating and managing baseline records."""
from datetime import date
from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.baseline import Baseline
from app.models.user import User
from app.models.document_artifact import DocumentArtifact
from app.orchestrators.base import BaseOrchestrator, OrchestrationError


class BaselineOrchestratorError(OrchestrationError):
    """Base exception for baseline orchestrator errors."""
    pass


class BaselineAlreadyExistsError(BaselineOrchestratorError):
    """Raised when attempting to create a baseline when one already exists."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


class BaselineOrchestrator(BaseOrchestrator[Dict[str, Any]]):
    """
    Orchestrator for creating and managing baseline records.
    
    Baselines are immutable once created. They represent the initial
    state and requirements of a PhD program.
    
    Extends BaseOrchestrator for:
    - Idempotency (prevents duplicate baseline creation)
    - Decision tracing (audit trail)
    - Evidence bundling (explainability)
    """
    
    @property
    def orchestrator_name(self) -> str:
        """Return orchestrator name for tracing."""
        return "baseline_orchestrator"
    
    def create(
        self,
        request_id: str,
        user_id: UUID,
        program_name: str,
        institution: str,
        field_of_study: str,
        start_date: date,
        document_id: Optional[UUID] = None,
        expected_end_date: Optional[date] = None,
        total_duration_months: Optional[int] = None,
        requirements_summary: Optional[str] = None,
        research_area: Optional[str] = None,
        advisor_info: Optional[str] = None,
        funding_status: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new immutable baseline record.
        
        Steps:
        1. Validate document exists (if provided)
        2. Ensure no baseline already exists for user
        3. Create immutable Baseline record
        4. Write DecisionTrace (via BaseOrchestrator)
        
        Args:
            request_id: Unique request identifier (idempotency key)
            user_id: ID of the user creating the baseline
            program_name: Name of the PhD program
            institution: Academic institution
            field_of_study: Research field/discipline
            start_date: Program start date
            document_id: Optional reference to source document
            expected_end_date: Expected completion date
            total_duration_months: Expected duration in months
            requirements_summary: Summary of program requirements
            research_area: Specific research area/topic
            advisor_info: Information about advisor(s)
            funding_status: Funding information
            notes: Additional notes
            
        Returns:
            Dictionary with baseline_id and metadata
            
        Raises:
            BaselineOrchestratorError: If validation fails
            BaselineAlreadyExistsError: If baseline already exists
        """
        input_data = {
            "user_id": str(user_id),
            "program_name": program_name,
            "institution": institution,
            "field_of_study": field_of_study,
            "start_date": start_date.isoformat() if start_date else None,
            "document_id": str(document_id) if document_id else None,
            "expected_end_date": expected_end_date.isoformat() if expected_end_date else None,
            "total_duration_months": total_duration_months,
            "requirements_summary": requirements_summary,
            "research_area": research_area,
            "advisor_info": advisor_info,
            "funding_status": funding_status,
            "notes": notes,
        }
        
        return self.execute(request_id=request_id, input_data=input_data)
    
    def _execute_pipeline(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the baseline creation pipeline.
        
        Steps:
        1. Validate document exists (if provided)
        2. Ensure no baseline already exists
        3. Create immutable Baseline record
        
        Args:
            context: Execution context with input data
            
        Returns:
            Dictionary with baseline_id and metadata
        """
        input_data = context['input']
        user_id = UUID(input_data['user_id'])
        
        # Step 1: Validate document exists (if provided)
        with self._trace_step("validate_document") as step:
            document_id = input_data.get('document_id')
            document = None
            
            if document_id:
                document_id_uuid = UUID(document_id)
                document = self.db.query(DocumentArtifact).filter(
                    DocumentArtifact.id == document_id_uuid
                ).first()
                
                if not document:
                    raise BaselineOrchestratorError(
                        f"Document with ID {document_id} not found"
                    )
                
                if document.user_id != user_id:
                    raise BaselineOrchestratorError(
                        f"Document {document_id} does not belong to user {user_id}"
                    )
                
                step.details = {
                    "document_id": document_id,
                    "document_title": document.title,
                    "document_type": document.document_type
                }
                
                self.add_evidence(
                    evidence_type="document_artifact",
                    data={
                        "document_id": document_id,
                        "title": document.title,
                        "file_type": document.file_type,
                        "word_count": document.word_count
                    },
                    source=f"DocumentArtifact:{document_id}",
                    confidence=1.0
                )
            else:
                step.details = {"document_id": None, "has_document": False}
        
        # Step 2: Ensure no baseline already exists
        with self._trace_step("check_existing_baseline") as step:
            existing_baseline = self.db.query(Baseline).filter(
                Baseline.user_id == user_id
            ).first()
            
            if existing_baseline:
                raise BaselineAlreadyExistsError(
                    f"Baseline already exists for user {user_id}. "
                    f"Baselines are immutable and cannot be modified. "
                    f"Existing baseline ID: {existing_baseline.id}",
                    details={
                        "user_id": str(user_id),
                        "existing_baseline_id": str(existing_baseline.id),
                        "program_name": existing_baseline.program_name,
                        "institution": existing_baseline.institution
                    }
                )
            
            step.details = {"has_existing_baseline": False}
        
        # Step 3: Create immutable Baseline record
        with self._trace_step("create_baseline") as step:
            baseline = Baseline(
                user_id=user_id,
                document_artifact_id=UUID(input_data['document_id']) if input_data.get('document_id') else None,
                program_name=input_data['program_name'],
                institution=input_data['institution'],
                field_of_study=input_data['field_of_study'],
                start_date=date.fromisoformat(input_data['start_date']),
                expected_end_date=date.fromisoformat(input_data['expected_end_date']) if input_data.get('expected_end_date') else None,
                total_duration_months=input_data.get('total_duration_months'),
                requirements_summary=input_data.get('requirements_summary'),
                research_area=input_data.get('research_area'),
                advisor_info=input_data.get('advisor_info'),
                funding_status=input_data.get('funding_status'),
                notes=input_data.get('notes'),
            )
            
            self.db.add(baseline)
            self.db.flush()
            
            step.details = {
                "baseline_id": str(baseline.id),
                "program_name": baseline.program_name,
                "institution": baseline.institution,
                "field_of_study": baseline.field_of_study
            }
            
            self.add_evidence(
                evidence_type="baseline_created",
                data={
                    "baseline_id": str(baseline.id),
                    "program_name": baseline.program_name,
                    "institution": baseline.institution,
                    "field_of_study": baseline.field_of_study,
                    "start_date": baseline.start_date.isoformat() if baseline.start_date else None
                },
                source=f"Baseline:{baseline.id}",
                confidence=1.0
            )
        
        return {
            "baseline_id": str(baseline.id),
            "program_name": baseline.program_name,
            "institution": baseline.institution,
            "field_of_study": baseline.field_of_study,
            "created_at": baseline.created_at.isoformat() if baseline.created_at else None
        }
    
    def create_baseline(
        self,
        user_id: UUID,
        program_name: str,
        institution: str,
        field_of_study: str,
        start_date: date,
        document_id: Optional[UUID] = None,
        expected_end_date: Optional[date] = None,
        total_duration_months: Optional[int] = None,
        requirements_summary: Optional[str] = None,
        research_area: Optional[str] = None,
        advisor_info: Optional[str] = None,
        funding_status: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> UUID:
        """
        Create a new baseline record.
        
        Args:
            user_id: ID of the user creating the baseline
            program_name: Name of the PhD program
            institution: Academic institution
            field_of_study: Research field/discipline
            start_date: Program start date
            document_id: Optional reference to source document
            expected_end_date: Expected completion date
            total_duration_months: Expected duration in months
            requirements_summary: Summary of program requirements
            research_area: Specific research area/topic
            advisor_info: Information about advisor(s)
            funding_status: Funding information
            notes: Additional notes
            
        Returns:
            UUID of the created Baseline
            
        Raises:
            BaselineOrchestratorError: If validation fails
        """
        # Verify user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise BaselineOrchestratorError(f"User with ID {user_id} not found")
        
        # Verify document exists and belongs to user (if provided)
        if document_id:
            document = self.db.query(DocumentArtifact).filter(
                DocumentArtifact.id == document_id
            ).first()
            
            if not document:
                raise BaselineOrchestratorError(f"Document with ID {document_id} not found")
            
            if document.user_id != user_id:
                raise BaselineOrchestratorError(
                    f"Document {document_id} does not belong to user {user_id}"
                )
        
        # Create baseline record
        baseline = Baseline(
            user_id=user_id,
            document_artifact_id=document_id,
            program_name=program_name,
            institution=institution,
            field_of_study=field_of_study,
            start_date=start_date,
            expected_end_date=expected_end_date,
            total_duration_months=total_duration_months,
            requirements_summary=requirements_summary,
            research_area=research_area,
            advisor_info=advisor_info,
            funding_status=funding_status,
            notes=notes,
        )
        
        self.db.add(baseline)
        self.db.commit()
        self.db.refresh(baseline)
        
        return baseline.id
    
    def get_baseline(self, baseline_id: UUID) -> Optional[Baseline]:
        """
        Get a baseline by ID.
        
        Args:
            baseline_id: Baseline ID
            
        Returns:
            Baseline or None if not found
        """
        return self.db.query(Baseline).filter(
            Baseline.id == baseline_id
        ).first()
    
    def get_user_baselines(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 100
    ) -> list[Baseline]:
        """
        Get all baselines for a user.
        
        Args:
            user_id: User ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of Baselines
        """
        return self.db.query(Baseline).filter(
            Baseline.user_id == user_id
        ).order_by(Baseline.created_at.desc()).offset(skip).limit(limit).all()
    
    def verify_baseline_ownership(
        self,
        baseline_id: UUID,
        user_id: UUID
    ) -> bool:
        """
        Verify that a baseline belongs to a specific user.
        
        Args:
            baseline_id: Baseline ID
            user_id: User ID
            
        Returns:
            True if baseline belongs to user, False otherwise
        """
        baseline = self.get_baseline(baseline_id)
        if not baseline:
            return False
        return baseline.user_id == user_id
    
    def get_baseline_with_document(self, baseline_id: UUID) -> Optional[dict]:
        """
        Get baseline with associated document information.
        
        Args:
            baseline_id: Baseline ID
            
        Returns:
            Dictionary with baseline and document info, or None if not found
        """
        baseline = self.db.query(Baseline).filter(
            Baseline.id == baseline_id
        ).first()
        
        if not baseline:
            return None
        
        result = {
            "baseline": baseline,
            "document": None,
        }
        
        if baseline.document_artifact_id:
            document = self.db.query(DocumentArtifact).filter(
                DocumentArtifact.id == baseline.document_artifact_id
            ).first()
            result["document"] = document
        
        return result
    
    def delete_baseline(self, baseline_id: UUID, user_id: UUID) -> bool:
        """
        Delete a baseline.
        
        Note: Baselines are immutable, but can be deleted by their owner.
        Deletion will cascade to dependent records (draft timelines).
        
        Args:
            baseline_id: Baseline ID
            user_id: User ID (for ownership verification)
            
        Returns:
            True if deleted, False if not found or not owned by user
            
        Raises:
            BaselineOrchestratorError: If baseline has committed timelines
        """
        baseline = self.get_baseline(baseline_id)
        
        if not baseline:
            return False
        
        if baseline.user_id != user_id:
            raise BaselineOrchestratorError(
                "Cannot delete baseline: not owned by user"
            )
        
        # Check if baseline is referenced by committed timelines
        from app.models.committed_timeline import CommittedTimeline
        committed_count = self.db.query(CommittedTimeline).filter(
            CommittedTimeline.baseline_id == baseline_id
        ).count()
        
        if committed_count > 0:
            raise BaselineOrchestratorError(
                f"Cannot delete baseline: {committed_count} committed timeline(s) reference it"
            )
        
        self.db.delete(baseline)
        self.db.commit()
        return True
