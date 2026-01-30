"""Timeline Intelligence Engine for extracting timeline information from text."""
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from enum import Enum


class StageType(str, Enum):
    """Enumeration of PhD timeline stages."""
    COURSEWORK = "coursework"
    LITERATURE_REVIEW = "literature_review"
    METHODOLOGY = "methodology"
    DATA_COLLECTION = "data_collection"
    ANALYSIS = "analysis"
    WRITING = "writing"
    SUBMISSION = "submission"
    DEFENSE = "defense"
    PUBLICATION = "publication"
    OTHER = "other"


@dataclass
class TextSegment:
    """Represents a segment of text."""
    content: str
    segment_index: int
    line_numbers: tuple
    segment_type: str = "paragraph"  # paragraph, section, list_item
    
    def __str__(self) -> str:
        return f"Segment {self.segment_index}: {self.content[:50]}..."


@dataclass
class EvidenceSnippet:
    """Represents evidence for a detected stage."""
    text: str
    source: str  # "section_header", "keyword_cluster", "temporal_phrase"
    location: str  # e.g., "Section 2.1", "Line 45-50"
    
    def __str__(self) -> str:
        return f"[{self.source}] {self.text[:50]}..."


@dataclass
class DetectedStage:
    """Represents a detected timeline stage."""
    stage_type: StageType
    title: str
    description: str
    confidence: float  # 0.0 to 1.0
    keywords_matched: List[str] = field(default_factory=list)
    source_segments: List[int] = field(default_factory=list)
    evidence: List[EvidenceSnippet] = field(default_factory=list)
    order_hint: int = 0  # Suggested order in timeline
    
    def __str__(self) -> str:
        return f"{self.stage_type.value}: {self.title} (confidence: {self.confidence:.2f})"


@dataclass
class ExtractedMilestone:
    """Represents an extracted milestone."""
    name: str
    description: str
    stage: str  # Associated stage name
    milestone_type: str  # deliverable, exam, review, publication, etc.
    evidence_snippet: str
    keywords: List[str] = field(default_factory=list)
    source_segment: Optional[int] = None
    is_critical: bool = False
    confidence: float = 0.5
    
    def __str__(self) -> str:
        return f"{'[CRITICAL] ' if self.is_critical else ''}{self.name}"


@dataclass
class DurationEstimate:
    """Represents a duration estimate with range."""
    item_description: str
    item_type: str  # "stage" or "milestone"
    duration_weeks_min: int
    duration_weeks_max: int
    duration_months_min: int
    duration_months_max: int
    confidence: str  # low, medium, high
    basis: str  # explicit, pattern, heuristic, default
    source_text: Optional[str] = None
    
    def __str__(self) -> str:
        return f"{self.item_description}: {self.duration_months_min}-{self.duration_months_max} months ({self.confidence})"


@dataclass
class Dependency:
    """Represents a dependency between stages or milestones."""
    dependent_item: str
    depends_on_item: str
    dependency_type: str  # sequential, prerequisite, parallel, blocks
    confidence: float
    reason: str = ""  # Why this dependency exists
    
    def __str__(self) -> str:
        return f"{self.dependent_item} -> {self.depends_on_item} ({self.dependency_type})"


@dataclass
class StructuredTimeline:
    """Complete structured timeline ready for DraftTimeline creation."""
    title: str
    description: str
    stages: List[DetectedStage]
    milestones: List[ExtractedMilestone]
    durations: List[DurationEstimate]
    dependencies: List[Dependency]
    total_duration_months_min: int
    total_duration_months_max: int
    is_dag_valid: bool
    
    def __str__(self) -> str:
        return f"Timeline: {self.title} ({len(self.stages)} stages, {len(self.milestones)} milestones)"


class TimelineIntelligenceEngine:
    """
    Deterministic rule-based engine for extracting timeline information.
    
    Uses pattern matching, keyword detection, and heuristic rules.
    No ML, no embeddings, no external APIs.
    """
    
    # Enhanced stage detection patterns
    STAGE_PATTERNS = {
        StageType.COURSEWORK: {
            "keywords": [
                r"coursework", r"courses?", r"classes?", r"curriculum",
                r"semester", r"credits?", r"modules?", r"taught\s+(?:courses|modules)"
            ],
            "section_headers": [
                "coursework", "courses", "curriculum", "modules", "taught phase"
            ],
            "temporal_phrases": [
                r"first\s+year", r"year\s+one", r"initial\s+phase",
                r"during\s+courses", r"while\s+taking\s+classes"
            ]
        },
        StageType.LITERATURE_REVIEW: {
            "keywords": [
                r"literature\s+review", r"lit\s+review", r"background\s+research",
                r"survey\s+(?:of\s+)?literature", r"prior\s+work", r"related\s+work",
                r"state\s+of\s+(?:the\s+)?art", r"theoretical\s+framework"
            ],
            "section_headers": [
                "literature review", "lit review", "background", "related work",
                "prior work", "theoretical background", "survey"
            ],
            "temporal_phrases": [
                r"begin\s+(?:by|with)\s+reviewing", r"initially\s+review",
                r"first\s+(?:review|survey)", r"comprehensive\s+review\s+of"
            ]
        },
        StageType.METHODOLOGY: {
            "keywords": [
                r"methodology", r"methods?", r"approach(?:es)?", r"research\s+design",
                r"experimental\s+design", r"study\s+design", r"research\s+(?:strategy|plan)",
                r"technical\s+approach"
            ],
            "section_headers": [
                "methodology", "methods", "approach", "research design",
                "experimental design", "materials and methods", "study design"
            ],
            "temporal_phrases": [
                r"will\s+(?:use|employ|apply)", r"plan\s+to\s+(?:use|employ)",
                r"proposed\s+(?:methodology|approach)", r"methodology\s+will\s+(?:involve|include)"
            ]
        },
        StageType.DATA_COLLECTION: {
            "keywords": [
                r"data\s+collection", r"collect(?:ing)?\s+data", r"gather(?:ing)?\s+data",
                r"experiments?", r"surveys?", r"interviews?", r"observations?",
                r"field\s+work", r"empirical\s+(?:work|study)", r"sampling"
            ],
            "section_headers": [
                "data collection", "experiments", "field work", "empirical work",
                "data gathering", "sampling", "survey"
            ],
            "temporal_phrases": [
                r"will\s+collect", r"plan\s+to\s+gather", r"during\s+(?:the\s+)?data\s+collection",
                r"(?:after|once)\s+collecting", r"before\s+analysis"
            ]
        },
        StageType.ANALYSIS: {
            "keywords": [
                r"analysis", r"data\s+analysis", r"statistical\s+analysis",
                r"evaluation", r"results?", r"findings?", r"interpretation",
                r"processing\s+(?:the\s+)?data", r"analyzing"
            ],
            "section_headers": [
                "analysis", "data analysis", "results", "findings",
                "evaluation", "statistical analysis", "interpretation"
            ],
            "temporal_phrases": [
                r"(?:after|following)\s+(?:data\s+)?collection", r"will\s+(?:analyze|examine)",
                r"during\s+analysis", r"once\s+data\s+(?:is\s+)?collected"
            ]
        },
        StageType.WRITING: {
            "keywords": [
                r"writing", r"dissertation", r"thesis", r"manuscript",
                r"draft(?:ing)?", r"composition", r"documentation",
                r"write\s+up", r"preparing\s+(?:the\s+)?(?:dissertation|thesis)"
            ],
            "section_headers": [
                "writing", "dissertation writing", "thesis writing",
                "documentation", "write-up"
            ],
            "temporal_phrases": [
                r"will\s+write", r"plan\s+to\s+write", r"during\s+writing",
                r"(?:while|when)\s+writing", r"(?:after|following)\s+analysis"
            ]
        },
        StageType.SUBMISSION: {
            "keywords": [
                r"submission", r"submit(?:ting)?", r"final\s+submission",
                r"hand\s+in", r"deliver(?:ing)?", r"turn\s+in",
                r"submit\s+(?:the\s+)?(?:dissertation|thesis)"
            ],
            "section_headers": [
                "submission", "final submission", "completion"
            ],
            "temporal_phrases": [
                r"will\s+submit", r"plan\s+to\s+submit", r"before\s+submission",
                r"(?:after|upon)\s+(?:completing|finishing)", r"final\s+(?:deadline|submission)"
            ]
        },
        StageType.DEFENSE: {
            "keywords": [
                r"defense", r"defence", r"viva", r"oral\s+exam(?:ination)?",
                r"dissertation\s+defense", r"thesis\s+defense",
                r"final\s+presentation", r"defending"
            ],
            "section_headers": [
                "defense", "defence", "viva", "oral examination",
                "final presentation", "dissertation defense"
            ],
            "temporal_phrases": [
                r"will\s+defend", r"plan\s+to\s+defend", r"before\s+(?:the\s+)?defense",
                r"(?:after|following)\s+submission", r"final\s+defense"
            ]
        },
        StageType.PUBLICATION: {
            "keywords": [
                r"publication", r"publish(?:ing)?", r"paper", r"journal\s+(?:article|paper)",
                r"conference\s+paper", r"submit\s+(?:for\s+)?publication",
                r"peer\s+review"
            ],
            "section_headers": [
                "publication", "publications", "dissemination",
                "papers", "conference papers"
            ],
            "temporal_phrases": [
                r"will\s+publish", r"plan\s+to\s+publish", r"during\s+(?:the\s+)?(?:phd|doctorate)",
                r"(?:aim|goal)\s+to\s+publish", r"target\s+(?:journals?|conferences?)"
            ]
        },
    }
    
    # Milestone keywords
    MILESTONE_KEYWORDS = {
        "exam": ["exam", "examination", "qualifying", "comprehensive", "preliminary"],
        "proposal": ["proposal", "prospectus", "research plan"],
        "review": ["review", "committee meeting", "progress review"],
        "publication": ["paper", "publication", "journal", "conference"],
        "deliverable": ["submit", "complete", "finish", "deliver"],
        "defense": ["defense", "defence", "viva", "presentation"],
    }
    
    # Duration patterns (e.g., "6 months", "two years")
    DURATION_PATTERNS = [
        (r"(\d+)\s*(?:months?|mos?\.?)", 1),  # "6 months"
        (r"(\d+)\s*years?", 12),  # "2 years"
        (r"(one|two|three|four|five|six)\s*months?", {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}),
        (r"(one|two|three|four|five)\s*years?", {"one": 12, "two": 24, "three": 36, "four": 48, "five": 60}),
    ]
    
    # Dependency signal words
    DEPENDENCY_SIGNALS = {
        "after": "sequential",
        "following": "sequential",
        "then": "sequential",
        "before": "prerequisite",
        "prior to": "prerequisite",
        "requires": "prerequisite",
        "depends on": "prerequisite",
        "simultaneously": "parallel",
        "concurrently": "parallel",
        "in parallel": "parallel",
    }
    
    def __init__(self):
        """Initialize the timeline intelligence engine."""
        pass
    
    def segment_text(self, text: str) -> List[TextSegment]:
        """
        Segment text into logical units.
        
        Uses deterministic rules:
        - Split by double newlines (paragraphs)
        - Detect numbered/bulleted lists
        - Identify section headers
        
        Args:
            text: Plain text input
            
        Returns:
            List of TextSegment objects
        """
        if not text or not text.strip():
            return []
        
        segments = []
        lines = text.split('\n')
        current_segment = []
        current_start_line = 0
        segment_index = 0
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            if not line:
                # Empty line - end current segment
                if current_segment:
                    content = ' '.join(current_segment)
                    segments.append(TextSegment(
                        content=content,
                        segment_index=segment_index,
                        line_numbers=(current_start_line, i),
                        segment_type=self._detect_segment_type(content)
                    ))
                    segment_index += 1
                    current_segment = []
                    current_start_line = i + 1
            else:
                current_segment.append(line)
        
        # Add final segment
        if current_segment:
            content = ' '.join(current_segment)
            segments.append(TextSegment(
                content=content,
                segment_index=segment_index,
                line_numbers=(current_start_line, len(lines)),
                segment_type=self._detect_segment_type(content)
            ))
        
        return segments
    
    def detect_stages(
        self, 
        text: str, 
        section_map: Optional[Dict] = None
    ) -> List[DetectedStage]:
        """
        Detect timeline stages using multiple detection methods.
        
        Detects stages like:
        - Literature Review
        - Methodology
        - Data Collection
        - Analysis
        - Writing
        - Submission
        
        Detection methods:
        1. Section headers - Matches section titles against known stage names
        2. Keyword clusters - Groups related keywords in text segments
        3. Temporal phrases - Identifies time-based indicators (e.g., "after collecting", "will analyze")
        
        Rules:
        - No dates: Does not extract or parse dates
        - No dependencies: Does not map dependencies between stages
        - Returns ordered stages with confidence scores and evidence snippets
        
        Args:
            text: Plain text input
            section_map: Optional section map from TextProcessor (JSONB from document)
            
        Returns:
            Ordered list of DetectedStage objects with:
            - stage_type: StageType enum
            - title: Human-readable title
            - description: Extracted description
            - confidence: Confidence score (0.0 to 1.0)
            - evidence: List of EvidenceSnippet objects with source and location
            - order_hint: Suggested chronological order
        """
        segments = self.segment_text(text)
        detected_stages = []
        
        for stage_type, detection_config in self.STAGE_PATTERNS.items():
            keywords = detection_config["keywords"]
            section_headers = detection_config["section_headers"]
            temporal_phrases = detection_config["temporal_phrases"]
            
            matched_keywords = []
            matching_segments = []
            evidence_snippets = []
            
            # Method 1: Check section headers
            if section_map and "sections" in section_map:
                for section in section_map["sections"]:
                    section_title = section["title"].lower()
                    
                    for header_pattern in section_headers:
                        if header_pattern.lower() in section_title:
                            evidence_snippets.append(EvidenceSnippet(
                                text=section["title"],
                                source="section_header",
                                location=f"Section (Line {section.get('start_line', '?')})"
                            ))
                            matched_keywords.append(f"header:{header_pattern}")
                            break
            
            # Method 2: Check keyword clusters in segments
            for segment in segments:
                content_lower = segment.content.lower()
                segment_keyword_matches = []
                
                for pattern in keywords:
                    matches = list(re.finditer(pattern, content_lower))
                    if matches:
                        segment_keyword_matches.append(pattern)
                        
                        # Extract evidence snippet
                        for match in matches[:1]:  # Take first match
                            snippet_start = max(0, match.start() - 30)
                            snippet_end = min(len(segment.content), match.end() + 30)
                            snippet = segment.content[snippet_start:snippet_end].strip()
                            
                            evidence_snippets.append(EvidenceSnippet(
                                text=snippet,
                                source="keyword_cluster",
                                location=f"Lines {segment.line_numbers[0]}-{segment.line_numbers[1]}"
                            ))
                
                if segment_keyword_matches:
                    matched_keywords.extend(segment_keyword_matches)
                    matching_segments.append(segment.segment_index)
            
            # Method 3: Check temporal phrases
            for segment in segments:
                content_lower = segment.content.lower()
                
                for temporal_pattern in temporal_phrases:
                    matches = list(re.finditer(temporal_pattern, content_lower))
                    if matches:
                        matched_keywords.append(f"temporal:{temporal_pattern}")
                        
                        # Extract evidence snippet
                        for match in matches[:1]:  # Take first match
                            snippet_start = max(0, match.start() - 20)
                            snippet_end = min(len(segment.content), match.end() + 40)
                            snippet = segment.content[snippet_start:snippet_end].strip()
                            
                            evidence_snippets.append(EvidenceSnippet(
                                text=snippet,
                                source="temporal_phrase",
                                location=f"Lines {segment.line_numbers[0]}-{segment.line_numbers[1]}"
                            ))
            
            # If we found matches, create a detected stage
            if matched_keywords:
                # Calculate confidence based on:
                # - Number of different detection methods used (max 3)
                # - Number of matches overall
                detection_methods_used = len(set(
                    e.source for e in evidence_snippets
                ))
                
                # Base confidence from detection methods (0.3, 0.6, or 0.9)
                base_confidence = detection_methods_used * 0.3
                
                # Bonus from number of matches (up to 0.1)
                match_bonus = min(len(matched_keywords) * 0.02, 0.1)
                
                confidence = min(base_confidence + match_bonus, 1.0)
                
                # Generate title and description
                title = self._generate_stage_title(stage_type)
                description = self._extract_stage_description(
                    segments, matching_segments
                )
                
                # Assign order hint based on typical PhD stage sequence
                order_hint = self._get_stage_order_hint(stage_type)
                
                detected_stages.append(DetectedStage(
                    stage_type=stage_type,
                    title=title,
                    description=description,
                    confidence=confidence,
                    keywords_matched=list(set(matched_keywords))[:10],  # Limit to 10
                    source_segments=matching_segments[:5],  # Limit to 5
                    evidence=evidence_snippets[:5],  # Limit to 5 strongest
                    order_hint=order_hint
                ))
        
        # Sort by order_hint (chronological), then by confidence
        detected_stages.sort(key=lambda x: (x.order_hint, -x.confidence))
        
        return detected_stages
    
    def extract_milestones(
        self, 
        text: str,
        section_map: Optional[Dict] = None
    ) -> List[ExtractedMilestone]:
        """
        Extract milestones for each detected stage.
        
        For each detected stage:
        - Generate 2-5 milestone candidates
        - Each milestone includes name, description, evidence_snippet
        - Milestones are generic and editable (no commitments)
        
        Rules:
        - No dates: Does not extract or parse dates
        - No dependencies: Does not map dependencies between milestones
        - Generic templates: All milestones are suggestions, not commitments
        
        Args:
            text: Plain text input
            section_map: Optional section map from document
            
        Returns:
            List of ExtractedMilestone objects (2-5 per stage) with:
            - name: Milestone name
            - description: Milestone description
            - evidence_snippet: Evidence text from document or generic template
            - stage: Associated stage title
            - milestone_type: Type (deliverable, exam, review, publication, etc.)
            - confidence: Confidence score (0.0 to 1.0)
        """
        # First detect stages
        stages = self.detect_stages(text, section_map)
        
        if not stages:
            return []
        
        segments = self.segment_text(text)
        all_milestones = []
        
        # Extract milestones for each detected stage
        for stage in stages:
            stage_milestones = []
            
            # Method 1: Look for explicit milestone mentions in relevant segments
            for segment_idx in stage.source_segments[:3]:  # Check first 3 segments
                if segment_idx >= len(segments):
                    continue
                    
                segment = segments[segment_idx]
                content_lower = segment.content.lower()
                
                # Check for milestone keywords
                for milestone_type, keywords in self.MILESTONE_KEYWORDS.items():
                    for keyword in keywords:
                        if keyword in content_lower:
                            # Extract milestone details
                            name = self._extract_milestone_name(
                                segment.content, keyword
                            )
                            description = self._extract_milestone_description(
                                segment.content, keyword
                            )
                            evidence = self._extract_milestone_evidence(
                                segment.content, keyword
                            )
                            
                            # Determine if critical
                            is_critical = self._is_critical_milestone(
                                content_lower, milestone_type
                            )
                            
                            stage_milestones.append(ExtractedMilestone(
                                name=name,
                                description=description,
                                stage=stage.title,
                                milestone_type=milestone_type,
                                evidence_snippet=evidence,
                                keywords=[keyword],
                                source_segment=segment_idx,
                                is_critical=is_critical,
                                confidence=0.7  # Higher confidence for explicit mentions
                            ))
            
            # Method 2: Generate generic milestones to ensure 2-5 per stage
            # Target: 2-5 milestones per stage (minimum 2, maximum 5)
            target_min = 2
            target_max = 5
            current_count = len(stage_milestones)
            
            # Calculate how many generic milestones we need
            if current_count < target_min:
                # Need at least 2 milestones - generate enough to reach 2
                needed = target_min - current_count
            elif current_count < target_max:
                # Have 2-4 milestones - add 1-2 more to reach closer to 5
                needed = min(target_max - current_count, 2)
            else:
                # Already have 5 or more - no need to add
                needed = 0
            
            if needed > 0:
                generic_milestones = self._generate_generic_milestones(
                    stage, current_count, needed, text
                )
                stage_milestones.extend(generic_milestones)
            
            # Final check: ensure we have at least 2 milestones
            if len(stage_milestones) < target_min:
                # Fallback: generate minimum 2 generic milestones
                fallback_needed = target_min - len(stage_milestones)
                fallback_milestones = self._generate_generic_milestones(
                    stage, len(stage_milestones), fallback_needed, text
                )
                stage_milestones.extend(fallback_milestones)
            
            # Limit to 5 milestones per stage
            stage_milestones = stage_milestones[:target_max]
            
            # Deduplicate within stage
            stage_milestones = self._deduplicate_milestones(stage_milestones)
            
            # Ensure all milestones have evidence_snippet
            for milestone in stage_milestones:
                if not milestone.evidence_snippet or milestone.evidence_snippet.strip() == "":
                    # Use stage description or generic evidence
                    milestone.evidence_snippet = (
                        stage.description[:150] if stage.description 
                        else f"Milestone for {stage.title} stage"
                    )
            
            all_milestones.extend(stage_milestones)
        
        return all_milestones
    
    def estimate_durations(
        self,
        text: str,
        stages: Optional[List[DetectedStage]] = None,
        milestones: Optional[List[ExtractedMilestone]] = None,
        section_map: Optional[Dict] = None,
        discipline: Optional[str] = None
    ) -> List[DurationEstimate]:
        """
        Estimate duration ranges for stages and milestones.
        
        Uses discipline-aware heuristics to provide accurate duration estimates.
        Returns duration ranges (min_weeks, max_weeks) - no absolute dates.
        
        Methods:
        1. Explicit mentions in text (e.g., "6 months", "2 years")
        2. Discipline-aware heuristics (adjusts based on field of study)
        3. Stage/milestone type defaults with ranges
        
        Rules:
        - Discipline-aware: Different disciplines have different typical durations
        - Returns ranges: (min_weeks, max_weeks) for flexibility
        - No absolute dates: Only relative durations
        - Pure deterministic: No ML, no randomness
        
        Args:
            text: Plain text input
            stages: Pre-detected stages (optional, will detect if not provided)
            milestones: Pre-extracted milestones (optional)
            section_map: Optional section map from document
            discipline: Optional discipline/field of study (e.g., "Computer Science", "Biology")
            
        Returns:
            List of DurationEstimate objects with ranges in weeks and months
        """
        segments = self.segment_text(text)
        estimates = []
        
        # Detect stages if not provided
        if stages is None:
            stages = self.detect_stages(text, section_map)
        
        # Extract milestones if not provided
        if milestones is None:
            milestones = self.extract_milestones(text, section_map)
        
        # Method 1: Look for explicit duration mentions
        explicit_durations = {}  # Map context to duration
        
        for segment in segments:
            content_lower = segment.content.lower()
            
            for pattern, multiplier in self.DURATION_PATTERNS:
                matches = re.finditer(pattern, content_lower, re.IGNORECASE)
                
                for match in matches:
                    value = match.group(1)
                    
                    # Calculate months
                    if isinstance(multiplier, dict):
                        months = multiplier.get(value.lower(), 0)
                    else:
                        try:
                            months = int(value) * multiplier
                        except ValueError:
                            continue
                    
                    # Extract context
                    context = self._extract_duration_context(
                        segment.content, match.start(), match.end()
                    )
                    
                    explicit_durations[context.lower()] = {
                        "months": months,
                        "source": match.group(0)
                    }
        
        # Method 2: Estimate stage durations
        for stage in stages:
            # Check if explicitly mentioned
            explicit_match = None
            for context, duration_info in explicit_durations.items():
                if any(keyword in context for keyword in [
                    stage.title.lower(),
                    stage.stage_type.value
                ]):
                    explicit_match = duration_info
                    break
            
            if explicit_match:
                months = explicit_match["months"]
                estimates.append(DurationEstimate(
                    item_description=stage.title,
                    item_type="stage",
                    duration_weeks_min=months * 4,
                    duration_weeks_max=months * 4,
                    duration_months_min=months,
                    duration_months_max=months,
                    confidence="high",
                    basis="explicit",
                    source_text=explicit_match["source"]
                ))
            else:
                # Use discipline-aware heuristics with ranges
                min_months, max_months = self._get_discipline_aware_duration_range(
                    stage.stage_type, discipline
                )
                estimates.append(DurationEstimate(
                    item_description=stage.title,
                    item_type="stage",
                    duration_weeks_min=min_months * 4,
                    duration_weeks_max=max_months * 4,
                    duration_months_min=min_months,
                    duration_months_max=max_months,
                    confidence="medium",
                    basis="heuristic" if not discipline else "discipline_heuristic"
                ))
        
        # Method 3: Estimate milestone durations
        milestone_estimates = self._estimate_milestone_durations(
            milestones, explicit_durations, discipline
        )
        estimates.extend(milestone_estimates)
        
        return estimates
    
    def map_dependencies(
        self,
        text: str,
        stages: Optional[List[DetectedStage]] = None,
        milestones: Optional[List[ExtractedMilestone]] = None,
        section_map: Optional[Dict] = None
    ) -> List[Dependency]:
        """
        Map dependencies between stages and milestones.
        
        Builds a Directed Acyclic Graph (DAG) with:
        - Logical ordering between stages enforced
        - Cycle detection and removal
        - Explicit validation of DAG property
        
        Methods:
        1. Explicit dependency signals in text ("after", "before", "requires")
        2. Implicit sequential ordering of stages (enforced)
        3. Stage-milestone parent relationships
        4. Critical blocking dependencies
        
        Rules:
        - Build DAG: Directed Acyclic Graph structure
        - Enforce logical ordering: Stages follow natural PhD progression
        - Validate no cycles: All cycles are detected and removed
        - Return dependency edges: List of Dependency objects
        
        Args:
            text: Plain text input
            stages: Pre-detected stages (optional, will detect if not provided)
            milestones: Pre-extracted milestones (optional)
            section_map: Optional section map from document
            
        Returns:
            List of Dependency objects (guaranteed to be DAG, validated)
            
        Raises:
            ValueError: If DAG validation fails after cycle removal
        """
        segments = self.segment_text(text)
        
        # Detect stages and milestones if not provided
        if stages is None:
            stages = self.detect_stages(text, section_map)
        if milestones is None:
            milestones = self.extract_milestones(text, section_map)
        
        # Sort stages by logical order to enforce ordering
        stages = self._enforce_stage_ordering(stages)
        
        dependencies = []
        
        # Method 1: Explicit dependency signals in text
        explicit_deps = self._extract_explicit_dependencies(
            segments, stages, milestones
        )
        dependencies.extend(explicit_deps)
        
        # Method 2: Implicit sequential dependencies for stages (enforced)
        stage_deps = self._create_stage_dependencies(stages)
        dependencies.extend(stage_deps)
        
        # Method 3: Milestone dependencies within stages
        milestone_deps = self._create_milestone_dependencies(milestones, stages)
        dependencies.extend(milestone_deps)
        
        # Method 4: Critical blocking dependencies
        blocking_deps = self._create_blocking_dependencies(stages, milestones)
        dependencies.extend(blocking_deps)
        
        # Remove duplicate dependencies (same dependent -> depends_on)
        dependencies = self._deduplicate_dependencies(dependencies)
        
        # Build DAG: Remove cycles and ensure acyclic structure
        dependencies = self._ensure_dag(dependencies, stages, milestones)
        
        # Validate DAG: Explicit check that no cycles exist
        if not self._validate_dag(dependencies, stages, milestones):
            raise ValueError(
                "Failed to create valid DAG: cycles detected after removal attempt. "
                "This should not happen - please report this error."
            )
        
        return dependencies
    
    # Helper methods
    
    def _detect_segment_type(self, content: str) -> str:
        """Detect the type of segment."""
        content_stripped = content.strip()
        
        if re.match(r'^\d+[\.\)]\s', content_stripped):
            return "numbered_list"
        elif re.match(r'^[-•*]\s', content_stripped):
            return "bullet_list"
        elif content_stripped.isupper() or re.match(r'^#{1,3}\s', content_stripped):
            return "header"
        else:
            return "paragraph"
    
    def _generate_stage_title(self, stage_type: StageType) -> str:
        """Generate a readable title for a stage."""
        titles = {
            StageType.COURSEWORK: "Coursework Phase",
            StageType.LITERATURE_REVIEW: "Literature Review",
            StageType.METHODOLOGY: "Methodology Development",
            StageType.DATA_COLLECTION: "Data Collection",
            StageType.ANALYSIS: "Data Analysis",
            StageType.WRITING: "Writing Phase",
            StageType.SUBMISSION: "Submission",
            StageType.DEFENSE: "Defense Preparation",
            StageType.PUBLICATION: "Publication Phase",
            StageType.OTHER: "Other Activities"
        }
        return titles.get(stage_type, stage_type.value.replace('_', ' ').title())
    
    def _get_stage_order_hint(self, stage_type: StageType) -> int:
        """Get typical order of stage in PhD timeline."""
        order = {
            StageType.COURSEWORK: 1,
            StageType.LITERATURE_REVIEW: 2,
            StageType.METHODOLOGY: 3,
            StageType.DATA_COLLECTION: 4,
            StageType.ANALYSIS: 5,
            StageType.WRITING: 6,
            StageType.SUBMISSION: 7,
            StageType.DEFENSE: 8,
            StageType.PUBLICATION: 9,
            StageType.OTHER: 10
        }
        return order.get(stage_type, 99)
    
    def _enforce_stage_ordering(self, stages: List[DetectedStage]) -> List[DetectedStage]:
        """
        Enforce logical ordering between stages.
        
        Sorts stages by their natural PhD progression order.
        This ensures dependencies follow logical sequence.
        
        Args:
            stages: List of detected stages
            
        Returns:
            Sorted list of stages in logical order
        """
        # Sort by order hint (natural PhD progression)
        sorted_stages = sorted(
            stages,
            key=lambda s: self._get_stage_order_hint(s.stage_type)
        )
        return sorted_stages
    
    def _deduplicate_dependencies(self, dependencies: List[Dependency]) -> List[Dependency]:
        """
        Remove duplicate dependencies.
        
        Keeps the dependency with highest confidence if duplicates exist.
        
        Args:
            dependencies: List of dependencies
            
        Returns:
            Deduplicated list of dependencies
        """
        seen = {}  # (dependent_item, depends_on_item) -> Dependency
        
        for dep in dependencies:
            key = (dep.dependent_item, dep.depends_on_item)
            
            # Skip self-dependencies (would create cycles)
            if dep.dependent_item == dep.depends_on_item:
                continue
            
            if key not in seen:
                seen[key] = dep
            else:
                # Keep the one with higher confidence
                if dep.confidence > seen[key].confidence:
                    seen[key] = dep
        
        return list(seen.values())
    
    def _extract_stage_description(
        self,
        segments: List[TextSegment],
        matching_indices: List[int]
    ) -> str:
        """Extract description from matching segments."""
        if not matching_indices:
            return ""
        
        # Get first matching segment
        first_match = next(
            (s for s in segments if s.segment_index == matching_indices[0]),
            None
        )
        
        if first_match:
            return first_match.content[:200]
        return ""
    
    def _extract_milestone_name(self, content: str, keyword: str) -> str:
        """Extract a concise milestone name from content."""
        # Try to find sentence containing the keyword
        sentences = re.split(r'[.!?]+', content)
        
        for sentence in sentences:
            if keyword.lower() in sentence.lower():
                # Extract a concise name (noun phrase if possible)
                sentence = sentence.strip()
                
                # Try to extract noun phrase around keyword
                words = sentence.split()
                keyword_words = keyword.split()
                
                # Find keyword position
                for i in range(len(words) - len(keyword_words) + 1):
                    if ' '.join(words[i:i+len(keyword_words)]).lower() == keyword.lower():
                        # Take surrounding context (2 words before, 3 words after)
                        start = max(0, i - 2)
                        end = min(len(words), i + len(keyword_words) + 3)
                        name = ' '.join(words[start:end])
                        
                        # Capitalize first letter
                        name = name[0].upper() + name[1:] if name else name
                        
                        # Limit length
                        if len(name) > 60:
                            name = name[:57] + "..."
                        
                        return name
                
                # Fallback: use cleaned sentence
                title = sentence.strip()
                if len(title) > 60:
                    title = title[:57] + "..."
                return title
        
        # Final fallback: capitalize keyword
        return keyword.title()
    
    def _extract_milestone_description(self, content: str, keyword: str) -> str:
        """Extract a milestone description from content."""
        # Find sentence containing the keyword
        sentences = re.split(r'[.!?]+', content)
        
        for sentence in sentences:
            if keyword.lower() in sentence.lower():
                description = sentence.strip()
                # Limit to 200 characters
                if len(description) > 200:
                    description = description[:197] + "..."
                return description
        
        # Fallback: use first 200 chars
        return content[:200].strip()
    
    def _extract_milestone_evidence(self, content: str, keyword: str) -> str:
        """Extract evidence snippet for milestone."""
        # Find sentence containing the keyword
        sentences = re.split(r'[.!?]+', content)
        
        for sentence in sentences:
            if keyword.lower() in sentence.lower():
                evidence = sentence.strip()
                # Limit to 150 characters
                if len(evidence) > 150:
                    # Try to find keyword position and extract around it
                    keyword_pos = evidence.lower().find(keyword.lower())
                    if keyword_pos != -1:
                        start = max(0, keyword_pos - 50)
                        end = min(len(evidence), keyword_pos + len(keyword) + 50)
                        evidence = evidence[start:end].strip()
                        if start > 0:
                            evidence = "..." + evidence
                        if end < len(evidence):
                            evidence = evidence + "..."
                    else:
                        evidence = evidence[:147] + "..."
                return evidence
        
        # Fallback: use first 150 chars
        snippet = content[:150].strip()
        if len(content) > 150:
            snippet += "..."
        return snippet
    
    def _generate_generic_milestones(
        self, 
        stage: DetectedStage, 
        existing_count: int,
        needed: int = None,
        text: str = ""
    ) -> List[ExtractedMilestone]:
        """
        Generate generic milestones for a stage.
        
        These are editable templates that users can customize.
        No commitments - all milestones are suggestions.
        
        Args:
            stage: The detected stage
            existing_count: Number of explicit milestones already found
            needed: Number of milestones to generate (default: 2 - existing_count)
            text: Optional text to extract evidence snippets from
            
        Returns:
            List of generic milestone templates (2-5 per stage)
        """
        # Generic milestone templates by stage type
        templates = {
            StageType.COURSEWORK: [
                {
                    "name": "Complete Required Courses",
                    "description": "Finish all mandatory coursework modules and assessments",
                    "type": "deliverable",
                    "critical": True
                },
                {
                    "name": "Pass Comprehensive Exams",
                    "description": "Successfully complete comprehensive or qualifying examinations",
                    "type": "exam",
                    "critical": True
                },
                {
                    "name": "Achieve Minimum Credit Requirements",
                    "description": "Accumulate required credit hours for PhD program",
                    "type": "deliverable",
                    "critical": True
                }
            ],
            StageType.LITERATURE_REVIEW: [
                {
                    "name": "Complete Literature Survey",
                    "description": "Review and synthesize existing research in the field",
                    "type": "deliverable",
                    "critical": False
                },
                {
                    "name": "Identify Research Gaps",
                    "description": "Analyze literature to identify knowledge gaps and opportunities",
                    "type": "deliverable",
                    "critical": False
                },
                {
                    "name": "Compile Bibliography",
                    "description": "Create comprehensive reference list of relevant sources",
                    "type": "deliverable",
                    "critical": False
                },
                {
                    "name": "Draft Literature Review Chapter",
                    "description": "Write initial draft of literature review section",
                    "type": "deliverable",
                    "critical": False
                }
            ],
            StageType.METHODOLOGY: [
                {
                    "name": "Finalize Research Design",
                    "description": "Complete and validate the research methodology approach",
                    "type": "deliverable",
                    "critical": True
                },
                {
                    "name": "Develop Data Collection Instruments",
                    "description": "Create surveys, interview guides, or experimental protocols",
                    "type": "deliverable",
                    "critical": False
                },
                {
                    "name": "Obtain Ethics Approval",
                    "description": "Secure necessary ethical clearances and permissions",
                    "type": "review",
                    "critical": True
                },
                {
                    "name": "Pilot Test Methods",
                    "description": "Conduct pilot study to validate research methods",
                    "type": "deliverable",
                    "critical": False
                }
            ],
            StageType.DATA_COLLECTION: [
                {
                    "name": "Begin Data Collection",
                    "description": "Initiate data gathering through approved methods",
                    "type": "deliverable",
                    "critical": True
                },
                {
                    "name": "Complete Primary Data Collection",
                    "description": "Finish collecting all primary research data",
                    "type": "deliverable",
                    "critical": True
                },
                {
                    "name": "Validate Data Quality",
                    "description": "Review and verify collected data for completeness and accuracy",
                    "type": "review",
                    "critical": False
                },
                {
                    "name": "Organize and Store Data",
                    "description": "Structure and securely store collected data for analysis",
                    "type": "deliverable",
                    "critical": False
                }
            ],
            StageType.ANALYSIS: [
                {
                    "name": "Complete Data Analysis",
                    "description": "Finish statistical or qualitative analysis of collected data",
                    "type": "deliverable",
                    "critical": True
                },
                {
                    "name": "Interpret Findings",
                    "description": "Analyze results and draw meaningful conclusions",
                    "type": "deliverable",
                    "critical": True
                },
                {
                    "name": "Validate Results",
                    "description": "Verify analysis results and check for consistency",
                    "type": "review",
                    "critical": False
                },
                {
                    "name": "Prepare Figures and Tables",
                    "description": "Create visual representations of key findings",
                    "type": "deliverable",
                    "critical": False
                }
            ],
            StageType.WRITING: [
                {
                    "name": "Complete First Draft",
                    "description": "Finish initial draft of full dissertation/thesis",
                    "type": "deliverable",
                    "critical": True
                },
                {
                    "name": "Revise Based on Feedback",
                    "description": "Incorporate supervisor and committee feedback",
                    "type": "deliverable",
                    "critical": True
                },
                {
                    "name": "Finalize All Chapters",
                    "description": "Complete and polish all dissertation chapters",
                    "type": "deliverable",
                    "critical": True
                },
                {
                    "name": "Proofread and Format",
                    "description": "Final proofreading and formatting to university standards",
                    "type": "deliverable",
                    "critical": False
                }
            ],
            StageType.SUBMISSION: [
                {
                    "name": "Submit Draft to Committee",
                    "description": "Provide draft to dissertation committee for review",
                    "type": "deliverable",
                    "critical": True
                },
                {
                    "name": "Final Submission",
                    "description": "Submit final dissertation to graduate school",
                    "type": "deliverable",
                    "critical": True
                }
            ],
            StageType.DEFENSE: [
                {
                    "name": "Schedule Defense Date",
                    "description": "Set and confirm dissertation defense date with committee",
                    "type": "deliverable",
                    "critical": True
                },
                {
                    "name": "Prepare Defense Presentation",
                    "description": "Create slides and practice defense presentation",
                    "type": "deliverable",
                    "critical": True
                },
                {
                    "name": "Successfully Defend Dissertation",
                    "description": "Pass oral defense examination",
                    "type": "exam",
                    "critical": True
                },
                {
                    "name": "Address Committee Feedback",
                    "description": "Make required revisions based on defense feedback",
                    "type": "deliverable",
                    "critical": True
                }
            ],
            StageType.PUBLICATION: [
                {
                    "name": "Prepare Manuscript",
                    "description": "Convert dissertation chapters into journal article format",
                    "type": "deliverable",
                    "critical": False
                },
                {
                    "name": "Submit to Journal",
                    "description": "Submit manuscript to target peer-reviewed journal",
                    "type": "publication",
                    "critical": False
                },
                {
                    "name": "Address Reviewer Comments",
                    "description": "Revise manuscript based on peer review feedback",
                    "type": "deliverable",
                    "critical": False
                },
                {
                    "name": "Publish Research Findings",
                    "description": "Achieve publication in peer-reviewed venue",
                    "type": "publication",
                    "critical": False
                }
            ]
        }
        
        # Get templates for this stage type
        stage_templates = templates.get(stage.stage_type, [])
        
        if not stage_templates:
            # Fallback generic milestones
            stage_templates = [
                {
                    "name": f"Begin {stage.title}",
                    "description": f"Initiate work on {stage.title.lower()} phase",
                    "type": "deliverable",
                    "critical": False
                },
                {
                    "name": f"Complete {stage.title}",
                    "description": f"Finish all activities in {stage.title.lower()} phase",
                    "type": "deliverable",
                    "critical": True
                }
            ]
        
        # Calculate how many generic milestones to add
        if needed is None:
            # Ensure at least 2 milestones total, up to 5 total
            needed = max(2 - existing_count, 0)  # At least 2 total
            needed = min(needed, 5 - existing_count)  # Max 5 total
        
        # Ensure we generate at least 2 if no explicit milestones found
        if existing_count == 0:
            needed = max(needed, 2)
        
        # Cap at maximum allowed (5 total)
        needed = min(needed, 5 - existing_count)
        
        # Ensure we don't generate negative or zero milestones
        needed = max(needed, 0)
        
        # Select templates (prioritize critical milestones first)
        available_templates = sorted(
            stage_templates, 
            key=lambda x: (not x["critical"], x["name"])
        )
        selected_templates = available_templates[:needed]
        
        # Extract evidence snippet from stage evidence if available
        evidence_snippet = ""
        if stage.evidence:
            # Use first evidence snippet as context
            first_evidence = stage.evidence[0]
            evidence_snippet = first_evidence.text[:150]
        elif stage.description:
            evidence_snippet = stage.description[:150]
        else:
            evidence_snippet = f"Generic milestone template for {stage.title} stage"
        
        # Convert to ExtractedMilestone objects
        milestones = []
        for template in selected_templates:
            milestones.append(ExtractedMilestone(
                name=template["name"],
                description=template["description"],
                stage=stage.title,
                milestone_type=template["type"],
                evidence_snippet=evidence_snippet,  # Use stage evidence or description
                keywords=[],
                source_segment=None,
                is_critical=template["critical"],
                confidence=0.4  # Lower confidence for generic milestones
            ))
        
        return milestones
    
    def create_structured_timeline(
        self,
        text: str,
        section_map: Optional[Dict] = None,
        title: str = "PhD Timeline",
        description: str = ""
    ) -> StructuredTimeline:
        """
        Create a fully structured timeline from text.
        
        This is the main orchestration method that:
        1. Detects stages
        2. Extracts milestones
        3. Estimates durations with ranges
        4. Maps dependencies (ensuring DAG)
        5. Returns a complete StructuredTimeline object
        
        Args:
            text: Plain text input
            section_map: Optional section map from document
            title: Timeline title
            description: Timeline description
            
        Returns:
            StructuredTimeline object ready for DraftTimeline creation
        """
        # Step 1: Detect stages
        stages = self.detect_stages(text, section_map)
        
        if not stages:
            # Return empty timeline if no stages detected
            return StructuredTimeline(
                title=title,
                description=description or "No stages detected in document",
                stages=[],
                milestones=[],
                durations=[],
                dependencies=[],
                total_duration_months_min=0,
                total_duration_months_max=0,
                is_dag_valid=True
            )
        
        # Step 2: Extract milestones
        milestones = self.extract_milestones(text, section_map)
        
        # Step 3: Estimate durations
        durations = self.estimate_durations(text, stages, milestones, section_map)
        
        # Step 4: Map dependencies (with DAG validation)
        dependencies = self.map_dependencies(text, stages, milestones, section_map)
        
        # Step 5: Calculate total duration
        stage_durations = [d for d in durations if d.item_type == "stage"]
        
        if stage_durations:
            # For sequential stages, sum durations
            total_min = sum(d.duration_months_min for d in stage_durations)
            total_max = sum(d.duration_months_max for d in stage_durations)
        else:
            total_min = 0
            total_max = 0
        
        # Step 6: Validate DAG
        is_dag_valid = self._validate_dag(dependencies, stages, milestones)
        
        return StructuredTimeline(
            title=title,
            description=description or f"PhD timeline with {len(stages)} stages and {len(milestones)} milestones",
            stages=stages,
            milestones=milestones,
            durations=durations,
            dependencies=dependencies,
            total_duration_months_min=total_min,
            total_duration_months_max=total_max,
            is_dag_valid=is_dag_valid
        )
    
    def _is_critical_milestone(self, content: str, milestone_type: str) -> bool:
        """Determine if a milestone is critical."""
        critical_keywords = ["required", "mandatory", "must", "critical", "essential"]
        critical_types = ["exam", "defense", "proposal"]
        
        if milestone_type in critical_types:
            return True
        
        return any(keyword in content for keyword in critical_keywords)
    
    def _deduplicate_milestones(
        self,
        milestones: List[ExtractedMilestone]
    ) -> List[ExtractedMilestone]:
        """Remove duplicate milestones."""
        seen = set()
        unique = []
        
        for milestone in milestones:
            # Create a key for deduplication
            key = (milestone.name.lower()[:50], milestone.stage, milestone.milestone_type)
            
            if key not in seen:
                seen.add(key)
                unique.append(milestone)
        
        return unique
    
    def _extract_duration_context(
        self,
        content: str,
        start: int,
        end: int,
        window: int = 50
    ) -> str:
        """Extract context around a duration mention."""
        context_start = max(0, start - window)
        context_end = min(len(content), end + window)
        context = content[context_start:context_end].strip()
        
        # Clean up
        if context_start > 0:
            context = "..." + context
        if context_end < len(content):
            context = context + "..."
        
        return context
    
    def _get_default_duration_range(self, stage_type: StageType) -> tuple:
        """
        Get default duration range for a stage type (min, max in months).
        
        Returns:
            Tuple of (min_months, max_months)
        """
        # Format: (min, max)
        defaults = {
            StageType.COURSEWORK: (12, 24),         # 1-2 years
            StageType.LITERATURE_REVIEW: (3, 9),    # 3-9 months
            StageType.METHODOLOGY: (2, 6),          # 2-6 months
            StageType.DATA_COLLECTION: (6, 18),     # 6-18 months
            StageType.ANALYSIS: (3, 9),             # 3-9 months
            StageType.WRITING: (6, 15),             # 6-15 months
            StageType.SUBMISSION: (1, 2),           # 1-2 months
            StageType.DEFENSE: (1, 3),              # 1-3 months
            StageType.PUBLICATION: (3, 12),         # 3-12 months
            StageType.OTHER: (1, 6)                 # 1-6 months
        }
        return defaults.get(stage_type, (3, 6))
    
    def _get_discipline_aware_duration_range(
        self, 
        stage_type: StageType, 
        discipline: Optional[str] = None
    ) -> tuple:
        """
        Get discipline-aware duration range for a stage type.
        
        Different disciplines have different typical durations:
        - Experimental sciences (Biology, Chemistry): Longer data collection
        - Theoretical sciences (Math, CS): Longer analysis/writing
        - Social sciences: Longer data collection and analysis
        - Humanities: Longer writing phase
        
        Args:
            stage_type: Type of stage
            discipline: Optional discipline/field of study
            
        Returns:
            Tuple of (min_months, max_months)
        """
        # Base defaults
        base_min, base_max = self._get_default_duration_range(stage_type)
        
        if not discipline:
            return (base_min, base_max)
        
        discipline_lower = discipline.lower()
        
        # Discipline categories
        experimental_sciences = ["biology", "chemistry", "physics", "engineering", "biomedical"]
        theoretical_sciences = ["mathematics", "computer science", "cs", "statistics", "theoretical"]
        social_sciences = ["psychology", "sociology", "anthropology", "economics", "political science"]
        humanities = ["history", "literature", "philosophy", "languages", "arts"]
        
        # Adjustments by discipline category and stage type
        adjustments = {
            # Experimental sciences: Longer data collection, shorter writing
            "experimental": {
                StageType.DATA_COLLECTION: (1.5, 1.8),  # 50-80% longer
                StageType.ANALYSIS: (1.2, 1.5),         # 20-50% longer
                StageType.WRITING: (0.8, 1.0),          # 0-20% shorter
            },
            # Theoretical sciences: Shorter data collection, longer analysis/writing
            "theoretical": {
                StageType.DATA_COLLECTION: (0.5, 0.8),  # 20-50% shorter
                StageType.ANALYSIS: (1.3, 1.8),          # 30-80% longer
                StageType.WRITING: (1.2, 1.5),           # 20-50% longer
                StageType.METHODOLOGY: (1.2, 1.5),       # 20-50% longer
            },
            # Social sciences: Longer data collection and analysis
            "social": {
                StageType.DATA_COLLECTION: (1.3, 1.8),  # 30-80% longer
                StageType.ANALYSIS: (1.2, 1.6),          # 20-60% longer
                StageType.WRITING: (1.1, 1.3),           # 10-30% longer
            },
            # Humanities: Longer literature review and writing
            "humanities": {
                StageType.LITERATURE_REVIEW: (1.5, 2.0),  # 50-100% longer
                StageType.WRITING: (1.5, 2.0),             # 50-100% longer
                StageType.DATA_COLLECTION: (0.7, 1.0),    # 0-30% shorter
            }
        }
        
        # Determine discipline category
        category = None
        if any(d in discipline_lower for d in experimental_sciences):
            category = "experimental"
        elif any(d in discipline_lower for d in theoretical_sciences):
            category = "theoretical"
        elif any(d in discipline_lower for d in social_sciences):
            category = "social"
        elif any(d in discipline_lower for d in humanities):
            category = "humanities"
        
        # Apply adjustments if category found and stage has adjustment
        if category and category in adjustments:
            stage_adjustments = adjustments[category]
            if stage_type in stage_adjustments:
                mult_min, mult_max = stage_adjustments[stage_type]
                adjusted_min = int(base_min * mult_min)
                adjusted_max = int(base_max * mult_max)
                return (adjusted_min, adjusted_max)
        
        # No adjustment found, return base
        return (base_min, base_max)
    
    def _estimate_milestone_durations(
        self,
        milestones: List[ExtractedMilestone],
        explicit_durations: Dict,
        discipline: Optional[str] = None
    ) -> List[DurationEstimate]:
        """
        Estimate durations for milestones.
        
        Uses discipline-aware heuristics when discipline is provided.
        Returns duration ranges in weeks (min_weeks, max_weeks).
        
        Args:
            milestones: List of milestones to estimate
            explicit_durations: Dictionary of explicit duration mentions
            discipline: Optional discipline/field of study
            
        Returns:
            List of DurationEstimate objects with ranges
        """
        estimates = []
        
        # Default milestone durations by type (weeks: min, max)
        milestone_defaults = {
            "exam": (2, 4),           # 2-4 weeks
            "proposal": (4, 8),        # 4-8 weeks
            "review": (1, 2),          # 1-2 weeks
            "publication": (12, 24),   # 12-24 weeks
            "deliverable": (2, 6),     # 2-6 weeks
            "defense": (4, 8),         # 4-8 weeks
        }
        
        for milestone in milestones:
            # Check explicit mentions
            explicit_match = None
            for context, duration_info in explicit_durations.items():
                if milestone.name.lower() in context:
                    explicit_match = duration_info
                    break
            
            if explicit_match:
                months = explicit_match["months"]
                weeks = months * 4
                estimates.append(DurationEstimate(
                    item_description=milestone.name,
                    item_type="milestone",
                    duration_weeks_min=weeks,
                    duration_weeks_max=weeks,
                    duration_months_min=months,
                    duration_months_max=months,
                    confidence="high",
                    basis="explicit",
                    source_text=explicit_match["source"]
                ))
            else:
                # Use defaults
                weeks_min, weeks_max = milestone_defaults.get(
                    milestone.milestone_type,
                    (2, 4)  # Default fallback
                )
                
                # Scale by criticality
                if milestone.is_critical:
                    weeks_max = int(weeks_max * 1.5)  # Critical milestones may take longer
                
                estimates.append(DurationEstimate(
                    item_description=milestone.name,
                    item_type="milestone",
                    duration_weeks_min=weeks_min,
                    duration_weeks_max=weeks_max,
                    duration_months_min=max(1, weeks_min // 4),
                    duration_months_max=max(1, weeks_max // 4),
                    confidence="low",
                    basis="default"
                ))
        
        return estimates
    
    def _extract_explicit_dependencies(
        self,
        segments: List[TextSegment],
        stages: List[DetectedStage],
        milestones: List[ExtractedMilestone]
    ) -> List[Dependency]:
        """Extract explicit dependency signals from text."""
        dependencies = []
        
        for segment in segments:
            content_lower = segment.content.lower()
            
            for signal, dep_type in self.DEPENDENCY_SIGNALS.items():
                if signal in content_lower:
                    # Try to find stages/milestones mentioned in this segment
                    mentioned_stages = [
                        s for s in stages 
                        if s.title.lower() in content_lower
                    ]
                    mentioned_milestones = [
                        m for m in milestones 
                        if m.name.lower() in content_lower
                    ]
                    
                    # Create dependencies for stages
                    if len(mentioned_stages) >= 2:
                        dependencies.append(Dependency(
                            dependent_item=mentioned_stages[1].title,
                            depends_on_item=mentioned_stages[0].title,
                            dependency_type=dep_type,
                            confidence=0.8,
                            reason=f"Explicit signal: '{signal}' in text"
                        ))
                    
                    # Create dependencies for milestones
                    if len(mentioned_milestones) >= 2:
                        dependencies.append(Dependency(
                            dependent_item=mentioned_milestones[1].name,
                            depends_on_item=mentioned_milestones[0].name,
                            dependency_type=dep_type,
                            confidence=0.7,
                            reason=f"Explicit signal: '{signal}' in text"
                        ))
        
        return dependencies
    
    def _create_stage_dependencies(
        self,
        stages: List[DetectedStage]
    ) -> List[Dependency]:
        """Create implicit sequential dependencies between stages."""
        dependencies = []
        
        # Stages are already sorted by order_hint
        for i in range(len(stages) - 1):
            current = stages[i]
            next_stage = stages[i + 1]
            
            dependencies.append(Dependency(
                dependent_item=next_stage.title,
                depends_on_item=current.title,
                dependency_type="sequential",
                confidence=0.6,
                reason=f"Implicit sequential order (PhD progression)"
            ))
        
        return dependencies
    
    def _create_milestone_dependencies(
        self,
        milestones: List[ExtractedMilestone],
        stages: List[DetectedStage]
    ) -> List[Dependency]:
        """Create dependencies for milestones within their stages."""
        dependencies = []
        
        # Group milestones by stage
        by_stage = {}
        for milestone in milestones:
            if milestone.stage not in by_stage:
                by_stage[milestone.stage] = []
            by_stage[milestone.stage].append(milestone)
        
        # Create sequential dependencies within each stage
        for stage_name, stage_milestones in by_stage.items():
            # Sort by criticality and confidence (critical first)
            stage_milestones.sort(
                key=lambda m: (not m.is_critical, -m.confidence)
            )
            
            # Create sequential dependencies
            for i in range(len(stage_milestones) - 1):
                # Only create dependencies if both milestones are in same stage
                dependencies.append(Dependency(
                    dependent_item=stage_milestones[i + 1].name,
                    depends_on_item=stage_milestones[i].name,
                    dependency_type="sequential",
                    confidence=0.5,
                    reason=f"Milestones within {stage_name} stage"
                ))
        
        return dependencies
    
    def _create_blocking_dependencies(
        self,
        stages: List[DetectedStage],
        milestones: List[ExtractedMilestone]
    ) -> List[Dependency]:
        """Create blocking dependencies for critical milestones."""
        dependencies = []
        
        # Critical milestones that block entire stages
        blocking_milestones = {
            "ethics approval": StageType.DATA_COLLECTION,
            "proposal": StageType.DATA_COLLECTION,
            "comprehensive exam": StageType.METHODOLOGY,
            "qualifying exam": StageType.METHODOLOGY,
        }
        
        for milestone in milestones:
            if not milestone.is_critical:
                continue
            
            milestone_name_lower = milestone.name.lower()
            
            # Check if this milestone blocks a stage
            for blocking_keyword, blocked_stage_type in blocking_milestones.items():
                if blocking_keyword in milestone_name_lower:
                    # Find the blocked stage
                    blocked_stage = next(
                        (s for s in stages if s.stage_type == blocked_stage_type),
                        None
                    )
                    
                    if blocked_stage:
                        dependencies.append(Dependency(
                            dependent_item=blocked_stage.title,
                            depends_on_item=milestone.name,
                            dependency_type="blocks",
                            confidence=0.9,
                            reason=f"{milestone.name} must be completed before {blocked_stage.title}"
                        ))
        
        return dependencies
    
    def _ensure_dag(
        self,
        dependencies: List[Dependency],
        stages: List[DetectedStage],
        milestones: List[ExtractedMilestone]
    ) -> List[Dependency]:
        """
        Build Directed Acyclic Graph (DAG) by removing cycles.
        
        Detects and removes cycles by priority:
        1. Keep higher confidence dependencies
        2. Keep blocking dependencies
        3. Keep sequential dependencies over prerequisite
        
        Algorithm:
        - Sort dependencies by priority (blocks > sequential > others, then by confidence)
        - Incrementally add dependencies to graph
        - Before adding each edge, check if it would create a cycle
        - Only add edges that maintain DAG property
        
        Returns:
            List of dependencies guaranteed to be acyclic (valid DAG)
        """
        # Initialize graph with all nodes (stages and milestones)
        graph = {}
        all_items = (
            [s.title for s in stages] + 
            [m.name for m in milestones]
        )
        
        for item in all_items:
            graph[item] = []
        
        # Cycle detection using DFS
        def would_create_cycle(from_node: str, to_node: str, current_graph: dict) -> bool:
            """
            Check if adding edge (from_node -> to_node) would create a cycle.
            
            Uses DFS to detect if there's a path from to_node back to from_node.
            If such a path exists, adding the edge would create a cycle.
            """
            if from_node not in current_graph or to_node not in current_graph:
                return False
            
            # Check if there's a path from to_node to from_node
            visited = set()
            stack = [to_node]
            
            while stack:
                node = stack.pop()
                if node == from_node:
                    return True  # Cycle detected
                
                if node in visited:
                    continue
                visited.add(node)
                
                # Add all neighbors to stack
                for neighbor in current_graph.get(node, []):
                    if neighbor not in visited:
                        stack.append(neighbor)
            
            return False
        
        # Sort dependencies by priority:
        # 1. Blocking dependencies (highest priority)
        # 2. Sequential dependencies
        # 3. Other dependencies
        # Within each group, sort by confidence (descending)
        sorted_deps = sorted(dependencies, key=lambda d: (
            0 if d.dependency_type == "blocks" else
            1 if d.dependency_type == "sequential" else 2,
            -d.confidence
        ))
        
        # Build DAG incrementally
        filtered_deps = []
        for dep in sorted_deps:
            # Skip if nodes don't exist in graph
            if dep.dependent_item not in graph or dep.depends_on_item not in graph:
                continue
            
            # Skip self-dependencies (would create cycles)
            if dep.dependent_item == dep.depends_on_item:
                continue
            
            # Check if adding this edge would create a cycle
            if not would_create_cycle(dep.dependent_item, dep.depends_on_item, graph):
                # Safe to add - no cycle created
                graph[dep.dependent_item].append(dep.depends_on_item)
                filtered_deps.append(dep)
            # Otherwise, skip this dependency (would create cycle)
        
        return filtered_deps
    
    def _validate_dag(
        self,
        dependencies: List[Dependency],
        stages: List[DetectedStage],
        milestones: List[ExtractedMilestone]
    ) -> bool:
        """
        Validate that dependencies form a Directed Acyclic Graph (DAG).
        
        Uses DFS with recursion stack to detect cycles.
        A valid DAG has no cycles - no path from a node back to itself.
        
        Args:
            dependencies: List of dependency edges to validate
            stages: List of stages (nodes in graph)
            milestones: List of milestones (nodes in graph)
            
        Returns:
            True if DAG is valid (no cycles), False otherwise
        """
        # Build adjacency list representation of the graph
        graph = {}
        all_items = (
            [s.title for s in stages] + 
            [m.name for m in milestones]
        )
        
        # Initialize all nodes
        for item in all_items:
            graph[item] = []
        
        # Add edges from dependencies
        for dep in dependencies:
            # Skip invalid dependencies (nodes not in graph)
            if dep.dependent_item not in graph or dep.depends_on_item not in graph:
                continue
            
            # Skip self-dependencies (would create cycles)
            if dep.dependent_item == dep.depends_on_item:
                return False  # Self-dependency is a cycle
            
            # Add edge: dependent_item -> depends_on_item
            graph[dep.dependent_item].append(dep.depends_on_item)
        
        # Detect cycles using DFS with recursion stack
        def has_cycle(node: str, visited: dict, rec_stack: dict) -> bool:
            """
            Check if there's a cycle reachable from this node.
            
            Uses DFS with recursion stack to detect back edges.
            A back edge (edge to a node in recursion stack) indicates a cycle.
            """
            visited[node] = True
            rec_stack[node] = True
            
            # Check all neighbors
            for neighbor in graph.get(node, []):
                if neighbor not in visited or not visited[neighbor]:
                    # Recurse into unvisited neighbor
                    if has_cycle(neighbor, visited, rec_stack):
                        return True
                elif rec_stack.get(neighbor, False):
                    # Back edge detected - cycle found
                    return True
            
            # Remove from recursion stack (backtrack)
            rec_stack[node] = False
            return False
        
        # Check all nodes for cycles
        visited = {}
        rec_stack = {}
        
        for node in graph:
            if node not in visited or not visited[node]:
                if has_cycle(node, visited, rec_stack):
                    return False  # Cycle detected
        
        return True  # No cycles found - valid DAG
