# Demo Scenarios Quick Reference

## Three PhD Stages with Complete Data

### 1. Early-Stage: Sarah Chen (Stanford ML)
**Status**: 6 months in | **Progress**: 40% | **Health**: 4.2/5.0

```
UUID Prefix: 11111111-*
Email: sarah.chen@university.edu
Timeline Version: 1.0
```

**Data Included**:
- ✅ User, Document, Baseline
- ✅ DraftTimeline + CommittedTimeline
- ✅ 4 Stages (1 completed, 1 in progress, 2 pending)
- ✅ 5 Milestones (2 completed, 3 pending)
- ✅ 2 Progress Events (course completion, research questions)
- ✅ 1 Journey Assessment (positive, high confidence)
- ✅ Analytics Snapshot (on track, good momentum)

**Key Characteristics**:
- Strong foundation
- Clear direction
- Minor delay (10 days)
- High motivation

---

### 2. Mid-Stage: Marcus Johnson (MIT NLP)
**Status**: 2.5 years in | **Progress**: 62.5% | **Health**: 3.2/5.0 ⚠️

```
UUID Prefix: 22222222-*
Email: marcus.johnson@university.edu
Timeline Version: 2.0 (revised)
```

**Data Included**:
- ✅ User, Document, Baseline
- ✅ DraftTimeline + CommittedTimeline (revised)
- ✅ 4 Stages (2 completed, 1 in progress, 1 pending)
- ✅ 8 Milestones (5 completed, 1 overdue, 2 pending)
- ✅ 3 Progress Events (quals passed, paper accepted, delays)
- ✅ 1 Journey Assessment (mixed, burnout indicators)
- ✅ Analytics Snapshot (at risk, intervention needed)

**Key Characteristics**:
- Research quality good
- Timeline slippage
- 1 critical overdue (60 days)
- Burnout risk

---

### 3. Late-Stage: Elena Rodriguez (Berkeley CV)
**Status**: 4.5 years in | **Progress**: 90% | **Health**: 4.5/5.0

```
UUID Prefix: 33333333-*
Email: elena.rodriguez@university.edu
Timeline Version: 3.0 (final year)
```

**Data Included**:
- ✅ User, Document, Baseline
- ✅ DraftTimeline + CommittedTimeline (3rd revision)
- ✅ 3 Stages (2 completed, 1 in progress)
- ✅ 10 Milestones (9 completed, 1 in progress)
- ✅ 3 Progress Events (publications, job interviews, dissertation)
- ✅ 1 Journey Assessment (excellent, finishing anxiety)
- ✅ Analytics Snapshot (on track, strong finish)

**Key Characteristics**:
- 3 papers published
- Job offers received
- Dissertation 90% done
- 30 days to defense

---

## Quick Seed Command

```bash
# From backend directory
cd /path/to/Phdpeer-Backend/backend

# Set environment variables and run
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname \
SECRET_KEY=your-secret-key \
python seed_demo_data.py
```

## Data Structure Summary

```
Each Scenario Contains:
├── User (1)
├── DocumentArtifact (1) - baseline document
├── Baseline (1) - extracted requirements
├── DraftTimeline (1) - structured plan
├── CommittedTimeline (1) - active version
│   └── TimelineStages (3-4)
│       └── TimelineMilestones (5-10 total)
│           └── ProgressEvents (linked)
├── JourneyAssessment (1) - self-assessment
└── AnalyticsSnapshot (1) - aggregated metrics
```

## Analytics Comparison

| Metric | Sarah (Early) | Marcus (Mid) | Elena (Late) |
|--------|---------------|--------------|--------------|
| **Completion %** | 40% | 62.5% | 90% |
| **Status** | On Track | At Risk ⚠️ | On Track |
| **Health Score** | 4.2 | 3.2 | 4.5 |
| **Overdue** | 0 | 1 critical | 0 |
| **Avg Delay** | 10 days | 45 days | 15 days |
| **Momentum** | 4.5 | 2.5 | 4.8 |

## Use Cases by Scenario

### Sarah (Early) - Good for:
- ✅ Onboarding demos
- ✅ Timeline creation flows
- ✅ Early progress tracking
- ✅ Positive health trajectory
- ✅ Course completion

### Marcus (Mid) - Good for:
- ✅ Risk detection
- ✅ Intervention workflows
- ✅ Timeline revisions
- ✅ Burnout prevention
- ✅ Delay management

### Elena (Late) - Good for:
- ✅ Success stories
- ✅ Completion workflows
- ✅ Job search integration
- ✅ Defense preparation
- ✅ Publication tracking

## Files Modified

- `backend/seed_demo_data.py` - Main seed script
- `backend/DEMO_SCENARIOS.md` - Detailed documentation
- `backend/DEMO_SCENARIOS_QUICK_REF.md` - This file

## Next Steps

1. **Start Database**: `docker-compose up -d postgres`
2. **Run Seeder**: `python seed_demo_data.py`
3. **Verify**: Check database for 3 users
4. **Test**: Use demo emails to login/test features

## Database Verification Queries

```sql
-- Check users
SELECT email, full_name, institution FROM users;

-- Check timelines
SELECT u.email, ct.title, ct.version_number, ct.is_active
FROM committed_timelines ct
JOIN users u ON ct.user_id = u.id;

-- Check analytics
SELECT u.email, 
       (summary_json->>'milestone_completion_percentage')::float as completion,
       summary_json->>'timeline_status' as status,
       (summary_json->>'latest_health_score')::float as health
FROM analytics_snapshots a
JOIN users u ON a.user_id = u.id;
```

## Contact

For questions about demo scenarios, see full documentation in `DEMO_SCENARIOS.md`
