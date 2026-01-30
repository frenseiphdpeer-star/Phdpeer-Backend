"""
Services package.

Services contain business logic and data access layer.
They handle CRUD operations and business rules.

Services should:
    - Accept database session as parameter
    - Perform database operations
    - Implement business logic
    - Return data or raise exceptions
"""

from app.services.document_service import (
    DocumentService,
    DocumentServiceError,
    UnsupportedFileTypeError,
)
from app.services.timeline_intelligence_engine import (
    TimelineIntelligenceEngine,
    StageType,
    TextSegment,
    DetectedStage,
    ExtractedMilestone,
    DurationEstimate,
    Dependency,
)
from app.services.progress_service import (
    ProgressService,
    ProgressServiceError,
)
from app.services.journey_health_engine import (
    JourneyHealthEngine,
    QuestionResponse,
    DimensionScore,
    HealthRecommendation,
    JourneyHealthReport,
    HealthStatus,
    HealthDimension,
)
from app.services.analytics_engine import (
    AnalyticsEngine,
    TimeSeriesPoint,
    TimeSeriesSummary,
    StatusIndicator,
    AnalyticsReport,
)
from app.services.sal_engine import (
    SALEngine,
    SALEngineError,
)
from app.services.cpa_engine import (
    CPAEngine,
    CPAEngineError,
)
from app.services.nmx_engine import (
    NMXEngine,
    NMXEngineError,
)

__all__ = [
    "DocumentService",
    "DocumentServiceError",
    "UnsupportedFileTypeError",
    "TimelineIntelligenceEngine",
    "StageType",
    "TextSegment",
    "DetectedStage",
    "ExtractedMilestone",
    "DurationEstimate",
    "Dependency",
    "ProgressService",
    "ProgressServiceError",
    "JourneyHealthEngine",
    "QuestionResponse",
    "DimensionScore",
    "HealthRecommendation",
    "JourneyHealthReport",
    "HealthStatus",
    "HealthDimension",
    "AnalyticsEngine",
    "TimeSeriesPoint",
    "TimeSeriesSummary",
    "StatusIndicator",
    "AnalyticsReport",
    "SALEngine",
    "SALEngineError",
    "CPAEngine",
    "CPAEngineError",
    "NMXEngine",
    "NMXEngineError",
]
