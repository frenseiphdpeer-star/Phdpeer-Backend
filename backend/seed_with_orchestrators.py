"""
Seed Data Loader - Orchestrator-Based Approach

This script loads demo data by going through all the proper orchestrators
and services, simulating real user workflows:

1. Document upload and processing
2. Baseline extraction
3. Timeline generation and commitment
4. Progress event logging
5. PhD Doctor assessment submission
6. Analytics generation

Each step uses the actual orchestrators and services, ensuring:
- Data validation
- Business logic execution
- Decision tracing
- Evidence bundling
- Idempotency guarantees
"""

import os
import sys
import uuid
import tempfile
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Any

from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base
from app.models import User, DocumentArtifact, ProgressEvent
from app.orchestrators import (
    BaselineOrchestrator,
    TimelineOrchestrator,
    PhDDoctorOrchestrator,
    AnalyticsOrchestrator,
)
from app.services import DocumentService, ProgressService


# ============================================================================
# DEMO DOCUMENT CONTENT
# ============================================================================

DEMO_DOCUMENTS = {
    "early_stage": {
        "filename": "stanford_ml_requirements.pdf",
        "title": "PhD Program Requirements - Machine Learning",
        "content": """
Stanford University
Department of Computer Science
PhD Program in Machine Learning

PROGRAM OVERVIEW
Duration: 5 years (60 months)
Start Date: September 2025
Expected Completion: August 2030

REQUIRED MILESTONES

Year 1: Coursework and Foundations (12 months)
- Complete 3 core ML courses: Deep Learning, Probabilistic Graphical Models, Reinforcement Learning
- Maintain minimum GPA of 3.5
- Complete literature review in research area
- Deadline: August 2026

Year 2: Research Development (18 months)
- Refine research questions with advisor
- Develop baseline algorithm or methodology
- Pass qualifying examination
- Begin preliminary experiments
- Deadline: February 2028

Year 3: Experimentation (18 months)
- Conduct major experiments
- Submit first paper to top-tier conference
- Present at lab meetings and seminars
- Deadline: August 2029

Year 4: Writing and Defense (12 months)
- Complete dissertation chapters
- Defend dissertation proposal
- Submit final dissertation
- Public defense
- Deadline: August 2030

RESEARCH AREA
Reinforcement Learning and Multi-Agent Systems

ADVISOR
Prof. David Martinez
Expert in Reinforcement Learning
Office: Gates 478

FUNDING
Fully funded through Stanford Graduate Fellowship
$45,000/year stipend + tuition coverage
""",
    },
    "mid_stage": {
        "filename": "mit_nlp_proposal.pdf",
        "title": "PhD Research Proposal - Neural Dialogue Systems",
        "content": """
Massachusetts Institute of Technology
Electrical Engineering and Computer Science
PhD Research Proposal

CANDIDATE: Marcus Johnson
ADVISOR: Prof. Lisa Wang
FIELD: Natural Language Processing
SUBMITTED: March 2024

RESEARCH AREA
Neural Dialogue Systems and Conversational AI

PROGRAM TIMELINE
Total Duration: 5 years
Start Date: January 2024
Expected Completion: December 2028

COMPLETED MILESTONES
✓ Coursework (12 months) - Completed January 2025
✓ Qualifying Examination - Passed June 2025 with minor revisions

CURRENT PHASE: Experimental Research (18 months)
In Progress:
- Initial dialogue system experiments - Completed
- First paper submission - Accepted to ACL 2024
- Large-scale experiments - IN PROGRESS (behind schedule)
- Second paper preparation - Pending

Target Completion: June 2026

REMAINING PHASES
Phase 3: Advanced Research and Publications (12 months)
- Complete large-scale evaluation
- Submit 2-3 additional papers
- Target: June 2027

Phase 4: Dissertation Writing and Defense (12 months)
- Write dissertation chapters
- Committee review and revisions
- Public defense
- Target: December 2028

RESEARCH METHODOLOGY
- Neural architecture development
- Large-scale data collection
- Human evaluation studies
- Comparative analysis with baselines

PUBLICATIONS TO DATE
- Johnson, M. & Wang, L. (2024). "Context-Aware Neural Dialogue"
  Accepted: ACL 2024 Main Conference

FUNDING STATUS
NSF Graduate Research Fellowship
3 years remaining
""",
    },
    "late_stage": {
        "filename": "berkeley_cv_dissertation.pdf",
        "title": "Dissertation Progress Report - Computer Vision",
        "content": """
University of California, Berkeley
Computer Science Division
Dissertation Progress Report

CANDIDATE: Elena Rodriguez
ADVISOR: Prof. Sarah Kim
COMMITTEE: Prof. Kim (chair), Prof. Chen, Prof. Thompson, Prof. Davis
FIELD: Computer Vision - 3D Scene Understanding

PROGRAM STATUS
Start Date: September 2021
Current Date: February 2026
Expected Defense: April 2026
Expected Submission: May 2026

DISSERTATION TITLE
"Neural Approaches to 3D Scene Understanding and Reconstruction"

COMPLETED WORK

Phase 1: Coursework and Qualification (18 months)
✓ All coursework completed with distinction
✓ Qualifying examination passed (October 2022)

Phase 2: Research and Publications (24 months)
✓ Novel architecture development
✓ Large-scale dataset creation
✓ Three papers published:
  - Rodriguez, E. et al. (2023). "3D Scene Reconstruction from Single Images" - CVPR 2023
  - Rodriguez, E. & Kim, S. (2024). "Multi-View Neural Rendering" - ICCV 2024
  - Rodriguez, E. et al. (2024). "Semantic 3D Understanding" - ECCV 2024

Phase 3: Dissertation Writing (Current - 90% complete)
✓ Chapter 1: Introduction - Complete
✓ Chapter 2: Related Work - Complete
✓ Chapter 3: Methodology - Complete
✓ Chapter 4: Experiments - Complete
✓ Chapter 5: Results and Analysis - Complete
✓ Chapter 6: Applications - Complete
→ Chapter 7: Conclusion and Future Work - IN PROGRESS (due: March 15, 2026)

DEFENSE PREPARATION
✓ Draft submitted to committee
✓ Committee feedback received
✓ Revisions in progress
→ Defense presentation preparation - IN PROGRESS
→ Defense date scheduled: April 20, 2026

JOB SEARCH STATUS
✓ 18 applications submitted (November 2025)
✓ 5 first-round interviews completed
✓ 2 campus visits scheduled (March 2026)
→ Offer negotiations in progress

TIMELINE ADHERENCE
Original target: May 2026
Current forecast: May 2026
Status: ON TRACK

ADVISOR NOTES
"Elena has made excellent progress. Her research contributions are significant and publication
record is strong. She is well-prepared for the job market. Expect successful defense in April."

NEXT STEPS
1. Complete Chapter 7 by March 15
2. Final committee review March 20-30
3. Defense presentation practice (2 weeks before)
4. Public defense April 20
5. Final revisions April 21-30
6. Submission to Graduate Division May 5
""",
    },
}


DEMO_QUESTIONNAIRES = {
    "early_stage": {
        "program_start": "2025-07-01",
        "field": "Machine Learning",
        "research_area": "Reinforcement Learning and Multi-Agent Systems",
        "advisor": "Prof. David Martinez",
        "institution": "Stanford University",
        "confidence_level": "confident",
        "main_challenges": "Defining research scope, balancing coursework with research",
        "recent_achievements": "Completed core ML courses with strong grades, finished literature review",
        "timeline_concerns": "Worried about narrowing research scope appropriately",
        "support_needs": "More guidance on experiment design",
    },
    "mid_stage": {
        "program_start": "2024-01-01",
        "field": "Natural Language Processing",
        "research_area": "Neural Dialogue Systems",
        "advisor": "Prof. Lisa Wang",
        "institution": "MIT",
        "confidence_level": "somewhat_confident",
        "main_challenges": "Behind on experiments due to GPU cluster issues, feeling burned out",
        "recent_achievements": "First paper accepted to ACL 2024",
        "timeline_concerns": "Worried about timeline slippage, experiments overdue by 2 months",
        "support_needs": "Timeline adjustment discussion, better work-life balance",
    },
    "late_stage": {
        "program_start": "2021-09-01",
        "field": "Computer Vision",
        "research_area": "3D Scene Understanding and Reconstruction",
        "advisor": "Prof. Sarah Kim",
        "institution": "UC Berkeley",
        "confidence_level": "very_confident",
        "main_challenges": "Balancing dissertation writing with job interviews, finishing anxiety",
        "recent_achievements": "3 papers published, job interviews secured, dissertation 90% complete",
        "timeline_concerns": "None - on track for May completion",
        "support_needs": "Defense presentation feedback",
    },
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_temp_document(content: str, filename: str) -> str:
    """Create a temporary file with document content."""
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, filename)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return file_path


def clear_database(db: Session):
    """Clear all data from database."""
    print("\n" + "="*70)
    print("CLEARING DATABASE")
    print("="*70)
    
    from app.models import (
        AnalyticsSnapshot, DecisionTrace, EvidenceBundle,
        ProgressEvent, TimelineMilestone, TimelineStage,
        CommittedTimeline, DraftTimeline, JourneyAssessment,
        Baseline, DocumentArtifact, User, QuestionnaireDraft,
        IdempotencyKey
    )
    
    tables = [
        ("Analytics Snapshots", AnalyticsSnapshot),
        ("Decision Traces", DecisionTrace),
        ("Evidence Bundles", EvidenceBundle),
        ("Progress Events", ProgressEvent),
        ("Timeline Milestones", TimelineMilestone),
        ("Timeline Stages", TimelineStage),
        ("Committed Timelines", CommittedTimeline),
        ("Draft Timelines", DraftTimeline),
        ("Journey Assessments", JourneyAssessment),
        ("Questionnaire Drafts", QuestionnaireDraft),
        ("Baselines", Baseline),
        ("Document Artifacts", DocumentArtifact),
        ("Idempotency Keys", IdempotencyKey),
        ("Users", User),
    ]
    
    for table_name, model in tables:
        count = db.query(model).count()
        if count > 0:
            db.query(model).delete()
            print(f"✓ Deleted {count} {table_name}")
    
    db.commit()
    print("✓ Database cleared\n")


def create_user(db: Session, email: str, name: str, institution: str, field: str) -> User:
    """Create a user."""
    user = User(
        email=email,
        full_name=name,
        institution=institution,
        field_of_study=field,
        is_active=True,
        hashed_password="demo_hash_not_for_production"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ============================================================================
# WORKFLOW FUNCTIONS
# ============================================================================

def load_early_stage_scenario(db: Session):
    """
    Early-Stage PhD: Sarah Chen
    - Upload baseline document
    - Extract baseline
    - Generate and commit timeline
    - Add initial progress events
    - Submit PhD Doctor assessment
    - Generate analytics
    """
    print("\n" + "="*70)
    print("SCENARIO 1: EARLY-STAGE PhD (Sarah Chen)")
    print("="*70)
    
    # Step 1: Create user
    print("\n[1/7] Creating user...")
    user = create_user(
        db,
        email="sarah.chen@stanford.edu",
        name="Sarah Chen",
        institution="Stanford University",
        field="Machine Learning"
    )
    print(f"✓ User created: {user.email} (ID: {user.id})")
    
    # Step 2: Upload and process document
    print("\n[2/7] Uploading baseline document...")
    doc_data = DEMO_DOCUMENTS["early_stage"]
    doc_path = create_temp_document(doc_data["content"], doc_data["filename"])
    
    doc_service = DocumentService(db)
    document = doc_service.process_document(
        user_id=user.id,
        file_path=doc_path,
        original_filename=doc_data["filename"],
        title=doc_data["title"],
        description="PhD program requirements and milestone guidelines",
        document_type="PROGRAM_REQUIREMENTS"
    )
    print(f"✓ Document processed: {document.title}")
    print(f"  - ID: {document.id}")
    print(f"  - Type: {document.document_type}")
    print(f"  - Extracted text: {len(document.extracted_text_preview or '')} chars")
    
    # Step 3: Extract baseline using orchestrator
    print("\n[3/7] Extracting baseline...")
    baseline_orch = BaselineOrchestrator(db, user_id=user.id)
    baseline_result = baseline_orch.run(
        request_id=f"baseline_sarah_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        document_artifact_id=document.id
    )
    print(f"✓ Baseline extracted:")
    print(f"  - Program: {baseline_result['program_name']}")
    print(f"  - Duration: {baseline_result['total_duration_months']} months")
    print(f"  - Research Area: {baseline_result['research_area']}")
    
    # Step 4: Generate timeline using orchestrator
    print("\n[4/7] Generating timeline...")
    timeline_orch = TimelineOrchestrator(db, user_id=user.id)
    timeline_result = timeline_orch.generate_timeline(
        request_id=f"timeline_sarah_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        baseline_id=uuid.UUID(baseline_result['baseline_id'])
    )
    print(f"✓ Timeline generated:")
    print(f"  - Title: {timeline_result['title']}")
    print(f"  - Stages: {len(timeline_result['stages'])}")
    print(f"  - Total Milestones: {sum(len(s['milestones']) for s in timeline_result['stages'])}")
    
    draft_timeline_id = uuid.UUID(timeline_result['draft_timeline_id'])
    
    # Step 5: Commit timeline
    print("\n[5/7] Committing timeline...")
    commit_result = timeline_orch.commit_timeline(
        request_id=f"commit_sarah_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        draft_timeline_id=draft_timeline_id
    )
    print(f"✓ Timeline committed:")
    print(f"  - Version: {commit_result['version_number']}")
    print(f"  - Committed Date: {commit_result['committed_date']}")
    print(f"  - Active: {commit_result['is_active']}")
    
    committed_timeline_id = uuid.UUID(commit_result['committed_timeline_id'])
    
    # Step 6: Add progress events
    print("\n[6/7] Adding progress events...")
    
    # Get first few milestones
    from app.models import TimelineStage, TimelineMilestone
    stages = db.query(TimelineStage).filter(
        TimelineStage.committed_timeline_id == committed_timeline_id
    ).order_by(TimelineStage.stage_order).all()
    
    milestone = db.query(TimelineMilestone).filter(
        TimelineMilestone.timeline_stage_id == stages[0].id
    ).first()
    
    if milestone:
        progress_service = ProgressService(db)
        
        # Mark first milestone as completed
        event1 = progress_service.record_milestone_completion(
            user_id=user.id,
            milestone_id=milestone.id,
            completion_date=datetime.now() - timedelta(days=30),
            notes="Successfully completed all core ML courses with A grades"
        )
        print(f"✓ Progress event 1: Milestone completed")
        print(f"  - {milestone.title}")
        
        # Add a general progress update
        event2 = progress_service.log_progress_event(
            user_id=user.id,
            event_type="progress_update",
            title="Research Questions Refined",
            description="Met with advisor and finalized research scope for multi-agent RL",
            event_date=datetime.now() - timedelta(days=5),
            impact_level="high"
        )
        print(f"✓ Progress event 2: Research progress")
    
    # Step 7: Submit PhD Doctor assessment
    print("\n[7/7] Submitting PhD Doctor assessment...")
    phd_doctor_orch = PhDDoctorOrchestrator(db, user_id=user.id)
    
    questionnaire_data = DEMO_QUESTIONNAIRES["early_stage"]
    assessment_result = phd_doctor_orch.submit_assessment(
        request_id=f"assessment_sarah_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        questionnaire_responses=questionnaire_data
    )
    print(f"✓ Assessment submitted:")
    print(f"  - Health Score: {assessment_result['journey_health']['overall_score']}")
    print(f"  - Status: {assessment_result['journey_health']['status']}")
    
    # Step 8: Generate analytics
    print("\n[8/7] Generating analytics...")
    analytics_orch = AnalyticsOrchestrator(db, user_id=user.id)
    analytics_result = analytics_orch.run(
        request_id=f"analytics_sarah_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        timeline_id=committed_timeline_id
    )
    print(f"✓ Analytics generated:")
    print(f"  - Completion: {analytics_result['milestones']['completion_percentage']:.1f}%")
    print(f"  - Status: {analytics_result['timeline_status']}")
    print(f"  - Health: {analytics_result['journey_health']['latest_score']:.1f}/5.0")
    
    print("\n" + "="*70)
    print("✓ EARLY-STAGE SCENARIO COMPLETE")
    print("="*70)
    
    return user.id, committed_timeline_id


def load_mid_stage_scenario(db: Session):
    """
    Mid-Stage PhD: Marcus Johnson
    - Already has timeline and progress
    - Experiencing delays
    - Submit assessment showing stress
    - Generate analytics showing risk
    """
    print("\n" + "="*70)
    print("SCENARIO 2: MID-STAGE PhD (Marcus Johnson)")
    print("="*70)
    
    # Step 1: Create user
    print("\n[1/7] Creating user...")
    user = create_user(
        db,
        email="marcus.johnson@mit.edu",
        name="Marcus Johnson",
        institution="MIT",
        field="Natural Language Processing"
    )
    print(f"✓ User created: {user.email} (ID: {user.id})")
    
    # Step 2: Upload document
    print("\n[2/7] Uploading research proposal...")
    doc_data = DEMO_DOCUMENTS["mid_stage"]
    doc_path = create_temp_document(doc_data["content"], doc_data["filename"])
    
    doc_service = DocumentService(db)
    document = doc_service.process_document(
        user_id=user.id,
        file_path=doc_path,
        original_filename=doc_data["filename"],
        title=doc_data["title"],
        description="Approved PhD research proposal for neural dialogue systems",
        document_type="PhD_PROPOSAL"
    )
    print(f"✓ Document processed: {document.title}")
    
    # Step 3: Extract baseline
    print("\n[3/7] Extracting baseline...")
    baseline_orch = BaselineOrchestrator(db, user_id=user.id)
    baseline_result = baseline_orch.run(
        request_id=f"baseline_marcus_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        document_artifact_id=document.id
    )
    print(f"✓ Baseline extracted")
    
    # Step 4: Generate timeline
    print("\n[4/7] Generating timeline...")
    timeline_orch = TimelineOrchestrator(db, user_id=user.id)
    timeline_result = timeline_orch.generate_timeline(
        request_id=f"timeline_marcus_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        baseline_id=uuid.UUID(baseline_result['baseline_id'])
    )
    print(f"✓ Timeline generated with {len(timeline_result['stages'])} stages")
    
    # Step 5: Commit timeline
    print("\n[5/7] Committing timeline...")
    commit_result = timeline_orch.commit_timeline(
        request_id=f"commit_marcus_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        draft_timeline_id=uuid.UUID(timeline_result['draft_timeline_id'])
    )
    print(f"✓ Timeline committed (v{commit_result['version_number']})")
    
    committed_timeline_id = uuid.UUID(commit_result['committed_timeline_id'])
    
    # Step 6: Add progress events showing delays and stress
    print("\n[6/7] Adding progress events...")
    progress_service = ProgressService(db)
    
    # Paper acceptance
    event1 = progress_service.log_progress_event(
        user_id=user.id,
        event_type="achievement",
        title="Paper Accepted to ACL 2024",
        description="First-author paper accepted to top-tier NLP conference",
        event_date=datetime.now() - timedelta(days=45),
        impact_level="high"
    )
    print(f"✓ Event 1: Paper accepted")
    
    # Challenge/delay
    event2 = progress_service.log_progress_event(
        user_id=user.id,
        event_type="challenge",
        title="Experimental Delays",
        description="GPU cluster downtime causing 60-day delay on large-scale experiments",
        event_date=datetime.now() - timedelta(days=20),
        impact_level="high"
    )
    print(f"✓ Event 2: Experimental delays")
    
    # Step 7: Submit stressed assessment
    print("\n[7/7] Submitting PhD Doctor assessment...")
    phd_doctor_orch = PhDDoctorOrchestrator(db, user_id=user.id)
    
    assessment_result = phd_doctor_orch.submit_assessment(
        request_id=f"assessment_marcus_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        questionnaire_responses=DEMO_QUESTIONNAIRES["mid_stage"]
    )
    print(f"✓ Assessment showing stress:")
    print(f"  - Health Score: {assessment_result['journey_health']['overall_score']}")
    print(f"  - Status: {assessment_result['journey_health']['status']}")
    
    # Step 8: Generate analytics showing risk
    print("\n[8/7] Generating analytics...")
    analytics_orch = AnalyticsOrchestrator(db, user_id=user.id)
    analytics_result = analytics_orch.run(
        request_id=f"analytics_marcus_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        timeline_id=committed_timeline_id
    )
    print(f"✓ Analytics showing risk:")
    print(f"  - Completion: {analytics_result['milestones']['completion_percentage']:.1f}%")
    print(f"  - Status: {analytics_result['timeline_status']}")
    print(f"  - Overdue: {analytics_result['delays']['overdue_milestones']}")
    
    print("\n" + "="*70)
    print("✓ MID-STAGE SCENARIO COMPLETE")
    print("="*70)
    
    return user.id, committed_timeline_id


def load_late_stage_scenario(db: Session):
    """
    Late-Stage PhD: Elena Rodriguez
    - Nearly complete
    - Multiple publications
    - Job offers
    - Analytics showing excellent progress
    """
    print("\n" + "="*70)
    print("SCENARIO 3: LATE-STAGE PhD (Elena Rodriguez)")
    print("="*70)
    
    # Step 1: Create user
    print("\n[1/7] Creating user...")
    user = create_user(
        db,
        email="elena.rodriguez@berkeley.edu",
        name="Elena Rodriguez",
        institution="UC Berkeley",
        field="Computer Vision"
    )
    print(f"✓ User created: {user.email} (ID: {user.id})")
    
    # Step 2: Upload document
    print("\n[2/7] Uploading dissertation progress report...")
    doc_data = DEMO_DOCUMENTS["late_stage"]
    doc_path = create_temp_document(doc_data["content"], doc_data["filename"])
    
    doc_service = DocumentService(db)
    document = doc_service.process_document(
        user_id=user.id,
        file_path=doc_path,
        original_filename=doc_data["filename"],
        title=doc_data["title"],
        description="Dissertation progress report showing near-completion status",
        document_type="DISSERTATION_DRAFT"
    )
    print(f"✓ Document processed")
    
    # Step 3: Extract baseline
    print("\n[3/7] Extracting baseline...")
    baseline_orch = BaselineOrchestrator(db, user_id=user.id)
    baseline_result = baseline_orch.run(
        request_id=f"baseline_elena_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        document_artifact_id=document.id
    )
    print(f"✓ Baseline extracted")
    
    # Step 4: Generate timeline
    print("\n[4/7] Generating timeline...")
    timeline_orch = TimelineOrchestrator(db, user_id=user.id)
    timeline_result = timeline_orch.generate_timeline(
        request_id=f"timeline_elena_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        baseline_id=uuid.UUID(baseline_result['baseline_id'])
    )
    print(f"✓ Timeline generated")
    
    # Step 5: Commit timeline
    print("\n[5/7] Committing timeline...")
    commit_result = timeline_orch.commit_timeline(
        request_id=f"commit_elena_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        draft_timeline_id=uuid.UUID(timeline_result['draft_timeline_id'])
    )
    print(f"✓ Timeline committed")
    
    committed_timeline_id = uuid.UUID(commit_result['committed_timeline_id'])
    
    # Step 6: Add progress events showing success
    print("\n[6/7] Adding progress events...")
    progress_service = ProgressService(db)
    
    # Publications
    event1 = progress_service.log_progress_event(
        user_id=user.id,
        event_type="achievement",
        title="Third Paper Published",
        description="Paper published in ECCV 2024 - completing publication requirements",
        event_date=datetime.now() - timedelta(days=60),
        impact_level="high"
    )
    print(f"✓ Event 1: Third publication")
    
    # Job interviews
    event2 = progress_service.log_progress_event(
        user_id=user.id,
        event_type="achievement",
        title="Campus Visits Scheduled",
        description="Two campus visits scheduled for faculty positions",
        event_date=datetime.now() - timedelta(days=15),
        impact_level="high"
    )
    print(f"✓ Event 2: Job interviews")
    
    # Dissertation progress
    event3 = progress_service.log_progress_event(
        user_id=user.id,
        event_type="progress_update",
        title="Dissertation 90% Complete",
        description="All chapters complete except conclusion, defense scheduled for April",
        event_date=datetime.now() - timedelta(days=3),
        impact_level="medium"
    )
    print(f"✓ Event 3: Dissertation progress")
    
    # Step 7: Submit positive assessment
    print("\n[7/7] Submitting PhD Doctor assessment...")
    phd_doctor_orch = PhDDoctorOrchestrator(db, user_id=user.id)
    
    assessment_result = phd_doctor_orch.submit_assessment(
        request_id=f"assessment_elena_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        questionnaire_responses=DEMO_QUESTIONNAIRES["late_stage"]
    )
    print(f"✓ Assessment showing excellence:")
    print(f"  - Health Score: {assessment_result['journey_health']['overall_score']}")
    print(f"  - Status: {assessment_result['journey_health']['status']}")
    
    # Step 8: Generate analytics
    print("\n[8/7] Generating analytics...")
    analytics_orch = AnalyticsOrchestrator(db, user_id=user.id)
    analytics_result = analytics_orch.run(
        request_id=f"analytics_elena_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        timeline_id=committed_timeline_id
    )
    print(f"✓ Analytics showing strong finish:")
    print(f"  - Completion: {analytics_result['milestones']['completion_percentage']:.1f}%")
    print(f"  - Status: {analytics_result['timeline_status']}")
    print(f"  - Health: {analytics_result['journey_health']['latest_score']:.1f}/5.0")
    
    print("\n" + "="*70)
    print("✓ LATE-STAGE SCENARIO COMPLETE")
    print("="*70)
    
    return user.id, committed_timeline_id


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Run the complete orchestrator-based seed data loading."""
    print("\n" + "="*70)
    print("PhD TIMELINE INTELLIGENCE - ORCHESTRATOR-BASED SEED LOADER")
    print("="*70)
    print("\nThis script loads demo data by going through all orchestrators:")
    print("  1. Document upload and processing")
    print("  2. Baseline extraction (BaselineOrchestrator)")
    print("  3. Timeline generation (TimelineOrchestrator)")
    print("  4. Timeline commitment (TimelineOrchestrator)")
    print("  5. Progress event logging (ProgressService)")
    print("  6. PhD Doctor assessment (PhDDoctorOrchestrator)")
    print("  7. Analytics generation (AnalyticsOrchestrator)")
    print("\nAll workflows use proper orchestrators with:")
    print("  - Decision tracing")
    print("  - Evidence bundling")
    print("  - Idempotency guarantees")
    print("  - Business logic validation")
    
    db = SessionLocal()
    
    try:
        # Optional: Clear existing data
        response = input("\nClear existing database data? (y/N): ")
        if response.lower() == 'y':
            clear_database(db)
        
        # Load all three scenarios
        print("\n" + "="*70)
        print("LOADING DEMO SCENARIOS")
        print("="*70)
        
        scenario_results = []
        
        # Scenario 1: Early-stage
        sarah_id, sarah_timeline = load_early_stage_scenario(db)
        scenario_results.append(("Sarah Chen (Early)", sarah_id, sarah_timeline))
        
        # Scenario 2: Mid-stage
        marcus_id, marcus_timeline = load_mid_stage_scenario(db)
        scenario_results.append(("Marcus Johnson (Mid)", marcus_id, marcus_timeline))
        
        # Scenario 3: Late-stage
        elena_id, elena_timeline = load_late_stage_scenario(db)
        scenario_results.append(("Elena Rodriguez (Late)", elena_id, elena_timeline))
        
        # Final summary
        print("\n" + "="*70)
        print("✓ ALL SCENARIOS LOADED SUCCESSFULLY")
        print("="*70)
        print("\nDemo Users Created:")
        for name, user_id, timeline_id in scenario_results:
            print(f"\n  {name}")
            print(f"    User ID: {user_id}")
            print(f"    Timeline ID: {timeline_id}")
        
        print("\n" + "="*70)
        print("NEXT STEPS")
        print("="*70)
        print("  1. Start the backend server:")
        print("     uvicorn app.main:app --reload")
        print("\n  2. Login with demo user emails:")
        print("     - sarah.chen@stanford.edu")
        print("     - marcus.johnson@mit.edu")
        print("     - elena.rodriguez@berkeley.edu")
        print("\n  3. Explore the data:")
        print("     - View timelines and progress")
        print("     - Check analytics dashboards")
        print("     - Review decision traces")
        print("     - Examine health assessments")
        print("\n  4. Query decision traces:")
        print("     SELECT * FROM decision_traces ORDER BY created_at DESC;")
        print("\n  5. View analytics:")
        print("     SELECT * FROM analytics_snapshots;")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error loading demo data: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    main()
