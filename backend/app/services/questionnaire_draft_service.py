"""Service for managing questionnaire drafts and versions."""
from typing import Dict, List, Optional, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.questionnaire_draft import QuestionnaireDraft, QuestionnaireVersion
from app.models.user import User


class QuestionnaireDraftError(Exception):
    """Base exception for questionnaire draft errors."""
    pass


class QuestionnaireVersionError(Exception):
    """Base exception for questionnaire version errors."""
    pass


class QuestionnaireDraftService:
    """
    Service for managing questionnaire drafts and versions.
    
    Rules:
    - Section-wise saving: Save responses section by section
    - Resume allowed: Users can resume drafts at any time
    - Submission locks responses: Once submitted, drafts are immutable
    - Version questionnaires: Support multiple questionnaire versions
    - No scoring yet: Scoring logic is not implemented in this service
    
    Capabilities:
    - Section-by-section saving
    - Draft resumption
    - Version management
    - Progress tracking
    - Submission locking
    """
    
    def __init__(self, db: Session):
        """
        Initialize questionnaire draft service.
        
        Args:
            db: Database session
        """
        self.db = db
    
    def create_draft(
        self,
        user_id: UUID,
        questionnaire_version_id: Optional[UUID] = None,
        draft_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UUID:
        """
        Create a new questionnaire draft.
        
        Args:
            user_id: User ID
            questionnaire_version_id: Specific version ID (defaults to active version)
            draft_name: Optional name for the draft
            metadata: Optional metadata (device, browser, etc.)
            
        Returns:
            UUID of created draft
            
        Raises:
            QuestionnaireDraftError: If validation fails
        """
        # Verify user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise QuestionnaireDraftError(f"User with ID {user_id} not found")
        
        # Get questionnaire version
        if questionnaire_version_id:
            version = self.db.query(QuestionnaireVersion).filter(
                QuestionnaireVersion.id == questionnaire_version_id
            ).first()
            if not version:
                raise QuestionnaireDraftError(
                    f"Questionnaire version {questionnaire_version_id} not found"
                )
        else:
            # Get active version
            version = self.get_active_version()
            if not version:
                raise QuestionnaireDraftError("No active questionnaire version found")
        
        # Create draft
        draft = QuestionnaireDraft(
            user_id=user_id,
            questionnaire_version_id=version.id,
            draft_name=draft_name or f"Draft {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
            responses_json={},
            completed_sections=[],
            progress_percentage=0,
            is_submitted=False,
            metadata_json=metadata or {}
        )
        
        self.db.add(draft)
        self.db.commit()
        self.db.refresh(draft)
        
        return draft.id
    
    def save_section(
        self,
        draft_id: UUID,
        user_id: UUID,
        section_id: str,
        responses: Dict[str, Any],
        is_section_complete: bool = False
    ) -> Dict[str, Any]:
        """
        Save responses for a specific section (section-wise saving).
        
        Rules:
        - Section-wise saving: Only updates the specified section
        - Submission locks responses: Cannot edit if already submitted
        - Resume allowed: Can save to any section at any time (if not submitted)
        
        Args:
            draft_id: Draft ID
            user_id: User ID (for ownership verification)
            section_id: Section identifier
            responses: Section responses {question_id: response_value}
            is_section_complete: Whether this section is now complete
            
        Returns:
            Updated draft summary
            
        Raises:
            QuestionnaireDraftError: If validation fails or draft is submitted
        """
        # Get draft
        draft = self.db.query(QuestionnaireDraft).filter(
            QuestionnaireDraft.id == draft_id,
            QuestionnaireDraft.user_id == user_id
        ).first()
        
        if not draft:
            raise QuestionnaireDraftError(
                f"Draft {draft_id} not found or not owned by user {user_id}"
            )
        
        # Submission locks responses - prevent any edits after submission
        if draft.is_submitted:
            raise QuestionnaireDraftError(
                "Cannot edit submitted draft. Submission locks all responses."
            )
        
        # Section-wise saving: Update only the specified section
        current_responses = draft.responses_json or {}
        
        # Merge section responses (section-wise update)
        if section_id not in current_responses:
            current_responses[section_id] = {}
        
        # Update section responses (merge with existing)
        current_responses[section_id].update(responses)
        draft.responses_json = current_responses
        
        # Update completed sections list
        completed_sections = list(draft.completed_sections or [])
        if is_section_complete and section_id not in completed_sections:
            completed_sections.append(section_id)
            draft.completed_sections = completed_sections
        elif not is_section_complete and section_id in completed_sections:
            completed_sections.remove(section_id)
            draft.completed_sections = completed_sections
        
        # Update progress percentage
        draft.progress_percentage = self._calculate_progress(draft)
        
        # Track last edited section (for resume functionality)
        draft.last_section_edited = section_id
        
        self.db.add(draft)
        self.db.commit()
        self.db.refresh(draft)
        
        return self._draft_to_dict(draft)
    
    def get_draft(
        self,
        draft_id: UUID,
        user_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Get a draft by ID (for resuming).
        
        Resume allowed: Users can retrieve and continue working on drafts.
        
        Args:
            draft_id: Draft ID
            user_id: User ID (for ownership verification)
            
        Returns:
            Draft dictionary or None if not found
        """
        draft = self.db.query(QuestionnaireDraft).filter(
            QuestionnaireDraft.id == draft_id,
            QuestionnaireDraft.user_id == user_id
        ).first()
        
        if not draft:
            return None
        
        return self._draft_to_dict(draft)
    
    def resume_draft(
        self,
        draft_id: UUID,
        user_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Resume a draft (get draft with resume context).
        
        Resume allowed: Users can resume drafts at any time (if not submitted).
        Returns draft with information about where to resume.
        
        Args:
            draft_id: Draft ID
            user_id: User ID (for ownership verification)
            
        Returns:
            Draft dictionary with resume information, or None if not found
            
        Raises:
            QuestionnaireDraftError: If draft is submitted (cannot resume)
        """
        draft = self.db.query(QuestionnaireDraft).filter(
            QuestionnaireDraft.id == draft_id,
            QuestionnaireDraft.user_id == user_id
        ).first()
        
        if not draft:
            return None
        
        # Submission locks responses - cannot resume submitted drafts
        if draft.is_submitted:
            raise QuestionnaireDraftError(
                "Cannot resume submitted draft. Submission locks all responses."
            )
        
        draft_dict = self._draft_to_dict(draft)
        
        # Add resume context
        draft_dict["resume_info"] = {
            "last_section_edited": draft.last_section_edited,
            "completed_sections": draft.completed_sections or [],
            "can_resume": True,
            "is_submitted": False
        }
        
        return draft_dict
    
    def get_user_drafts(
        self,
        user_id: UUID,
        include_submitted: bool = False,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get all drafts for a user.
        
        Args:
            user_id: User ID
            include_submitted: Whether to include submitted drafts
            limit: Maximum number of drafts to return
            
        Returns:
            List of draft dictionaries
        """
        query = self.db.query(QuestionnaireDraft).filter(
            QuestionnaireDraft.user_id == user_id
        )
        
        if not include_submitted:
            query = query.filter(QuestionnaireDraft.is_submitted == False)
        
        drafts = query.order_by(
            desc(QuestionnaireDraft.updated_at)
        ).limit(limit).all()
        
        return [self._draft_to_dict(draft) for draft in drafts]
    
    def delete_draft(
        self,
        draft_id: UUID,
        user_id: UUID
    ) -> bool:
        """
        Delete a draft.
        
        Rules:
        - Submission locks responses: Cannot delete submitted drafts
        
        Args:
            draft_id: Draft ID
            user_id: User ID (for ownership verification)
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            QuestionnaireDraftError: If draft is already submitted (locked)
        """
        draft = self.db.query(QuestionnaireDraft).filter(
            QuestionnaireDraft.id == draft_id,
            QuestionnaireDraft.user_id == user_id
        ).first()
        
        if not draft:
            return False
        
        # Submission locks responses - cannot delete submitted drafts
        if draft.is_submitted:
            raise QuestionnaireDraftError(
                "Cannot delete submitted draft. Submission locks all responses."
            )
        
        self.db.delete(draft)
        self.db.commit()
        
        return True
    
    def mark_as_submitted(
        self,
        draft_id: UUID,
        user_id: UUID,
        submission_id: UUID
    ) -> Dict[str, Any]:
        """
        Mark a draft as submitted (submission locks responses).
        
        Rules:
        - Submission locks responses: After submission, draft becomes immutable
        - Cannot edit: All future save_section() calls will fail
        - Cannot delete: Draft cannot be deleted after submission
        - Cannot resume: Draft cannot be resumed after submission
        
        Args:
            draft_id: Draft ID
            user_id: User ID (for ownership verification)
            submission_id: ID of the JourneyAssessment created from this draft
            
        Returns:
            Updated draft dictionary (now locked)
            
        Raises:
            QuestionnaireDraftError: If validation fails or already submitted
        """
        draft = self.db.query(QuestionnaireDraft).filter(
            QuestionnaireDraft.id == draft_id,
            QuestionnaireDraft.user_id == user_id
        ).first()
        
        if not draft:
            raise QuestionnaireDraftError(
                f"Draft {draft_id} not found or not owned by user {user_id}"
            )
        
        if draft.is_submitted:
            raise QuestionnaireDraftError("Draft already submitted")
        
        # Submission locks responses - mark as submitted (immutable)
        draft.is_submitted = True
        draft.submission_id = submission_id
        
        self.db.add(draft)
        self.db.commit()
        self.db.refresh(draft)
        
        return self._draft_to_dict(draft)
    
    # Questionnaire Version Management
    
    def create_version(
        self,
        version_number: str,
        title: str,
        schema: Dict[str, Any],
        description: Optional[str] = None,
        release_notes: Optional[str] = None,
        is_active: bool = True
    ) -> UUID:
        """
        Create a new questionnaire version (version questionnaires).
        
        Rules:
        - Version questionnaires: Support multiple versions of questionnaire schema
        - Each draft is tied to a specific version
        - Only one active version at a time
        - Versions can be deprecated but not deleted
        
        Args:
            version_number: Version number (e.g., "1.0", "1.1", "2.0")
            title: Version title
            schema: Complete questionnaire schema (sections, questions, etc.)
            description: Optional description
            release_notes: Optional release notes
            is_active: Whether this version is active (only one can be active)
            
        Returns:
            UUID of created version
            
        Raises:
            QuestionnaireVersionError: If validation fails or version exists
        """
        # Check if version already exists
        existing = self.db.query(QuestionnaireVersion).filter(
            QuestionnaireVersion.version_number == version_number
        ).first()
        
        if existing:
            raise QuestionnaireVersionError(
                f"Version {version_number} already exists"
            )
        
        # Calculate totals from schema
        total_sections = len(schema.get("sections", []))
        total_questions = sum(
            len(section.get("questions", []))
            for section in schema.get("sections", [])
        )
        
        # If this version is active, deactivate others
        if is_active:
            self.db.query(QuestionnaireVersion).update({"is_active": False})
        
        # Create version
        version = QuestionnaireVersion(
            version_number=version_number,
            title=title,
            description=description,
            schema_json=schema,
            is_active=is_active,
            is_deprecated=False,
            total_questions=total_questions,
            total_sections=total_sections,
            release_notes=release_notes
        )
        
        self.db.add(version)
        self.db.commit()
        self.db.refresh(version)
        
        return version.id
    
    def get_active_version(self) -> Optional[QuestionnaireVersion]:
        """
        Get the currently active questionnaire version.
        
        Returns:
            Active QuestionnaireVersion or None
        """
        return self.db.query(QuestionnaireVersion).filter(
            QuestionnaireVersion.is_active == True
        ).first()
    
    def get_version(self, version_id: UUID) -> Optional[QuestionnaireVersion]:
        """
        Get a questionnaire version by ID.
        
        Args:
            version_id: Version ID
            
        Returns:
            QuestionnaireVersion or None
        """
        return self.db.query(QuestionnaireVersion).filter(
            QuestionnaireVersion.id == version_id
        ).first()
    
    def get_all_versions(
        self,
        include_deprecated: bool = False
    ) -> List[QuestionnaireVersion]:
        """
        Get all questionnaire versions.
        
        Args:
            include_deprecated: Whether to include deprecated versions
            
        Returns:
            List of QuestionnaireVersion objects
        """
        query = self.db.query(QuestionnaireVersion)
        
        if not include_deprecated:
            query = query.filter(QuestionnaireVersion.is_deprecated == False)
        
        return query.order_by(desc(QuestionnaireVersion.created_at)).all()
    
    def deprecate_version(self, version_id: UUID) -> bool:
        """
        Mark a version as deprecated.
        
        Args:
            version_id: Version ID
            
        Returns:
            True if deprecated, False if not found
        """
        version = self.db.query(QuestionnaireVersion).filter(
            QuestionnaireVersion.id == version_id
        ).first()
        
        if not version:
            return False
        
        version.is_deprecated = True
        version.is_active = False
        
        self.db.add(version)
        self.db.commit()
        
        return True
    
    # Private helper methods
    
    def _calculate_progress(self, draft: QuestionnaireDraft) -> int:
        """
        Calculate progress percentage for a draft.
        
        Args:
            draft: QuestionnaireDraft object
            
        Returns:
            Progress percentage (0-100)
        """
        # Get version schema
        version = draft.questionnaire_version
        if not version or not version.schema_json:
            return 0
        
        total_questions = version.total_questions
        if total_questions == 0:
            return 0
        
        # Count answered questions
        answered_count = 0
        responses = draft.responses_json or {}
        
        for section_responses in responses.values():
            if isinstance(section_responses, dict):
                # Count non-empty responses
                answered_count += sum(
                    1 for v in section_responses.values()
                    if v is not None and v != ""
                )
        
        progress = (answered_count / total_questions) * 100
        return min(100, int(progress))
    
    def _draft_to_dict(self, draft: QuestionnaireDraft) -> Dict[str, Any]:
        """
        Convert draft to dictionary for API responses.
        
        Args:
            draft: QuestionnaireDraft object
            
        Returns:
            Dictionary representation
        """
        return {
            "id": str(draft.id),
            "user_id": str(draft.user_id),
            "questionnaire_version_id": str(draft.questionnaire_version_id),
            "questionnaire_version_number": draft.questionnaire_version.version_number if draft.questionnaire_version else None,
            "draft_name": draft.draft_name,
            "responses": draft.responses_json or {},
            "completed_sections": draft.completed_sections or [],
            "progress_percentage": draft.progress_percentage,
            "is_submitted": draft.is_submitted,
            "submission_id": str(draft.submission_id) if draft.submission_id else None,
            "last_section_edited": draft.last_section_edited,
            "metadata": draft.metadata_json or {},
            "created_at": draft.created_at.isoformat() if draft.created_at else None,
            "updated_at": draft.updated_at.isoformat() if draft.updated_at else None
        }
