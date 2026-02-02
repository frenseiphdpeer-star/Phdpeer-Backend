# Seed with Orchestrators - Quick Reference

## Quick Start

```bash
cd backend
DATABASE_URL=postgresql://user:pass@localhost:5432/db \
SECRET_KEY=secret \
python seed_with_orchestrators.py
```

## What It Does

**Full workflow simulation using orchestrators:**

1. 📄 Document Upload → `DocumentService`
2. 📋 Baseline Extraction → `BaselineOrchestrator`
3. 🗓️ Timeline Generation → `TimelineOrchestrator`
4. ✅ Timeline Commitment → `TimelineOrchestrator`
5. 📈 Progress Logging → `ProgressService`
6. 🩺 Assessment → `PhDDoctorOrchestrator`
7. 📊 Analytics → `AnalyticsOrchestrator`

## Three Scenarios Created

| Scenario | User | Stage | Progress | Health | Status |
|----------|------|-------|----------|--------|--------|
| **1** | Sarah Chen | Early (6mo) | 40% | 4.2 | ✅ On track |
| **2** | Marcus Johnson | Mid (2.5y) | 62.5% | 3.2 | ⚠️ At risk |
| **3** | Elena Rodriguez | Late (4.5y) | 90% | 4.5 | ✅ Finishing |

## Demo User Emails

```
sarah.chen@stanford.edu        # Early-stage ML
marcus.johnson@mit.edu         # Mid-stage NLP (delays)
elena.rodriguez@berkeley.edu   # Late-stage CV (success)
```

## Key Benefits

✅ **Real workflows** - Same code as production
✅ **Decision traces** - Full audit trail
✅ **Idempotent** - Safe to re-run
✅ **Validated** - All business logic applied
✅ **Evidence** - Complete evidence bundles

## Data Generated (per scenario)

```
User → Document → Baseline → Timeline
  ├─ Stages (3-4)
  │   └─ Milestones (5-10)
  ├─ Progress Events (2-3)
  ├─ Journey Assessment
  ├─ Analytics Snapshot
  ├─ Decision Traces (6-8)
  └─ Evidence Bundles (6-8)
```

## Decision Traces Created

Each scenario generates ~7-8 traces:
- Document processing
- Baseline extraction
- Timeline generation
- Timeline commitment
- Progress logging
- Assessment submission
- Analytics generation

## Query Examples

```sql
-- View all decision traces
SELECT orchestrator, operation, status, created_at
FROM decision_traces
ORDER BY created_at DESC;

-- Check analytics
SELECT u.email, 
       (a.summary_json->>'milestone_completion_percentage')::float as completion,
       a.summary_json->>'timeline_status' as status
FROM analytics_snapshots a
JOIN users u ON a.user_id = u.id;

-- View evidence
SELECT dt.orchestrator, eb.evidence_type, eb.confidence
FROM evidence_bundles eb
JOIN decision_traces dt ON eb.decision_trace_id = dt.id;
```

## vs Direct Seed (`seed_demo_data.py`)

| Feature | Direct | Orchestrator |
|---------|--------|--------------|
| **Speed** | ⚡ Fast | Slower |
| **Validation** | ❌ None | ✅ Full |
| **Traces** | ❌ No | ✅ Yes |
| **Business Logic** | ❌ Bypassed | ✅ Executed |
| **Use Case** | Quick setup | Realistic testing |

## Troubleshooting

**Connection error?**
```bash
docker-compose up -d postgres
```

**Environment vars?**
```bash
export DATABASE_URL=postgresql://...
export SECRET_KEY=secret
```

**Re-run failed?**
- Safe to re-run (idempotent)
- Completed steps are skipped
- Only failed steps retry

## After Loading

1. **Start server**: `uvicorn app.main:app --reload`
2. **Login**: Use demo emails above
3. **Explore**: Timelines, analytics, traces
4. **Test**: API endpoints with real data

## Files

- `seed_with_orchestrators.py` - Main script
- `SEED_WITH_ORCHESTRATORS.md` - Full docs
- `SEED_WITH_ORCHESTRATORS_QUICK_REF.md` - This file

## Summary

Orchestrator-based seed loader that:
- Uses production code paths
- Generates decision traces
- Ensures data integrity
- Creates realistic demos

Perfect for: demos, testing, validation!
