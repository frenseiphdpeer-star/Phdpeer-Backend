"""
Demo Seed Data Script

Creates realistic demo data for three PhD student personas:
- Early-stage PhD (Sarah Chen)
- Mid-stage PhD (Marcus Johnson)
- Late-stage PhD (Elena Rodriguez)
"""

import uuid
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base
from app.models import (
    User, DocumentArtifact, Baseline, DraftTimeline, CommittedTimeline,
    TimelineStage, TimelineMilestone, ProgressEvent, JourneyAssessment,
    AnalyticsSnapshot
)


def clear_all_data(db: Session):
    """Clear all existing data (for demo purposes only)"""
    print("Clearing existing data...")
    db.query(AnalyticsSnapshot).delete()
    db.query(ProgressEvent).delete()
    db.query(TimelineMilestone).delete()
    db.query(TimelineStage).delete()
    db.query(CommittedTimeline).delete()
    db.query(DraftTimeline).delete()
    db.query(JourneyAssessment).delete()
    db.query(Baseline).delete()
    db.query(DocumentArtifact).delete()
    db.query(User).delete()
    db.commit()
    print("✓ Data cleared")


def create_early_stage_phd(db: Session):
    """
    Early-stage PhD: Sarah Chen
    - 6 months into program
    - Just completed literature review
    - Developing research methodology
    - High motivation, some anxiety about scope
    """
    print("\nCreating Early-Stage PhD: Sarah Chen...")
    
    # User
    sarah = User(
        id=uuid.UUID('11111111-1111-1111-1111-111111111111'),
        email='sarah.chen@university.edu',
        full_name='Sarah Chen',
        institution='Stanford University',
        field_of_study='Machine Learning',
        is_active=True
    )
    db.add(sarah)
    
    # Document
    doc = DocumentArtifact(
        id=uuid.UUID('11111111-2222-1111-1111-111111111111'),
        user_id=sarah.id,
        title='PhD Program Requirements - Machine Learning',
        description='Official program guidelines and milestone requirements',
        file_type='application/pdf',
        file_path='/uploads/sarah_requirements.pdf',
        file_size_bytes=245760,
        document_type='PROGRAM_REQUIREMENTS',
        extracted_text_preview='Stanford University PhD Program in Machine Learning...'
    )
    db.add(doc)
    
    # Baseline
    start_date = date.today() - timedelta(days=180)  # 6 months ago
    expected_end = start_date + timedelta(days=1825)  # 5 years
    
    baseline = Baseline(
        id=uuid.UUID('11111111-3333-1111-1111-111111111111'),
        user_id=sarah.id,
        document_artifact_id=doc.id,
        program_name='PhD in Computer Science',
        institution='Stanford University',
        field_of_study='Machine Learning',
        start_date=start_date,
        expected_end_date=expected_end,
        total_duration_months=60,
        requirements_summary='Comprehensive ML program with coursework, qualifying exam, dissertation',
        research_area='Reinforcement Learning and Multi-Agent Systems',
        advisor_info='Prof. David Martinez - Expert in RL',
        funding_status='FULLY_FUNDED'
    )
    db.add(baseline)
    
    # Draft Timeline (source for committed timeline)
    draft_timeline = DraftTimeline(
        id=uuid.UUID('11111111-3333-1111-1111-111111111110'),
        user_id=sarah.id,
        baseline_id=baseline.id,
        title='Sarah\'s PhD Journey - ML Research',
        description='5-year plan for PhD completion in Machine Learning',
        version_number='1.0',
        is_committed=True
    )
    db.add(draft_timeline)
    
    # Committed Timeline
    timeline = CommittedTimeline(
        id=uuid.UUID('11111111-4444-1111-1111-111111111111'),
        user_id=sarah.id,
        baseline_id=baseline.id,
        draft_timeline_id=draft_timeline.id,
        title='Sarah\'s PhD Journey - ML Research',
        description='5-year plan for PhD completion in Machine Learning',
        version_number='1.0',
        committed_date=date.today() - timedelta(days=30),
        target_completion_date=expected_end,
        is_active=True
    )
    db.add(timeline)
    
    # Stage 1: Coursework (COMPLETED)
    stage1 = TimelineStage(
        id=uuid.UUID('11111111-5555-1111-1111-111111111111'),
        committed_timeline_id=timeline.id,
        title='Coursework and Foundations',
        description='Complete required courses and build ML foundation',
        stage_order=1,
        duration_months=12,
        start_date=start_date,
        end_date=start_date + timedelta(days=365),
        status='COMPLETED'
    )
    db.add(stage1)
    
    # Milestones for Stage 1
    m1 = TimelineMilestone(
        timeline_stage_id=stage1.id,
        title='Complete Core ML Courses',
        description='Deep Learning, Probabilistic Graphical Models, RL',
        milestone_order=1,
        target_date=start_date + timedelta(days=180),
        actual_completion_date=start_date + timedelta(days=175),
        is_completed=True,
        is_critical=True,
        status='COMPLETED'
    )
    db.add(m1)
    
    m2 = TimelineMilestone(
        timeline_stage_id=stage1.id,
        title='Literature Review',
        description='Comprehensive review of multi-agent RL literature',
        milestone_order=2,
        target_date=start_date + timedelta(days=240),
        actual_completion_date=start_date + timedelta(days=250),
        is_completed=True,
        is_critical=False,
        status='COMPLETED'
    )
    db.add(m2)
    
    # Stage 2: Research Development (IN PROGRESS)
    stage2 = TimelineStage(
        id=uuid.UUID('11111111-6666-1111-1111-111111111111'),
        committed_timeline_id=timeline.id,
        title='Research Methodology Development',
        description='Develop research questions and methodology',
        stage_order=2,
        duration_months=18,
        start_date=start_date + timedelta(days=365),
        end_date=start_date + timedelta(days=910),
        status='IN_PROGRESS'
    )
    db.add(stage2)
    
    # Milestones for Stage 2
    m3 = TimelineMilestone(
        timeline_stage_id=stage2.id,
        title='Refine Research Questions',
        description='Narrow down research scope and define key questions',
        milestone_order=1,
        target_date=date.today() - timedelta(days=15),
        actual_completion_date=date.today() - timedelta(days=10),
        is_completed=True,
        is_critical=True,
        status='COMPLETED'
    )
    db.add(m3)
    
    m4 = TimelineMilestone(
        timeline_stage_id=stage2.id,
        title='Develop Baseline Algorithm',
        description='Implement baseline multi-agent RL algorithm',
        milestone_order=2,
        target_date=date.today() + timedelta(days=90),
        is_completed=False,
        is_critical=True,
        status='PENDING'
    )
    db.add(m4)
    
    m5 = TimelineMilestone(
        timeline_stage_id=stage2.id,
        title='Qualifying Exam Preparation',
        description='Prepare for and pass qualifying exam',
        milestone_order=3,
        target_date=date.today() + timedelta(days=180),
        is_completed=False,
        is_critical=True,
        status='PENDING'
    )
    db.add(m5)
    
    # Stage 3: Experimentation (PENDING)
    stage3 = TimelineStage(
        committed_timeline_id=timeline.id,
        title='Experimental Research',
        description='Conduct experiments and gather results',
        stage_order=3,
        duration_months=18,
        status='PENDING'
    )
    db.add(stage3)
    
    # Stage 4: Writing (PENDING)
    stage4 = TimelineStage(
        committed_timeline_id=timeline.id,
        title='Dissertation Writing',
        description='Write and defend dissertation',
        stage_order=4,
        duration_months=12,
        status='PENDING'
    )
    db.add(stage4)
    
    # Progress Events
    event1 = ProgressEvent(
        user_id=sarah.id,
        milestone_id=m1.id,
        event_type='MILESTONE_COMPLETED',
        title='Completed Core ML Courses',
        description='Successfully completed all three core courses with A grades',
        event_date=m1.actual_completion_date,
        impact_level='HIGH'
    )
    db.add(event1)
    
    event2 = ProgressEvent(
        user_id=sarah.id,
        milestone_id=m3.id,
        event_type='MILESTONE_COMPLETED',
        title='Research Questions Defined',
        description='Met with advisor and finalized research scope',
        event_date=m3.actual_completion_date,
        impact_level='HIGH'
    )
    db.add(event2)
    
    # Journey Assessment (Recent, positive)
    assessment = JourneyAssessment(
        user_id=sarah.id,
        assessment_date=datetime.now() - timedelta(days=7),
        assessment_type='self_assessment',
        overall_progress_rating=4.2,
        research_quality_rating=4.0,
        timeline_adherence_rating=4.5,
        strengths='Strong coursework foundation, clear research direction, excellent advisor support',
        challenges='Defining appropriate research scope, balancing coursework and research',
        action_items='Focus on developing baseline algorithm, prepare for qualifying exam',
        notes='Feeling confident but need to narrow research scope'
    )
    db.add(assessment)
    
    # Analytics Snapshot - Early Stage
    analytics_snapshot = AnalyticsSnapshot(
        id=uuid.UUID('11111111-9999-1111-1111-111111111111'),
        user_id=sarah.id,
        timeline_version='1.0',
        summary_json={
            "timeline_id": str(timeline.id),
            "user_id": str(sarah.id),
            "generated_at": datetime.now().isoformat(),
            "timeline_status": "on_track",
            "milestone_completion_percentage": 40.0,
            "total_milestones": 5,
            "completed_milestones": 2,
            "pending_milestones": 3,
            "total_delays": 1,
            "overdue_milestones": 0,
            "overdue_critical_milestones": 0,
            "average_delay_days": 10.0,
            "max_delay_days": 10,
            "latest_health_score": 4.2,
            "health_dimensions": {
                "momentum": 4.5,
                "clarity": 4.0,
                "support": 4.3,
                "confidence": 4.0
            },
            "longitudinal_summary": {
                "trend": "positive",
                "velocity": "good",
                "completion_forecast": "2029-01-15"
            }
        }
    )
    db.add(analytics_snapshot)
    
    db.commit()
    print("✓ Early-stage PhD created: Sarah Chen")
    print("  - 6 months in, coursework completed")
    print("  - Developing research methodology")
    print("  - High motivation, some scope anxiety")
    print("  - Analytics: 40% complete, on track")


def create_mid_stage_phd(db: Session):
    """
    Mid-stage PhD: Marcus Johnson
    - 2.5 years into program
    - Passed qualifying exam
    - Conducting experiments
    - Some delays, mixed progress
    """
    print("\nCreating Mid-Stage PhD: Marcus Johnson...")
    
    # User
    marcus = User(
        id=uuid.UUID('22222222-2222-2222-2222-222222222222'),
        email='marcus.johnson@university.edu',
        full_name='Marcus Johnson',
        institution='MIT',
        field_of_study='Natural Language Processing',
        is_active=True
    )
    db.add(marcus)
    
    # Document
    doc = DocumentArtifact(
        id=uuid.UUID('22222222-2222-2222-2222-222222222221'),
        user_id=marcus.id,
        title='PhD Research Proposal - NLP',
        description='Approved research proposal for dialogue systems',
        file_type='application/pdf',
        file_path='/uploads/marcus_proposal.pdf',
        file_size_bytes=512000,
        document_type='PhD_PROPOSAL'
    )
    db.add(doc)
    
    # Baseline
    start_date = date.today() - timedelta(days=912)  # 2.5 years ago
    expected_end = start_date + timedelta(days=1825)  # 5 years total
    
    baseline = Baseline(
        id=uuid.UUID('22222222-2222-2222-2222-222222222223'),
        user_id=marcus.id,
        document_artifact_id=doc.id,
        program_name='PhD in Electrical Engineering and Computer Science',
        institution='MIT',
        field_of_study='Natural Language Processing',
        start_date=start_date,
        expected_end_date=expected_end,
        total_duration_months=60,
        research_area='Neural Dialogue Systems and Conversational AI',
        advisor_info='Prof. Lisa Wang - NLP and Dialogue Systems'
    )
    db.add(baseline)
    
    # Draft Timeline (source for committed timeline)
    draft_timeline = DraftTimeline(
        id=uuid.UUID('22222222-2222-2222-2222-222222222220'),
        user_id=marcus.id,
        baseline_id=baseline.id,
        title='Marcus\' PhD Timeline - NLP Research',
        description='Research plan for neural dialogue systems',
        version_number='2.0',
        is_committed=True
    )
    db.add(draft_timeline)
    
    # Committed Timeline
    timeline = CommittedTimeline(
        id=uuid.UUID('22222222-2222-2222-2222-222222222224'),
        user_id=marcus.id,
        baseline_id=baseline.id,
        draft_timeline_id=draft_timeline.id,
        title='Marcus\' PhD Timeline - NLP Research',
        description='Research plan for neural dialogue systems',
        version_number='2.0',
        committed_date=start_date + timedelta(days=365),
        target_completion_date=expected_end,
        is_active=True
    )
    db.add(timeline)
    
    # Stage 1: Coursework (COMPLETED)
    stage1 = TimelineStage(
        committed_timeline_id=timeline.id,
        title='Coursework',
        stage_order=1,
        duration_months=12,
        status='COMPLETED'
    )
    db.add(stage1)
    
    # Stage 2: Qualifying Exam (COMPLETED)
    stage2 = TimelineStage(
        id=uuid.UUID('22222222-2222-2222-2222-222222222225'),
        committed_timeline_id=timeline.id,
        title='Qualifying Examination',
        stage_order=2,
        duration_months=6,
        status='COMPLETED'
    )
    db.add(stage2)
    
    m_qual = TimelineMilestone(
        timeline_stage_id=stage2.id,
        title='Pass Qualifying Exam',
        milestone_order=1,
        target_date=start_date + timedelta(days=547),  # 18 months
        actual_completion_date=start_date + timedelta(days=580),  # ~30 days late
        is_completed=True,
        is_critical=True,
        status='COMPLETED'
    )
    db.add(m_qual)
    
    # Stage 3: Research & Experimentation (IN PROGRESS - DELAYED)
    stage3 = TimelineStage(
        id=uuid.UUID('22222222-2222-2222-2222-222222222226'),
        committed_timeline_id=timeline.id,
        title='Research and Experimentation',
        description='Develop and test dialogue system models',
        stage_order=3,
        duration_months=18,
        status='IN_PROGRESS'
    )
    db.add(stage3)
    
    # Milestones for Stage 3 - Mixed completion
    m1 = TimelineMilestone(
        timeline_stage_id=stage3.id,
        title='Build Baseline Dialogue System',
        milestone_order=1,
        target_date=start_date + timedelta(days=730),  # 2 years
        actual_completion_date=start_date + timedelta(days=760),  # 30 days late
        is_completed=True,
        is_critical=True,
        status='COMPLETED'
    )
    db.add(m1)
    
    m2 = TimelineMilestone(
        timeline_stage_id=stage3.id,
        title='First Paper Submission',
        description='Submit first research paper to ACL conference',
        milestone_order=2,
        target_date=start_date + timedelta(days=820),
        actual_completion_date=start_date + timedelta(days=840),  # 20 days late
        is_completed=True,
        is_critical=True,
        status='COMPLETED'
    )
    db.add(m2)
    
    m3 = TimelineMilestone(
        id=uuid.UUID('22222222-2222-2222-2222-222222222227'),
        timeline_stage_id=stage3.id,
        title='Run Large-Scale Experiments',
        description='Complete experiments with 10K+ dialogue examples',
        milestone_order=3,
        target_date=date.today() - timedelta(days=45),  # OVERDUE by 45 days
        is_completed=False,
        is_critical=True,
        status='OVERDUE'
    )
    db.add(m3)
    
    m4 = TimelineMilestone(
        timeline_stage_id=stage3.id,
        title='Second Paper Submission',
        milestone_order=4,
        target_date=date.today() + timedelta(days=60),
        is_completed=False,
        is_critical=True,
        status='PENDING'
    )
    db.add(m4)
    
    # Stage 4: Writing (PENDING)
    stage4 = TimelineStage(
        committed_timeline_id=timeline.id,
        title='Dissertation Writing and Defense',
        stage_order=4,
        duration_months=12,
        status='PENDING'
    )
    db.add(stage4)
    
    # Progress Events
    event1 = ProgressEvent(
        user_id=marcus.id,
        milestone_id=m_qual.id,
        event_type='MILESTONE_COMPLETED',
        title='Passed Qualifying Exam',
        description='Successfully passed quals with minor revisions',
        event_date=m_qual.actual_completion_date,
        impact_level='HIGH'
    )
    db.add(event1)
    
    event2 = ProgressEvent(
        user_id=marcus.id,
        milestone_id=m2.id,
        event_type='MILESTONE_COMPLETED',
        title='First Paper Accepted!',
        description='Paper accepted to ACL 2024 main conference',
        event_date=date.today() - timedelta(days=30),
        impact_level='HIGH'
    )
    db.add(event2)
    
    event3 = ProgressEvent(
        user_id=marcus.id,
        milestone_id=m3.id,
        event_type='CHALLENGE',
        title='Experimental Delays',
        description='GPU cluster downtime causing delays in large-scale experiments',
        event_date=date.today() - timedelta(days=20),
        impact_level='MEDIUM'
    )
    db.add(event3)
    
    # Journey Assessment (Recent, mixed feelings)
    assessment = JourneyAssessment(
        user_id=marcus.id,
        assessment_date=datetime.now() - timedelta(days=3),
        assessment_type='self_assessment',
        overall_progress_rating=3.2,
        research_quality_rating=4.0,
        timeline_adherence_rating=2.5,
        strengths='Research quality is good, paper accepted, strong technical skills',
        challenges='Behind schedule on experiments, feeling stressed about timeline, work-life balance suffering',
        action_items='Complete experiments ASAP, talk to advisor about timeline adjustment, take weekend off',
        notes='Feeling burned out, need to address delays and manage stress'
    )
    db.add(assessment)
    
    # Analytics Snapshot - Mid Stage
    analytics_snapshot = AnalyticsSnapshot(
        id=uuid.UUID('22222222-9999-2222-2222-222222222222'),
        user_id=marcus.id,
        timeline_version='1.0',
        summary_json={
            "timeline_id": str(timeline.id),
            "user_id": str(marcus.id),
            "generated_at": datetime.now().isoformat(),
            "timeline_status": "at_risk",
            "milestone_completion_percentage": 62.5,
            "total_milestones": 8,
            "completed_milestones": 5,
            "pending_milestones": 3,
            "total_delays": 3,
            "overdue_milestones": 1,
            "overdue_critical_milestones": 1,
            "average_delay_days": 45.0,
            "max_delay_days": 60,
            "latest_health_score": 3.2,
            "health_dimensions": {
                "momentum": 2.5,
                "clarity": 3.5,
                "support": 3.0,
                "confidence": 3.0,
                "work_life_balance": 2.0
            },
            "longitudinal_summary": {
                "trend": "concerning",
                "velocity": "slow",
                "completion_forecast": "2027-08-15",
                "risk_factors": ["overdue_experiments", "burnout_indicators"]
            }
        }
    )
    db.add(analytics_snapshot)
    
    db.commit()
    print("✓ Mid-stage PhD created: Marcus Johnson")
    print("  - 2.5 years in, some delays")
    print("  - Paper accepted, but experiments overdue")
    print("  - Managing stress and timeline pressure")
    print("  - Analytics: 62.5% complete, at risk")


def create_late_stage_phd(db: Session):
    """
    Late-stage PhD: Elena Rodriguez
    - 4.5 years into program
    - Writing dissertation
    - Job hunting
    - Final push to completion
    """
    print("\nCreating Late-Stage PhD: Elena Rodriguez...")
    
    # User
    elena = User(
        id=uuid.UUID('33333333-3333-3333-3333-333333333333'),
        email='elena.rodriguez@university.edu',
        full_name='Elena Rodriguez',
        institution='UC Berkeley',
        field_of_study='Computer Vision',
        is_active=True
    )
    db.add(elena)
    
    # Document
    doc = DocumentArtifact(
        id=uuid.UUID('33333333-3333-3333-3333-333333333331'),
        user_id=elena.id,
        title='Dissertation Outline - Computer Vision',
        description='Approved dissertation outline and chapter structure',
        file_type='application/pdf',
        file_path='/uploads/elena_outline.pdf',
        file_size_bytes=128000,
        document_type='THESIS_GUIDELINES'
    )
    db.add(doc)
    
    # Baseline
    start_date = date.today() - timedelta(days=1642)  # 4.5 years ago
    expected_end = start_date + timedelta(days=1825)  # 5 years total (6 months left)
    
    baseline = Baseline(
        id=uuid.UUID('33333333-3333-3333-3333-333333333332'),
        user_id=elena.id,
        document_artifact_id=doc.id,
        program_name='PhD in Computer Science',
        institution='UC Berkeley',
        field_of_study='Computer Vision',
        start_date=start_date,
        expected_end_date=expected_end,
        total_duration_months=60,
        research_area='3D Scene Understanding and Reconstruction',
        advisor_info='Prof. Sarah Kim - Computer Vision and Graphics'
    )
    db.add(baseline)
    
    # Draft Timeline (source for committed timeline)
    draft_timeline = DraftTimeline(
        id=uuid.UUID('33333333-3333-3333-3333-333333333330'),
        user_id=elena.id,
        baseline_id=baseline.id,
        title='Elena\'s PhD Timeline - Computer Vision',
        description='Final year timeline focusing on dissertation completion',
        version_number='3.0',
        is_committed=True
    )
    db.add(draft_timeline)
    
    # Committed Timeline
    timeline = CommittedTimeline(
        id=uuid.UUID('33333333-3333-3333-3333-333333333333'),
        user_id=elena.id,
        baseline_id=baseline.id,
        draft_timeline_id=draft_timeline.id,
        title='Elena\'s PhD Timeline - Computer Vision',
        description='Final year timeline focusing on dissertation completion',
        version_number='3.0',
        committed_date=start_date + timedelta(days=1460),  # Year 4
        target_completion_date=expected_end,
        is_active=True
    )
    db.add(timeline)
    
    # Stage 1-3: All completed
    stage1 = TimelineStage(
        committed_timeline_id=timeline.id,
        title='Coursework and Quals',
        stage_order=1,
        duration_months=18,
        status='COMPLETED'
    )
    db.add(stage1)
    
    stage2 = TimelineStage(
        committed_timeline_id=timeline.id,
        title='Research and Publications',
        stage_order=2,
        duration_months=30,
        status='COMPLETED'
    )
    db.add(stage2)
    
    # Stage 3: Dissertation Writing (IN PROGRESS)
    stage3 = TimelineStage(
        id=uuid.UUID('33333333-3333-3333-3333-333333333334'),
        committed_timeline_id=timeline.id,
        title='Dissertation Writing and Job Search',
        description='Write dissertation and secure postdoc/faculty position',
        stage_order=3,
        duration_months=12,
        status='IN_PROGRESS'
    )
    db.add(stage3)
    
    # Milestones for Stage 3 - Nearly complete
    m1 = TimelineMilestone(
        timeline_stage_id=stage3.id,
        title='Complete Chapter 1-3',
        milestone_order=1,
        target_date=date.today() - timedelta(days=120),
        actual_completion_date=date.today() - timedelta(days=115),
        is_completed=True,
        is_critical=True,
        status='COMPLETED'
    )
    db.add(m1)
    
    m2 = TimelineMilestone(
        timeline_stage_id=stage3.id,
        title='Complete Chapter 4-5',
        milestone_order=2,
        target_date=date.today() - timedelta(days=60),
        actual_completion_date=date.today() - timedelta(days=65),
        is_completed=True,
        is_critical=True,
        status='COMPLETED'
    )
    db.add(m2)
    
    m3 = TimelineMilestone(
        timeline_stage_id=stage3.id,
        title='Submit Job Applications',
        description='Apply to 15+ postdoc and faculty positions',
        milestone_order=3,
        target_date=date.today() - timedelta(days=30),
        actual_completion_date=date.today() - timedelta(days=25),
        is_completed=True,
        is_critical=True,
        status='COMPLETED'
    )
    db.add(m3)
    
    m4 = TimelineMilestone(
        id=uuid.UUID('33333333-3333-3333-3333-333333333335'),
        timeline_stage_id=stage3.id,
        title='Complete Full Dissertation Draft',
        milestone_order=4,
        target_date=date.today() + timedelta(days=30),
        is_completed=False,
        is_critical=True,
        status='IN_PROGRESS'
    )
    db.add(m4)
    
    m5 = TimelineMilestone(
        timeline_stage_id=stage3.id,
        title='Dissertation Defense',
        milestone_order=5,
        target_date=date.today() + timedelta(days=90),
        is_completed=False,
        is_critical=True,
        status='PENDING'
    )
    db.add(m5)
    
    m6 = TimelineMilestone(
        timeline_stage_id=stage3.id,
        title='Final Revisions and Submission',
        milestone_order=6,
        target_date=date.today() + timedelta(days=120),
        is_completed=False,
        is_critical=True,
        status='PENDING'
    )
    db.add(m6)
    
    # Progress Events
    event1 = ProgressEvent(
        user_id=elena.id,
        milestone_id=m3.id,
        event_type='MILESTONE_COMPLETED',
        title='Job Applications Submitted',
        description='Submitted 18 applications to top institutions',
        event_date=m3.actual_completion_date,
        impact_level='HIGH'
    )
    db.add(event1)
    
    event2 = ProgressEvent(
        user_id=elena.id,
        event_type='ACHIEVEMENT',
        title='First Job Interview!',
        description='Invited for faculty interview at University of Washington',
        event_date=date.today() - timedelta(days=10),
        impact_level='HIGH'
    )
    db.add(event2)
    
    event3 = ProgressEvent(
        user_id=elena.id,
        milestone_id=m4.id,
        event_type='PROGRESS_UPDATE',
        title='Dissertation Progress',
        description='90% complete with dissertation, final chapter in progress',
        event_date=date.today() - timedelta(days=2),
        impact_level='MEDIUM'
    )
    db.add(event3)
    
    # Journey Assessment (Recent, cautiously optimistic)
    assessment = JourneyAssessment(
        user_id=elena.id,
        assessment_date=datetime.now() - timedelta(days=2),
        assessment_type='self_assessment',
        overall_progress_rating=4.5,
        research_quality_rating=4.8,
        timeline_adherence_rating=4.3,
        strengths='Strong publication record, dissertation nearly complete, job interviews secured, clear finish line in sight',
        challenges='Balancing dissertation writing with job interviews, managing finishing anxiety, revisions taking longer than expected',
        action_items='Complete final chapter this week, prepare for defense presentation, respond to job offers',
        notes='Excited but anxious about finishing. Seeing light at end of tunnel!'
    )
    db.add(assessment)
    
    # Analytics Snapshot - Late Stage
    analytics_snapshot = AnalyticsSnapshot(
        id=uuid.UUID('33333333-9999-3333-3333-333333333333'),
        user_id=elena.id,
        timeline_version='1.0',
        summary_json={
            "timeline_id": str(timeline.id),
            "user_id": str(elena.id),
            "generated_at": datetime.now().isoformat(),
            "timeline_status": "on_track",
            "milestone_completion_percentage": 90.0,
            "total_milestones": 10,
            "completed_milestones": 9,
            "pending_milestones": 1,
            "total_delays": 2,
            "overdue_milestones": 0,
            "overdue_critical_milestones": 0,
            "average_delay_days": 15.0,
            "max_delay_days": 30,
            "latest_health_score": 4.5,
            "health_dimensions": {
                "momentum": 4.8,
                "clarity": 5.0,
                "support": 4.5,
                "confidence": 4.3,
                "work_life_balance": 3.5,
                "finishing_anxiety": 3.8
            },
            "longitudinal_summary": {
                "trend": "positive",
                "velocity": "excellent",
                "completion_forecast": "2026-05-15",
                "achievements": [
                    "3 papers published",
                    "dissertation 90% complete",
                    "job offers received"
                ]
            }
        }
    )
    db.add(analytics_snapshot)
    
    db.commit()
    print("✓ Late-stage PhD created: Elena Rodriguez")
    print("  - 4.5 years in, nearing completion")
    print("  - Dissertation 90% complete")
    print("  - Job interviews secured")
    print("  - Analytics: 90% complete, on track")


def main():
    """Run the complete demo data seeding"""
    print("="*60)
    print("PhD Timeline Intelligence Platform - Demo Data Seeder")
    print("="*60)
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Clear existing data (optional - comment out if you want to keep existing data)
        clear_all_data(db)
        
        # Create demo personas
        create_early_stage_phd(db)
        create_mid_stage_phd(db)
        create_late_stage_phd(db)
        
        print("\n" + "="*60)
        print("✓ Demo data successfully seeded!")
        print("="*60)
        print("\nDemo Users Created:")
        print("  1. Sarah Chen (Early-stage)")
        print("     Email: sarah.chen@university.edu")
        print("     Status: 6 months in, developing methodology")
        print()
        print("  2. Marcus Johnson (Mid-stage)")
        print("     Email: marcus.johnson@university.edu")
        print("     Status: 2.5 years in, some delays, paper accepted")
        print()
        print("  3. Elena Rodriguez (Late-stage)")
        print("     Email: elena.rodriguez@university.edu")
        print("     Status: 4.5 years in, dissertation 90% complete")
        print()
        print("Next Steps:")
        print("  - Start the backend server")
        print("  - Login with any of the demo user emails")
        print("  - Explore timelines, progress, and health assessments")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Error seeding data: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    main()
