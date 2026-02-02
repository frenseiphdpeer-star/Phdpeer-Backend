# Orchestrator-Based Seed Data Loader

## Overview

`seed_with_orchestrators.py` is a comprehensive seed data loader that simulates real user workflows by going through all the proper orchestrators and services. Unlike direct database inserts, this script ensures all business logic, validation, decision tracing, and evidence bundling are executed.

## Key Differences from Direct Seed Script

| Feature | `seed_demo_data.py` | `seed_with_orchestrators.py` |
|---------|---------------------|------------------------------|
| **Approach** | Direct DB inserts | Orchestrator workflows |
| **Validation** | Manual | Automatic via orchestrators |
| **Decision Traces** | ❌ None | ✅ Full tracing |
| **Evidence Bundles** | ❌ None | ✅ Complete evidence |
| **Idempotency** | ❌ None | ✅ Guaranteed |
| **Business Logic** | ❌ Bypassed | ✅ Fully executed |
| **Realistic** | Data only | Complete workflows |

## What It Does

### Workflow Steps for Each Scenario

1. **Document Upload** → `DocumentService.process_document()`
   - Creates temporary document files
   - Processes through document service
   - Extracts text and metadata

2. **Baseline Extraction** → `BaselineOrchestrator.run()`
   - Analyzes document content
   - Extracts program requirements
   - Creates baseline record
   - Traces decision with evidence

3. **Timeline Generation** → `TimelineOrchestrator.generate_timeline()`
   - Generates structured timeline
   - Creates stages and milestones
   - Applies intelligence engine
   - Records generation decisions

4. **Timeline Commitment** → `TimelineOrchestrator.commit_timeline()`
   - Commits draft to active timeline
   - Versions timeline (1.0, 2.0, etc.)
   - Makes immutable snapshot
   - Traces commitment decision

5. **Progress Logging** → `ProgressService.log_progress_event()`
   - Records milestone completions
   - Logs achievements and challenges
   - Tracks delays and blockers
   - Documents impact levels

6. **PhD Doctor Assessment** → `PhDDoctorOrchestrator.submit_assessment()`
   - Processes questionnaire responses
   - Generates health assessment
   - Calculates dimension scores
   - Provides recommendations
   - Full decision tracing

7. **Analytics Generation** → `AnalyticsOrchestrator.run()`
   - Aggregates timeline data
   - Analyzes progress patterns
   - Calculates completion metrics
   - Generates health insights
   - Creates immutable snapshot
   - Validates read-only contract

## Three Demo Scenarios

### Scenario 1: Early-Stage PhD
**Sarah Chen - Stanford ML**

```
Duration: 6 months in
Progress: 40% complete
Status: On track
Health: 4.2/5.0
```

**Document**: Stanford ML program requirements
**Workflow**:
- ✅ Document uploaded and processed
- ✅ Baseline extracted (5-year program)
- ✅ Timeline generated (4 stages, 5 milestones)
- ✅ Timeline committed (version 1.0)
- ✅ 2 progress events logged
- ✅ Positive health assessment
- ✅ Analytics showing good momentum

**Decision Traces Created**:
- Baseline extraction decisions
- Timeline generation logic
- Commitment rationale
- Assessment analysis
- Analytics aggregation

### Scenario 2: Mid-Stage PhD
**Marcus Johnson - MIT NLP**

```
Duration: 2.5 years in
Progress: 62.5% complete
Status: At risk ⚠️
Health: 3.2/5.0
```

**Document**: MIT NLP research proposal
**Workflow**:
- ✅ Proposal processed
- ✅ Baseline extracted (5-year program)
- ✅ Timeline generated and committed (v2.0)
- ✅ 2 progress events (1 achievement, 1 challenge)
- ✅ Stressed assessment with burnout indicators
- ✅ Analytics showing risk and delays

**Key Features**:
- Paper acceptance logged
- 60-day experimental delay recorded
- Assessment shows work-life imbalance
- Analytics identifies intervention needs

### Scenario 3: Late-Stage PhD
**Elena Rodriguez - Berkeley CV**

```
Duration: 4.5 years in
Progress: 90% complete
Status: On track
Health: 4.5/5.0
```

**Document**: Dissertation progress report
**Workflow**:
- ✅ Dissertation report processed
- ✅ Baseline extracted
- ✅ Timeline generated and committed (v3.0)
- ✅ 3 progress events (publications, interviews, progress)
- ✅ Excellent assessment with normal finishing anxiety
- ✅ Analytics showing strong completion trajectory

**Achievements Logged**:
- 3 papers published (CVPR, ICCV, ECCV)
- Campus visits scheduled
- Dissertation 90% complete
- Defense scheduled

## Usage

### Prerequisites

```bash
# Ensure PostgreSQL is running
docker-compose up -d postgres

# Ensure virtual environment is activated
source venv/bin/activate
```

### Running the Script

```bash
cd backend
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname \
SECRET_KEY=your-secret-key \
python seed_with_orchestrators.py
```

### Interactive Prompts

```
Clear existing database data? (y/N): y
```

- **y**: Clears all data and starts fresh
- **N**: Keeps existing data and adds new scenarios

### Expected Output

```
============================================================
PhD TIMELINE INTELLIGENCE - ORCHESTRATOR-BASED SEED LOADER
============================================================

This script loads demo data by going through all orchestrators:
  1. Document upload and processing
  2. Baseline extraction (BaselineOrchestrator)
  3. Timeline generation (TimelineOrchestrator)
  4. Timeline commitment (TimelineOrchestrator)
  5. Progress event logging (ProgressService)
  6. PhD Doctor assessment (PhDDoctorOrchestrator)
  7. Analytics generation (AnalyticsOrchestrator)

============================================================
SCENARIO 1: EARLY-STAGE PhD (Sarah Chen)
============================================================

[1/7] Creating user...
✓ User created: sarah.chen@stanford.edu (ID: ...)

[2/7] Uploading baseline document...
✓ Document processed: PhD Program Requirements - Machine Learning
  - ID: ...
  - Type: PROGRAM_REQUIREMENTS
  - Extracted text: 1234 chars

[3/7] Extracting baseline...
✓ Baseline extracted:
  - Program: PhD in Computer Science
  - Duration: 60 months
  - Research Area: Reinforcement Learning and Multi-Agent Systems

[4/7] Generating timeline...
✓ Timeline generated:
  - Title: Sarah's PhD Journey - ML Research
  - Stages: 4
  - Total Milestones: 5

[5/7] Committing timeline...
✓ Timeline committed:
  - Version: 1.0
  - Committed Date: 2026-02-02
  - Active: True

[6/7] Adding progress events...
✓ Progress event 1: Milestone completed
  - Complete Core ML Courses
✓ Progress event 2: Research progress

[7/7] Submitting PhD Doctor assessment...
✓ Assessment submitted:
  - Health Score: 4.2
  - Status: healthy

[8/7] Generating analytics...
✓ Analytics generated:
  - Completion: 40.0%
  - Status: on_track
  - Health: 4.2/5.0

============================================================
✓ EARLY-STAGE SCENARIO COMPLETE
============================================================

... [similar output for mid and late stage]

============================================================
✓ ALL SCENARIOS LOADED SUCCESSFULLY
============================================================

Demo Users Created:

  Sarah Chen (Early)
    User ID: ...
    Timeline ID: ...

  Marcus Johnson (Mid)
    User ID: ...
    Timeline ID: ...

  Elena Rodriguez (Late)
    User ID: ...
    Timeline ID: ...

============================================================
NEXT STEPS
============================================================
  1. Start the backend server:
     uvicorn app.main:app --reload

  2. Login with demo user emails:
     - sarah.chen@stanford.edu
     - marcus.johnson@mit.edu
     - elena.rodriguez@berkeley.edu

  3. Explore the data:
     - View timelines and progress
     - Check analytics dashboards
     - Review decision traces
     - Examine health assessments

  4. Query decision traces:
     SELECT * FROM decision_traces ORDER BY created_at DESC;

  5. View analytics:
     SELECT * FROM analytics_snapshots;
============================================================
```

## Data Generated

### Per Scenario

```
User (1)
  └── DocumentArtifact (1)
       └── Baseline (1)
            └── DraftTimeline (1)
                 └── CommittedTimeline (1)
                      └── TimelineStage (3-4)
                           └── TimelineMilestone (5-10)
  └── ProgressEvent (2-3)
  └── JourneyAssessment (1)
  └── AnalyticsSnapshot (1)
  
+ DecisionTrace (6-8 per scenario)
+ EvidenceBundle (6-8 per scenario)
+ IdempotencyKey (7-8 per scenario)
```

### Total Across All Scenarios

- **Users**: 3
- **Documents**: 3
- **Baselines**: 3
- **Timelines**: 3 draft + 3 committed = 6
- **Stages**: ~10-12
- **Milestones**: ~20-25
- **Progress Events**: ~7-8
- **Assessments**: 3
- **Analytics Snapshots**: 3
- **Decision Traces**: ~20-25
- **Evidence Bundles**: ~20-25
- **Idempotency Keys**: ~20-25

## Decision Trace Examples

### Baseline Extraction

```json
{
  "orchestrator": "baseline_orchestrator",
  "operation": "extract_baseline",
  "status": "success",
  "decision_summary": "Extracted program requirements from document",
  "evidence": [
    {
      "type": "document_analyzed",
      "data": {
        "document_id": "...",
        "document_type": "PROGRAM_REQUIREMENTS",
        "text_length": 1234
      }
    },
    {
      "type": "baseline_created",
      "data": {
        "program_name": "PhD in Computer Science",
        "duration_months": 60
      }
    }
  ]
}
```

### Timeline Generation

```json
{
  "orchestrator": "timeline_orchestrator",
  "operation": "generate_timeline",
  "status": "success",
  "decision_summary": "Generated 4-stage timeline with 5 milestones",
  "evidence": [
    {
      "type": "baseline_loaded",
      "confidence": 1.0
    },
    {
      "type": "stages_generated",
      "data": {
        "stage_count": 4,
        "milestone_count": 5
      }
    }
  ]
}
```

### Analytics Generation

```json
{
  "orchestrator": "analytics_orchestrator",
  "operation": "generate_analytics",
  "status": "success",
  "decision_summary": "Aggregated timeline data and calculated metrics",
  "evidence": [
    {
      "type": "data_loaded",
      "data": {
        "progress_events_count": 2,
        "milestones_count": 5
      }
    },
    {
      "type": "analytics_aggregated",
      "data": {
        "timeline_status": "on_track",
        "completion_percentage": 40.0
      }
    }
  ]
}
```

## Validation

All orchestrators perform validation:

✅ **BaselineOrchestrator**
- Document exists and is accessible
- User owns document
- No duplicate baseline for same document
- Required fields extracted

✅ **TimelineOrchestrator**
- Baseline exists
- User owns baseline
- Timeline structure is valid
- Commitment validates draft exists
- No duplicate commits

✅ **PhDDoctorOrchestrator**
- Questionnaire responses complete
- User exists
- Assessment calculations valid
- Health scores in valid range

✅ **AnalyticsOrchestrator**
- Committed timeline exists
- User owns timeline
- Read-only contract enforced
- No upstream mutations
- Valid write targets only

## Benefits Over Direct Inserts

### 1. **Business Logic Execution**
- All validation rules applied
- All constraints checked
- All calculations performed
- All side effects triggered

### 2. **Decision Tracing**
- Complete audit trail
- Evidence-based decisions
- Reproducible workflows
- Debugging support

### 3. **Idempotency**
- Safe to re-run
- No duplicate data
- Consistent results
- Request ID tracking

### 4. **Data Integrity**
- Referential integrity maintained
- State transitions valid
- Immutability enforced
- Versioning correct

### 5. **Realistic Testing**
- Same code paths as production
- Same validation as users
- Same orchestration flow
- Same error handling

## Troubleshooting

### Database Connection Error
```
psycopg2.OperationalError: connection failed
```

**Solution**: Ensure PostgreSQL is running
```bash
docker-compose up -d postgres
```

### Missing Environment Variables
```
ValidationError: DATABASE_URL Field required
```

**Solution**: Set environment variables
```bash
export DATABASE_URL=postgresql://...
export SECRET_KEY=your-secret-key
```

### Orchestrator Errors

If an orchestrator fails, check:
1. Decision traces for debugging info
2. Evidence bundles for context
3. Error messages for specific issues
4. Database state for conflicts

### Re-running After Partial Failure

The script uses idempotency keys, so you can:
1. Fix the issue
2. Re-run the script
3. Already-completed steps will be skipped
4. Only failed steps will be retried

## Comparison with Direct Seed

### When to Use `seed_with_orchestrators.py`

✅ Testing end-to-end workflows
✅ Validating orchestrator logic
✅ Generating decision traces
✅ Creating realistic demo data
✅ Testing with production code paths

### When to Use `seed_demo_data.py`

✅ Quick database setup
✅ Known-good data states
✅ Performance testing (faster)
✅ Bypassing validation for tests
✅ Creating specific edge cases

## Next Steps After Loading

### 1. Explore Decision Traces
```sql
SELECT 
  orchestrator,
  operation,
  status,
  decision_summary,
  created_at
FROM decision_traces
ORDER BY created_at DESC
LIMIT 10;
```

### 2. View Evidence Bundles
```sql
SELECT 
  dt.orchestrator,
  eb.evidence_type,
  eb.data,
  eb.confidence
FROM evidence_bundles eb
JOIN decision_traces dt ON eb.decision_trace_id = dt.id
ORDER BY eb.created_at DESC;
```

### 3. Check Analytics
```sql
SELECT 
  u.email,
  (a.summary_json->>'milestone_completion_percentage')::float as completion,
  a.summary_json->>'timeline_status' as status,
  (a.summary_json->>'latest_health_score')::float as health
FROM analytics_snapshots a
JOIN users u ON a.user_id = u.id;
```

### 4. Test API Endpoints

```bash
# Get user timeline
curl http://localhost:8000/api/users/{user_id}/timeline

# Get analytics
curl http://localhost:8000/api/users/{user_id}/analytics

# Get decision traces
curl http://localhost:8000/api/decision-traces?user_id={user_id}
```

## Summary

`seed_with_orchestrators.py` provides a production-quality seed data loader that:
- ✅ Uses real orchestrator workflows
- ✅ Generates complete decision traces
- ✅ Ensures data integrity
- ✅ Validates all business logic
- ✅ Creates realistic demo scenarios
- ✅ Supports idempotent execution

Perfect for demos, testing, and validating the complete system architecture!
