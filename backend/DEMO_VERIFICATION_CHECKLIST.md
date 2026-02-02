# Demo Scenario Verification Checklist

## Quick Verification (Manual)

### ✅ 1. Explainability Check (<10 Minutes Per Scenario)

**Early-Stage (Sarah Chen):**
- [ ] Intro: New student, 6 months in (30 sec)
- [ ] Document: Program requirements uploaded (30 sec)
- [ ] Timeline: 4 stages, 5 milestones generated (2 min)
- [ ] Progress: 2 milestones completed (1 min)
- [ ] Status: 40% complete, on track (1 min)
- [ ] Health: 4.2/5.0, high momentum (1 min)
- [ ] Story: Strong start, minor delay, clear path (2 min)
- **Total: ~8 minutes** ✓

**Mid-Stage (Marcus Johnson):**
- [ ] Intro: Mid-program, 2.5 years in (30 sec)
- [ ] Situation: Paper accepted but experiments delayed (1 min)
- [ ] Timeline: Revised to v2.0, some overdue items (2 min)
- [ ] Progress: 62.5% complete, 1 critical delay (1 min)
- [ ] Status: At risk, burnout indicators (1 min)
- [ ] Health: 3.2/5.0, needs intervention (1 min)
- [ ] Story: Quality research vs timeline pressure (2 min)
- **Total: ~8.5 minutes** ✓

**Late-Stage (Elena Rodriguez):**
- [ ] Intro: Near completion, 4.5 years in (30 sec)
- [ ] Achievements: 3 papers, job offers (1 min)
- [ ] Timeline: v3.0, final year adjustments (1.5 min)
- [ ] Progress: 90% complete, defense scheduled (1 min)
- [ ] Status: On track for May completion (1 min)
- [ ] Health: 4.5/5.0, finishing strong (1 min)
- [ ] Story: Success trajectory, normal finishing anxiety (2 min)
- **Total: ~8 minutes** ✓

---

### 📊 2. Analytics Differentiation

**Completion Percentage:**
- [ ] Early (Sarah): ~40% ✓
- [ ] Mid (Marcus): ~62.5% ✓
- [ ] Late (Elena): ~90% ✓
- [ ] Clear progression: Low → Medium → High ✓

**Timeline Status:**
- [ ] Early: "on_track" ✓
- [ ] Mid: "at_risk" ⚠️ ✓
- [ ] Late: "on_track" ✓
- [ ] Variation shows different states ✓

**Health Score:**
- [ ] Early: ~4.2/5.0 (good) ✓
- [ ] Mid: ~3.2/5.0 (concerning) ⚠️ ✓
- [ ] Late: ~4.5/5.0 (excellent) ✓
- [ ] Range: >1.0 point difference ✓

**Overdue Milestones:**
- [ ] Early: 0 ✓
- [ ] Mid: 1+ (shows delays) ⚠️ ✓
- [ ] Late: 0 ✓
- [ ] Clear differentiation ✓

**Health Dimensions:**
- [ ] Early: High momentum (4.5), good clarity (4.0)
- [ ] Mid: Low momentum (2.5), poor work-life (2.0)
- [ ] Late: Excellent momentum (4.8), perfect clarity (5.0)
- [ ] Each scenario has distinct profile ✓

---

### 🔧 3. No Manual DB Edits Required

**Data Created Via Orchestrators:**
- [ ] DocumentService: All documents processed ✓
- [ ] BaselineOrchestrator: All baselines extracted ✓
- [ ] TimelineOrchestrator: All timelines generated & committed ✓
- [ ] ProgressService: All events logged ✓
- [ ] PhDDoctorOrchestrator: All assessments submitted ✓
- [ ] AnalyticsOrchestrator: All analytics generated ✓

**Decision Traces Present:**
- [ ] Baseline extraction traces exist (3) ✓
- [ ] Timeline generation traces exist (3) ✓
- [ ] Timeline commitment traces exist (3) ✓
- [ ] Assessment submission traces exist (3) ✓
- [ ] Analytics generation traces exist (3) ✓
- [ ] Total: ~20-25 decision traces ✓

**Evidence Bundles Present:**
- [ ] Each decision trace has evidence ✓
- [ ] Evidence includes confidence scores ✓
- [ ] Evidence shows data sources ✓

**Idempotency Keys:**
- [ ] Each orchestrator call has key ✓
- [ ] Keys prevent duplicate operations ✓
- [ ] Safe to re-run seed script ✓

---

## Automated Verification

### Run the Verification Script

```bash
cd backend
python verify_demo_scenarios.py
```

**Expected Output:**
```
============================================================
                 DEMO SCENARIO VERIFICATION                
============================================================

Check 1: Demo Users
✓ All 3 demo users found

Check 2: Orchestrator Workflow
✓ Found 20+ decision traces, 20+ evidence bundles

Check 3: Complete Data Chain
✓ All users have complete data chains

Check 4: Analytics Differentiation
✓ Analytics clearly differ across scenarios

Check 5: Explainability (<10 minutes)
✓ All scenarios explainable in <10 minutes

Check 6: No Manual DB Edits
✓ All data created via orchestrators

VERIFICATION SUMMARY
✓ ALL CHECKS PASSED
```

---

## Quick SQL Verification

### Check Analytics Differences

```sql
SELECT 
  u.email,
  (a.summary_json->>'milestone_completion_percentage')::float as completion,
  a.summary_json->>'timeline_status' as status,
  (a.summary_json->>'latest_health_score')::float as health,
  (a.summary_json->>'overdue_milestones')::int as overdue
FROM analytics_snapshots a
JOIN users u ON a.user_id = u.id
ORDER BY completion;
```

**Expected Result:**
```
sarah.chen@stanford.edu     | 40.0  | on_track | 4.2 | 0
marcus.johnson@mit.edu      | 62.5  | at_risk  | 3.2 | 1
elena.rodriguez@berkeley.edu| 90.0  | on_track | 4.5 | 0
```

### Check Decision Traces

```sql
SELECT 
  orchestrator,
  operation,
  COUNT(*) as count
FROM decision_traces
GROUP BY orchestrator, operation
ORDER BY orchestrator, operation;
```

**Expected Result:**
```
analytics_orchestrator  | generate_analytics    | 3
baseline_orchestrator   | extract_baseline      | 3
phd_doctor_orchestrator | submit_assessment     | 3
timeline_orchestrator   | commit_timeline       | 3
timeline_orchestrator   | generate_timeline     | 3
```

### Check Data Completeness

```sql
SELECT 
  u.email,
  COUNT(DISTINCT d.id) as documents,
  COUNT(DISTINCT b.id) as baselines,
  COUNT(DISTINCT ct.id) as timelines,
  COUNT(DISTINCT pe.id) as events,
  COUNT(DISTINCT ja.id) as assessments,
  COUNT(DISTINCT a.id) as analytics
FROM users u
LEFT JOIN document_artifacts d ON d.user_id = u.id
LEFT JOIN baselines b ON b.user_id = u.id
LEFT JOIN committed_timelines ct ON ct.user_id = u.id
LEFT JOIN progress_events pe ON pe.user_id = u.id
LEFT JOIN journey_assessments ja ON ja.user_id = u.id
LEFT JOIN analytics_snapshots a ON a.user_id = u.id
WHERE u.email LIKE '%@%edu'
GROUP BY u.email
ORDER BY u.email;
```

**Expected Result (each user should have):**
```
documents: 1
baselines: 1
timelines: 1
events: 2-3
assessments: 1
analytics: 1
```

---

## Manual Spot Check

### Scenario 1: Early-Stage (Sarah)

```bash
# Check user
SELECT email, full_name, institution FROM users 
WHERE email = 'sarah.chen@stanford.edu';

# Check completion
SELECT summary_json->>'milestone_completion_percentage' 
FROM analytics_snapshots a
JOIN users u ON a.user_id = u.id
WHERE u.email = 'sarah.chen@stanford.edu';

# Expected: ~40%
```

### Scenario 2: Mid-Stage (Marcus)

```bash
# Check delays
SELECT summary_json->>'overdue_milestones'
FROM analytics_snapshots a
JOIN users u ON a.user_id = u.id
WHERE u.email = 'marcus.johnson@mit.edu';

# Expected: 1 or more
```

### Scenario 3: Late-Stage (Elena)

```bash
# Check completion
SELECT summary_json->>'milestone_completion_percentage'
FROM analytics_snapshots a
JOIN users u ON a.user_id = u.id
WHERE u.email = 'elena.rodriguez@berkeley.edu';

# Expected: ~90%
```

---

## Troubleshooting

### ❌ Missing Users
**Problem**: Not all 3 users found
**Solution**: Re-run `seed_with_orchestrators.py`

### ❌ No Decision Traces
**Problem**: Data exists but no traces
**Solution**: Data was manually inserted. Clear DB and re-run orchestrator seed.

### ❌ Analytics Don't Differ
**Problem**: All scenarios show similar metrics
**Solution**: Check that different scenarios were actually created. Verify progress events.

### ⚠️ Explanation Takes >10 Minutes
**Problem**: Too much detail in scenario
**Solution**: Focus on high-level story, skip minor milestones in demo.

---

## Sign-Off Checklist

Before demo/presentation:

- [ ] Ran `verify_demo_scenarios.py` - all checks passed ✓
- [ ] Tested each scenario explanation - under 10 minutes ✓
- [ ] Verified analytics show clear differences ✓
- [ ] Confirmed all data via orchestrators (no manual edits) ✓
- [ ] Tested API endpoints with each user ✓
- [ ] Reviewed decision traces for completeness ✓
- [ ] Backend server starts without errors ✓
- [ ] Demo environment ready ✓

**Verified by:** _________________
**Date:** _________________
**Ready for Demo:** ✅ YES / ❌ NO
