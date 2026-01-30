"""Analytics engine for aggregating timeline progress and journey health data."""
from typing import Dict, List, Optional, Any
from uuid import UUID
from datetime import date, timedelta
from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.models.journey_assessment import JourneyAssessment
from app.models.progress_event import ProgressEvent
from app.models.committed_timeline import CommittedTimeline
from app.models.timeline_stage import TimelineStage
from app.models.timeline_milestone import TimelineMilestone
from app.services.progress_service import ProgressService


@dataclass
class TimeSeriesPoint:
    """A single point in a time series."""
    date: date
    value: float
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class TimeSeriesSummary:
    """Summary of a time series."""
    metric_name: str
    points: List[TimeSeriesPoint]
    current_value: Optional[float]
    trend: Optional[str]  # "increasing", "decreasing", "stable", None
    average: Optional[float]
    min_value: Optional[float]
    max_value: Optional[float]


@dataclass
class StatusIndicator:
    """Status indicator for a metric."""
    name: str
    value: Any
    status: str  # "excellent", "good", "fair", "concerning", "critical", "unknown"
    message: Optional[str] = None


@dataclass
class AnalyticsReport:
    """Complete analytics report."""
    user_id: UUID
    timeline_id: Optional[UUID]
    generated_at: date
    time_series: List[TimeSeriesSummary]
    status_indicators: List[StatusIndicator]
    summary: Dict[str, Any]


class AnalyticsEngine:
    """
    Analytics engine for aggregating timeline progress and journey health.
    
    Rules:
    - No predictions: Only aggregates historical data
    - Time-series summaries: Aggregates data points over time
    - Status indicators: Computes current status from historical data
    - Deterministic: Same inputs produce same outputs
    
    Inputs:
    - Timeline progress (from ProgressService)
    - Journey health (from JourneyAssessment)
    - (Future) Writing intelligence
    
    Outputs:
    - Time-series summaries
    - Status indicators
    """
    
    def __init__(self, db: Session):
        """
        Initialize analytics engine.
        
        Args:
            db: Database session
        """
        self.db = db
        self.progress_service = ProgressService(db)
    
    def aggregate(
        self,
        user_id: UUID,
        timeline_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> AnalyticsReport:
        """
        Aggregate timeline progress and journey health data.
        
        Steps:
        1. Collect timeline progress time-series
        2. Collect journey health time-series
        3. Compute status indicators
        4. Generate summary
        
        Args:
            user_id: User ID
            timeline_id: Optional committed timeline ID
            start_date: Optional start date for aggregation (default: 6 months ago)
            end_date: Optional end date for aggregation (default: today)
            
        Returns:
            AnalyticsReport with time-series summaries and status indicators
        """
        # Set default date range (6 months if not specified)
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=180)  # 6 months
        
        # Step 1: Collect timeline progress time-series
        timeline_series = self._aggregate_timeline_progress(
            user_id=user_id,
            timeline_id=timeline_id,
            start_date=start_date,
            end_date=end_date
        )
        
        # Step 2: Collect journey health time-series
        health_series = self._aggregate_journey_health(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )
        
        # Step 3: Compute status indicators
        status_indicators = self._compute_status_indicators(
            user_id=user_id,
            timeline_id=timeline_id,
            timeline_series=timeline_series,
            health_series=health_series
        )
        
        # Step 4: Generate summary
        summary = self._generate_summary(
            timeline_series=timeline_series,
            health_series=health_series,
            status_indicators=status_indicators
        )
        
        # Combine all time series
        all_series = timeline_series + health_series
        
        return AnalyticsReport(
            user_id=user_id,
            timeline_id=timeline_id,
            generated_at=date.today(),
            time_series=all_series,
            status_indicators=status_indicators,
            summary=summary
        )
    
    def _aggregate_timeline_progress(
        self,
        user_id: UUID,
        timeline_id: Optional[UUID],
        start_date: date,
        end_date: date
    ) -> List[TimeSeriesSummary]:
        """
        Aggregate timeline progress into time-series.
        
        Returns time-series for:
        - Completion percentage over time
        - Milestone completion rate
        - Delay trends
        
        Args:
            user_id: User ID
            timeline_id: Optional timeline ID
            start_date: Start date
            end_date: End date
            
        Returns:
            List of TimeSeriesSummary objects
        """
        series = []
        
        # Get committed timeline
        if timeline_id:
            timeline = self.db.query(CommittedTimeline).filter(
                CommittedTimeline.id == timeline_id,
                CommittedTimeline.user_id == user_id
            ).first()
        else:
            # Get most recent committed timeline
            timeline = self.db.query(CommittedTimeline).filter(
                CommittedTimeline.user_id == user_id
            ).order_by(CommittedTimeline.committed_date.desc()).first()
        
        if not timeline:
            return series
        
        # Get milestones for this timeline via stages
        stages = self.db.query(TimelineStage).filter(
            TimelineStage.committed_timeline_id == timeline.id
        ).all()
        
        milestones = []
        for stage in stages:
            stage_milestones = self.db.query(TimelineMilestone).filter(
                TimelineMilestone.timeline_stage_id == stage.id
            ).all()
            milestones.extend(stage_milestones)
        
        if not milestones:
            return series
        
        # Get progress events
        milestone_ids = [m.id for m in milestones]
        events = self.db.query(ProgressEvent).filter(
            ProgressEvent.user_id == user_id,
            ProgressEvent.milestone_id.in_(milestone_ids),
            ProgressEvent.event_date >= start_date,
            ProgressEvent.event_date <= end_date
        ).order_by(ProgressEvent.event_date.asc()).all()
        
        # Build completion percentage time-series
        completion_points = []
        total_milestones = len(milestones)
        completed_count = 0
        
        # Initialize with start date
        if timeline.committed_date and timeline.committed_date >= start_date:
            completion_points.append(TimeSeriesPoint(
                date=timeline.committed_date,
                value=0.0,
                metadata={"total": total_milestones, "completed": 0}
            ))
        
        # Process events chronologically
        for event in events:
            if event.event_type == "milestone_completed":
                completed_count += 1
                completion_pct = (completed_count / total_milestones) * 100 if total_milestones > 0 else 0.0
                completion_points.append(TimeSeriesPoint(
                    date=event.event_date,
                    value=completion_pct,
                    metadata={
                        "total": total_milestones,
                        "completed": completed_count,
                        "event_id": str(event.id)
                    }
                ))
        
        # Add current state
        current_progress = self.progress_service.get_timeline_progress(timeline.id)
        if current_progress and current_progress.get("has_data"):
            current_completion = current_progress.get("completion_percentage", 0.0)
            if not completion_points or completion_points[-1].date < end_date:
                completion_points.append(TimeSeriesPoint(
                    date=end_date,
                    value=current_completion,
                    metadata={
                        "total": current_progress.get("total_milestones", total_milestones),
                        "completed": current_progress.get("completed_milestones", completed_count)
                    }
                ))
        
        if completion_points:
            series.append(self._create_time_series_summary(
                metric_name="timeline_completion_percentage",
                points=completion_points
            ))
        
        # Build delay trend time-series
        delay_points = []
        for event in events:
            if event.milestone_id:
                milestone = next((m for m in milestones if m.id == event.milestone_id), None)
                if milestone and milestone.target_date:
                    if event.event_type == "milestone_completed" and milestone.actual_completion_date:
                        delay_days = (milestone.actual_completion_date - milestone.target_date).days
                        delay_points.append(TimeSeriesPoint(
                            date=event.event_date,
                            value=float(delay_days),
                            metadata={
                                "milestone_id": str(milestone.id),
                                "milestone_title": milestone.title,
                                "is_critical": milestone.is_critical
                            }
                        ))
        
        if delay_points:
            series.append(self._create_time_series_summary(
                metric_name="milestone_delay_days",
                points=delay_points
            ))
        
        return series
    
    def _aggregate_journey_health(
        self,
        user_id: UUID,
        start_date: date,
        end_date: date
    ) -> List[TimeSeriesSummary]:
        """
        Aggregate journey health assessments into time-series.
        
        Returns time-series for:
        - Overall health score over time
        - Research quality rating over time
        - Timeline adherence rating over time
        
        Args:
            user_id: User ID
            start_date: Start date
            end_date: End date
            
        Returns:
            List of TimeSeriesSummary objects
        """
        series = []
        
        # Get assessments in date range
        assessments = self.db.query(JourneyAssessment).filter(
            JourneyAssessment.user_id == user_id,
            JourneyAssessment.assessment_date >= start_date,
            JourneyAssessment.assessment_date <= end_date
        ).order_by(JourneyAssessment.assessment_date.asc()).all()
        
        if not assessments:
            return series
        
        # Overall progress rating time-series
        overall_points = []
        for assessment in assessments:
            if assessment.overall_progress_rating is not None:
                # Convert 1-10 scale to 0-100 for consistency
                score = (assessment.overall_progress_rating / 10) * 100
                overall_points.append(TimeSeriesPoint(
                    date=assessment.assessment_date,
                    value=float(score),
                    metadata={
                        "assessment_id": str(assessment.id),
                        "assessment_type": assessment.assessment_type,
                        "raw_rating": assessment.overall_progress_rating
                    }
                ))
        
        if overall_points:
            series.append(self._create_time_series_summary(
                metric_name="journey_health_overall_score",
                points=overall_points
            ))
        
        # Research quality rating time-series
        research_points = []
        for assessment in assessments:
            if assessment.research_quality_rating is not None:
                score = (assessment.research_quality_rating / 10) * 100
                research_points.append(TimeSeriesPoint(
                    date=assessment.assessment_date,
                    value=float(score),
                    metadata={
                        "assessment_id": str(assessment.id),
                        "raw_rating": assessment.research_quality_rating
                    }
                ))
        
        if research_points:
            series.append(self._create_time_series_summary(
                metric_name="journey_health_research_quality",
                points=research_points
            ))
        
        # Timeline adherence rating time-series
        adherence_points = []
        for assessment in assessments:
            if assessment.timeline_adherence_rating is not None:
                score = (assessment.timeline_adherence_rating / 10) * 100
                adherence_points.append(TimeSeriesPoint(
                    date=assessment.assessment_date,
                    value=float(score),
                    metadata={
                        "assessment_id": str(assessment.id),
                        "raw_rating": assessment.timeline_adherence_rating
                    }
                ))
        
        if adherence_points:
            series.append(self._create_time_series_summary(
                metric_name="journey_health_timeline_adherence",
                points=adherence_points
            ))
        
        return series
    
    def _compute_status_indicators(
        self,
        user_id: UUID,
        timeline_id: Optional[UUID],
        timeline_series: List[TimeSeriesSummary],
        health_series: List[TimeSeriesSummary]
    ) -> List[StatusIndicator]:
        """
        Compute status indicators from aggregated data.
        
        Args:
            user_id: User ID
            timeline_id: Optional timeline ID
            timeline_series: Timeline progress time-series
            health_series: Journey health time-series
            
        Returns:
            List of StatusIndicator objects
        """
        indicators = []
        
        # Timeline progress indicator
        completion_series = next(
            (s for s in timeline_series if s.metric_name == "timeline_completion_percentage"),
            None
        )
        if completion_series and completion_series.current_value is not None:
            value = completion_series.current_value
            if value >= 80:
                status = "excellent"
                message = "Timeline completion is on track"
            elif value >= 60:
                status = "good"
                message = "Timeline completion is progressing well"
            elif value >= 40:
                status = "fair"
                message = "Timeline completion needs attention"
            elif value >= 20:
                status = "concerning"
                message = "Timeline completion is behind schedule"
            else:
                status = "critical"
                message = "Timeline completion is significantly behind"
            
            indicators.append(StatusIndicator(
                name="timeline_completion",
                value=value,
                status=status,
                message=message
            ))
        
        # Delay indicator
        delay_series = next(
            (s for s in timeline_series if s.metric_name == "milestone_delay_days"),
            None
        )
        if delay_series and delay_series.average is not None:
            avg_delay = delay_series.average
            if avg_delay <= 0:
                status = "excellent"
                message = "No delays on average"
            elif avg_delay <= 7:
                status = "good"
                message = "Minor delays on average"
            elif avg_delay <= 14:
                status = "fair"
                message = "Moderate delays on average"
            elif avg_delay <= 30:
                status = "concerning"
                message = "Significant delays on average"
            else:
                status = "critical"
                message = "Severe delays on average"
            
            indicators.append(StatusIndicator(
                name="average_delay",
                value=avg_delay,
                status=status,
                message=message
            ))
        
        # Overall health indicator
        health_series_overall = next(
            (s for s in health_series if s.metric_name == "journey_health_overall_score"),
            None
        )
        if health_series_overall and health_series_overall.current_value is not None:
            value = health_series_overall.current_value
            if value >= 80:
                status = "excellent"
                message = "Journey health is excellent"
            elif value >= 65:
                status = "good"
                message = "Journey health is good"
            elif value >= 50:
                status = "fair"
                message = "Journey health is fair"
            elif value >= 35:
                status = "concerning"
                message = "Journey health needs attention"
            else:
                status = "critical"
                message = "Journey health requires immediate attention"
            
            indicators.append(StatusIndicator(
                name="journey_health_overall",
                value=value,
                status=status,
                message=message
            ))
        
        # Health trend indicator
        if health_series_overall and len(health_series_overall.points) >= 2:
            trend = health_series_overall.trend
            if trend == "increasing":
                indicators.append(StatusIndicator(
                    name="journey_health_trend",
                    value=trend,
                    status="good",
                    message="Journey health is improving"
                ))
            elif trend == "decreasing":
                indicators.append(StatusIndicator(
                    name="journey_health_trend",
                    value=trend,
                    status="concerning",
                    message="Journey health is declining"
                ))
            else:
                indicators.append(StatusIndicator(
                    name="journey_health_trend",
                    value=trend or "stable",
                    status="fair",
                    message="Journey health is stable"
                ))
        
        return indicators
    
    def _create_time_series_summary(
        self,
        metric_name: str,
        points: List[TimeSeriesPoint]
    ) -> TimeSeriesSummary:
        """
        Create a TimeSeriesSummary from points.
        
        Args:
            metric_name: Name of the metric
            points: List of time series points
            
        Returns:
            TimeSeriesSummary object
        """
        if not points:
            return TimeSeriesSummary(
                metric_name=metric_name,
                points=[],
                current_value=None,
                trend=None,
                average=None,
                min_value=None,
                max_value=None
            )
        
        values = [p.value for p in points]
        current_value = points[-1].value if points else None
        
        # Compute trend (comparing last 3 points if available)
        trend = None
        if len(points) >= 3:
            recent_values = [p.value for p in points[-3:]]
            if recent_values[2] > recent_values[0]:
                trend = "increasing"
            elif recent_values[2] < recent_values[0]:
                trend = "decreasing"
            else:
                trend = "stable"
        elif len(points) == 2:
            if points[1].value > points[0].value:
                trend = "increasing"
            elif points[1].value < points[0].value:
                trend = "decreasing"
            else:
                trend = "stable"
        
        return TimeSeriesSummary(
            metric_name=metric_name,
            points=points,
            current_value=current_value,
            trend=trend,
            average=sum(values) / len(values) if values else None,
            min_value=min(values) if values else None,
            max_value=max(values) if values else None
        )
    
    def _generate_summary(
        self,
        timeline_series: List[TimeSeriesSummary],
        health_series: List[TimeSeriesSummary],
        status_indicators: List[StatusIndicator]
    ) -> Dict[str, Any]:
        """
        Generate overall summary from aggregated data.
        
        Args:
            timeline_series: Timeline progress time-series
            health_series: Journey health time-series
            status_indicators: Status indicators
            
        Returns:
            Summary dictionary
        """
        summary = {
            "has_timeline_data": len(timeline_series) > 0,
            "has_health_data": len(health_series) > 0,
            "total_metrics": len(timeline_series) + len(health_series),
            "total_indicators": len(status_indicators),
            "critical_indicators": [
                ind.name for ind in status_indicators if ind.status == "critical"
            ],
            "concerning_indicators": [
                ind.name for ind in status_indicators if ind.status == "concerning"
            ],
        }
        
        # Add latest values
        if timeline_series:
            completion = next(
                (s for s in timeline_series if s.metric_name == "timeline_completion_percentage"),
                None
            )
            if completion and completion.current_value is not None:
                summary["current_completion_percentage"] = completion.current_value
        
        if health_series:
            health = next(
                (s for s in health_series if s.metric_name == "journey_health_overall_score"),
                None
            )
            if health and health.current_value is not None:
                summary["current_health_score"] = health.current_value
        
        return summary
