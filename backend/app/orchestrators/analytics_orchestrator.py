"""Analytics orchestrator for generating analytics reports."""
from typing import Dict, List, Optional, Any
from uuid import UUID
from datetime import date, timedelta
from sqlalchemy.orm import Session
import json

from app.orchestrators.base import BaseOrchestrator
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.user import User
from app.models.committed_timeline import CommittedTimeline
from app.services.analytics_engine import (
    AnalyticsEngine,
    AnalyticsReport,
    AnalyticsSummary,
    TimeSeriesSummary,
    StatusIndicator,
)
from app.models.progress_event import ProgressEvent
from app.models.journey_assessment import JourneyAssessment
from app.models.timeline_stage import TimelineStage
from app.models.timeline_milestone import TimelineMilestone
from app.models.idempotency import DecisionTrace, EvidenceBundle


class AnalyticsOrchestratorError(Exception):
    """Base exception for analytics orchestrator errors."""
    pass


class AnalyticsOrchestrator(BaseOrchestrator[Dict[str, Any]]):
    """
    Orchestrator for generating analytics reports.
    
    Steps:
    1. Load longitudinal data
    2. Call AnalyticsEngine
    3. Persist analytics snapshot
    4. Return dashboard-ready JSON
    
    Extends BaseOrchestrator to provide:
    - Idempotent analytics generation
    - Decision tracing
    - Evidence bundling
    
    READ-ONLY CONTRACT:
    - Only READS from: CommittedTimeline, ProgressEvent, JourneyAssessment
    - Only WRITES to: AnalyticsSnapshot, DecisionTrace/EvidenceBundle
    - NO mutations to upstream state
    - Enforced via _validate_read_only_contract()
    """
    
    # Allowed models for READ operations
    _ALLOWED_READ_MODELS = {
        'User',
        'CommittedTimeline',
        'TimelineStage',
        'TimelineMilestone',
        'ProgressEvent',
        'JourneyAssessment',
        'DraftTimeline',
    }
    
    # Allowed models for WRITE operations
    _ALLOWED_WRITE_MODELS = {
        'AnalyticsSnapshot',
        'DecisionTrace',
        'EvidenceBundle',
    }
    
    @property
    def orchestrator_name(self) -> str:
        """Return orchestrator name."""
        return "analytics_orchestrator"
    
    def __init__(self, db: Session, user_id: Optional[UUID] = None):
        """
        Initialize analytics orchestrator.
        
        Args:
            db: Database session
            user_id: Optional user ID
        """
        super().__init__(db, user_id)
        self.analytics_engine = AnalyticsEngine(db)
        self._read_operations = []  # Track read operations for validation
        self._write_operations = []  # Track write operations for validation
    
    def run(
        self,
        request_id: str,
        user_id: UUID,
        timeline_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Run analytics aggregation with idempotency and tracing.
        
        Steps:
        1. Validate a CommittedTimeline exists
        2. Load: latest CommittedTimeline, ProgressEvents, latest JourneyAssessment
        3. Call AnalyticsEngine.aggregate()
        4. Persist AnalyticsSnapshot
        5. Write DecisionTrace (automatic via BaseOrchestrator)
        6. Return dashboard-ready JSON
        
        Rules:
        - Do NOT mutate any upstream state
        - Analytics is read + aggregate only
        
        Args:
            request_id: Idempotency key
            user_id: User ID
            timeline_id: Optional committed timeline ID (uses latest if not provided)
            
        Returns:
            Dashboard-ready JSON with analytics data
            
        Raises:
            AnalyticsOrchestratorError: If generation fails
        """
        return self.execute(
            request_id=request_id,
            input_data={
                "user_id": str(user_id),
                "timeline_id": str(timeline_id) if timeline_id else None,
            }
        )
    
    def generate(
        self,
        request_id: str,
        user_id: UUID,
        timeline_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        snapshot_type: str = "on_demand",
    ) -> Dict[str, Any]:
        """
        Generate analytics report with idempotency and tracing.
        
        Steps:
        1. Load longitudinal data
        2. Call AnalyticsEngine
        3. Persist analytics snapshot
        4. Return dashboard-ready JSON
        
        Args:
            request_id: Idempotency key
            user_id: User ID
            timeline_id: Optional committed timeline ID
            start_date: Optional start date for aggregation
            end_date: Optional end date for aggregation
            snapshot_type: Type of snapshot (daily, weekly, on_demand)
            
        Returns:
            Dashboard-ready JSON with analytics data
            
        Raises:
            AnalyticsOrchestratorError: If generation fails
        """
        return self.execute(
            request_id=request_id,
            input_data={
                "user_id": str(user_id),
                "timeline_id": str(timeline_id) if timeline_id else None,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "snapshot_type": snapshot_type,
            }
        )
    
    def _execute_pipeline(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the analytics generation pipeline.
        
        Steps:
        1. Validate a CommittedTimeline exists
        2. Load: latest CommittedTimeline, ProgressEvents, latest JourneyAssessment
        3. Call AnalyticsEngine.aggregate()
        4. Persist AnalyticsSnapshot
        5. Write DecisionTrace (automatic via BaseOrchestrator)
        6. Return dashboard-ready JSON
        
        Rules:
        - Do NOT mutate any upstream state
        - Analytics is read + aggregate only
        
        This is called by BaseOrchestrator.execute() which automatically
        writes DecisionTrace after successful completion.
        
        Args:
            context: Execution context with input data
            
        Returns:
            Dashboard-ready JSON response
        """
        # Reset operation tracking
        self._read_operations = []
        self._write_operations = []
        
        user_id = UUID(context["user_id"])
        timeline_id = UUID(context["timeline_id"]) if context.get("timeline_id") else None
        
        # Step 1: Validate a CommittedTimeline exists
        with self._trace_step("validate_committed_timeline") as step:
            # Invariant check: No analytics without committed timeline
            from app.utils.invariants import check_analytics_has_committed_timeline
            check_analytics_has_committed_timeline(
                db=self.db,
                user_id=user_id,
                timeline_id=timeline_id
            )
            
            # Validate user exists (READ operation)
            user = self._tracked_read(User, User.id == user_id).first()
            if not user:
                raise AnalyticsOrchestratorError(f"User with ID {user_id} not found")
            
            # Get committed timeline (READ operation)
            if timeline_id:
                committed_timeline = self._tracked_read(
                    CommittedTimeline,
                    CommittedTimeline.id == timeline_id,
                    CommittedTimeline.user_id == user_id
                ).first()
                if not committed_timeline:
                    raise AnalyticsOrchestratorError(
                        f"Timeline {timeline_id} not found or not owned by user {user_id}"
                    )
            else:
                # Get latest committed timeline
                committed_timeline = self._tracked_read(
                    CommittedTimeline,
                    CommittedTimeline.user_id == user_id
                ).order_by(CommittedTimeline.committed_date.desc()).first()
                
                if not committed_timeline:
                    raise AnalyticsOrchestratorError(
                        f"No committed timeline found for user {user_id}"
                    )
            
            step.details = {
                "user_id": str(user_id),
                "timeline_id": str(committed_timeline.id),
                "timeline_title": committed_timeline.title,
            }
            
            self.add_evidence(
                evidence_type="timeline_validated",
                data={
                    "timeline_id": str(committed_timeline.id),
                    "timeline_title": committed_timeline.title,
                    "committed_date": committed_timeline.committed_date.isoformat() if committed_timeline.committed_date else None,
                },
                source=f"CommittedTimeline:{committed_timeline.id}",
                confidence=1.0
            )
        
        # Step 2: Load data (read-only, no mutations)
        with self._trace_step("load_data") as step:
            # Get all milestones for this timeline to find progress events (READ operations)
            stages = self._tracked_read(
                TimelineStage,
                TimelineStage.committed_timeline_id == committed_timeline.id
            ).all()
            
            milestone_ids = []
            for stage in stages:
                milestones = self._tracked_read(
                    TimelineMilestone,
                    TimelineMilestone.timeline_stage_id == stage.id
                ).all()
                milestone_ids.extend([m.id for m in milestones])
            
            # Load ProgressEvents (READ operation)
            if milestone_ids:
                progress_events = self._tracked_read(
                    ProgressEvent,
                    ProgressEvent.user_id == user_id,
                    ProgressEvent.milestone_id.in_(milestone_ids)
                ).order_by(ProgressEvent.event_date.asc()).all()
            else:
                progress_events = []
            
            # Load latest JourneyAssessment (READ operation)
            latest_assessment = self._tracked_read(
                JourneyAssessment,
                JourneyAssessment.user_id == user_id
            ).order_by(JourneyAssessment.assessment_date.desc()).first()
            
            step.details = {
                "progress_events_count": len(progress_events),
                "has_latest_assessment": latest_assessment is not None,
                "milestones_count": len(milestone_ids),
            }
            
            self.add_evidence(
                evidence_type="data_loaded",
                data={
                    "progress_events_count": len(progress_events),
                    "has_latest_assessment": latest_assessment is not None,
                    "latest_assessment_date": latest_assessment.assessment_date.isoformat() if latest_assessment else None,
                    "milestones_count": len(milestone_ids),
                },
                source="Database",
                confidence=1.0
            )
        
        # Step 3: Call AnalyticsEngine.aggregate()
        with self._trace_step("call_analytics_engine") as step:
            analytics_summary = self.analytics_engine.aggregate(
                committed_timeline=committed_timeline,
                progress_events=progress_events,
                latest_assessment=latest_assessment
            )
            
            step.details = {
                "timeline_status": analytics_summary.timeline_status,
                "completion_percentage": analytics_summary.milestone_completion_percentage,
                "overdue_milestones": analytics_summary.overdue_milestones,
                "has_health_data": analytics_summary.latest_health_score is not None,
            }
            
            self.add_evidence(
                evidence_type="analytics_aggregated",
                data={
                    "timeline_status": analytics_summary.timeline_status,
                    "completion_percentage": analytics_summary.milestone_completion_percentage,
                    "overdue_milestones": analytics_summary.overdue_milestones,
                    "latest_health_score": analytics_summary.latest_health_score,
                },
                source="AnalyticsEngine",
                confidence=1.0
            )
        
        # Step 4: Persist AnalyticsSnapshot (WRITE operation)
        with self._trace_step("persist_analytics_snapshot") as step:
            # Get timeline version from draft_timeline if available
            timeline_version = self._extract_timeline_version(committed_timeline)
            
            snapshot_id = self._persist_snapshot(
                user_id=user_id,
                timeline_version=timeline_version,
                analytics_summary=analytics_summary
            )
            
            step.details = {
                "snapshot_id": str(snapshot_id),
                "timeline_version": timeline_version,
            }
            
            self.add_evidence(
                evidence_type="snapshot_persisted",
                data={
                    "snapshot_id": str(snapshot_id),
                    "timeline_version": timeline_version,
                },
                source=f"AnalyticsSnapshot:{snapshot_id}",
                confidence=1.0
            )
        
        # Step 5: Validate read-only contract
        self._validate_read_only_contract()
        
        # Step 6: Write DecisionTrace (automatic via BaseOrchestrator.execute())
        # The BaseOrchestrator.execute() method automatically writes DecisionTrace
        # after _execute_pipeline completes successfully
        
        # Step 7: Return dashboard-ready JSON
        dashboard_json = self._build_dashboard_json_from_summary(
            analytics_summary=analytics_summary,
            snapshot_id=snapshot_id
        )
        
        return dashboard_json
    
    def _extract_timeline_version(
        self,
        committed_timeline: CommittedTimeline
    ) -> str:
        """
        Extract timeline version from committed timeline.
        
        Tries to get version from draft_timeline relationship,
        or extracts from notes, or defaults to "1.0".
        
        Args:
            committed_timeline: Committed timeline object
            
        Returns:
            Version string (e.g., "1.0", "2.0")
        """
        # Try to get version from draft_timeline
        if committed_timeline.draft_timeline_id:
            from app.models.draft_timeline import DraftTimeline
            draft = self._tracked_read(
                DraftTimeline,
                DraftTimeline.id == committed_timeline.draft_timeline_id
            ).first()
            if draft and draft.version_number:
                return draft.version_number
        
        # Try to extract from notes (format: "Version X.Y")
        if committed_timeline.notes:
            import re
            match = re.search(r'Version\s+(\d+\.\d+)', committed_timeline.notes)
            if match:
                return match.group(1)
        
        # Default version
        return "1.0"
    
    def _persist_snapshot(
        self,
        user_id: UUID,
        timeline_version: str,
        analytics_summary: AnalyticsSummary
    ) -> UUID:
        """
        Persist analytics snapshot to database.
        
        Stores the AnalyticsSummary output as an immutable snapshot.
        
        Args:
            user_id: User ID
            timeline_version: Timeline version string
            analytics_summary: Analytics summary to persist
            
        Returns:
            UUID of created snapshot
        """
        # Convert AnalyticsSummary to JSON-serializable dict
        summary_json = {
            "timeline_id": str(analytics_summary.timeline_id),
            "user_id": str(analytics_summary.user_id),
            "generated_at": analytics_summary.generated_at.isoformat(),
            "timeline_status": analytics_summary.timeline_status,
            "milestone_completion_percentage": analytics_summary.milestone_completion_percentage,
            "total_milestones": analytics_summary.total_milestones,
            "completed_milestones": analytics_summary.completed_milestones,
            "pending_milestones": analytics_summary.pending_milestones,
            "total_delays": analytics_summary.total_delays,
            "overdue_milestones": analytics_summary.overdue_milestones,
            "overdue_critical_milestones": analytics_summary.overdue_critical_milestones,
            "average_delay_days": analytics_summary.average_delay_days,
            "max_delay_days": analytics_summary.max_delay_days,
            "latest_health_score": analytics_summary.latest_health_score,
            "health_dimensions": analytics_summary.health_dimensions,
            "longitudinal_summary": analytics_summary.longitudinal_summary
        }
        
        # Create snapshot record (immutable) using tracked write
        snapshot = AnalyticsSnapshot(
            user_id=user_id,
            timeline_version=timeline_version,
            summary_json=summary_json
        )
        
        self._tracked_write(snapshot)
        self.db.commit()
        self.db.refresh(snapshot)
        
        return snapshot.id
    
    def _build_dashboard_json_from_summary(
        self,
        analytics_summary: AnalyticsSummary,
        snapshot_id: UUID
    ) -> Dict[str, Any]:
        """
        Build dashboard-ready JSON from analytics summary.
        
        Args:
            analytics_summary: Analytics summary
            snapshot_id: Snapshot ID
            
        Returns:
            Dashboard-ready JSON dictionary
        """
        return {
            "snapshot_id": str(snapshot_id),
            "generated_at": analytics_summary.generated_at.isoformat(),
            "user_id": str(analytics_summary.user_id),
            "timeline_id": str(analytics_summary.timeline_id),
            "timeline_status": analytics_summary.timeline_status,
            "milestones": {
                "completion_percentage": analytics_summary.milestone_completion_percentage,
                "total": analytics_summary.total_milestones,
                "completed": analytics_summary.completed_milestones,
                "pending": analytics_summary.pending_milestones,
            },
            "delays": {
                "total_delays": analytics_summary.total_delays,
                "overdue_milestones": analytics_summary.overdue_milestones,
                "overdue_critical_milestones": analytics_summary.overdue_critical_milestones,
                "average_delay_days": analytics_summary.average_delay_days,
                "max_delay_days": analytics_summary.max_delay_days,
            },
            "journey_health": {
                "latest_score": analytics_summary.latest_health_score,
                "dimensions": analytics_summary.health_dimensions,
            },
            "longitudinal_summary": analytics_summary.longitudinal_summary
        }
    
    def _build_dashboard_json(
        self,
        analytics_report: AnalyticsReport,
        snapshot_id: UUID
    ) -> Dict[str, Any]:
        """
        Build dashboard-ready JSON from analytics report.
        
        Args:
            analytics_report: Analytics report
            snapshot_id: Snapshot ID
            
        Returns:
            Dashboard-ready JSON dictionary
        """
        # Organize time series by category
        timeline_series = [
            ts for ts in analytics_report.time_series
            if ts.metric_name.startswith("timeline_")
        ]
        health_series = [
            ts for ts in analytics_report.time_series
            if ts.metric_name.startswith("journey_health_")
        ]
        
        # Organize status indicators by category
        timeline_indicators = [
            ind for ind in analytics_report.status_indicators
            if ind.name.startswith("timeline_") or ind.name == "average_delay"
        ]
        health_indicators = [
            ind for ind in analytics_report.status_indicators
            if ind.name.startswith("journey_health_")
        ]
        
        # Get critical and concerning indicators
        critical_indicators = [
            ind for ind in analytics_report.status_indicators
            if ind.status == "critical"
        ]
        concerning_indicators = [
            ind for ind in analytics_report.status_indicators
            if ind.status == "concerning"
        ]
        
        return {
            "snapshot_id": str(snapshot_id),
            "generated_at": analytics_report.generated_at.isoformat(),
            "user_id": str(analytics_report.user_id),
            "timeline_id": str(analytics_report.timeline_id) if analytics_report.timeline_id else None,
            "time_series": {
                "timeline": [
                    {
                        "metric": ts.metric_name,
                        "current_value": ts.current_value,
                        "trend": ts.trend,
                        "average": ts.average,
                        "min": ts.min_value,
                        "max": ts.max_value,
                        "points": [
                            {
                                "date": p.date.isoformat(),
                                "value": p.value,
                                "metadata": p.metadata
                            }
                            for p in ts.points
                        ]
                    }
                    for ts in timeline_series
                ],
                "health": [
                    {
                        "metric": ts.metric_name,
                        "current_value": ts.current_value,
                        "trend": ts.trend,
                        "average": ts.average,
                        "min": ts.min_value,
                        "max": ts.max_value,
                        "points": [
                            {
                                "date": p.date.isoformat(),
                                "value": p.value,
                                "metadata": p.metadata
                            }
                            for p in ts.points
                        ]
                    }
                    for ts in health_series
                ]
            },
            "status_indicators": {
                "timeline": [
                    {
                        "name": ind.name,
                        "value": ind.value,
                        "status": ind.status,
                        "message": ind.message
                    }
                    for ind in timeline_indicators
                ],
                "health": [
                    {
                        "name": ind.name,
                        "value": ind.value,
                        "status": ind.status,
                        "message": ind.message
                    }
                    for ind in health_indicators
                ],
                "all": [
                    {
                        "name": ind.name,
                        "value": ind.value,
                        "status": ind.status,
                        "message": ind.message
                    }
                    for ind in analytics_report.status_indicators
                ]
            },
            "alerts": {
                "critical": [
                    {
                        "name": ind.name,
                        "value": ind.value,
                        "status": ind.status,
                        "message": ind.message
                    }
                    for ind in critical_indicators
                ],
                "concerning": [
                    {
                        "name": ind.name,
                        "value": ind.value,
                        "status": ind.status,
                        "message": ind.message
                    }
                    for ind in concerning_indicators
                ]
            },
            "summary": analytics_report.summary
        }
    
    def _tracked_read(self, model, *filters):
        """
        Perform a tracked database read operation.
        
        Logs the model being read from and validates it's an allowed read model.
        
        Args:
            model: SQLAlchemy model class
            *filters: Query filters
            
        Returns:
            SQLAlchemy query object
        """
        model_name = model.__name__
        self._validate_read_operation(model_name)
        self._read_operations.append(model_name)
        return self.db.query(model).filter(*filters)
    
    def _tracked_write(self, instance):
        """
        Perform a tracked database write operation.
        
        Logs the model being written to and validates it's an allowed write model.
        
        Args:
            instance: SQLAlchemy model instance
        """
        model_name = instance.__class__.__name__
        self._validate_write_operation(model_name)
        self._write_operations.append(model_name)
        self.db.add(instance)
    
    def _validate_read_operation(self, model_name: str):
        """
        Validate a read operation is allowed.
        
        Args:
            model_name: Name of the model being read
            
        Raises:
            StateMutationInAnalyticsOrchestratorError: If read from non-allowed model
        """
        if model_name not in self._ALLOWED_READ_MODELS:
            raise StateMutationInAnalyticsOrchestratorError(
                f"AnalyticsOrchestrator attempted to read from non-allowed model: {model_name}. "
                f"Allowed read models: {', '.join(sorted(self._ALLOWED_READ_MODELS))}"
            )
    
    def _validate_write_operation(self, model_name: str):
        """
        Validate a write operation is allowed.
        
        Args:
            model_name: Name of the model being written
            
        Raises:
            StateMutationInAnalyticsOrchestratorError: If write to non-allowed model
        """
        if model_name not in self._ALLOWED_WRITE_MODELS:
            raise StateMutationInAnalyticsOrchestratorError(
                f"AnalyticsOrchestrator attempted to write to non-allowed model: {model_name}. "
                f"Allowed write models: {', '.join(sorted(self._ALLOWED_WRITE_MODELS))}"
            )
    
    def _validate_read_only_contract(self):
        """
        Validate the read-only contract was maintained during execution.
        
        Checks:
        - All reads were from allowed models
        - All writes were to allowed models
        - No upstream state mutation occurred
        
        Raises:
            StateMutationInAnalyticsOrchestratorError: If contract violated
        """
        # Check all read operations
        invalid_reads = [op for op in self._read_operations if op not in self._ALLOWED_READ_MODELS]
        if invalid_reads:
            raise StateMutationInAnalyticsOrchestratorError(
                f"AnalyticsOrchestrator violated read-only contract. "
                f"Invalid read operations: {', '.join(set(invalid_reads))}. "
                f"Allowed read models: {', '.join(sorted(self._ALLOWED_READ_MODELS))}"
            )
        
        # Check all write operations
        invalid_writes = [op for op in self._write_operations if op not in self._ALLOWED_WRITE_MODELS]
        if invalid_writes:
            raise StateMutationInAnalyticsOrchestratorError(
                f"AnalyticsOrchestrator violated read-only contract. "
                f"Invalid write operations: {', '.join(set(invalid_writes))}. "
                f"Allowed write models: {', '.join(sorted(self._ALLOWED_WRITE_MODELS))}"
            )


class StateMutationInAnalyticsOrchestratorError(Exception):
    """
    Exception raised when AnalyticsOrchestrator violates read-only contract.
    
    This indicates the orchestrator attempted to mutate upstream state,
    which violates the analytics-only constraint.
    """
    pass
