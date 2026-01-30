"""Journey Health Engine for assessing PhD journey well-being."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class HealthStatus(str, Enum):
    """Health status levels."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    CONCERNING = "concerning"
    CRITICAL = "critical"


class HealthDimension(str, Enum):
    """PhD journey health dimensions."""
    RESEARCH_PROGRESS = "research_progress"
    WORK_LIFE_BALANCE = "work_life_balance"
    SUPERVISOR_RELATIONSHIP = "supervisor_relationship"
    MENTAL_WELLBEING = "mental_wellbeing"
    ACADEMIC_CONFIDENCE = "academic_confidence"
    TIME_MANAGEMENT = "time_management"
    MOTIVATION = "motivation"
    SUPPORT_NETWORK = "support_network"


@dataclass
class QuestionResponse:
    """Response to a questionnaire question."""
    dimension: HealthDimension
    question_id: str
    response_value: int  # 1-5 scale typically
    question_text: Optional[str] = None


@dataclass
class DimensionScore:
    """Score for a health dimension."""
    dimension: HealthDimension
    score: float  # 0-100
    status: HealthStatus
    response_count: int
    strengths: List[str] = field(default_factory=list)
    concerns: List[str] = field(default_factory=list)
    
    def __str__(self) -> str:
        return f"{self.dimension.value}: {self.score:.1f} ({self.status.value})"


@dataclass
class HealthRecommendation:
    """Recommendation for improving health."""
    dimension: HealthDimension
    priority: str  # high, medium, low
    title: str
    description: str
    action_items: List[str] = field(default_factory=list)
    
    def __str__(self) -> str:
        return f"[{self.priority.upper()}] {self.title}"


@dataclass
class JourneyHealthReport:
    """Complete journey health assessment report."""
    overall_score: float
    overall_status: HealthStatus
    dimension_scores: Dict[HealthDimension, DimensionScore]
    recommendations: List[HealthRecommendation]
    total_responses: int
    assessment_date: str
    
    def get_critical_dimensions(self) -> List[DimensionScore]:
        """Get dimensions with critical or concerning status."""
        return [
            score for score in self.dimension_scores.values()
            if score.status in [HealthStatus.CRITICAL, HealthStatus.CONCERNING]
        ]
    
    def get_healthy_dimensions(self) -> List[DimensionScore]:
        """Get dimensions with good or excellent status."""
        return [
            score for score in self.dimension_scores.values()
            if score.status in [HealthStatus.EXCELLENT, HealthStatus.GOOD]
        ]


class JourneyHealthEngine:
    """
    Rule-based engine for assessing PhD journey health.
    
    Rules:
    - Deterministic scoring: Pure mathematical calculations, no randomness
    - Dimension-wise scores (0-100): Each dimension scored independently
    - Threshold-based classification: Status determined by score thresholds
    - Rule-to-recommendation mapping: Structured templates, no free-text
    - No free-text logic: All outputs use predefined templates
    
    Capabilities:
    - Convert 1-5 scale responses to 0-100 dimension scores
    - Classify dimensions using threshold-based status (excellent to critical)
    - Generate recommendations using rule-based templates
    - Calculate weighted overall score
    
    No document access, no timeline access, no writing evaluation.
    No ML, no free-text generation, no randomness.
    """
    
    # Score thresholds for status determination
    THRESHOLDS = {
        HealthStatus.EXCELLENT: 80,
        HealthStatus.GOOD: 65,
        HealthStatus.FAIR: 50,
        HealthStatus.CONCERNING: 35,
        HealthStatus.CRITICAL: 0,
    }
    
    # Dimension-specific question patterns and scoring rules
    DIMENSION_RULES = {
        HealthDimension.RESEARCH_PROGRESS: {
            "weight": 1.2,  # Higher weight for critical dimensions
            "low_score_threshold": 40,
        },
        HealthDimension.MENTAL_WELLBEING: {
            "weight": 1.3,
            "low_score_threshold": 45,
        },
        HealthDimension.SUPERVISOR_RELATIONSHIP: {
            "weight": 1.1,
            "low_score_threshold": 40,
        },
        HealthDimension.WORK_LIFE_BALANCE: {
            "weight": 1.0,
            "low_score_threshold": 45,
        },
        HealthDimension.ACADEMIC_CONFIDENCE: {
            "weight": 1.0,
            "low_score_threshold": 40,
        },
        HealthDimension.TIME_MANAGEMENT: {
            "weight": 0.9,
            "low_score_threshold": 50,
        },
        HealthDimension.MOTIVATION: {
            "weight": 1.1,
            "low_score_threshold": 40,
        },
        HealthDimension.SUPPORT_NETWORK: {
            "weight": 1.0,
            "low_score_threshold": 45,
        },
    }
    
    def __init__(self):
        """Initialize the journey health engine."""
        pass
    
    def assess_health(
        self,
        responses: List[QuestionResponse],
        assessment_date: Optional[str] = None,
    ) -> JourneyHealthReport:
        """
        Assess journey health from questionnaire responses.
        
        Rules:
        - Deterministic scoring: Pure mathematical calculations
        - Dimension-wise scores (0-100): Each dimension scored independently
        - Threshold-based classification: Status determined by score thresholds
        - Rule-to-recommendation mapping: Structured templates only
        - No free-text logic: All outputs use predefined templates
        
        Process:
        1. Calculate dimension-wise scores (0-100) from responses
        2. Classify each dimension using threshold-based status
        3. Calculate weighted overall score
        4. Generate recommendations using rule-to-recommendation mapping
        
        Args:
            responses: List of questionnaire responses (1-5 scale)
            assessment_date: Optional date string
            
        Returns:
            JourneyHealthReport with:
            - Overall score (0-100) and status
            - Dimension scores (0-100) with status for each
            - Recommendations (from structured templates)
            - Strengths and concerns (rule-based)
        """
        if not responses:
            raise ValueError("No questionnaire responses provided")
        
        # Step 1: Calculate dimension-wise scores (0-100)
        dimension_scores = self._calculate_dimension_scores(responses)
        
        # Step 2: Calculate overall score (deterministic weighted average)
        overall_score = self._calculate_overall_score(dimension_scores)
        
        # Step 3: Threshold-based classification
        overall_status = self._determine_status(overall_score)
        
        # Step 4: Rule-to-recommendation mapping
        recommendations = self._generate_recommendations(dimension_scores)
        
        return JourneyHealthReport(
            overall_score=overall_score,
            overall_status=overall_status,
            dimension_scores=dimension_scores,
            recommendations=recommendations,
            total_responses=len(responses),
            assessment_date=assessment_date or "N/A",
        )
    
    def _calculate_dimension_scores(
        self,
        responses: List[QuestionResponse]
    ) -> Dict[HealthDimension, DimensionScore]:
        """
        Calculate scores for each health dimension.
        
        Args:
            responses: List of question responses
            
        Returns:
            Dictionary mapping dimensions to scores
        """
        # Group responses by dimension
        dimension_responses = {}
        for response in responses:
            if response.dimension not in dimension_responses:
                dimension_responses[response.dimension] = []
            dimension_responses[response.dimension].append(response)
        
        # Calculate score for each dimension
        dimension_scores = {}
        for dimension, dim_responses in dimension_responses.items():
            score = self._score_dimension(dimension, dim_responses)
            dimension_scores[dimension] = score
        
        return dimension_scores
    
    def _score_dimension(
        self,
        dimension: HealthDimension,
        responses: List[QuestionResponse]
    ) -> DimensionScore:
        """
        Score a single dimension from its responses (dimension-wise scoring).
        
        Deterministic scoring: Pure mathematical calculation.
        Dimension-wise scores (0-100): Converts 1-5 scale to 0-100.
        
        Formula:
        - Convert each response: score = ((response_value - 1) / 4) * 100
        - Average all responses for the dimension
        
        Args:
            dimension: Health dimension
            responses: Responses for this dimension
            
        Returns:
            DimensionScore object with score (0-100) and status
        """
        if not responses:
            return DimensionScore(
                dimension=dimension,
                score=0.0,
                status=HealthStatus.CRITICAL,
                response_count=0,
            )
        
        # Deterministic scoring: Convert 1-5 scale to 0-100
        # Formula: score = ((response_value - 1) / 4) * 100
        # 1 -> 0, 2 -> 25, 3 -> 50, 4 -> 75, 5 -> 100
        values = [((r.response_value - 1) / 4) * 100 for r in responses]
        
        # Dimension-wise score: Average of all responses for this dimension
        average_score = sum(values) / len(values)
        
        # Threshold-based classification
        status = self._determine_status(average_score)
        
        # Identify strengths and concerns (using structured rules, no free-text)
        strengths = self._identify_strengths(dimension, responses)
        concerns = self._identify_concerns(dimension, responses)
        
        return DimensionScore(
            dimension=dimension,
            score=round(average_score, 1),  # Dimension-wise score (0-100)
            status=status,  # Threshold-based classification
            response_count=len(responses),
            strengths=strengths,
            concerns=concerns,
        )
    
    def _determine_status(self, score: float) -> HealthStatus:
        """
        Determine health status using threshold-based classification.
        
        Threshold-based classification: Uses fixed score thresholds.
        Deterministic: Same score always produces same status.
        
        Thresholds:
        - Excellent: score >= 80
        - Good: score >= 65
        - Fair: score >= 50
        - Concerning: score >= 35
        - Critical: score < 35
        
        Args:
            score: Score (0-100)
            
        Returns:
            HealthStatus enum value (determined by thresholds)
        """
        # Threshold-based classification (deterministic)
        if score >= self.THRESHOLDS[HealthStatus.EXCELLENT]:
            return HealthStatus.EXCELLENT
        elif score >= self.THRESHOLDS[HealthStatus.GOOD]:
            return HealthStatus.GOOD
        elif score >= self.THRESHOLDS[HealthStatus.FAIR]:
            return HealthStatus.FAIR
        elif score >= self.THRESHOLDS[HealthStatus.CONCERNING]:
            return HealthStatus.CONCERNING
        else:
            return HealthStatus.CRITICAL
    
    def _identify_strengths(
        self,
        dimension: HealthDimension,
        responses: List[QuestionResponse]
    ) -> List[str]:
        """
        Identify strengths using rule-based logic (no free-text).
        
        Rule: If ≥60% of responses are 4 or 5, mark as strength.
        Uses structured template, no free-text generation.
        
        Args:
            dimension: Health dimension
            responses: Responses for this dimension
            
        Returns:
            List of structured strength descriptions
        """
        strengths = []
        high_responses = [r for r in responses if r.response_value >= 4]
        
        # Rule-based: ≥60% high responses = strength
        if len(high_responses) >= len(responses) * 0.6:
            # Structured template (no free-text)
            strengths.append(f"Strong {dimension.value.replace('_', ' ')}")
        
        return strengths
    
    def _identify_concerns(
        self,
        dimension: HealthDimension,
        responses: List[QuestionResponse]
    ) -> List[str]:
        """
        Identify concerns using rule-based logic (no free-text).
        
        Rule: If ≥40% of responses are 1 or 2, mark as concern.
        Uses structured template, no free-text generation.
        
        Args:
            dimension: Health dimension
            responses: Responses for this dimension
            
        Returns:
            List of structured concern descriptions
        """
        concerns = []
        low_responses = [r for r in responses if r.response_value <= 2]
        
        # Rule-based: ≥40% low responses = concern
        if len(low_responses) >= len(responses) * 0.4:
            # Structured template (no free-text)
            concerns.append(f"Low {dimension.value.replace('_', ' ')}")
        
        return concerns
    
    def _calculate_overall_score(
        self,
        dimension_scores: Dict[HealthDimension, DimensionScore]
    ) -> float:
        """
        Calculate overall health score using deterministic weighted average.
        
        Deterministic scoring: Pure mathematical calculation.
        Formula: overall = sum(dimension_score * weight) / sum(weights)
        
        Args:
            dimension_scores: Dictionary of dimension scores (0-100 each)
            
        Returns:
            Overall score (0-100), weighted average of dimension scores
        """
        if not dimension_scores:
            return 0.0
        
        total_weighted_score = 0.0
        total_weight = 0.0
        
        # Deterministic scoring: Weighted average
        for dimension, score in dimension_scores.items():
            weight = self.DIMENSION_RULES.get(dimension, {}).get("weight", 1.0)
            total_weighted_score += score.score * weight
            total_weight += weight
        
        # Deterministic calculation
        overall = total_weighted_score / total_weight if total_weight > 0 else 0.0
        return round(overall, 1)
    
    def _generate_recommendations(
        self,
        dimension_scores: Dict[HealthDimension, DimensionScore]
    ) -> List[HealthRecommendation]:
        """
        Generate recommendations using rule-to-recommendation mapping.
        
        Rule-to-recommendation mapping:
        - Critical status → High priority recommendation
        - Concerning status → Medium priority recommendation
        - Fair status → Low priority recommendation
        - Good/Excellent status → No recommendation
        
        No free-text logic: All recommendations use structured templates.
        Deterministic: Same scores always produce same recommendations.
        
        Args:
            dimension_scores: Dictionary of dimension scores
            
        Returns:
            List of recommendations (sorted by priority)
        """
        recommendations = []
        
        for dimension, score in dimension_scores.items():
            # Rule-to-recommendation mapping: Status → Priority
            if score.status in [HealthStatus.CRITICAL, HealthStatus.CONCERNING]:
                # Threshold-based: Critical/Concerning → High/Medium priority
                priority = "high" if score.status == HealthStatus.CRITICAL else "medium"
                recommendation = self._generate_dimension_recommendation(
                    dimension, score, priority
                )
                recommendations.append(recommendation)
            elif score.status == HealthStatus.FAIR:
                # Threshold-based: Fair → Low priority
                recommendation = self._generate_dimension_recommendation(
                    dimension, score, "low"
                )
                recommendations.append(recommendation)
            # Good/Excellent: No recommendations (rule-based)
        
        # Sort by priority (deterministic ordering)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda r: priority_order[r.priority])
        
        return recommendations
    
    def _generate_dimension_recommendation(
        self,
        dimension: HealthDimension,
        score: DimensionScore,
        priority: str
    ) -> HealthRecommendation:
        """
        Generate recommendation using rule-to-recommendation mapping.
        
        Rule-to-recommendation mapping: Each dimension has predefined templates.
        No free-text logic: All recommendations use structured templates.
        Deterministic: Same dimension + status = same recommendation.
        
        Args:
            dimension: Health dimension
            score: Dimension score (for context)
            priority: Priority level (high, medium, low)
            
        Returns:
            HealthRecommendation object (from structured template)
        """
        # Dimension-specific recommendations
        templates = {
            HealthDimension.RESEARCH_PROGRESS: {
                "title": "Improve Research Progress",
                "description": "Your research progress scores indicate room for improvement.",
                "actions": [
                    "Break down research goals into smaller, achievable tasks",
                    "Schedule regular check-ins with your supervisor",
                    "Review and update your research timeline",
                    "Identify and address any blockers or obstacles",
                ]
            },
            HealthDimension.MENTAL_WELLBEING: {
                "title": "Prioritize Mental Well-being",
                "description": "Your mental well-being needs attention.",
                "actions": [
                    "Consider speaking with a counselor or therapist",
                    "Establish regular self-care routines",
                    "Practice stress management techniques",
                    "Connect with university mental health resources",
                ]
            },
            HealthDimension.SUPERVISOR_RELATIONSHIP: {
                "title": "Strengthen Supervisor Relationship",
                "description": "Improving your supervisor relationship can benefit your journey.",
                "actions": [
                    "Schedule regular one-on-one meetings",
                    "Communicate expectations and concerns clearly",
                    "Seek feedback on your work proactively",
                    "Consider involving a third party if issues persist",
                ]
            },
            HealthDimension.WORK_LIFE_BALANCE: {
                "title": "Improve Work-Life Balance",
                "description": "Your work-life balance could be better managed.",
                "actions": [
                    "Set clear boundaries for work hours",
                    "Schedule regular breaks and time off",
                    "Engage in hobbies and social activities",
                    "Practice saying no to non-essential commitments",
                ]
            },
            HealthDimension.ACADEMIC_CONFIDENCE: {
                "title": "Build Academic Confidence",
                "description": "Working on your academic confidence can enhance your experience.",
                "actions": [
                    "Celebrate small wins and achievements",
                    "Seek peer support and study groups",
                    "Attend workshops on imposter syndrome",
                    "Remember that struggle is part of the learning process",
                ]
            },
            HealthDimension.TIME_MANAGEMENT: {
                "title": "Enhance Time Management",
                "description": "Better time management can reduce stress and improve productivity.",
                "actions": [
                    "Use time-blocking techniques",
                    "Prioritize tasks using frameworks like Eisenhower Matrix",
                    "Minimize distractions during focused work periods",
                    "Review and adjust your schedule weekly",
                ]
            },
            HealthDimension.MOTIVATION: {
                "title": "Boost Motivation Levels",
                "description": "Addressing motivation challenges can reinvigorate your journey.",
                "actions": [
                    "Reconnect with your research passion and purpose",
                    "Set short-term, achievable goals",
                    "Celebrate progress and milestones",
                    "Seek inspiration from peers and mentors",
                ]
            },
            HealthDimension.SUPPORT_NETWORK: {
                "title": "Strengthen Support Network",
                "description": "Building a strong support network is crucial for PhD success.",
                "actions": [
                    "Join PhD student groups and communities",
                    "Attend departmental social events",
                    "Connect with peers in your research area",
                    "Maintain relationships outside academia",
                ]
            },
        }
        
        template = templates.get(dimension, {
            "title": f"Improve {dimension.value.replace('_', ' ').title()}",
            "description": f"Consider focusing on {dimension.value.replace('_', ' ')}.",
            "actions": ["Review this area with your supervisor or mentor"],
        })
        
        return HealthRecommendation(
            dimension=dimension,
            priority=priority,
            title=template["title"],
            description=template["description"],
            action_items=template["actions"],
        )
