"""PhD Doctor orchestrator for journey health assessments."""
from typing import Dict, List, Optional, Any
from uuid import UUID
from datetime import date
from sqlalchemy.orm import Session
import json

from app.orchestrators.base import BaseOrchestrator
from app.models.journey_assessment import JourneyAssessment
from app.models.user import User
from app.models.questionnaire_draft import QuestionnaireDraft
from app.services.journey_health_engine import (
    JourneyHealthEngine,
    QuestionResponse,
    HealthDimension,
    JourneyHealthReport,
    HealthStatus,
)
from app.utils.invariants import check_assessment_has_submission


class PhDDoctorOrchestratorError(Exception):
    """Base exception for PhD Doctor orchestrator errors."""
    pass


class IncompleteSubmissionError(PhDDoctorOrchestratorError):
    """Raised when submission is incomplete."""
    pass


class PhDDoctorOrchestrator(BaseOrchestrator[Dict[str, Any]]):
    """
    Orchestrator for PhD journey health assessments.
    
    Rules:
    - Isolation from timeline: No timeline data access
    - Isolation from documents: No document data access
    - Questionnaire-only: Only uses questionnaire responses
    - Deterministic scoring: Pure rule-based calculations
    
    Steps:
    1. Validate completeness
    2. Compute scores
    3. Persist JourneyAssessment
    4. Write DecisionTrace (automatic via BaseOrchestrator)
    
    Extends BaseOrchestrator to provide:
    - Idempotent submission
    - Decision tracing
    - Evidence bundling
    """
    
    @property
    def orchestrator_name(self) -> str:
        """Return orchestrator name."""
        return "phd_doctor_orchestrator"
    
    def __init__(self, db: Session, user_id: Optional[UUID] = None):
        """
        Initialize PhD Doctor orchestrator.
        
        Args:
            db: Database session
            user_id: Optional user ID
        """
        super().__init__(db, user_id)
        self.health_engine = JourneyHealthEngine()
    
    def submit(
        self,
        request_id: str,
        user_id: UUID,
        responses: List[Dict[str, Any]],
        draft_id: Optional[UUID] = None,
        assessment_type: str = "self_assessment",
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Submit questionnaire with idempotency and tracing.
        
        Steps:
        1. Validate completeness
        2. Compute scores
        3. Persist JourneyAssessment
        4. Write DecisionTrace (automatic via BaseOrchestrator)
        
        Isolation:
        - No timeline access: Does not query or use timeline data
        - No document access: Does not query or use document data
        - Questionnaire-only: Only uses questionnaire responses
        
        Args:
            request_id: Idempotency key
            user_id: User ID
            responses: List of questionnaire responses
            draft_id: Optional draft ID to mark as submitted
            assessment_type: Type of assessment
            notes: Optional notes
            
        Returns:
            Assessment summary with scores and recommendations
            
        Raises:
            IncompleteSubmissionError: If submission incomplete
            PhDDoctorOrchestratorError: If validation fails
        """
        return self.execute(
            request_id=request_id,
            input_data={
                "user_id": str(user_id),
                "responses": responses,
                "draft_id": str(draft_id) if draft_id else None,
                "assessment_type": assessment_type,
                "notes": notes
            }
        )
    
    def _execute_pipeline(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the submission pipeline.
        
        Steps:
        1. Validate completeness
        2. Compute scores
        3. Persist JourneyAssessment
        4. Write DecisionTrace (automatic via BaseOrchestrator.execute())
        
        Isolation:
        - No timeline access: Does not query timeline data
        - No document access: Does not query document data
        - Questionnaire-only: Only uses questionnaire responses
        
        This is called by BaseOrchestrator.execute() which automatically
        writes DecisionTrace after successful completion.
        
        Args:
            context: Execution context with input data
            
        Returns:
            Assessment summary with scores and recommendations
        """
        user_id = UUID(context["user_id"])
        responses = context["responses"]
        draft_id = UUID(context["draft_id"]) if context.get("draft_id") else None
        assessment_type = context.get("assessment_type", "self_assessment")
        notes = context.get("notes")
        
        # Step 1: Validate completeness
        with self._trace_step("validate_completeness") as step:
            self._validate_submission(user_id, responses, draft_id)
            
            step.details = {
                "user_id": str(user_id),
                "total_responses": len(responses),
                "has_draft": draft_id is not None,
                "validation_passed": True
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="completeness_validation",
                data={
                    "valid": True,
                    "response_count": len(responses),
                    "has_draft": draft_id is not None
                },
                source=f"User:{user_id}",
                confidence=1.0
            )
        
        # Invariant check: No PhD Doctor score without submission
        check_assessment_has_submission(
            db=self.db,
            user_id=user_id,
            responses_count=len(responses),
            is_explicit_submission=True
        )
        
        # Convert responses to QuestionResponse objects
        question_responses = self._convert_responses(responses)
        
        # Step 2: Compute scores
        with self._trace_step("compute_scores") as step:
            # Isolation: Only uses questionnaire responses, no timeline/document access
            health_report = self.health_engine.assess_health(
                responses=question_responses,
                assessment_date=str(date.today())
            )
            
            step.details = {
                "overall_score": health_report.overall_score,
                "overall_status": health_report.overall_status.value,
                "dimensions_count": len(health_report.dimension_scores),
                "recommendations_count": len(health_report.recommendations)
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="computed_scores",
                data={
                    "overall_score": health_report.overall_score,
                    "overall_status": health_report.overall_status.value,
                    "dimension_scores": {
                        d.value: s.score 
                        for d, s in health_report.dimension_scores.items()
                    },
                    "isolation": "questionnaire_only"
                },
                source="JourneyHealthEngine",
                confidence=1.0
            )
        
        # Step 3: Persist JourneyAssessment
        with self._trace_step("persist_journey_assessment") as step:
            assessment_id = self._store_assessment(
                user_id=user_id,
                health_report=health_report,
                assessment_type=assessment_type,
                notes=notes
            )
            
            step.details = {
                "assessment_id": str(assessment_id),
                "assessment_type": assessment_type,
                "overall_score": health_report.overall_score
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="persisted_assessment",
                data={
                    "assessment_id": str(assessment_id),
                    "overall_score": health_report.overall_score,
                    "assessment_type": assessment_type
                },
                source=f"JourneyAssessment:{assessment_id}",
                confidence=1.0
            )
        
        # Mark draft as submitted (if provided) - optional step
        if draft_id:
            with self._trace_step("mark_draft_submitted") as step:
                self._mark_draft_submitted(draft_id, user_id, assessment_id)
                step.details = {"draft_id": str(draft_id)}
        
        # Step 4: Write DecisionTrace (automatic via BaseOrchestrator.execute())
        # The BaseOrchestrator.execute() method automatically writes DecisionTrace
        # after _execute_pipeline completes successfully
        
        # Generate summary for response
        summary = self._generate_summary(assessment_id, health_report)
        
        return summary
    
    def _validate_submission(
        self,
        user_id: UUID,
        responses: List[Dict[str, Any]],
        draft_id: Optional[UUID] = None
    ) -> None:
        """
        Validate completeness of submission.
        
        Rules:
        - User must exist
        - Minimum responses required
        - All responses must have required fields
        - Response values must be valid (1-5)
        - Draft must exist and not be submitted (if provided)
        
        Isolation: Only validates questionnaire data, no timeline/document access.
        
        Args:
            user_id: User ID
            responses: List of responses
            draft_id: Optional draft ID
            
        Raises:
            PhDDoctorOrchestratorError: If user not found
            IncompleteSubmissionError: If submission incomplete
        """
        # Verify user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise PhDDoctorOrchestratorError(f"User with ID {user_id} not found")
        
        # Validate minimum responses
        if not responses:
            raise IncompleteSubmissionError("No questionnaire responses provided")
        
        if len(responses) < 5:
            raise IncompleteSubmissionError(
                f"Insufficient responses: {len(responses)} provided, minimum 5 required"
            )
        
        # Validate all responses have required fields
        for i, resp in enumerate(responses):
            if "dimension" not in resp:
                raise IncompleteSubmissionError(f"Response {i} missing 'dimension' field")
            if "question_id" not in resp:
                raise IncompleteSubmissionError(f"Response {i} missing 'question_id' field")
            if "response_value" not in resp:
                raise IncompleteSubmissionError(f"Response {i} missing 'response_value' field")
            
            # Validate response value range
            value = resp["response_value"]
            if not isinstance(value, int) or value < 1 or value > 5:
                raise IncompleteSubmissionError(
                    f"Response {i} has invalid value {value}, must be 1-5"
                )
        
        # If draft provided, verify it exists and belongs to user
        if draft_id:
            draft = self.db.query(QuestionnaireDraft).filter(
                QuestionnaireDraft.id == draft_id,
                QuestionnaireDraft.user_id == user_id
            ).first()
            
            if not draft:
                raise PhDDoctorOrchestratorError(
                    f"Draft {draft_id} not found or not owned by user {user_id}"
                )
            
            if draft.is_submitted:
                raise PhDDoctorOrchestratorError(
                    f"Draft {draft_id} has already been submitted"
                )
    
    def _mark_draft_submitted(
        self,
        draft_id: UUID,
        user_id: UUID,
        assessment_id: UUID
    ) -> None:
        """
        Mark draft as submitted.
        
        Args:
            draft_id: Draft ID
            user_id: User ID
            assessment_id: Created assessment ID
        """
        draft = self.db.query(QuestionnaireDraft).filter(
            QuestionnaireDraft.id == draft_id,
            QuestionnaireDraft.user_id == user_id
        ).first()
        
        if draft:
            draft.is_submitted = True
            draft.submission_id = assessment_id
            self.db.add(draft)
            self.db.flush()
    
    def submit_questionnaire(
        self,
        user_id: UUID,
        responses: List[Dict[str, any]],
        assessment_type: str = "self_assessment",
        notes: Optional[str] = None,
    ) -> Dict:
        """
        Submit questionnaire and generate health assessment.
        
        Args:
            user_id: ID of user submitting questionnaire
            responses: List of response dictionaries with keys:
                - dimension: str (dimension name)
                - question_id: str
                - response_value: int (1-5)
                - question_text: str (optional)
            assessment_type: Type of assessment (self, advisor, quarterly, etc.)
            notes: Optional notes
            
        Returns:
            Dictionary with assessment summary
            
        Raises:
            PhDDoctorOrchestratorError: If validation fails
        """
        # Step 1: Verify user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise PhDDoctorOrchestratorError(f"User with ID {user_id} not found")
        
        # Step 2: Validate and convert responses
        question_responses = self._convert_responses(responses)
        
        if not question_responses:
            raise PhDDoctorOrchestratorError("No valid questionnaire responses provided")
        
        # Step 3: Call health engine
        health_report = self.health_engine.assess_health(
            responses=question_responses,
            assessment_date=str(date.today())
        )
        
        # Step 4: Store assessment in database
        assessment_id = self._store_assessment(
            user_id=user_id,
            health_report=health_report,
            assessment_type=assessment_type,
            notes=notes,
        )
        
        # Step 5: Generate summary for frontend
        summary = self._generate_summary(
            assessment_id=assessment_id,
            health_report=health_report,
        )
        
        return summary
    
    def get_assessment(
        self,
        assessment_id: UUID
    ) -> Optional[Dict]:
        """
        Get a stored assessment.
        
        Args:
            assessment_id: Assessment ID
            
        Returns:
            Assessment dictionary or None if not found
        """
        assessment = self.db.query(JourneyAssessment).filter(
            JourneyAssessment.id == assessment_id
        ).first()
        
        if not assessment:
            return None
        
        return self._assessment_to_dict(assessment)
    
    def get_user_assessments(
        self,
        user_id: UUID,
        assessment_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict]:
        """
        Get assessments for a user.
        
        Args:
            user_id: User ID
            assessment_type: Optional filter by type
            limit: Maximum number to return
            
        Returns:
            List of assessment dictionaries
        """
        query = self.db.query(JourneyAssessment).filter(
            JourneyAssessment.user_id == user_id
        )
        
        if assessment_type:
            query = query.filter(JourneyAssessment.assessment_type == assessment_type)
        
        assessments = query.order_by(
            JourneyAssessment.assessment_date.desc()
        ).limit(limit).all()
        
        return [self._assessment_to_dict(a) for a in assessments]
    
    def get_latest_assessment(
        self,
        user_id: UUID
    ) -> Optional[Dict]:
        """
        Get the most recent assessment for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Assessment dictionary or None if no assessments
        """
        assessments = self.get_user_assessments(user_id, limit=1)
        return assessments[0] if assessments else None
    
    def compare_assessments(
        self,
        assessment_id_1: UUID,
        assessment_id_2: UUID,
    ) -> Optional[Dict]:
        """
        Compare two assessments to show progress.
        
        Args:
            assessment_id_1: First assessment ID (older)
            assessment_id_2: Second assessment ID (newer)
            
        Returns:
            Comparison dictionary
        """
        assessment_1 = self.db.query(JourneyAssessment).filter(
            JourneyAssessment.id == assessment_id_1
        ).first()
        
        assessment_2 = self.db.query(JourneyAssessment).filter(
            JourneyAssessment.id == assessment_id_2
        ).first()
        
        if not assessment_1 or not assessment_2:
            return None
        
        # Compare overall progress
        progress_change = assessment_2.overall_progress_rating - assessment_1.overall_progress_rating
        
        # Parse stored data for dimension comparison
        # (In a real system, you might store dimension scores separately)
        
        return {
            "assessment_1_id": assessment_id_1,
            "assessment_1_date": assessment_1.assessment_date,
            "assessment_1_score": assessment_1.overall_progress_rating,
            "assessment_2_id": assessment_id_2,
            "assessment_2_date": assessment_2.assessment_date,
            "assessment_2_score": assessment_2.overall_progress_rating,
            "change": progress_change,
            "improvement": progress_change > 0,
            "percentage_change": (progress_change / assessment_1.overall_progress_rating * 100) 
                                 if assessment_1.overall_progress_rating > 0 else 0,
        }
    
    # Private helper methods
    
    def _convert_responses(
        self,
        response_dicts: List[Dict]
    ) -> List[QuestionResponse]:
        """
        Convert response dictionaries to QuestionResponse objects.
        
        Args:
            response_dicts: List of response dictionaries
            
        Returns:
            List of QuestionResponse objects
        """
        question_responses = []
        
        for resp in response_dicts:
            try:
                # Parse dimension
                dimension_str = resp.get("dimension", "").upper()
                dimension = HealthDimension[dimension_str]
                
                question_response = QuestionResponse(
                    dimension=dimension,
                    question_id=resp.get("question_id", ""),
                    response_value=int(resp.get("response_value", 3)),
                    question_text=resp.get("question_text"),
                )
                question_responses.append(question_response)
                
            except (KeyError, ValueError) as e:
                # Skip invalid responses
                continue
        
        return question_responses
    
    def _store_assessment(
        self,
        user_id: UUID,
        health_report: JourneyHealthReport,
        assessment_type: str,
        notes: Optional[str],
    ) -> UUID:
        """
        Persist JourneyAssessment to database.
        
        Isolation: Only stores questionnaire-based assessment data.
        No timeline or document data is stored or referenced.
        
        Args:
            user_id: User ID
            health_report: Health report from JourneyHealthEngine
            assessment_type: Type of assessment
            notes: Optional notes
            
        Returns:
            UUID of created JourneyAssessment record
        """
        # Extract ratings from report
        overall_rating = int(health_report.overall_score)
        
        # Get specific dimension ratings if available
        research_rating = None
        timeline_rating = None
        
        if HealthDimension.RESEARCH_PROGRESS in health_report.dimension_scores:
            research_rating = int(
                health_report.dimension_scores[HealthDimension.RESEARCH_PROGRESS].score
            )
        
        # Map time management dimension to timeline adherence rating
        # Note: This is questionnaire-based only, no actual timeline data access
        if HealthDimension.TIME_MANAGEMENT in health_report.dimension_scores:
            timeline_rating = int(
                health_report.dimension_scores[HealthDimension.TIME_MANAGEMENT].score
            )
        
        # Serialize full report for storage
        strengths = self._extract_strengths(health_report)
        challenges = self._extract_challenges(health_report)
        action_items = self._extract_action_items(health_report)
        
        # Create assessment record
        assessment = JourneyAssessment(
            user_id=user_id,
            assessment_date=date.today(),
            assessment_type=assessment_type,
            overall_progress_rating=overall_rating,
            research_quality_rating=research_rating,
            timeline_adherence_rating=timeline_rating,
            strengths=strengths,
            challenges=challenges,
            action_items=action_items,
            advisor_feedback=None,  # Not from questionnaire
            notes=notes,
        )
        
        self.db.add(assessment)
        self.db.commit()
        self.db.refresh(assessment)
        
        return assessment.id
    
    def _generate_summary(
        self,
        assessment_id: UUID,
        health_report: JourneyHealthReport,
    ) -> Dict:
        """
        Generate frontend summary from health report.
        
        Args:
            assessment_id: Created assessment ID
            health_report: Health report
            
        Returns:
            Summary dictionary for frontend
        """
        # Get critical dimensions
        critical = health_report.get_critical_dimensions()
        healthy = health_report.get_healthy_dimensions()
        
        return {
            "assessment_id": str(assessment_id),
            "overall_score": health_report.overall_score,
            "overall_status": health_report.overall_status.value,
            "assessment_date": health_report.assessment_date,
            "total_responses": health_report.total_responses,
            "dimensions": {
                dimension.value: {
                    "score": score.score,
                    "status": score.status.value,
                    "strengths": score.strengths,
                    "concerns": score.concerns,
                }
                for dimension, score in health_report.dimension_scores.items()
            },
            "critical_areas": [
                {
                    "dimension": dim.dimension.value,
                    "score": dim.score,
                    "concerns": dim.concerns,
                }
                for dim in critical
            ],
            "healthy_areas": [
                {
                    "dimension": dim.dimension.value,
                    "score": dim.score,
                    "strengths": dim.strengths,
                }
                for dim in healthy
            ],
            "recommendations": [
                {
                    "priority": rec.priority,
                    "title": rec.title,
                    "description": rec.description,
                    "dimension": rec.dimension.value,
                    "action_items": rec.action_items,
                }
                for rec in health_report.recommendations
            ],
            "summary": self._generate_text_summary(health_report),
        }
    
    def _extract_strengths(self, health_report: JourneyHealthReport) -> str:
        """Extract strengths as text."""
        all_strengths = []
        
        for score in health_report.dimension_scores.values():
            if score.strengths:
                all_strengths.extend(score.strengths)
        
        return "; ".join(all_strengths) if all_strengths else "Areas for development identified"
    
    def _extract_challenges(self, health_report: JourneyHealthReport) -> str:
        """Extract challenges as text."""
        all_concerns = []
        
        for score in health_report.dimension_scores.values():
            if score.concerns:
                all_concerns.extend(score.concerns)
        
        return "; ".join(all_concerns) if all_concerns else "No major concerns identified"
    
    def _extract_action_items(self, health_report: JourneyHealthReport) -> str:
        """Extract action items as text."""
        all_actions = []
        
        for rec in health_report.recommendations[:3]:  # Top 3
            all_actions.append(f"{rec.title}: {rec.action_items[0]}")
        
        return "; ".join(all_actions) if all_actions else "Continue current approach"
    
    def _generate_text_summary(self, health_report: JourneyHealthReport) -> str:
        """Generate human-readable summary."""
        status = health_report.overall_status.value
        score = health_report.overall_score
        
        critical = health_report.get_critical_dimensions()
        healthy = health_report.get_healthy_dimensions()
        
        summary_parts = [
            f"Your overall PhD journey health is {status} with a score of {score:.1f}/100."
        ]
        
        if healthy:
            healthy_list = ", ".join([d.dimension.value.replace("_", " ") for d in healthy[:3]])
            summary_parts.append(f"You're doing well in: {healthy_list}.")
        
        if critical:
            critical_list = ", ".join([d.dimension.value.replace("_", " ") for d in critical[:3]])
            summary_parts.append(f"Areas needing attention: {critical_list}.")
        
        if health_report.recommendations:
            top_rec = health_report.recommendations[0]
            summary_parts.append(f"Top recommendation: {top_rec.title}.")
        
        return " ".join(summary_parts)
    
    def _assessment_to_dict(self, assessment: JourneyAssessment) -> Dict:
        """Convert assessment model to dictionary."""
        return {
            "id": str(assessment.id),
            "user_id": str(assessment.user_id),
            "assessment_date": assessment.assessment_date.isoformat(),
            "assessment_type": assessment.assessment_type,
            "overall_progress_rating": assessment.overall_progress_rating,
            "research_quality_rating": assessment.research_quality_rating,
            "timeline_adherence_rating": assessment.timeline_adherence_rating,
            "strengths": assessment.strengths,
            "challenges": assessment.challenges,
            "action_items": assessment.action_items,
            "advisor_feedback": assessment.advisor_feedback,
            "notes": assessment.notes,
            "created_at": assessment.created_at.isoformat(),
        }
