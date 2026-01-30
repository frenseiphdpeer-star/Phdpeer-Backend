"""
Orchestrators package.

Orchestrators coordinate multiple services to implement complex workflows.
They handle business processes that span multiple services or domains.

Orchestrators should:
    - Coordinate multiple services
    - Handle complex business workflows
    - Manage transactions across services
    - Implement cross-cutting concerns

Example:
    class UserOnboardingOrchestrator:
        def __init__(self, db: Session):
            self.user_service = UserService(db)
            self.email_service = EmailService()
            self.timeline_service = TimelineService(db)
            
        def onboard_user(self, user_data: dict) -> User:
            # Create user
            user = self.user_service.create(user_data)
            
            # Send welcome email
            self.email_service.send_welcome_email(user.email)
            
            # Create initial timeline
            self.timeline_service.create_default_timeline(user.id)
            
            return user

Difference between Services and Orchestrators:
    - Services: Single-responsibility, focused on one domain/entity
    - Orchestrators: Multi-service coordination, complex workflows
"""

from app.orchestrators.baseline_orchestrator import (
    BaselineOrchestrator,
    BaselineOrchestratorError,
    BaselineAlreadyExistsError,
)
from app.orchestrators.timeline_orchestrator import (
    TimelineOrchestrator,
    TimelineOrchestratorError,
    TimelineAlreadyCommittedError,
    TimelineImmutableError,
)
from app.orchestrators.phd_doctor_orchestrator import (
    PhDDoctorOrchestrator,
    PhDDoctorOrchestratorError,
    IncompleteSubmissionError,
)
from app.orchestrators.analytics_orchestrator import (
    AnalyticsOrchestrator,
    AnalyticsOrchestratorError,
)
from app.orchestrators.writing_baseline_orchestrator import (
    WritingBaselineOrchestrator,
    WritingBaselineOrchestratorError,
)

__all__ = [
    "BaselineOrchestrator",
    "BaselineOrchestratorError",
    "BaselineAlreadyExistsError",
    "TimelineOrchestrator",
    "TimelineOrchestratorError",
    "TimelineAlreadyCommittedError",
    "TimelineImmutableError",
    "PhDDoctorOrchestrator",
    "PhDDoctorOrchestratorError",
    "IncompleteSubmissionError",
    "AnalyticsOrchestrator",
    "AnalyticsOrchestratorError",
    "WritingBaselineOrchestrator",
    "WritingBaselineOrchestratorError",
]
