"""Timeline orchestrator for creating draft timelines from baselines."""
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy.orm import Session

from app.orchestrators.base import BaseOrchestrator
from app.models.baseline import Baseline
from app.models.draft_timeline import DraftTimeline
from app.models.committed_timeline import CommittedTimeline
from app.models.timeline_stage import TimelineStage
from app.models.timeline_milestone import TimelineMilestone
from app.models.document_artifact import DocumentArtifact
from app.models.user import User
from app.models.timeline_edit_history import TimelineEditHistory
from app.services.timeline_intelligence_engine import (
    TimelineIntelligenceEngine,
    StageType,
    DetectedStage,
    ExtractedMilestone,
    DurationEstimate,
    Dependency,
    StructuredTimeline,
)
from app.utils.invariants import check_committed_timeline_has_draft


class TimelineOrchestratorError(Exception):
    """Base exception for timeline orchestrator errors."""
    pass


class TimelineAlreadyCommittedError(TimelineOrchestratorError):
    """Raised when attempting to commit an already committed timeline."""
    pass


class TimelineImmutableError(TimelineOrchestratorError):
    """Raised when attempting to modify an immutable committed timeline."""
    pass


class TimelineOrchestrator(BaseOrchestrator[Dict[str, Any]]):
    """
    Orchestrator for creating and managing draft and committed timelines.
    
    Extends BaseOrchestrator for idempotency and decision tracing.
    Coordinates document loading, intelligence extraction, timeline creation,
    and timeline commitment with version management.
    """
    
    # Timeline status constants
    STATUS_DRAFT = "DRAFT"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_COMMITTED = "COMMITTED"
    
    @property
    def orchestrator_name(self) -> str:
        """Return the orchestrator name."""
        return "timeline_orchestrator"
    
    def __init__(self, db: Session, user_id: Optional[UUID] = None):
        """
        Initialize timeline orchestrator.
        
        Args:
            db: Database session
            user_id: Optional user ID for this operation
        """
        super().__init__(db, user_id)
        self.intelligence_engine = TimelineIntelligenceEngine()
    
    @property
    def orchestrator_name(self) -> str:
        """Get orchestrator name for tracing."""
        return "timeline_orchestrator"
    
    def _execute_pipeline(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the timeline generation pipeline.
        
        This is called by BaseOrchestrator's execute() method.
        DecisionTrace is automatically written by BaseOrchestrator.
        
        Steps:
        1. Validate baseline exists
        2. Load baseline document text
        3. Call detect_stages()
        4. Call extract_milestones()
        5. Call estimate_durations()
        6. Call map_dependencies()
        7. Assemble DraftTimeline
        8. Persist DraftTimeline + children
        9. Write DecisionTrace (automatic via BaseOrchestrator)
        
        Args:
            context: Pipeline context with baseline_id, user_id, etc.
            
        Returns:
            UI-ready JSON response
        """
        # Extract input data from context wrapper (BaseOrchestrator pattern)
        input_data = context['input']
        
        baseline_id = UUID(input_data['baseline_id'])
        user_id = UUID(input_data['user_id'])
        title = input_data.get('title')
        description = input_data.get('description')
        version_number = input_data.get('version_number', '1.0')
        
        # Step 1: Validate baseline exists
        with self._trace_step("validate_baseline") as step:
            baseline = self.db.query(Baseline).filter(
                Baseline.id == baseline_id
            ).first()
            
            if not baseline:
                raise TimelineOrchestratorError(f"Baseline with ID {baseline_id} not found")
            
            if baseline.user_id != user_id:
                raise TimelineOrchestratorError(
                    f"Baseline {baseline_id} does not belong to user {user_id}"
                )
            
            step.details = {
                "baseline_id": str(baseline_id),
                "program_name": baseline.program_name,
                "institution": baseline.institution
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="baseline_data",
                data={
                    "program_name": baseline.program_name,
                    "institution": baseline.institution,
                    "field_of_study": baseline.field_of_study
                },
                source=f"Baseline:{baseline_id}",
                confidence=1.0
            )
        
        # Step 2: Load baseline document text
        with self._trace_step("load_document_text") as step:
            if not baseline.document_artifact_id:
                raise TimelineOrchestratorError(
                    "Baseline has no associated document artifact"
                )
            
            document = self.db.query(DocumentArtifact).filter(
                DocumentArtifact.id == baseline.document_artifact_id
            ).first()
            
            if not document:
                raise TimelineOrchestratorError(
                    f"Document artifact {baseline.document_artifact_id} not found"
                )
            
            # Use normalized document_text
            document_text = document.document_text
            section_map = document.section_map_json
            
            if not document_text:
                raise TimelineOrchestratorError(
                    "No document text available for timeline extraction"
                )
            
            step.details = {
                "document_id": str(document.id),
                "text_length": len(document_text),
                "word_count": document.word_count,
                "has_section_map": section_map is not None
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="document_text",
                data={
                    "excerpt": document_text[:500],
                    "word_count": document.word_count,
                    "detected_language": document.detected_language,
                    "section_count": section_map.get("total_sections", 0) if section_map else 0
                },
                source=f"DocumentArtifact:{document.id}",
                confidence=1.0
            )
        
        # Step 3: Call detect_stages()
        with self._trace_step("detect_stages") as step:
            detected_stages = self.intelligence_engine.detect_stages(
                text=document_text,
                section_map=section_map
            )
            
            step.details = {
                "stages_detected": len(detected_stages),
                "stage_titles": [s.title for s in detected_stages]
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="detected_stages",
                data={
                    "stages": [s.title for s in detected_stages],
                    "stage_types": [s.stage_type.value for s in detected_stages]
                },
                source="TimelineIntelligenceEngine.detect_stages()",
                confidence=0.9
            )
        
        # Step 4: Call extract_milestones()
        with self._trace_step("extract_milestones") as step:
            extracted_milestones = self.intelligence_engine.extract_milestones(
                text=document_text,
                section_map=section_map
            )
            
            step.details = {
                "milestones_extracted": len(extracted_milestones),
                "critical_milestones": len([m for m in extracted_milestones if m.is_critical])
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="extracted_milestones",
                data={
                    "total_milestones": len(extracted_milestones),
                    "milestone_names": [m.name for m in extracted_milestones[:10]]
                },
                source="TimelineIntelligenceEngine.extract_milestones()",
                confidence=0.8
            )
        
        # Step 5: Call estimate_durations()
        with self._trace_step("estimate_durations") as step:
            # Extract discipline from baseline if available
            discipline = getattr(baseline, 'field_of_study', None)
            
            duration_estimates = self.intelligence_engine.estimate_durations(
                text=document_text,
                stages=detected_stages,
                milestones=extracted_milestones,
                section_map=section_map,
                discipline=discipline
            )
            
            step.details = {
                "duration_estimates": len(duration_estimates),
                "stage_estimates": len([d for d in duration_estimates if d.item_type == "stage"]),
                "milestone_estimates": len([d for d in duration_estimates if d.item_type == "milestone"])
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="duration_estimates",
                data={
                    "total_estimates": len(duration_estimates),
                    "discipline": discipline
                },
                source="TimelineIntelligenceEngine.estimate_durations()",
                confidence=0.7
            )
        
        # Step 6: Call map_dependencies()
        with self._trace_step("map_dependencies") as step:
            dependencies = self.intelligence_engine.map_dependencies(
                text=document_text,
                stages=detected_stages,
                milestones=extracted_milestones,
                section_map=section_map
            )
            
            step.details = {
                "dependencies_mapped": len(dependencies),
                "dependency_types": list(set(d.dependency_type for d in dependencies))
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="dependencies",
                data={
                    "total_dependencies": len(dependencies),
                    "dependency_types": list(set(d.dependency_type for d in dependencies))
                },
                source="TimelineIntelligenceEngine.map_dependencies()",
                confidence=0.8
            )
        
        # Step 7: Assemble DraftTimeline
        with self._trace_step("assemble_draft_timeline") as step:
            # Generate default title if not provided
            if not title:
                title = f"Draft Timeline: {baseline.program_name}"
            
            # Generate default description if not provided
            if not description:
                description = (
                    f"Draft timeline for {baseline.program_name} at {baseline.institution}. "
                    f"Generated from baseline requirements and program structure."
                )
            
            draft_timeline = DraftTimeline(
                user_id=user_id,
                baseline_id=baseline_id,
                title=title,
                description=description,
                version_number=version_number,
                is_active=True,
                notes=f"Status: {self.STATUS_DRAFT}"  # Status must be DRAFT
            )
            
            step.details = {
                "title": draft_timeline.title,
                "status": self.STATUS_DRAFT
            }
        
        # Step 8: Persist DraftTimeline + children
        with self._trace_step("persist_draft_timeline") as step:
            self.db.add(draft_timeline)
            self.db.flush()  # Get ID without committing
            
            # Create stage records
            stage_records = self._create_stage_records(
                draft_timeline_id=draft_timeline.id,
                detected_stages=detected_stages,
                duration_estimates=duration_estimates
            )
            
            # Create milestone records
            milestone_records = self._create_milestone_records(
                stage_records=stage_records,
                extracted_milestones=extracted_milestones,
                detected_stages=detected_stages
            )
            
            # Commit all changes
            self.db.commit()
            self.db.refresh(draft_timeline)
            
            step.details = {
                "draft_timeline_id": str(draft_timeline.id),
                "stages_created": len(stage_records),
                "milestones_created": len(milestone_records)
            }
        
        # Step 9: Write DecisionTrace (automatic via BaseOrchestrator.execute())
        # The BaseOrchestrator.execute() method automatically writes DecisionTrace
        # after _execute_pipeline completes successfully
        
        # Build UI-ready response
        response = self._build_ui_response_from_components(
            draft_timeline=draft_timeline,
            stage_records=stage_records,
            milestone_records=milestone_records,
            detected_stages=detected_stages,
            extracted_milestones=extracted_milestones,
            duration_estimates=duration_estimates,
            dependencies=dependencies
        )
        
        return response
    
    def _build_ui_response_from_components(
        self,
        draft_timeline: DraftTimeline,
        stage_records: List[TimelineStage],
        milestone_records: List[TimelineMilestone],
        detected_stages: List[DetectedStage],
        extracted_milestones: List[ExtractedMilestone],
        duration_estimates: List[DurationEstimate],
        dependencies: List[Dependency]
    ) -> Dict[str, Any]:
        """
        Build UI-ready JSON response from individual components.
        
        Args:
            draft_timeline: Created draft timeline
            stage_records: Created stage records
            milestone_records: Created milestone records
            detected_stages: Detected stages from intelligence engine
            extracted_milestones: Extracted milestones from intelligence engine
            duration_estimates: Duration estimates from intelligence engine
            dependencies: Dependencies from intelligence engine
            
        Returns:
            UI-ready JSON dictionary
        """
        # Group milestones by stage
        milestones_by_stage = {}
        for milestone in milestone_records:
            stage_id = milestone.timeline_stage_id
            if stage_id not in milestones_by_stage:
                milestones_by_stage[stage_id] = []
            milestones_by_stage[stage_id].append(milestone)
        
        # Build stages array with milestones
        stages_array = []
        for stage in stage_records:
            stage_milestones = milestones_by_stage.get(stage.id, [])
            
            stages_array.append({
                "id": str(stage.id),
                "title": stage.title,
                "description": stage.description,
                "stage_order": stage.stage_order,
                "duration_months": stage.duration_months,
                "status": stage.status,
                "milestones": [
                    {
                        "id": str(m.id),
                        "title": m.title,
                        "description": m.description,
                        "milestone_order": m.milestone_order,
                        "is_critical": m.is_critical,
                        "is_completed": m.is_completed,
                        "deliverable_type": m.deliverable_type
                    }
                    for m in stage_milestones
                ]
            })
        
        # Build dependencies array
        dependencies_array = [
            {
                "dependent_item": dep.dependent_item,
                "depends_on_item": dep.depends_on_item,
                "dependency_type": dep.dependency_type,
                "confidence": dep.confidence,
                "reason": dep.reason
            }
            for dep in dependencies
        ]
        
        # Build duration estimates array
        durations_array = [
            {
                "item_description": dur.item_description,
                "item_type": dur.item_type,
                "duration_weeks_min": dur.duration_weeks_min,
                "duration_weeks_max": dur.duration_weeks_max,
                "duration_months_min": dur.duration_months_min,
                "duration_months_max": dur.duration_months_max,
                "confidence": dur.confidence,
                "basis": dur.basis
            }
            for dur in duration_estimates
        ]
        
        # Calculate total duration from estimates
        stage_durations = [d for d in duration_estimates if d.item_type == "stage"]
        total_duration_months_min = sum(d.duration_months_min for d in stage_durations) if stage_durations else 0
        total_duration_months_max = sum(d.duration_months_max for d in stage_durations) if stage_durations else 0
        
        # Build complete response
        return {
            "timeline": {
                "id": str(draft_timeline.id),
                "baseline_id": str(draft_timeline.baseline_id),
                "user_id": str(draft_timeline.user_id),
                "title": draft_timeline.title,
                "description": draft_timeline.description,
                "version_number": draft_timeline.version_number,
                "is_active": draft_timeline.is_active,
                "status": self.STATUS_DRAFT,  # Status must be DRAFT
                "created_at": draft_timeline.created_at.isoformat() if draft_timeline.created_at else None
            },
            "stages": stages_array,
            "dependencies": dependencies_array,
            "durations": durations_array,
            "metadata": {
                "total_stages": len(stage_records),
                "total_milestones": len(milestone_records),
                "total_duration_months_min": total_duration_months_min,
                "total_duration_months_max": total_duration_months_max,
                "is_dag_valid": len(dependencies) > 0,  # DAG validation done in map_dependencies
                "generated_at": datetime.utcnow().isoformat()
            }
        }
    
    def generate(
        self,
        request_id: str,
        baseline_id: UUID,
        user_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        version_number: str = "1.0"
    ) -> Dict[str, Any]:
        """
        Generate a draft timeline from a baseline.
        
        This is the main entry point for timeline generation with:
        - Idempotency (duplicate requests return cached response)
        - Decision tracing (full audit trail)
        - Evidence bundling (all inputs recorded)
        - UI-ready JSON output
        
        Steps:
        1. Validate baseline exists
        2. Load baseline document text
        3. Call detect_stages()
        4. Call extract_milestones()
        5. Call estimate_durations()
        6. Call map_dependencies()
        7. Assemble DraftTimeline
        8. Persist DraftTimeline + children
        9. Write DecisionTrace (automatic via BaseOrchestrator)
        
        Status must be DRAFT.
        
        Args:
            request_id: Idempotency key (use UUID for new requests)
            baseline_id: ID of the baseline to create timeline from
            user_id: ID of the user creating the timeline
            title: Optional timeline title
            description: Optional timeline description
            version_number: Version number (defaults to "1.0")
            
        Returns:
            UI-ready JSON with timeline, stages, milestones, and metadata
            
        Raises:
            TimelineOrchestratorError: If validation fails or processing errors occur
        """
        return self.execute(
            request_id=request_id,
            input_data={
                "baseline_id": str(baseline_id),
                "user_id": str(user_id),
                "title": title,
                "description": description,
                "version_number": version_number
            }
        )
    
    def create_draft_timeline(
        self,
        baseline_id: UUID,
        user_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        version_number: Optional[str] = "1.0",
    ) -> UUID:
        """
        Create a draft timeline from a baseline.
        
        Workflow:
        1. Verify user and baseline ownership
        2. Load document artifact text
        3. Call intelligence engine methods in sequence
        4. Create draft timeline with stages and milestones
        5. Store in database
        
        Args:
            baseline_id: ID of the baseline to create timeline from
            user_id: ID of the user creating the timeline
            title: Optional timeline title (defaults to baseline-based title)
            description: Optional timeline description
            version_number: Version number (defaults to "1.0")
            
        Returns:
            UUID of the created DraftTimeline
            
        Raises:
            TimelineOrchestratorError: If validation fails or processing errors occur
        """
        # Step 1: Verify user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise TimelineOrchestratorError(f"User with ID {user_id} not found")
        
        # Step 2: Get baseline and verify ownership
        baseline = self.db.query(Baseline).filter(
            Baseline.id == baseline_id
        ).first()
        
        if not baseline:
            raise TimelineOrchestratorError(f"Baseline with ID {baseline_id} not found")
        
        if baseline.user_id != user_id:
            raise TimelineOrchestratorError(
                f"Baseline {baseline_id} does not belong to user {user_id}"
            )
        
        # Step 3: Load document artifact text
        document_text = self._load_document_text(baseline)
        
        if not document_text:
            raise TimelineOrchestratorError(
                "No document text available for timeline extraction"
            )
        
        # Step 4: Call intelligence engine methods in sequence
        detected_stages = self.intelligence_engine.detect_stages(document_text)
        extracted_milestones = self.intelligence_engine.extract_milestones(document_text)
        duration_estimates = self.intelligence_engine.estimate_durations(document_text)
        dependencies = self.intelligence_engine.map_dependencies(document_text)
        
        # Step 5: Create draft timeline
        draft_timeline = self._create_draft_timeline_record(
            baseline=baseline,
            user_id=user_id,
            title=title,
            description=description,
            version_number=version_number,
        )
        
        # Step 6: Create timeline stages
        stage_records = self._create_stage_records(
            draft_timeline_id=draft_timeline.id,
            detected_stages=detected_stages,
            duration_estimates=duration_estimates,
        )
        
        # Step 7: Create timeline milestones
        self._create_milestone_records(
            stage_records=stage_records,
            extracted_milestones=extracted_milestones,
            detected_stages=detected_stages,
        )
        
        # Commit all changes
        self.db.commit()
        self.db.refresh(draft_timeline)
        
        return draft_timeline.id
    
    def get_draft_timeline(self, draft_timeline_id: UUID) -> Optional[DraftTimeline]:
        """
        Get a draft timeline by ID.
        
        Args:
            draft_timeline_id: Draft timeline ID
            
        Returns:
            DraftTimeline or None if not found
        """
        return self.db.query(DraftTimeline).filter(
            DraftTimeline.id == draft_timeline_id
        ).first()
    
    def get_draft_timeline_with_details(
        self,
        draft_timeline_id: UUID
    ) -> Optional[Dict]:
        """
        Get draft timeline with stages and milestones.
        
        Args:
            draft_timeline_id: Draft timeline ID
            
        Returns:
            Dictionary with timeline, stages, and milestones
        """
        draft_timeline = self.get_draft_timeline(draft_timeline_id)
        
        if not draft_timeline:
            return None
        
        # Get stages
        stages = self.db.query(TimelineStage).filter(
            TimelineStage.draft_timeline_id == draft_timeline_id
        ).order_by(TimelineStage.stage_order).all()
        
        # Get milestones for each stage
        stages_with_milestones = []
        for stage in stages:
            milestones = self.db.query(TimelineMilestone).filter(
                TimelineMilestone.timeline_stage_id == stage.id
            ).order_by(TimelineMilestone.milestone_order).all()
            
            stages_with_milestones.append({
                "stage": stage,
                "milestones": milestones
            })
        
        return {
            "timeline": draft_timeline,
            "baseline": draft_timeline.baseline,
            "stages": stages_with_milestones,
            "total_stages": len(stages),
            "total_milestones": sum(len(s["milestones"]) for s in stages_with_milestones)
        }
    
    def get_user_draft_timelines(
        self,
        user_id: UUID,
        baseline_id: Optional[UUID] = None,
        active_only: bool = False
    ) -> List[DraftTimeline]:
        """
        Get draft timelines for a user.
        
        Args:
            user_id: User ID
            baseline_id: Optional baseline ID to filter by
            active_only: If True, only return active drafts
            
        Returns:
            List of DraftTimeline objects
        """
        query = self.db.query(DraftTimeline).filter(
            DraftTimeline.user_id == user_id
        )
        
        if baseline_id:
            query = query.filter(DraftTimeline.baseline_id == baseline_id)
        
        if active_only:
            query = query.filter(DraftTimeline.is_active == True)
        
        return query.order_by(DraftTimeline.created_at.desc()).all()
    
    def apply_edits(
        self,
        draft_timeline_id: UUID,
        user_id: UUID,
        edits: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Apply user edits to a draft timeline.
        
        Accepts a list of edit operations and applies them to the draft timeline,
        recording each change in the edit history.
        
        Args:
            draft_timeline_id: ID of draft timeline to edit
            user_id: ID of user making edits
            edits: List of edit operations, each with:
                {
                    "operation": "update" | "add" | "delete" | "reorder",
                    "entity_type": "timeline" | "stage" | "milestone",
                    "entity_id": "uuid" (for update/delete),
                    "data": {...} (new/updated values)
                }
        
        Returns:
            Summary of applied edits
        """
        # Verify draft timeline exists and belongs to user
        draft_timeline = self.db.query(DraftTimeline).filter(
            DraftTimeline.id == draft_timeline_id,
            DraftTimeline.user_id == user_id
        ).first()
        
        if not draft_timeline:
            raise TimelineOrchestratorError(
                f"Draft timeline {draft_timeline_id} not found or not owned by user"
            )
        
        if not draft_timeline.is_active:
            raise TimelineImmutableError(
                "Cannot edit committed timeline"
            )
        
        applied_edits = []
        
        for edit in edits:
            operation = edit.get("operation")
            entity_type = edit.get("entity_type")
            entity_id = edit.get("entity_id")
            data = edit.get("data", {})
            
            # Apply edit based on operation and entity type
            if entity_type == "timeline":
                result = self._apply_timeline_edit(
                    draft_timeline, operation, data, user_id
                )
            elif entity_type == "stage":
                result = self._apply_stage_edit(
                    draft_timeline_id, operation, entity_id, data, user_id
                )
            elif entity_type == "milestone":
                result = self._apply_milestone_edit(
                    draft_timeline_id, operation, entity_id, data, user_id
                )
            else:
                continue
            
            if result:
                applied_edits.append(result)
        
        self.db.commit()
        
        return {
            "draft_timeline_id": str(draft_timeline_id),
            "edits_applied": len(applied_edits),
            "edits": applied_edits
        }
    
    def commit(
        self,
        request_id: str,
        draft_timeline_id: UUID,
        user_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Commit a draft timeline to create an immutable committed timeline.
        
        Rules:
        - DraftTimeline must exist and belong to user
        - Validate completeness (stages, milestones required)
        - Create CommittedTimeline (immutable copy)
        - Freeze content (mark draft as inactive)
        - Increment version (automatic version bump)
        - Prevent re-commit (idempotency + explicit check)
        
        Committed timelines must be immutable.
        
        Enhanced with:
        - Idempotency (duplicate commits return cached response)
        - Decision tracing (full audit trail)
        - Edit history preservation
        - Immutability enforcement
        
        Args:
            request_id: Idempotency key for commit operation
            draft_timeline_id: ID of draft timeline to commit
            user_id: ID of user committing the timeline
            title: Optional title override
            description: Optional description override
            
        Returns:
            UI-ready JSON with committed timeline details
            
        Raises:
            TimelineOrchestratorError: If validation fails
            TimelineAlreadyCommittedError: If already committed
        """
        return self.execute(
            request_id=request_id,
            input_data={
                "draft_timeline_id": str(draft_timeline_id),
                "user_id": str(user_id),
                "title": title,
                "description": description
            }
        )
    
    def _execute_commit_pipeline(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the timeline commit pipeline.
        
        Steps:
        1. Validate DraftTimeline exists and belongs to user
        2. Validate completeness (stages, milestones required)
        3. Prevent re-commit (check if already committed)
        4. Increment version
        5. Create CommittedTimeline (immutable)
        6. Copy stages and milestones to committed timeline
        7. Freeze content (mark draft as inactive)
        8. Persist all changes
        9. Write DecisionTrace (automatic via BaseOrchestrator)
        
        Committed timelines are immutable after creation.
        
        Args:
            context: Pipeline context with draft_timeline_id, user_id, etc.
            
        Returns:
            UI-ready JSON response
        """
        # Extract input data from context wrapper (BaseOrchestrator pattern)
        input_data = context['input']
        
        draft_timeline_id = UUID(input_data['draft_timeline_id'])
        user_id = UUID(input_data['user_id'])
        title = input_data.get('title')
        description = input_data.get('description')
        
        # Step 1: Validate DraftTimeline must exist
        with self._trace_step("validate_draft_timeline_exists") as step:
            draft_timeline = self.db.query(DraftTimeline).filter(
                DraftTimeline.id == draft_timeline_id
            ).first()
            
            if not draft_timeline:
                raise TimelineOrchestratorError(
                    f"Draft timeline {draft_timeline_id} not found"
                )
            
            # Validate ownership
            if draft_timeline.user_id != user_id:
                raise TimelineOrchestratorError(
                    f"Draft timeline {draft_timeline_id} does not belong to user {user_id}"
                )
            
            step.details = {
                "draft_timeline_id": str(draft_timeline_id),
                "title": draft_timeline.title,
                "version": draft_timeline.version_number,
                "is_active": draft_timeline.is_active
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="draft_timeline_data",
                data={
                    "id": str(draft_timeline.id),
                    "title": draft_timeline.title,
                    "baseline_id": str(draft_timeline.baseline_id),
                    "is_active": draft_timeline.is_active
                },
                source=f"DraftTimeline:{draft_timeline_id}",
                confidence=1.0
            )
        
        # Step 2: Validate completeness
        with self._trace_step("validate_completeness") as step:
            draft_stages = self.db.query(TimelineStage).filter(
                TimelineStage.draft_timeline_id == draft_timeline_id
            ).order_by(TimelineStage.stage_order).all()
            
            if not draft_stages:
                raise TimelineOrchestratorError(
                    "Draft timeline has no stages. Cannot commit incomplete timeline."
                )
            
            # Validate each stage has required fields
            incomplete_stages = []
            for stage in draft_stages:
                if not stage.title or not stage.title.strip():
                    incomplete_stages.append(f"Stage {stage.stage_order}: missing title")
                if stage.duration_months is None or stage.duration_months <= 0:
                    incomplete_stages.append(f"Stage {stage.stage_order}: invalid duration")
            
            if incomplete_stages:
                raise TimelineOrchestratorError(
                    f"Draft timeline is incomplete: {', '.join(incomplete_stages)}"
                )
            
            # Get milestones for completeness check
            total_milestones = 0
            milestones_by_stage = {}
            for stage in draft_stages:
                milestones = self.db.query(TimelineMilestone).filter(
                    TimelineMilestone.timeline_stage_id == stage.id
                ).order_by(TimelineMilestone.milestone_order).all()
                milestones_by_stage[stage.id] = milestones
                total_milestones += len(milestones)
            
            step.details = {
                "total_stages": len(draft_stages),
                "total_milestones": total_milestones,
                "is_complete": True
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="completeness_validation",
                data={
                    "stages": [s.title for s in draft_stages],
                    "total_milestones": total_milestones,
                    "stage_count": len(draft_stages)
                },
                source=f"DraftTimeline:{draft_timeline_id}",
                confidence=1.0
            )
        
        # Step 3: Prevent re-commit
        with self._trace_step("prevent_recommit") as step:
            existing_commit = self.db.query(CommittedTimeline).filter(
                CommittedTimeline.draft_timeline_id == draft_timeline_id
            ).first()
            
            if existing_commit:
                raise TimelineAlreadyCommittedError(
                    f"Draft timeline {draft_timeline_id} has already been committed. "
                    f"Committed timeline ID: {existing_commit.id}. "
                    f"Cannot commit the same draft timeline twice."
                )
            
            # Also check if draft is already frozen
            if not draft_timeline.is_active:
                raise TimelineImmutableError(
                    f"Draft timeline {draft_timeline_id} is already frozen (inactive). "
                    f"It may have been committed previously."
                )
            
            step.details = {
                "already_committed": False,
                "is_active": draft_timeline.is_active
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="recommit_check",
                data={
                    "already_committed": False,
                    "is_active": draft_timeline.is_active
                },
                source=f"DraftTimeline:{draft_timeline_id}",
                confidence=1.0
            )
        
        # Step 4: Capture edit history
        with self._trace_step("capture_edit_history") as step:
            edit_history = self.db.query(TimelineEditHistory).filter(
                TimelineEditHistory.draft_timeline_id == draft_timeline_id
            ).order_by(TimelineEditHistory.created_at).all()
            
            step.details = {
                "total_edits": len(edit_history)
            }
            
            # Add evidence
            if edit_history:
                self.add_evidence(
                    evidence_type="edit_history",
                    data={
                        "edit_count": len(edit_history),
                        "edit_types": list(set(e.edit_type for e in edit_history))
                    },
                    source=f"DraftTimeline:{draft_timeline_id}",
                    confidence=1.0
                )
        
        # Step 5: Increment version
        with self._trace_step("increment_version") as step:
            current_version = draft_timeline.version_number or "1.0"
            new_version = self._increment_version(current_version)
            
            step.details = {
                "old_version": current_version,
                "new_version": new_version
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="version_increment",
                data={
                    "old_version": current_version,
                    "new_version": new_version
                },
                source=f"DraftTimeline:{draft_timeline_id}",
                confidence=1.0
            )
        
        # Step 6: Create CommittedTimeline (immutable)
        with self._trace_step("create_committed_timeline") as step:
            committed_timeline = self._create_committed_timeline_record(
                draft_timeline=draft_timeline,
                user_id=user_id,
                title=title,
                description=description,
                version_number=new_version
            )
            
            step.details = {
                "committed_timeline_id": str(committed_timeline.id),
                "version": new_version,
                "is_immutable": True
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="committed_timeline_created",
                data={
                    "id": str(committed_timeline.id),
                    "draft_timeline_id": str(draft_timeline_id),
                    "version": new_version
                },
                source=f"CommittedTimeline:{committed_timeline.id}",
                confidence=1.0
            )
        
        # Step 7: Copy stages and milestones to committed timeline
        with self._trace_step("copy_stages_and_milestones") as step:
            stage_mapping = self._copy_stages_to_committed(
                draft_stages=draft_stages,
                committed_timeline_id=committed_timeline.id
            )
            
            self._copy_milestones_to_committed(
                draft_stages=draft_stages,
                stage_mapping=stage_mapping
            )
            
            step.details = {
                "stages_copied": len(stage_mapping),
                "milestones_copied": total_milestones
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="content_copied",
                data={
                    "stages_copied": len(stage_mapping),
                    "milestones_copied": total_milestones
                },
                source=f"CommittedTimeline:{committed_timeline.id}",
                confidence=1.0
            )
        
        # Step 8: Freeze content (mark draft as inactive)
        with self._trace_step("freeze_content") as step:
            draft_timeline.is_active = False
            draft_timeline.notes = (
                f"{draft_timeline.notes or ''}\n"
                f"Status: {self.STATUS_COMMITTED} on {datetime.utcnow().isoformat()}\n"
                f"Committed Timeline ID: {committed_timeline.id}\n"
                f"Version: {new_version}"
            )
            self.db.add(draft_timeline)
            
            step.details = {
                "frozen": True,
                "is_active": False,
                "status": self.STATUS_COMMITTED
            }
            
            # Add evidence
            self.add_evidence(
                evidence_type="draft_frozen",
                data={
                    "draft_timeline_id": str(draft_timeline_id),
                    "is_active": False,
                    "committed_timeline_id": str(committed_timeline.id)
                },
                source=f"DraftTimeline:{draft_timeline_id}",
                confidence=1.0
            )
        
        # Step 9: Persist all changes
        with self._trace_step("persist_changes"):
            self.db.commit()
            self.db.refresh(committed_timeline)
            self.db.refresh(draft_timeline)
        
        # Step 10: Write DecisionTrace (automatic via BaseOrchestrator.execute())
        # The BaseOrchestrator.execute() method automatically writes DecisionTrace
        # after _execute_commit_pipeline completes successfully
        
        # Build UI response
        response = self._build_commit_response(
            committed_timeline=committed_timeline,
            draft_timeline=draft_timeline,
            stage_mapping=stage_mapping,
            edit_history=edit_history
        )
        
        return response
    
    def commit_timeline(
        self,
        draft_timeline_id: UUID,
        user_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> UUID:
        """
        Commit a draft timeline to create an immutable committed timeline.
        
        Rules:
        - Draft timeline must exist and belong to user
        - Draft timeline must not have been committed already
        - Creates a new CommittedTimeline record
        - Copies all stages and milestones
        - Marks draft timeline as inactive (committed)
        - Version numbers increment automatically
        
        Args:
            draft_timeline_id: ID of draft timeline to commit
            user_id: ID of user committing the timeline
            title: Optional title override
            description: Optional description override
            
        Returns:
            UUID of created CommittedTimeline
            
        Raises:
            TimelineOrchestratorError: If validation fails
            TimelineAlreadyCommittedError: If draft already committed
        """
        # Step 1: Verify user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise TimelineOrchestratorError(f"User with ID {user_id} not found")
        
        # Step 2: Get draft timeline and verify ownership
        draft_timeline = self.db.query(DraftTimeline).filter(
            DraftTimeline.id == draft_timeline_id
        ).first()
        
        if not draft_timeline:
            raise TimelineOrchestratorError(
                f"Draft timeline with ID {draft_timeline_id} not found"
            )
        
        if draft_timeline.user_id != user_id:
            raise TimelineOrchestratorError(
                f"Draft timeline {draft_timeline_id} does not belong to user {user_id}"
            )
        
        # Step 3: Check if already committed
        if not draft_timeline.is_active or self.STATUS_COMMITTED in (draft_timeline.notes or ""):
            # Check if a committed timeline already references this draft
            existing_commit = self.db.query(CommittedTimeline).filter(
                CommittedTimeline.draft_timeline_id == draft_timeline_id
            ).first()
            
            if existing_commit:
                raise TimelineAlreadyCommittedError(
                    f"Draft timeline {draft_timeline_id} has already been committed "
                    f"(committed timeline: {existing_commit.id})"
                )
        
        # Step 4: Get draft timeline stages
        draft_stages = self.db.query(TimelineStage).filter(
            TimelineStage.draft_timeline_id == draft_timeline_id
        ).order_by(TimelineStage.stage_order).all()
        
        if not draft_stages:
            raise TimelineOrchestratorError(
                "Draft timeline has no stages. Cannot commit empty timeline."
            )
        
        # Step 5: Increment version number
        new_version = self._increment_version(draft_timeline.version_number or "1.0")
        
        # Step 6: Create committed timeline
        committed_timeline = self._create_committed_timeline_record(
            draft_timeline=draft_timeline,
            user_id=user_id,
            title=title,
            description=description,
            version_number=new_version,
        )
        
        # Step 7: Copy stages to committed timeline
        stage_mapping = self._copy_stages_to_committed(
            draft_stages=draft_stages,
            committed_timeline_id=committed_timeline.id,
        )
        
        # Step 8: Copy milestones to committed timeline
        self._copy_milestones_to_committed(
            draft_stages=draft_stages,
            stage_mapping=stage_mapping,
        )
        
        # Step 9: Mark draft timeline as committed (inactive)
        draft_timeline.is_active = False
        draft_timeline.notes = f"{draft_timeline.notes or ''}\nStatus: {self.STATUS_COMMITTED} on {committed_timeline.created_at}"
        self.db.add(draft_timeline)
        
        # Commit all changes
        self.db.commit()
        self.db.refresh(committed_timeline)
        
        return committed_timeline.id
    
    def get_committed_timeline(
        self,
        committed_timeline_id: UUID
    ) -> Optional[CommittedTimeline]:
        """
        Get a committed timeline by ID.
        
        Args:
            committed_timeline_id: Committed timeline ID
            
        Returns:
            CommittedTimeline or None if not found
        """
        return self.db.query(CommittedTimeline).filter(
            CommittedTimeline.id == committed_timeline_id
        ).first()
    
    def get_committed_timeline_with_details(
        self,
        committed_timeline_id: UUID
    ) -> Optional[Dict]:
        """
        Get committed timeline with stages and milestones.
        
        Args:
            committed_timeline_id: Committed timeline ID
            
        Returns:
            Dictionary with timeline, stages, and milestones
        """
        committed_timeline = self.get_committed_timeline(committed_timeline_id)
        
        if not committed_timeline:
            return None
        
        # Get stages
        stages = self.db.query(TimelineStage).filter(
            TimelineStage.committed_timeline_id == committed_timeline_id
        ).order_by(TimelineStage.stage_order).all()
        
        # Get milestones for each stage
        stages_with_milestones = []
        for stage in stages:
            milestones = self.db.query(TimelineMilestone).filter(
                TimelineMilestone.timeline_stage_id == stage.id
            ).order_by(TimelineMilestone.milestone_order).all()
            
            stages_with_milestones.append({
                "stage": stage,
                "milestones": milestones
            })
        
        return {
            "timeline": committed_timeline,
            "baseline": committed_timeline.baseline,
            "draft_timeline": committed_timeline.draft_timeline,
            "stages": stages_with_milestones,
            "total_stages": len(stages),
            "total_milestones": sum(len(s["milestones"]) for s in stages_with_milestones)
        }
    
    def get_user_committed_timelines(
        self,
        user_id: UUID,
        baseline_id: Optional[UUID] = None,
    ) -> List[CommittedTimeline]:
        """
        Get committed timelines for a user.
        
        Args:
            user_id: User ID
            baseline_id: Optional baseline ID to filter by
            
        Returns:
            List of CommittedTimeline objects
        """
        query = self.db.query(CommittedTimeline).filter(
            CommittedTimeline.user_id == user_id
        )
        
        if baseline_id:
            query = query.filter(CommittedTimeline.baseline_id == baseline_id)
        
        return query.order_by(CommittedTimeline.committed_date.desc()).all()
    
    def is_timeline_committed(self, draft_timeline_id: UUID) -> bool:
        """
        Check if a draft timeline has been committed.
        
        Args:
            draft_timeline_id: Draft timeline ID
            
        Returns:
            True if committed, False otherwise
        """
        committed = self.db.query(CommittedTimeline).filter(
            CommittedTimeline.draft_timeline_id == draft_timeline_id
        ).first()
        
        return committed is not None
    
    # Private helper methods
    
    def _load_document_text(self, baseline: Baseline) -> Optional[str]:
        """
        Load document text from baseline's associated document.
        
        Args:
            baseline: Baseline object
            
        Returns:
            Document text or None if no document
        """
        if not baseline.document_artifact_id:
            return None
        
        document = self.db.query(DocumentArtifact).filter(
            DocumentArtifact.id == baseline.document_artifact_id
        ).first()
        
        if not document:
            return None
        
        # Extract text from metadata field (where DocumentService stores it)
        return document.metadata
    
    def _create_draft_timeline_record(
        self,
        baseline: Baseline,
        user_id: UUID,
        title: Optional[str],
        description: Optional[str],
        version_number: str,
    ) -> DraftTimeline:
        """
        Create the draft timeline database record.
        
        Args:
            baseline: Baseline object
            user_id: User ID
            title: Timeline title
            description: Timeline description
            version_number: Version number
            
        Returns:
            Created DraftTimeline object
        """
        # Generate default title if not provided
        if not title:
            title = f"Draft Timeline: {baseline.program_name}"
        
        # Generate default description if not provided
        if not description:
            description = (
                f"Draft timeline for {baseline.program_name} at {baseline.institution}. "
                f"Generated from baseline requirements and program structure."
            )
        
        draft_timeline = DraftTimeline(
            user_id=user_id,
            baseline_id=baseline.id,
            title=title,
            description=description,
            version_number=version_number,
            is_active=True,  # Mark as active draft
            notes=f"Status: {self.STATUS_DRAFT}",  # Store status in notes
        )
        
        self.db.add(draft_timeline)
        self.db.flush()  # Get ID without committing
        
        return draft_timeline
    
    def _create_stage_records(
        self,
        draft_timeline_id: UUID,
        detected_stages: List[DetectedStage],
        duration_estimates: List[DurationEstimate],
    ) -> List[TimelineStage]:
        """
        Create timeline stage records.
        
        Args:
            draft_timeline_id: Draft timeline ID
            detected_stages: List of detected stages from intelligence engine
            duration_estimates: List of duration estimates
            
        Returns:
            List of created TimelineStage objects
        """
        stage_records = []
        
        # Create a mapping of stage descriptions to durations (use average of min/max)
        duration_map = {
            est.item_description.lower(): (est.duration_months_min + est.duration_months_max) // 2
            for est in duration_estimates
        }
        
        for order, stage in enumerate(detected_stages, start=1):
            # Try to find matching duration estimate
            duration = None
            for desc, months in duration_map.items():
                if stage.stage_type.value in desc or stage.title.lower() in desc:
                    duration = months
                    break
            
            # Use default if no match found
            if duration is None:
                duration = self._get_default_stage_duration(stage.stage_type)
            
            # Map stage status
            status = "not_started"
            
            stage_record = TimelineStage(
                draft_timeline_id=draft_timeline_id,
                title=stage.title,
                description=stage.description,
                stage_order=order,
                duration_months=duration,
                status=status,
                notes=f"Confidence: {stage.confidence:.2f}, Keywords: {', '.join(stage.keywords_matched[:3])}"
            )
            
            self.db.add(stage_record)
            self.db.flush()
            stage_records.append(stage_record)
        
        return stage_records
    
    def _create_milestone_records(
        self,
        stage_records: List[TimelineStage],
        extracted_milestones: List[ExtractedMilestone],
        detected_stages: List[DetectedStage],
    ) -> List[TimelineMilestone]:
        """
        Create timeline milestone records.
        
        Args:
            stage_records: List of created TimelineStage objects
            extracted_milestones: List of extracted milestones
            detected_stages: List of detected stages (for mapping)
            
        Returns:
            List of created TimelineMilestone objects
        """
        milestone_records = []
        
        # Create a mapping of milestones to stages based on keywords
        for milestone in extracted_milestones:
            # Find the most appropriate stage for this milestone
            assigned_stage = self._assign_milestone_to_stage(
                milestone, stage_records, detected_stages
            )
            
            if assigned_stage:
                # Get milestone order within the stage
                milestone_order = len([
                    m for m in milestone_records 
                    if m.timeline_stage_id == assigned_stage.id
                ]) + 1
                
                milestone_record = TimelineMilestone(
                    timeline_stage_id=assigned_stage.id,
                    title=milestone.title,
                    description=milestone.description,
                    milestone_order=milestone_order,
                    is_critical=milestone.is_critical,
                    is_completed=False,
                    deliverable_type=milestone.milestone_type,
                    notes=f"Keywords: {', '.join(milestone.keywords)}"
                )
                
                self.db.add(milestone_record)
                self.db.flush()
                milestone_records.append(milestone_record)
        
        return milestone_records
    
    def _assign_milestone_to_stage(
        self,
        milestone: ExtractedMilestone,
        stage_records: List[TimelineStage],
        detected_stages: List[DetectedStage],
    ) -> Optional[TimelineStage]:
        """
        Assign a milestone to the most appropriate stage.
        
        Args:
            milestone: Extracted milestone
            stage_records: List of stage records
            detected_stages: List of detected stages
            
        Returns:
            TimelineStage to assign milestone to, or None
        """
        if not stage_records:
            return None
        
        # Map milestone types to stage types
        milestone_stage_mapping = {
            "exam": [StageType.COURSEWORK, StageType.RESEARCH],
            "proposal": [StageType.RESEARCH, StageType.LITERATURE_REVIEW],
            "review": [StageType.RESEARCH, StageType.WRITING],
            "publication": [StageType.PUBLICATION, StageType.RESEARCH],
            "deliverable": [StageType.WRITING, StageType.RESEARCH],
            "defense": [StageType.DEFENSE],
        }
        
        # Get preferred stage types for this milestone
        preferred_types = milestone_stage_mapping.get(
            milestone.milestone_type,
            [StageType.OTHER]
        )
        
        # Try to find a matching stage
        for stage_type in preferred_types:
            for i, detected_stage in enumerate(detected_stages):
                if detected_stage.stage_type == stage_type:
                    return stage_records[i]
        
        # Fallback: assign to first stage
        return stage_records[0]
    
    def _get_default_stage_duration(self, stage_type: StageType) -> int:
        """
        Get default duration for a stage type.
        
        Args:
            stage_type: Stage type
            
        Returns:
            Duration in months
        """
        defaults = {
            StageType.COURSEWORK: 18,
            StageType.LITERATURE_REVIEW: 6,
            StageType.RESEARCH: 24,
            StageType.ANALYSIS: 6,
            StageType.WRITING: 12,
            StageType.DEFENSE: 3,
            StageType.PUBLICATION: 6,
            StageType.OTHER: 3
        }
        return defaults.get(stage_type, 6)
    
    def _increment_version(self, version: str) -> str:
        """
        Increment version number.
        
        Supports formats like:
        - "1.0" -> "2.0"
        - "1.5" -> "2.0"
        - "2" -> "3"
        
        Args:
            version: Current version string
            
        Returns:
            Incremented version string
        """
        try:
            parts = version.split('.')
            major = int(parts[0])
            return f"{major + 1}.0"
        except (ValueError, IndexError):
            return "2.0"
    
    def _create_committed_timeline_record(
        self,
        draft_timeline: DraftTimeline,
        user_id: UUID,
        title: Optional[str],
        description: Optional[str],
        version_number: str,
    ) -> CommittedTimeline:
        """
        Create the committed timeline database record.
        
        Args:
            draft_timeline: Source draft timeline
            user_id: User ID
            title: Timeline title (or None to use draft title)
            description: Timeline description (or None to use draft description)
            version_number: Version number
            
        Returns:
            Created CommittedTimeline object
        """
        from datetime import date
        
        committed_timeline = CommittedTimeline(
            user_id=user_id,
            baseline_id=draft_timeline.baseline_id,
            draft_timeline_id=draft_timeline.id,
            title=title or draft_timeline.title,
            description=description or draft_timeline.description,
            committed_date=date.today(),
            target_completion_date=None,  # Can be calculated from stages
            notes=f"Version {version_number}. Committed from draft timeline {draft_timeline.id}"
        )
        
        self.db.add(committed_timeline)
        self.db.flush()
        
        return committed_timeline
    
    def _copy_stages_to_committed(
        self,
        draft_stages: List[TimelineStage],
        committed_timeline_id: UUID,
    ) -> Dict[UUID, TimelineStage]:
        """
        Copy stages from draft timeline to committed timeline.
        
        Args:
            draft_stages: List of draft stages to copy
            committed_timeline_id: Target committed timeline ID
            
        Returns:
            Dictionary mapping draft stage ID to committed stage
        """
        stage_mapping = {}
        
        for draft_stage in draft_stages:
            committed_stage = TimelineStage(
                committed_timeline_id=committed_timeline_id,
                title=draft_stage.title,
                description=draft_stage.description,
                stage_order=draft_stage.stage_order,
                start_date=draft_stage.start_date,
                end_date=draft_stage.end_date,
                duration_months=draft_stage.duration_months,
                status=draft_stage.status,
                notes=draft_stage.notes,
            )
            
            self.db.add(committed_stage)
            self.db.flush()
            stage_mapping[draft_stage.id] = committed_stage
        
        return stage_mapping
    
    def _copy_milestones_to_committed(
        self,
        draft_stages: List[TimelineStage],
        stage_mapping: Dict[UUID, TimelineStage],
    ) -> None:
        """
        Copy milestones from draft stages to committed stages.
        
        Args:
            draft_stages: List of draft stages
            stage_mapping: Mapping of draft stage ID to committed stage
        """
        for draft_stage in draft_stages:
            committed_stage = stage_mapping[draft_stage.id]
            
            # Get milestones for this draft stage
            draft_milestones = self.db.query(TimelineMilestone).filter(
                TimelineMilestone.timeline_stage_id == draft_stage.id
            ).order_by(TimelineMilestone.milestone_order).all()
            
            # Copy each milestone
            for draft_milestone in draft_milestones:
                committed_milestone = TimelineMilestone(
                    timeline_stage_id=committed_stage.id,
                    title=draft_milestone.title,
                    description=draft_milestone.description,
                    milestone_order=draft_milestone.milestone_order,
                    target_date=draft_milestone.target_date,
                    actual_completion_date=draft_milestone.actual_completion_date,
                    is_completed=draft_milestone.is_completed,
                    is_critical=draft_milestone.is_critical,
                    deliverable_type=draft_milestone.deliverable_type,
                    notes=draft_milestone.notes,
                )
                
                self.db.add(committed_milestone)
    
    def _create_stages_from_structured(
        self,
        draft_timeline_id: UUID,
        structured_timeline: StructuredTimeline
    ) -> List[TimelineStage]:
        """
        Create stage records from structured timeline.
        
        Args:
            draft_timeline_id: Draft timeline ID
            structured_timeline: Structured timeline from intelligence engine
            
        Returns:
            List of created TimelineStage objects
        """
        stage_records = []
        
        # Create duration lookup
        duration_lookup = {
            d.item_description.lower(): d
            for d in structured_timeline.durations
            if d.item_type == "stage"
        }
        
        for order, stage in enumerate(structured_timeline.stages, start=1):
            # Find duration for this stage
            duration_est = duration_lookup.get(stage.title.lower())
            
            if duration_est:
                duration_months = duration_est.duration_months_max  # Use max for planning
            else:
                duration_months = self._get_default_stage_duration(stage.stage_type)
            
            stage_record = TimelineStage(
                draft_timeline_id=draft_timeline_id,
                title=stage.title,
                description=stage.description,
                stage_order=order,
                duration_months=duration_months,
                status="not_started",
                notes=f"Confidence: {stage.confidence:.2f}, Order hint: {stage.order_hint}"
            )
            
            self.db.add(stage_record)
            self.db.flush()
            stage_records.append(stage_record)
        
        return stage_records
    
    def _create_milestones_from_structured(
        self,
        stage_records: List[TimelineStage],
        structured_timeline: StructuredTimeline
    ) -> List[TimelineMilestone]:
        """
        Create milestone records from structured timeline.
        
        Args:
            stage_records: List of created TimelineStage objects
            structured_timeline: Structured timeline from intelligence engine
            
        Returns:
            List of created TimelineMilestone objects
        """
        milestone_records = []
        
        # Group milestones by stage
        by_stage = {}
        for milestone in structured_timeline.milestones:
            stage_name = milestone.stage
            if stage_name not in by_stage:
                by_stage[stage_name] = []
            by_stage[stage_name].append(milestone)
        
        # Create milestone records for each stage
        for stage_record in stage_records:
            stage_milestones = by_stage.get(stage_record.title, [])
            
            for order, milestone in enumerate(stage_milestones, start=1):
                milestone_record = TimelineMilestone(
                    timeline_stage_id=stage_record.id,
                    title=milestone.name,
                    description=milestone.description,
                    milestone_order=order,
                    is_critical=milestone.is_critical,
                    is_completed=False,
                    deliverable_type=milestone.milestone_type,
                    notes=f"Confidence: {milestone.confidence:.2f}, Evidence: {milestone.evidence_snippet[:50]}..."
                )
                
                self.db.add(milestone_record)
                self.db.flush()
                milestone_records.append(milestone_record)
        
        return milestone_records
    
    def _build_ui_response(
        self,
        draft_timeline: DraftTimeline,
        stage_records: List[TimelineStage],
        milestone_records: List[TimelineMilestone],
        structured_timeline: StructuredTimeline
    ) -> Dict[str, Any]:
        """
        Build UI-ready JSON response.
        
        Args:
            draft_timeline: Created draft timeline
            stage_records: Created stage records
            milestone_records: Created milestone records
            structured_timeline: Structured timeline with metadata
            
        Returns:
            UI-ready JSON dictionary
        """
        # Group milestones by stage
        milestones_by_stage = {}
        for milestone in milestone_records:
            stage_id = milestone.timeline_stage_id
            if stage_id not in milestones_by_stage:
                milestones_by_stage[stage_id] = []
            milestones_by_stage[stage_id].append(milestone)
        
        # Build stages array with milestones
        stages_array = []
        for stage in stage_records:
            stage_milestones = milestones_by_stage.get(stage.id, [])
            
            stages_array.append({
                "id": str(stage.id),
                "title": stage.title,
                "description": stage.description,
                "stage_order": stage.stage_order,
                "duration_months": stage.duration_months,
                "status": stage.status,
                "milestones": [
                    {
                        "id": str(m.id),
                        "title": m.title,
                        "description": m.description,
                        "milestone_order": m.milestone_order,
                        "is_critical": m.is_critical,
                        "is_completed": m.is_completed,
                        "deliverable_type": m.deliverable_type
                    }
                    for m in stage_milestones
                ]
            })
        
        # Build dependencies array
        dependencies_array = [
            {
                "dependent_item": dep.dependent_item,
                "depends_on_item": dep.depends_on_item,
                "dependency_type": dep.dependency_type,
                "confidence": dep.confidence,
                "reason": dep.reason
            }
            for dep in structured_timeline.dependencies
        ]
        
        # Build duration estimates array
        durations_array = [
            {
                "item_description": dur.item_description,
                "item_type": dur.item_type,
                "duration_weeks_min": dur.duration_weeks_min,
                "duration_weeks_max": dur.duration_weeks_max,
                "duration_months_min": dur.duration_months_min,
                "duration_months_max": dur.duration_months_max,
                "confidence": dur.confidence,
                "basis": dur.basis
            }
            for dur in structured_timeline.durations
        ]
        
        # Build complete response
        return {
            "timeline": {
                "id": str(draft_timeline.id),
                "baseline_id": str(draft_timeline.baseline_id),
                "user_id": str(draft_timeline.user_id),
                "title": draft_timeline.title,
                "description": draft_timeline.description,
                "version_number": draft_timeline.version_number,
                "is_active": draft_timeline.is_active,
                "status": self.STATUS_DRAFT,
                "created_at": draft_timeline.created_at.isoformat() if draft_timeline.created_at else None
            },
            "stages": stages_array,
            "dependencies": dependencies_array,
            "durations": durations_array,
            "metadata": {
                "total_stages": len(stage_records),
                "total_milestones": len(milestone_records),
                "total_duration_months_min": structured_timeline.total_duration_months_min,
                "total_duration_months_max": structured_timeline.total_duration_months_max,
                "is_dag_valid": structured_timeline.is_dag_valid,
                "generated_at": datetime.utcnow().isoformat()
            }
        }
    
    def _apply_timeline_edit(
        self,
        draft_timeline: DraftTimeline,
        operation: str,
        data: Dict[str, Any],
        user_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Apply edit to timeline itself (title, description)."""
        if operation != "update":
            return None
        
        changes = {}
        
        if "title" in data and data["title"] != draft_timeline.title:
            changes["title"] = {
                "before": draft_timeline.title,
                "after": data["title"]
            }
            draft_timeline.title = data["title"]
        
        if "description" in data and data["description"] != draft_timeline.description:
            changes["description"] = {
                "before": draft_timeline.description,
                "after": data["description"]
            }
            draft_timeline.description = data["description"]
        
        if changes:
            # Record edit in history
            edit_record = TimelineEditHistory(
                draft_timeline_id=draft_timeline.id,
                user_id=user_id,
                edit_type="modified",
                entity_type="timeline",
                entity_id=draft_timeline.id,
                changes_json=changes,
                description="Timeline metadata updated"
            )
            self.db.add(edit_record)
            self.db.flush()
            
            return {
                "entity_type": "timeline",
                "operation": "update",
                "changes": changes
            }
        
        return None
    
    def _apply_stage_edit(
        self,
        draft_timeline_id: UUID,
        operation: str,
        entity_id: Optional[str],
        data: Dict[str, Any],
        user_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Apply edit to stage."""
        if operation == "update" and entity_id:
            stage = self.db.query(TimelineStage).filter(
                TimelineStage.id == UUID(entity_id),
                TimelineStage.draft_timeline_id == draft_timeline_id
            ).first()
            
            if not stage:
                return None
            
            changes = {}
            
            if "title" in data and data["title"] != stage.title:
                changes["title"] = {"before": stage.title, "after": data["title"]}
                stage.title = data["title"]
            
            if "description" in data and data["description"] != stage.description:
                changes["description"] = {"before": stage.description, "after": data["description"]}
                stage.description = data["description"]
            
            if "duration_months" in data and data["duration_months"] != stage.duration_months:
                changes["duration_months"] = {"before": stage.duration_months, "after": data["duration_months"]}
                stage.duration_months = data["duration_months"]
            
            if "status" in data and data["status"] != stage.status:
                changes["status"] = {"before": stage.status, "after": data["status"]}
                stage.status = data["status"]
            
            if changes:
                edit_record = TimelineEditHistory(
                    draft_timeline_id=draft_timeline_id,
                    user_id=user_id,
                    edit_type="modified",
                    entity_type="stage",
                    entity_id=stage.id,
                    changes_json=changes,
                    description=f"Stage '{stage.title}' updated"
                )
                self.db.add(edit_record)
                self.db.flush()
                
                return {
                    "entity_type": "stage",
                    "entity_id": str(stage.id),
                    "operation": "update",
                    "changes": changes
                }
        
        elif operation == "add":
            # Create new stage
            stage_order = self.db.query(TimelineStage).filter(
                TimelineStage.draft_timeline_id == draft_timeline_id
            ).count() + 1
            
            new_stage = TimelineStage(
                draft_timeline_id=draft_timeline_id,
                title=data.get("title", "New Stage"),
                description=data.get("description", ""),
                stage_order=stage_order,
                duration_months=data.get("duration_months", 6),
                status=data.get("status", "not_started")
            )
            self.db.add(new_stage)
            self.db.flush()
            
            edit_record = TimelineEditHistory(
                draft_timeline_id=draft_timeline_id,
                user_id=user_id,
                edit_type="added",
                entity_type="stage",
                entity_id=new_stage.id,
                changes_json={"title": data.get("title", "New Stage")},
                description=f"New stage '{new_stage.title}' added"
            )
            self.db.add(edit_record)
            self.db.flush()
            
            return {
                "entity_type": "stage",
                "entity_id": str(new_stage.id),
                "operation": "add",
                "title": new_stage.title
            }
        
        elif operation == "delete" and entity_id:
            stage = self.db.query(TimelineStage).filter(
                TimelineStage.id == UUID(entity_id),
                TimelineStage.draft_timeline_id == draft_timeline_id
            ).first()
            
            if stage:
                stage_title = stage.title
                
                edit_record = TimelineEditHistory(
                    draft_timeline_id=draft_timeline_id,
                    user_id=user_id,
                    edit_type="deleted",
                    entity_type="stage",
                    entity_id=stage.id,
                    changes_json={"title": stage_title},
                    description=f"Stage '{stage_title}' deleted"
                )
                self.db.add(edit_record)
                
                self.db.delete(stage)
                self.db.flush()
                
                return {
                    "entity_type": "stage",
                    "entity_id": str(UUID(entity_id)),
                    "operation": "delete",
                    "title": stage_title
                }
        
        return None
    
    def _apply_milestone_edit(
        self,
        draft_timeline_id: UUID,
        operation: str,
        entity_id: Optional[str],
        data: Dict[str, Any],
        user_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Apply edit to milestone."""
        if operation == "update" and entity_id:
            milestone = self.db.query(TimelineMilestone).filter(
                TimelineMilestone.id == UUID(entity_id)
            ).join(TimelineStage).filter(
                TimelineStage.draft_timeline_id == draft_timeline_id
            ).first()
            
            if not milestone:
                return None
            
            changes = {}
            
            if "title" in data and data["title"] != milestone.title:
                changes["title"] = {"before": milestone.title, "after": data["title"]}
                milestone.title = data["title"]
            
            if "description" in data and data["description"] != milestone.description:
                changes["description"] = {"before": milestone.description, "after": data["description"]}
                milestone.description = data["description"]
            
            if "is_critical" in data and data["is_critical"] != milestone.is_critical:
                changes["is_critical"] = {"before": milestone.is_critical, "after": data["is_critical"]}
                milestone.is_critical = data["is_critical"]
            
            if "is_completed" in data and data["is_completed"] != milestone.is_completed:
                changes["is_completed"] = {"before": milestone.is_completed, "after": data["is_completed"]}
                milestone.is_completed = data["is_completed"]
            
            if changes:
                edit_record = TimelineEditHistory(
                    draft_timeline_id=draft_timeline_id,
                    user_id=user_id,
                    edit_type="modified",
                    entity_type="milestone",
                    entity_id=milestone.id,
                    changes_json=changes,
                    description=f"Milestone '{milestone.title}' updated"
                )
                self.db.add(edit_record)
                self.db.flush()
                
                return {
                    "entity_type": "milestone",
                    "entity_id": str(milestone.id),
                    "operation": "update",
                    "changes": changes
                }
        
        elif operation == "add" and "timeline_stage_id" in data:
            milestone_order = self.db.query(TimelineMilestone).filter(
                TimelineMilestone.timeline_stage_id == UUID(data["timeline_stage_id"])
            ).count() + 1
            
            new_milestone = TimelineMilestone(
                timeline_stage_id=UUID(data["timeline_stage_id"]),
                title=data.get("title", "New Milestone"),
                description=data.get("description", ""),
                milestone_order=milestone_order,
                is_critical=data.get("is_critical", False),
                is_completed=False,
                deliverable_type=data.get("deliverable_type", "deliverable")
            )
            self.db.add(new_milestone)
            self.db.flush()
            
            edit_record = TimelineEditHistory(
                draft_timeline_id=draft_timeline_id,
                user_id=user_id,
                edit_type="added",
                entity_type="milestone",
                entity_id=new_milestone.id,
                changes_json={"title": new_milestone.title},
                description=f"New milestone '{new_milestone.title}' added"
            )
            self.db.add(edit_record)
            self.db.flush()
            
            return {
                "entity_type": "milestone",
                "entity_id": str(new_milestone.id),
                "operation": "add",
                "title": new_milestone.title
            }
        
        elif operation == "delete" and entity_id:
            milestone = self.db.query(TimelineMilestone).filter(
                TimelineMilestone.id == UUID(entity_id)
            ).join(TimelineStage).filter(
                TimelineStage.draft_timeline_id == draft_timeline_id
            ).first()
            
            if milestone:
                milestone_title = milestone.title
                
                edit_record = TimelineEditHistory(
                    draft_timeline_id=draft_timeline_id,
                    user_id=user_id,
                    edit_type="deleted",
                    entity_type="milestone",
                    entity_id=milestone.id,
                    changes_json={"title": milestone_title},
                    description=f"Milestone '{milestone_title}' deleted"
                )
                self.db.add(edit_record)
                
                self.db.delete(milestone)
                self.db.flush()
                
                return {
                    "entity_type": "milestone",
                    "entity_id": str(UUID(entity_id)),
                    "operation": "delete",
                    "title": milestone_title
                }
        
        return None
    
    def _build_commit_response(
        self,
        committed_timeline: CommittedTimeline,
        draft_timeline: DraftTimeline,
        stage_mapping: Dict[UUID, TimelineStage],
        edit_history: List[TimelineEditHistory]
    ) -> Dict[str, Any]:
        """Build UI-ready response for commit operation."""
        # Get committed stages with milestones
        committed_stages = self.db.query(TimelineStage).filter(
            TimelineStage.committed_timeline_id == committed_timeline.id
        ).order_by(TimelineStage.stage_order).all()
        
        stages_array = []
        total_milestones = 0
        
        for stage in committed_stages:
            milestones = self.db.query(TimelineMilestone).filter(
                TimelineMilestone.timeline_stage_id == stage.id
            ).order_by(TimelineMilestone.milestone_order).all()
            
            total_milestones += len(milestones)
            
            stages_array.append({
                "id": str(stage.id),
                "title": stage.title,
                "description": stage.description,
                "stage_order": stage.stage_order,
                "duration_months": stage.duration_months,
                "status": stage.status,
                "milestones": [
                    {
                        "id": str(m.id),
                        "title": m.title,
                        "description": m.description,
                        "milestone_order": m.milestone_order,
                        "is_critical": m.is_critical,
                        "is_completed": m.is_completed,
                        "deliverable_type": m.deliverable_type
                    }
                    for m in milestones
                ]
            })
        
        # Build edit history summary
        edit_summary = {
            "total_edits": len(edit_history),
            "edit_types": {
                "added": len([e for e in edit_history if e.edit_type == "added"]),
                "modified": len([e for e in edit_history if e.edit_type == "modified"]),
                "deleted": len([e for e in edit_history if e.edit_type == "deleted"])
            },
            "edits": [
                {
                    "id": str(e.id),
                    "edit_type": e.edit_type,
                    "entity_type": e.entity_type,
                    "description": e.description,
                    "created_at": e.created_at.isoformat() if e.created_at else None
                }
                for e in edit_history
            ]
        }
        
        return {
            "committed_timeline": {
                "id": str(committed_timeline.id),
                "draft_timeline_id": str(committed_timeline.draft_timeline_id),
                "baseline_id": str(committed_timeline.baseline_id),
                "user_id": str(committed_timeline.user_id),
                "title": committed_timeline.title,
                "description": committed_timeline.description,
                "committed_date": committed_timeline.committed_date.isoformat() if committed_timeline.committed_date else None,
                "status": "COMMITTED",
                "is_immutable": True,
                "created_at": committed_timeline.created_at.isoformat() if committed_timeline.created_at else None
            },
            "draft_timeline": {
                "id": str(draft_timeline.id),
                "title": draft_timeline.title,
                "version_number": draft_timeline.version_number,
                "is_active": draft_timeline.is_active,
                "frozen": not draft_timeline.is_active
            },
            "stages": stages_array,
            "edit_history": edit_summary,
            "metadata": {
                "total_stages": len(stages_array),
                "total_milestones": total_milestones,
                "total_edits_applied": len(edit_history),
                "committed_at": datetime.utcnow().isoformat()
            }
        }
