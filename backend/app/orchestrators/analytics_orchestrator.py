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
    TimeSeriesSummary,
    StatusIndicator,
)


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
    """
    
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
        1. Load longitudinal data
        2. Call AnalyticsEngine
        3. Persist analytics snapshot
        4. Return dashboard-ready JSON
        
        This is called by BaseOrchestrator.execute() which automatically
        writes DecisionTrace after successful completion.
        
        Args:
            context: Execution context with input data
            
        Returns:
            Dashboard-ready JSON response
        """
        user_id = UUID(context["user_id"])
        timeline_id = UUID(context["timeline_id"]) if context.get("timeline_id") else None
        start_date = date.fromisoformat(context["start_date"]) if context.get("start_date") else None
        end_date = date.fromisoformat(context["end_date"]) if context.get("end_date") else None
        snapshot_type = context.get("snapshot_type", "on_demand")
        
        # Step 1: Load longitudinal data
        with self._trace_step("load_longitudinal_data") as step:
            # Validate user exists
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise AnalyticsOrchestratorError(f"User with ID {user_id} not found")
            
            # Validate timeline if provided
            if timeline_id:
                timeline = self.db.query(CommittedTimeline).filter(
                    CommittedTimeline.id == timeline_id,
                    CommittedTimeline.user_id == user_id
                ).first()
                if not timeline:
                    raise AnalyticsOrchestratorError(
                        f"Timeline {timeline_id} not found or not owned by user {user_id}"
                    )
            
            step.details = {
                "user_id": str(user_id),
                "timeline_id": str(timeline_id) if timeline_id else None,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
            }
            
            self.add_evidence(
                evidence_type="longitudinal_data_loaded",
                data={
                    "user_id": str(user_id),
                    "has_timeline": timeline_id is not None,
                    "date_range": {
                        "start": start_date.isoformat() if start_date else None,
                        "end": end_date.isoformat() if end_date else None,
                    }
                },
                source=f"User:{user_id}",
                confidence=1.0
            )
        
        # Step 2: Call AnalyticsEngine
        with self._trace_step("call_analytics_engine") as step:
            analytics_report = self.analytics_engine.aggregate(
                user_id=user_id,
                timeline_id=timeline_id,
                start_date=start_date,
                end_date=end_date
            )
            
            step.details = {
                "time_series_count": len(analytics_report.time_series),
                "status_indicators_count": len(analytics_report.status_indicators),
                "has_timeline_data": analytics_report.summary.get("has_timeline_data", False),
                "has_health_data": analytics_report.summary.get("has_health_data", False),
            }
            
            self.add_evidence(
                evidence_type="analytics_report_generated",
                data={
                    "time_series_count": len(analytics_report.time_series),
                    "status_indicators_count": len(analytics_report.status_indicators),
                    "generated_at": analytics_report.generated_at.isoformat(),
                },
                source="AnalyticsEngine",
                confidence=1.0
            )
        
        # Step 3: Persist analytics snapshot
        with self._trace_step("persist_analytics_snapshot") as step:
            snapshot_id = self._persist_snapshot(
                user_id=user_id,
                timeline_id=timeline_id,
                analytics_report=analytics_report,
                snapshot_type=snapshot_type
            )
            
            step.details = {
                "snapshot_id": str(snapshot_id),
                "snapshot_type": snapshot_type,
            }
            
            self.add_evidence(
                evidence_type="snapshot_persisted",
                data={
                    "snapshot_id": str(snapshot_id),
                    "snapshot_type": snapshot_type,
                },
                source=f"AnalyticsSnapshot:{snapshot_id}",
                confidence=1.0
            )
        
        # Step 4: Return dashboard-ready JSON
        dashboard_json = self._build_dashboard_json(
            analytics_report=analytics_report,
            snapshot_id=snapshot_id
        )
        
        return dashboard_json
    
    def _persist_snapshot(
        self,
        user_id: UUID,
        timeline_id: Optional[UUID],
        analytics_report: AnalyticsReport,
        snapshot_type: str
    ) -> UUID:
        """
        Persist analytics snapshot to database.
        
        Args:
            user_id: User ID
            timeline_id: Optional timeline ID
            analytics_report: Analytics report to persist
            snapshot_type: Type of snapshot
            
        Returns:
            UUID of created snapshot
        """
        # Convert AnalyticsReport to JSON-serializable dict
        snapshot_data = {
            "user_id": str(analytics_report.user_id),
            "timeline_id": str(analytics_report.timeline_id) if analytics_report.timeline_id else None,
            "generated_at": analytics_report.generated_at.isoformat(),
            "time_series": [
                {
                    "metric_name": ts.metric_name,
                    "current_value": ts.current_value,
                    "trend": ts.trend,
                    "average": ts.average,
                    "min_value": ts.min_value,
                    "max_value": ts.max_value,
                    "points": [
                        {
                            "date": p.date.isoformat(),
                            "value": p.value,
                            "metadata": p.metadata
                        }
                        for p in ts.points
                    ]
                }
                for ts in analytics_report.time_series
            ],
            "status_indicators": [
                {
                    "name": ind.name,
                    "value": ind.value,
                    "status": ind.status,
                    "message": ind.message
                }
                for ind in analytics_report.status_indicators
            ],
            "summary": analytics_report.summary
        }
        
        # Create snapshot record
        snapshot = AnalyticsSnapshot(
            user_id=user_id,
            timeline_id=timeline_id,
            snapshot_date=analytics_report.generated_at,
            analytics_data=snapshot_data,
            snapshot_type=snapshot_type
        )
        
        self.db.add(snapshot)
        self.db.commit()
        self.db.refresh(snapshot)
        
        return snapshot.id
    
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
