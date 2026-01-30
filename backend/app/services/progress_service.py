"""Progress service for tracking milestone completion and timeline progress."""
from datetime import date, datetime
from typing import Optional, Dict, List
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.timeline_milestone import TimelineMilestone
from app.models.timeline_stage import TimelineStage
from app.models.progress_event import ProgressEvent
from app.models.committed_timeline import CommittedTimeline
from app.models.user import User
from app.utils.invariants import check_progress_event_has_milestone


class ProgressServiceError(Exception):
    """Base exception for progress service errors."""
    pass


class ProgressService:
    """
    Service for tracking and calculating timeline progress.
    
    Capabilities:
    - Mark milestones completed
    - Append ProgressEvent (append-only, immutable)
    - Compute delay flags (planned vs actual)
    
    Rules:
    - No prediction logic
    - No ML algorithms
    - Pure deterministic calculations
    - ProgressEvent is append-only (never updated or deleted)
    """
    
    # Event types
    EVENT_TYPE_MILESTONE_COMPLETED = "milestone_completed"
    EVENT_TYPE_MILESTONE_DELAYED = "milestone_delayed"
    EVENT_TYPE_STAGE_STARTED = "stage_started"
    EVENT_TYPE_STAGE_COMPLETED = "stage_completed"
    EVENT_TYPE_ACHIEVEMENT = "achievement"
    EVENT_TYPE_BLOCKER = "blocker"
    EVENT_TYPE_UPDATE = "update"
    
    # Impact levels
    IMPACT_LOW = "low"
    IMPACT_MEDIUM = "medium"
    IMPACT_HIGH = "high"
    
    def __init__(self, db: Session):
        """
        Initialize progress service.
        
        Args:
            db: Database session
        """
        self.db = db
    
    def mark_milestone_completed(
        self,
        milestone_id: UUID,
        user_id: UUID,
        completion_date: Optional[date] = None,
        notes: Optional[str] = None,
    ) -> UUID:
        """
        Mark a milestone as completed and log a progress event.
        
        Args:
            milestone_id: ID of milestone to complete
            user_id: ID of user completing the milestone
            completion_date: Date of completion (defaults to today)
            notes: Optional completion notes
            
        Returns:
            UUID of created ProgressEvent
            
        Raises:
            ProgressServiceError: If validation fails
        """
        # Verify user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ProgressServiceError(f"User with ID {user_id} not found")
        
        # Invariant check: No progress event without committed milestone
        check_progress_event_has_milestone(
            db=self.db,
            milestone_id=milestone_id,
            user_id=user_id
        )
        
        # Get milestone
        milestone = self.db.query(TimelineMilestone).filter(
            TimelineMilestone.id == milestone_id
        ).first()
        
        if not milestone:
            raise ProgressServiceError(f"Milestone with ID {milestone_id} not found")
        
        # Check if already completed
        if milestone.is_completed:
            raise ProgressServiceError(
                f"Milestone {milestone_id} is already marked as completed"
            )
        
        # Set completion date
        if completion_date is None:
            completion_date = date.today()
        
        # Update milestone
        milestone.is_completed = True
        milestone.actual_completion_date = completion_date
        if notes:
            milestone.notes = f"{milestone.notes or ''}\nCompleted: {notes}".strip()
        
        self.db.add(milestone)
        self.db.flush()
        
        # Compute delay flags (planned vs actual)
        delay_days = self._calculate_delay_days(
            milestone.target_date,
            completion_date
        )
        
        is_delayed = delay_days > 0
        is_on_time = delay_days == 0
        is_early = delay_days < 0
        
        # Determine impact level based on delay flags
        impact_level = self._determine_impact_level(delay_days, milestone.is_critical)
        
        # Build event description with delay information
        event_description = f"Completed milestone: {milestone.title}"
        if is_delayed:
            event_description += f" (delayed by {delay_days} days)"
        elif is_early:
            event_description += f" (completed {abs(delay_days)} days early)"
        elif is_on_time:
            event_description += " (completed on time)"
        
        # Append ProgressEvent (append-only, immutable)
        progress_event_id = self.log_progress_event(
            user_id=user_id,
            milestone_id=milestone_id,
            event_type=self.EVENT_TYPE_MILESTONE_COMPLETED,
            title=f"Milestone Completed: {milestone.title[:50]}",
            description=event_description,
            event_date=completion_date,
            impact_level=impact_level,
            notes=notes,
        )
        
        # Note: log_progress_event already commits, but we ensure milestone update is committed
        self.db.commit()
        
        return progress_event_id
    
    def log_progress_event(
        self,
        user_id: UUID,
        event_type: str,
        title: str,
        description: str,
        event_date: Optional[date] = None,
        milestone_id: Optional[UUID] = None,
        impact_level: Optional[str] = None,
        tags: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> UUID:
        """
        Append a progress event (append-only operation).
        
        ProgressEvent records are immutable once created - they can never be
        updated or deleted. This ensures a complete audit trail.
        
        Args:
            user_id: ID of user logging the event
            event_type: Type of event
            title: Event title
            description: Event description
            event_date: Date of event (defaults to today)
            milestone_id: Optional related milestone
            impact_level: Optional impact level (low, medium, high)
            tags: Optional comma-separated tags
            notes: Optional notes
            
        Returns:
            UUID of created ProgressEvent (immutable, append-only)
            
        Raises:
            ProgressServiceError: If validation fails
        """
        # Verify user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ProgressServiceError(f"User with ID {user_id} not found")
        
        if event_date is None:
            event_date = date.today()
        
        # Create new ProgressEvent (append-only, never updated)
        progress_event = ProgressEvent(
            user_id=user_id,
            milestone_id=milestone_id,
            event_type=event_type,
            title=title,
            description=description,
            event_date=event_date,
            impact_level=impact_level or self.IMPACT_LOW,
            tags=tags,
            notes=notes,
        )
        
        # Append to database (immutable record)
        self.db.add(progress_event)
        self.db.commit()
        self.db.refresh(progress_event)
        
        return progress_event.id
    
    def compute_delay_flags(
        self,
        milestone_id: UUID
    ) -> Optional[Dict]:
        """
        Compute delay flags by comparing planned vs actual dates.
        
        Pure deterministic calculation - no prediction, no ML.
        Compares target_date (planned) with actual_completion_date (actual).
        For incomplete milestones, compares target_date with today.
        
        Args:
            milestone_id: Milestone ID
            
        Returns:
            Dictionary with delay flags and status, or None if milestone not found
            
        Returns structure:
        {
            "milestone_id": UUID,
            "milestone_title": str,
            "is_completed": bool,
            "is_critical": bool,
            "planned_date": date,              # target_date (planned)
            "actual_date": date,               # actual_completion_date or today
            "delay_days": int,                 # Positive=delayed, Negative=early, Zero=on_time
            "is_delayed": bool,                # True if delay_days > 0
            "is_on_time": bool,                # True if delay_days == 0
            "is_early": bool,                  # True if delay_days < 0
            "status": str,                     # overdue, due_today, on_track, completed_on_time, completed_delayed, no_target_date
            "has_target_date": bool
        }
        """
        return self.calculate_milestone_delay(milestone_id)
    
    def calculate_milestone_delay(
        self,
        milestone_id: UUID
    ) -> Optional[Dict]:
        """
        Calculate delay for a milestone (planned vs actual).
        
        Compares target_date (planned) with actual_completion_date (actual).
        For incomplete milestones, compares target_date with today.
        
        Pure deterministic calculation - no prediction, no ML.
        
        Args:
            milestone_id: Milestone ID
            
        Returns:
            Dictionary with delay information or None if milestone not found
        """
        milestone = self.db.query(TimelineMilestone).filter(
            TimelineMilestone.id == milestone_id
        ).first()
        
        if not milestone:
            return None
        
        if not milestone.target_date:
            return {
                "milestone_id": milestone_id,
                "milestone_title": milestone.title,
                "has_target_date": False,
                "delay_days": None,
                "status": "no_target_date",
            }
        
        # Calculate delay
        if milestone.is_completed and milestone.actual_completion_date:
            delay_days = self._calculate_delay_days(
                milestone.target_date,
                milestone.actual_completion_date
            )
            status = "completed_on_time" if delay_days <= 0 else "completed_delayed"
            comparison_date = milestone.actual_completion_date
        else:
            delay_days = self._calculate_delay_days(
                milestone.target_date,
                date.today()
            )
            if delay_days > 0:
                status = "overdue"
            elif delay_days == 0:
                status = "due_today"
            else:
                status = "on_track"
            comparison_date = date.today()
        
        # Compute delay flags
        is_delayed = delay_days > 0
        is_on_time = delay_days == 0
        is_early = delay_days < 0
        
        return {
            "milestone_id": milestone_id,
            "milestone_title": milestone.title,
            "is_completed": milestone.is_completed,
            "is_critical": milestone.is_critical,
            "planned_date": milestone.target_date,  # target_date (planned)
            "actual_date": comparison_date,  # actual_completion_date or today
            "target_date": milestone.target_date,  # Alias for backward compatibility
            "actual_completion_date": milestone.actual_completion_date,
            "comparison_date": comparison_date,  # Alias for backward compatibility
            "delay_days": delay_days,
            "is_delayed": is_delayed,  # Delay flag: True if delayed
            "is_on_time": is_on_time,  # Delay flag: True if on time
            "is_early": is_early,  # Delay flag: True if early
            "status": status,
            "has_target_date": True,
        }
    
    def get_stage_progress(
        self,
        stage_id: UUID
    ) -> Optional[Dict]:
        """
        Calculate progress for a stage.
        
        Args:
            stage_id: Stage ID
            
        Returns:
            Dictionary with stage progress metrics
        """
        stage = self.db.query(TimelineStage).filter(
            TimelineStage.id == stage_id
        ).first()
        
        if not stage:
            return None
        
        # Get all milestones for this stage
        milestones = self.db.query(TimelineMilestone).filter(
            TimelineMilestone.timeline_stage_id == stage_id
        ).all()
        
        if not milestones:
            return {
                "stage_id": stage_id,
                "stage_title": stage.title,
                "total_milestones": 0,
                "completed_milestones": 0,
                "completion_percentage": 0.0,
                "has_milestones": False,
            }
        
        total = len(milestones)
        completed = sum(1 for m in milestones if m.is_completed)
        completion_percentage = (completed / total) * 100 if total > 0 else 0.0
        
        # Calculate average delay for completed milestones
        delays = []
        overdue_count = 0
        
        for milestone in milestones:
            if milestone.target_date:
                if milestone.is_completed and milestone.actual_completion_date:
                    delay = self._calculate_delay_days(
                        milestone.target_date,
                        milestone.actual_completion_date
                    )
                    delays.append(delay)
                elif not milestone.is_completed:
                    delay = self._calculate_delay_days(
                        milestone.target_date,
                        date.today()
                    )
                    if delay > 0:
                        overdue_count += 1
        
        avg_delay = sum(delays) / len(delays) if delays else 0.0
        
        return {
            "stage_id": stage_id,
            "stage_title": stage.title,
            "stage_order": stage.stage_order,
            "total_milestones": total,
            "completed_milestones": completed,
            "pending_milestones": total - completed,
            "completion_percentage": round(completion_percentage, 1),
            "overdue_milestones": overdue_count,
            "average_delay_days": round(avg_delay, 1),
            "has_milestones": True,
        }
    
    def get_timeline_progress(
        self,
        committed_timeline_id: UUID
    ) -> Optional[Dict]:
        """
        Calculate overall progress for a committed timeline.
        
        Args:
            committed_timeline_id: Committed timeline ID
            
        Returns:
            Dictionary with timeline progress metrics
        """
        timeline = self.db.query(CommittedTimeline).filter(
            CommittedTimeline.id == committed_timeline_id
        ).first()
        
        if not timeline:
            return None
        
        # Get all stages
        stages = self.db.query(TimelineStage).filter(
            TimelineStage.committed_timeline_id == committed_timeline_id
        ).all()
        
        if not stages:
            return {
                "timeline_id": committed_timeline_id,
                "timeline_title": timeline.title,
                "total_stages": 0,
                "has_data": False,
            }
        
        # Calculate stage-level metrics
        total_stages = len(stages)
        completed_stages = sum(1 for s in stages if s.status == "completed")
        
        # Get all milestones across all stages
        all_milestones = []
        for stage in stages:
            milestones = self.db.query(TimelineMilestone).filter(
                TimelineMilestone.timeline_stage_id == stage.id
            ).all()
            all_milestones.extend(milestones)
        
        if not all_milestones:
            return {
                "timeline_id": committed_timeline_id,
                "timeline_title": timeline.title,
                "total_stages": total_stages,
                "completed_stages": completed_stages,
                "total_milestones": 0,
                "has_data": False,
            }
        
        # Calculate milestone metrics
        total_milestones = len(all_milestones)
        completed_milestones = sum(1 for m in all_milestones if m.is_completed)
        critical_milestones = sum(1 for m in all_milestones if m.is_critical)
        completed_critical = sum(
            1 for m in all_milestones 
            if m.is_critical and m.is_completed
        )
        
        completion_percentage = (
            (completed_milestones / total_milestones) * 100 
            if total_milestones > 0 else 0.0
        )
        
        # Calculate delays
        delays = []
        overdue_count = 0
        overdue_critical_count = 0
        
        for milestone in all_milestones:
            if milestone.target_date:
                if milestone.is_completed and milestone.actual_completion_date:
                    delay = self._calculate_delay_days(
                        milestone.target_date,
                        milestone.actual_completion_date
                    )
                    delays.append(delay)
                elif not milestone.is_completed:
                    delay = self._calculate_delay_days(
                        milestone.target_date,
                        date.today()
                    )
                    if delay > 0:
                        overdue_count += 1
                        if milestone.is_critical:
                            overdue_critical_count += 1
        
        avg_delay = sum(delays) / len(delays) if delays else 0.0
        max_delay = max(delays) if delays else 0
        
        # Calculate timeline duration progress
        duration_progress = None
        if timeline.committed_date and timeline.target_completion_date:
            total_days = (timeline.target_completion_date - timeline.committed_date).days
            elapsed_days = (date.today() - timeline.committed_date).days
            
            if total_days > 0:
                duration_progress = (elapsed_days / total_days) * 100
        
        return {
            "timeline_id": committed_timeline_id,
            "timeline_title": timeline.title,
            "committed_date": timeline.committed_date,
            "target_completion_date": timeline.target_completion_date,
            "duration_progress_percentage": round(duration_progress, 1) if duration_progress else None,
            "total_stages": total_stages,
            "completed_stages": completed_stages,
            "total_milestones": total_milestones,
            "completed_milestones": completed_milestones,
            "pending_milestones": total_milestones - completed_milestones,
            "completion_percentage": round(completion_percentage, 1),
            "critical_milestones": critical_milestones,
            "completed_critical_milestones": completed_critical,
            "overdue_milestones": overdue_count,
            "overdue_critical_milestones": overdue_critical_count,
            "average_delay_days": round(avg_delay, 1),
            "max_delay_days": max_delay,
            "has_data": True,
        }
    
    def get_user_progress_events(
        self,
        user_id: UUID,
        milestone_id: Optional[UUID] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[ProgressEvent]:
        """
        Get progress events for a user.
        
        Args:
            user_id: User ID
            milestone_id: Optional filter by milestone
            event_type: Optional filter by event type
            limit: Maximum number of events to return
            
        Returns:
            List of ProgressEvent objects
        """
        query = self.db.query(ProgressEvent).filter(
            ProgressEvent.user_id == user_id
        )
        
        if milestone_id:
            query = query.filter(ProgressEvent.milestone_id == milestone_id)
        
        if event_type:
            query = query.filter(ProgressEvent.event_type == event_type)
        
        return query.order_by(
            ProgressEvent.event_date.desc()
        ).limit(limit).all()
    
    def get_all_delayed_milestones(
        self,
        committed_timeline_id: UUID,
        include_completed: bool = False
    ) -> List[Dict]:
        """
        Get all delayed milestones for a timeline using delay flag computation.
        
        Uses compute_delay_flags() to determine which milestones are delayed.
        
        Args:
            committed_timeline_id: Committed timeline ID
            include_completed: Whether to include completed but delayed milestones
            
        Returns:
            List of delayed milestone information dicts with delay flags
        """
        # Get all stages
        stages = self.db.query(TimelineStage).filter(
            TimelineStage.committed_timeline_id == committed_timeline_id
        ).all()
        
        delayed = []
        
        for stage in stages:
            milestones = self.db.query(TimelineMilestone).filter(
                TimelineMilestone.timeline_stage_id == stage.id
            ).all()
            
            for milestone in milestones:
                if not milestone.target_date:
                    continue
                
                # Skip completed milestones unless requested
                if milestone.is_completed and not include_completed:
                    continue
                
                # Compute delay flags (planned vs actual)
                delay_info = self.compute_delay_flags(milestone.id)
                
                # Only include milestones with is_delayed flag = True
                if delay_info and delay_info.get("is_delayed", False):
                    delayed.append({
                        **delay_info,
                        "stage_id": str(stage.id),
                        "stage_title": stage.title,
                        "stage_order": stage.stage_order
                    })
        
        # Sort by delay (most delayed first)
        delayed.sort(key=lambda x: x["delay_days"], reverse=True)
        
        return delayed
    
    def get_progress_summary(
        self,
        user_id: UUID,
        committed_timeline_id: UUID
    ) -> Dict:
        """
        Get comprehensive progress summary for a user's timeline.
        
        Combines timeline progress, delayed milestones, and recent events.
        
        Args:
            user_id: User ID
            committed_timeline_id: Committed timeline ID
            
        Returns:
            Dictionary with comprehensive progress data
        """
        timeline_progress = self.get_timeline_progress(committed_timeline_id)
        
        if not timeline_progress or not timeline_progress.get("has_data"):
            return {
                "has_data": False,
                "message": "No timeline data available"
            }
        
        delayed_milestones = self.get_all_delayed_milestones(
            committed_timeline_id,
            include_completed=False
        )
        
        recent_events = self.get_user_progress_events(
            user_id=user_id,
            limit=10
        )
        
        # Calculate health indicators
        total_milestones = timeline_progress["total_milestones"]
        overdue_count = timeline_progress["overdue_milestones"]
        overdue_critical_count = timeline_progress["overdue_critical_milestones"]
        
        # Determine overall health status
        if overdue_critical_count > 0:
            health_status = "at_risk"
        elif overdue_count > (total_milestones * 0.2):  # More than 20% overdue
            health_status = "needs_attention"
        elif timeline_progress["completion_percentage"] < 10:
            health_status = "early_stage"
        else:
            health_status = "on_track"
        
        return {
            "has_data": True,
            "timeline_progress": timeline_progress,
            "delayed_milestones": delayed_milestones[:5],  # Top 5 most delayed
            "recent_events": [
                {
                    "id": str(e.id),
                    "event_type": e.event_type,
                    "title": e.title,
                    "event_date": e.event_date.isoformat() if e.event_date else None,
                    "impact_level": e.impact_level
                }
                for e in recent_events
            ],
            "health_status": health_status,
            "risk_indicators": {
                "overdue_milestones": overdue_count,
                "overdue_critical": overdue_critical_count,
                "completion_below_expected": (
                    timeline_progress["completion_percentage"] < 
                    (timeline_progress.get("duration_progress_percentage", 0) or 0)
                ),
                "average_delay_positive": timeline_progress["average_delay_days"] > 0
            }
        }
    
    # Private helper methods
    
    def _calculate_delay_days(
        self,
        target_date: Optional[date],
        actual_date: date
    ) -> int:
        """
        Calculate delay in days.
        
        Positive = delayed
        Negative = early
        Zero = on time
        
        Args:
            target_date: Target/expected date
            actual_date: Actual/comparison date
            
        Returns:
            Number of days delayed (positive) or early (negative)
        """
        if target_date is None:
            return 0
        
        delta = actual_date - target_date
        return delta.days
    
    def _determine_impact_level(
        self,
        delay_days: int,
        is_critical: bool
    ) -> str:
        """
        Determine impact level based on delay and criticality.
        
        Args:
            delay_days: Number of days delayed
            is_critical: Whether milestone is critical
            
        Returns:
            Impact level (low, medium, high)
        """
        if is_critical:
            if delay_days > 7:
                return self.IMPACT_HIGH
            elif delay_days > 0:
                return self.IMPACT_MEDIUM
            else:
                return self.IMPACT_LOW
        else:
            if delay_days > 30:
                return self.IMPACT_HIGH
            elif delay_days > 7:
                return self.IMPACT_MEDIUM
            else:
                return self.IMPACT_LOW
