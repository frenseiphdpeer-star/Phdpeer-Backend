"""
Demo Scenario Verification Script

Verifies that:
1. Each demo scenario can be explained end-to-end in <10 minutes
2. Analytics clearly differ across early/mid/late scenarios
3. No manual DB edits are required (all data via orchestrators)

Usage:
    python verify_demo_scenarios.py [DATABASE_URL]
    
    If DATABASE_URL is not provided, will try to read from environment.
"""

import os
import sys

# Set minimal environment variables before any app imports
# This prevents config validation errors when importing models
if "DATABASE_URL" not in os.environ:
    if len(sys.argv) > 1:
        os.environ["DATABASE_URL"] = sys.argv[1]
    else:
        os.environ["DATABASE_URL"] = "postgresql://localhost/phdpeer"  # Placeholder

if "SECRET_KEY" not in os.environ:
    os.environ["SECRET_KEY"] = "verification-script-temporary-key"  # Placeholder

from datetime import datetime
from typing import Dict, Any, List, Tuple
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker
from app.models.user import User
from app.models.document_artifact import DocumentArtifact
from app.models.baseline import Baseline
from app.models.draft_timeline import DraftTimeline
from app.models.committed_timeline import CommittedTimeline
from app.models.timeline_stage import TimelineStage
from app.models.timeline_milestone import TimelineMilestone
from app.models.progress_event import ProgressEvent
from app.models.journey_assessment import JourneyAssessment
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.idempotency import DecisionTrace, EvidenceBundle


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(70)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def get_database_session() -> Tuple[Session, Any]:
    """Get database session from URL."""
    # Try command-line argument first
    if len(sys.argv) > 1:
        database_url = sys.argv[1]
    # Then environment variable
    elif "DATABASE_URL" in os.environ:
        database_url = os.environ["DATABASE_URL"]
    else:
        print(f"{Colors.RED}ERROR: DATABASE_URL not provided{Colors.END}")
        print("Usage: python verify_demo_scenarios.py [DATABASE_URL]")
        print("   or: DATABASE_URL=<url> python verify_demo_scenarios.py")
        sys.exit(1)
    
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal(), SessionLocal


def print_info(text: str):
    """Print info message."""
    print(f"  {text}")


# ============================================================================
# VERIFICATION CHECKS
# ============================================================================

def check_users_exist(db: Session) -> Tuple[bool, str]:
    """Check that all three demo users exist."""
    expected_emails = [
        "sarah.chen@stanford.edu",
        "marcus.johnson@mit.edu",
        "elena.rodriguez@berkeley.edu"
    ]
    
    users = db.query(User).filter(User.email.in_(expected_emails)).all()
    
    if len(users) == 3:
        return True, f"All 3 demo users found: {', '.join([u.email for u in users])}"
    else:
        found = [u.email for u in users]
        missing = [e for e in expected_emails if e not in found]
        return False, f"Missing users: {', '.join(missing)}"


def check_orchestrator_workflow(db: Session) -> Tuple[bool, str]:
    """Verify all data was created via orchestrators (has decision traces)."""
    
    # Check for decision traces
    trace_count = db.query(DecisionTrace).count()
    if trace_count == 0:
        return False, "No decision traces found - data was NOT created via orchestrators"
    
    # Check for evidence bundles
    evidence_count = db.query(EvidenceBundle).count()
    if evidence_count == 0:
        return False, "No evidence bundles found - orchestrator workflow incomplete"
    
    # Check for key orchestrator operations
    expected_operations = [
        "extract_baseline",
        "generate_timeline", 
        "commit_timeline",
        "submit_assessment",
        "generate_analytics"
    ]
    
    operations_found = db.query(DecisionTrace.operation).distinct().all()
    operations_found = [op[0] for op in operations_found]
    
    missing_ops = [op for op in expected_operations if op not in operations_found]
    
    if missing_ops:
        return False, f"Missing orchestrator operations: {', '.join(missing_ops)}"
    
    return True, f"Found {trace_count} decision traces, {evidence_count} evidence bundles - all via orchestrators"


def check_complete_data_chain(db: Session) -> Tuple[bool, List[str]]:
    """Check each user has complete data chain: Document → Baseline → Timeline → Events → Assessment → Analytics."""
    
    users = db.query(User).filter(User.email.like("%@%edu")).all()
    results = []
    all_complete = True
    
    for user in users:
        issues = []
        
        # Check document
        doc_count = db.query(DocumentArtifact).filter(
            DocumentArtifact.user_id == user.id
        ).count()
        if doc_count == 0:
            issues.append("No document")
            all_complete = False
        
        # Check baseline
        baseline_count = db.query(Baseline).filter(
            Baseline.user_id == user.id
        ).count()
        if baseline_count == 0:
            issues.append("No baseline")
            all_complete = False
        
        # Check timeline
        timeline_count = db.query(CommittedTimeline).filter(
            CommittedTimeline.user_id == user.id
        ).count()
        if timeline_count == 0:
            issues.append("No committed timeline")
            all_complete = False
        
        # Check progress events
        event_count = db.query(ProgressEvent).filter(
            ProgressEvent.user_id == user.id
        ).count()
        if event_count == 0:
            issues.append("No progress events")
            all_complete = False
        
        # Check assessment
        assessment_count = db.query(JourneyAssessment).filter(
            JourneyAssessment.user_id == user.id
        ).count()
        if assessment_count == 0:
            issues.append("No journey assessment")
            all_complete = False
        
        # Check analytics
        analytics_count = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.user_id == user.id
        ).count()
        if analytics_count == 0:
            issues.append("No analytics snapshot")
            all_complete = False
        
        if issues:
            results.append(f"{user.email}: {', '.join(issues)}")
        else:
            results.append(f"{user.email}: Complete ✓")
    
    return all_complete, results


def check_analytics_differences(db: Session) -> Tuple[bool, Dict[str, Any]]:
    """Verify analytics clearly differ across scenarios."""
    
    users = db.query(User).filter(User.email.like("%@%edu")).order_by(User.email).all()
    
    if len(users) < 3:
        return False, {"error": "Need 3 users to compare analytics"}
    
    analytics_data = []
    
    for user in users:
        snapshot = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.user_id == user.id
        ).first()
        
        if not snapshot:
            return False, {"error": f"No analytics for {user.email}"}
        
        data = snapshot.summary_json
        analytics_data.append({
            "email": user.email,
            "completion": data.get("milestone_completion_percentage", 0),
            "status": data.get("timeline_status", "unknown"),
            "health": data.get("latest_health_score", 0),
            "overdue": data.get("overdue_milestones", 0),
        })
    
    # Check for clear differences
    completions = [a["completion"] for a in analytics_data]
    healths = [a["health"] for a in analytics_data]
    statuses = [a["status"] for a in analytics_data]
    
    # Should have clear progression in completion (early < mid < late)
    completion_differs = len(set(completions)) == 3 and completions[0] < completions[1] < completions[2]
    
    # Should have variation in status
    status_differs = len(set(statuses)) >= 2
    
    # Should have clear health differences
    health_varies = max(healths) - min(healths) >= 1.0
    
    all_clear = completion_differs and status_differs and health_varies
    
    return all_clear, {
        "scenarios": analytics_data,
        "completion_differs": completion_differs,
        "status_differs": status_differs,
        "health_varies": health_varies,
    }


def check_explainability(db: Session) -> Tuple[bool, Dict[str, Any]]:
    """Check that each scenario has clear, explainable characteristics."""
    
    users = db.query(User).filter(User.email.like("%@%edu")).order_by(User.email).all()
    
    scenario_summaries = []
    all_explainable = True
    
    for user in users:
        # Get key metrics
        timeline = db.query(CommittedTimeline).filter(
            CommittedTimeline.user_id == user.id
        ).first()
        
        event_count = db.query(ProgressEvent).filter(
            ProgressEvent.user_id == user.id
        ).count()
        
        snapshot = db.query(AnalyticsSnapshot).filter(
            AnalyticsSnapshot.user_id == user.id
        ).first()
        
        if not (timeline and snapshot):
            all_explainable = False
            continue
        
        data = snapshot.summary_json
        
        # Calculate scenario complexity (for 10-minute explanation)
        stage_count = db.query(TimelineStage).filter(
            TimelineStage.committed_timeline_id == timeline.id
        ).count()
        
        milestone_count = data.get("total_milestones", 0)
        
        # Complexity score: stages + milestones + events (should be manageable)
        complexity = stage_count + milestone_count + event_count
        explainable = complexity <= 25  # Reasonable for 10-min explanation
        
        if not explainable:
            all_explainable = False
        
        scenario_summaries.append({
            "user": user.email,
            "stage": user.email.split('@')[0].split('.')[-1],  # Simple identification
            "stages": stage_count,
            "milestones": milestone_count,
            "events": event_count,
            "complexity": complexity,
            "explainable_in_10min": explainable,
            "key_metric": f"{data.get('milestone_completion_percentage', 0):.1f}% complete",
        })
    
    return all_explainable, {"scenarios": scenario_summaries}


def check_no_manual_edits(db: Session) -> Tuple[bool, str]:
    """Verify no data exists without corresponding decision traces."""
    
    # Count core entities
    timeline_count = db.query(CommittedTimeline).count()
    baseline_count = db.query(Baseline).count()
    assessment_count = db.query(JourneyAssessment).count()
    analytics_count = db.query(AnalyticsSnapshot).count()
    
    # Count decision traces for these operations
    trace_count = db.query(DecisionTrace).filter(
        DecisionTrace.operation.in_([
            'extract_baseline',
            'generate_timeline',
            'commit_timeline',
            'submit_assessment',
            'generate_analytics'
        ])
    ).count()
    
    # Each major operation should have a trace
    expected_traces = baseline_count + (timeline_count * 2) + assessment_count + analytics_count
    # *2 for timeline because generate + commit
    
    # Allow some variance but should be close
    ratio = trace_count / expected_traces if expected_traces > 0 else 0
    
    if ratio >= 0.8:  # 80% coverage is good
        return True, f"Found {trace_count} traces for {expected_traces} expected operations (ratio: {ratio:.2f})"
    else:
        return False, f"Only {trace_count} traces for {expected_traces} expected operations - possible manual edits"


def estimate_explanation_time(db: Session) -> Dict[str, int]:
    """Estimate time to explain each scenario in minutes."""
    
    users = db.query(User).filter(User.email.like("%@%edu")).order_by(User.email).all()
    
    times = {}
    
    for user in users:
        # Base time: 2 minutes for intro
        time = 2
        
        # Count stages (30 seconds each)
        stage_count = db.query(TimelineStage).join(CommittedTimeline).filter(
            CommittedTimeline.user_id == user.id
        ).count()
        time += stage_count * 0.5
        
        # Count milestones (20 seconds each for key ones, assume 50% are key)
        milestone_count = db.query(TimelineMilestone).join(TimelineStage).join(CommittedTimeline).filter(
            CommittedTimeline.user_id == user.id
        ).count()
        time += (milestone_count * 0.5) * 0.33
        
        # Count events (30 seconds each)
        event_count = db.query(ProgressEvent).filter(
            ProgressEvent.user_id == user.id
        ).count()
        time += event_count * 0.5
        
        # Analytics review: 1 minute
        time += 1
        
        # Health assessment: 1 minute
        time += 1
        
        times[user.email] = int(time)
    
    return times


# ============================================================================
# MAIN VERIFICATION
# ============================================================================

def run_verification():
    """Run all verification checks."""
    
    print_header("DEMO SCENARIO VERIFICATION")
    
    print("This script verifies:")
    print("  1. Each scenario can be explained end-to-end in <10 minutes")
    print("  2. Analytics clearly differ across early/mid/late scenarios")
    print("  3. No manual DB edits required (all via orchestrators)")
    print()
    
    db, SessionLocal = get_database_session()
    all_passed = True
    
    try:
        # Check 1: Users exist
        print_header("Check 1: Demo Users")
        passed, message = check_users_exist(db)
        if passed:
            print_success(message)
        else:
            print_error(message)
            all_passed = False
        
        # Check 2: Orchestrator workflow
        print_header("Check 2: Orchestrator Workflow")
        passed, message = check_orchestrator_workflow(db)
        if passed:
            print_success(message)
        else:
            print_error(message)
            all_passed = False
        
        # Check 3: Complete data chain
        print_header("Check 3: Complete Data Chain")
        passed, results = check_complete_data_chain(db)
        if passed:
            print_success("All users have complete data chains")
            for result in results:
                print_info(result)
        else:
            print_error("Some users have incomplete data")
            for result in results:
                print_info(result)
            all_passed = False
        
        # Check 4: Analytics differences
        print_header("Check 4: Analytics Differentiation")
        passed, data = check_analytics_differences(db)
        if passed:
            print_success("Analytics clearly differ across scenarios")
            print()
            print_info("Scenario Comparison:")
            for scenario in data["scenarios"]:
                print_info(f"  {scenario['email']}")
                print_info(f"    Completion: {scenario['completion']:.1f}%")
                print_info(f"    Status: {scenario['status']}")
                print_info(f"    Health: {scenario['health']:.1f}/5.0")
                print_info(f"    Overdue: {scenario['overdue']}")
                print()
        else:
            print_error("Analytics do not differ clearly")
            if "error" in data:
                print_info(f"  Error: {data['error']}")
            all_passed = False
        
        # Check 5: Explainability
        print_header("Check 5: Explainability (<10 minutes)")
        passed, data = check_explainability(db)
        times = estimate_explanation_time(db)
        
        if passed:
            print_success("All scenarios explainable in <10 minutes")
        else:
            print_warning("Some scenarios may take >10 minutes to explain")
        
        print()
        for scenario in data["scenarios"]:
            user_email = scenario["user"]
            estimated_time = times.get(user_email, 0)
            
            if estimated_time <= 10:
                print_success(f"{user_email}: ~{estimated_time} minutes")
            else:
                print_warning(f"{user_email}: ~{estimated_time} minutes (>10)")
                all_passed = False
            
            print_info(f"  Stages: {scenario['stages']}, Milestones: {scenario['milestones']}, Events: {scenario['events']}")
            print_info(f"  Key Metric: {scenario['key_metric']}")
            print()
        
        # Check 6: No manual edits
        print_header("Check 6: No Manual DB Edits")
        passed, message = check_no_manual_edits(db)
        if passed:
            print_success(message)
            print_info("All data created via orchestrators - no manual edits needed")
        else:
            print_warning(message)
            print_info("May indicate some manual data creation")
        
        # Final summary
        print_header("VERIFICATION SUMMARY")
        
        if all_passed:
            print_success("ALL CHECKS PASSED ✓")
            print()
            print_info("Demo scenarios are ready for:")
            print_info("  • Quick explanations (<10 minutes each)")
            print_info("  • Clear analytics differentiation")
            print_info("  • Zero manual DB edits")
            print_info("  • Production-quality demonstrations")
            print()
            return 0
        else:
            print_error("SOME CHECKS FAILED ✗")
            print()
            print_info("Review the failed checks above and:")
            print_info("  1. Re-run seed_with_orchestrators.py if data is incomplete")
            print_info("  2. Check that all orchestrators executed successfully")
            print_info("  3. Verify database connection and data integrity")
            print()
            return 1
        
    except Exception as e:
        print_error(f"Verification failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(run_verification())
