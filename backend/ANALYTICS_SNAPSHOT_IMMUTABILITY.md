# AnalyticsSnapshot Immutability and Versioning

## Overview

`AnalyticsSnapshot` is an **immutable** model that stores historical analytics data. This document describes the immutability guarantees, versioning behavior, and guards that enforce these rules.

## Core Principles

### 1. Immutability

**AnalyticsSnapshot records are IMMUTABLE once created.**

- ✅ **ALLOWED:** Create new snapshots
- ❌ **FORBIDDEN:** Update existing snapshots
- ❌ **FORBIDDEN:** Delete snapshots (they are historical records)

**Rationale:**
- Snapshots serve as audit trails of analytics state over time
- Historical data must be preserved for analysis and compliance
- Immutability prevents accidental data corruption
- Users can trust that historical snapshots reflect actual past state

### 2. Versioning

**Snapshots are versioned by `timeline_version` field.**

- Each snapshot is linked to a specific timeline version (e.g., "1.0", "2.0")
- Multiple snapshots can exist for the same `timeline_version`
- Each snapshot has a unique `id` and `created_at` timestamp
- Snapshots form a chronological history

**Example:**
```
Timeline Version 1.0:
  - Snapshot A (created_at: 2024-01-01)
  - Snapshot B (created_at: 2024-01-15)
  
Timeline Version 2.0:
  - Snapshot C (created_at: 2024-02-01)
  - Snapshot D (created_at: 2024-02-15)
```

### 3. Non-Overwriting

**Re-running analytics creates a NEW snapshot, not overwriting existing ones.**

When analytics are re-run:
1. A new snapshot is created with current timestamp
2. Previous snapshots remain unchanged
3. Historical snapshots are preserved
4. Users can compare snapshots over time

## Implementation

### Model Definition

```python
class AnalyticsSnapshot(Base, BaseModel):
    """Immutable analytics snapshot."""
    
    user_id = Column(UUID, ForeignKey("users.id"), nullable=False, index=True)
    timeline_version = Column(String(50), nullable=False, index=True)
    summary_json = Column(JSONB, nullable=False)
    # created_at inherited from BaseModel
```

### Snapshot Creation

Snapshots are created in `AnalyticsOrchestrator._persist_snapshot()`:

```python
def _persist_snapshot(self, user_id, timeline_version, analytics_summary):
    """Create immutable snapshot."""
    snapshot = AnalyticsSnapshot(
        user_id=user_id,
        timeline_version=timeline_version,
        summary_json=summary_json
    )
    self.db.add(snapshot)  # Only add, never update
    self.db.commit()
    return snapshot.id
```

**Key Points:**
- Only `db.add()` is used (creates new record)
- Never `db.query().update()` (would modify existing)
- Never `db.delete()` (would remove history)

### Version Extraction

Timeline version is extracted in `AnalyticsOrchestrator._extract_timeline_version()`:

```python
def _extract_timeline_version(self, committed_timeline):
    """Extract version from timeline."""
    # Try draft_timeline.version_number
    if committed_timeline.draft_timeline_id:
        draft = db.query(DraftTimeline).filter(...).first()
        if draft and draft.version_number:
            return draft.version_number
    
    # Try extract from notes (format: "Version X.Y")
    if committed_timeline.notes:
        match = re.search(r'Version\s+(\d+\.\d+)', committed_timeline.notes)
        if match:
            return match.group(1)
    
    # Default version
    return "1.0"
```

## Guards and Invariants

### Application-Level Guards

**File:** `app/utils/invariants.py`

#### 1. Prevent Snapshot Modifications

```python
check_analytics_snapshot_not_modified(db, snapshot_id)
```

**Raises:** `AnalyticsSnapshotMutationError` if modification attempted

**Usage:**
```python
# This should NEVER be done:
# snapshot.summary_json = {...}  # ❌ FORBIDDEN
# db.commit()

# Instead, create a new snapshot:
new_snapshot = AnalyticsSnapshot(...)  # ✅ CORRECT
db.add(new_snapshot)
db.commit()
```

#### 2. Prevent Snapshot Deletions

```python
check_analytics_snapshot_not_deleted(db, snapshot_id)
```

**Raises:** `AnalyticsSnapshotDeletionError` if deletion attempted

**Usage:**
```python
# This should NEVER be done:
# db.delete(snapshot)  # ❌ FORBIDDEN
# db.commit()

# Snapshots should be preserved as historical records
```

### Code Review Checklist

When reviewing code that touches AnalyticsSnapshot:

- [ ] ✅ Only creates new snapshots via `AnalyticsSnapshot(...)`
- [ ] ❌ Never modifies existing snapshots
- [ ] ❌ Never deletes snapshots
- [ ] ✅ Uses `timeline_version` for versioning
- [ ] ✅ Preserves historical data

## Testing

### Test Coverage

**File:** `tests/test_analytics_snapshot_immutability.py`

Tests verify:
1. **Model has no update methods**
2. **Critical fields are non-nullable** (data integrity)
3. **Snapshots are versioned** by `timeline_version`
4. **Re-running creates new snapshot** (non-overwriting)
5. **Original snapshots remain unchanged** (immutability)
6. **Multiple snapshots per version** (historical tracking)
7. **Snapshot history is preserved** across timeline changes
8. **Idempotent calls** use cached results (no duplicates)

### Running Tests

```bash
# Run all snapshot immutability tests
pytest tests/test_analytics_snapshot_immutability.py -v

# Run specific test
pytest tests/test_analytics_snapshot_immutability.py::TestAnalyticsSnapshotImmutability::test_snapshot_is_versioned_by_timeline_version -v
```

**Note:** Tests require PostgreSQL (models use PostgreSQL-specific UUID types).

## Query Patterns

### Get Latest Snapshot for Version

```python
latest_snapshot = db.query(AnalyticsSnapshot).filter(
    AnalyticsSnapshot.user_id == user_id,
    AnalyticsSnapshot.timeline_version == "1.0"
).order_by(AnalyticsSnapshot.created_at.desc()).first()
```

### Get All Snapshots for User

```python
snapshots = db.query(AnalyticsSnapshot).filter(
    AnalyticsSnapshot.user_id == user_id
).order_by(AnalyticsSnapshot.created_at.asc()).all()
```

### Get Snapshots by Version Range

```python
snapshots = db.query(AnalyticsSnapshot).filter(
    AnalyticsSnapshot.user_id == user_id,
    AnalyticsSnapshot.timeline_version.in_(["1.0", "2.0", "3.0"])
).order_by(AnalyticsSnapshot.created_at).all()
```

### Compare Snapshots Over Time

```python
# Get first and latest snapshot for comparison
snapshots = db.query(AnalyticsSnapshot).filter(
    AnalyticsSnapshot.user_id == user_id
).order_by(AnalyticsSnapshot.created_at).all()

if len(snapshots) >= 2:
    first = snapshots[0]
    latest = snapshots[-1]
    
    # Compare completion percentages
    first_completion = first.summary_json['milestone_completion_percentage']
    latest_completion = latest.summary_json['milestone_completion_percentage']
    improvement = latest_completion - first_completion
```

## Best Practices

### ✅ DO

- **Create new snapshots** when analytics are re-run
- **Use timeline_version** to organize snapshots
- **Preserve all snapshots** for historical analysis
- **Query by created_at** for chronological ordering
- **Use idempotency keys** to prevent duplicate snapshots

### ❌ DON'T

- **Never update** existing snapshot fields
- **Never delete** snapshots (they're historical records)
- **Don't reuse snapshot IDs** across different analytics runs
- **Don't store mutable data** in summary_json (use immutable structures)

## Future Enhancements

### Database-Level Constraints

Consider adding:

1. **Trigger to prevent updates:**
```sql
CREATE TRIGGER prevent_analytics_snapshot_update
BEFORE UPDATE ON analytics_snapshots
FOR EACH ROW
EXECUTE FUNCTION prevent_update();
```

2. **Trigger to prevent deletes:**
```sql
CREATE TRIGGER prevent_analytics_snapshot_delete
BEFORE DELETE ON analytics_snapshots
FOR EACH ROW
EXECUTE FUNCTION prevent_delete();
```

3. **Audit table for deletion attempts:**
```sql
CREATE TABLE analytics_snapshot_deletion_attempts (
    id UUID PRIMARY KEY,
    snapshot_id UUID NOT NULL,
    attempted_at TIMESTAMP NOT NULL,
    attempted_by TEXT
);
```

### Soft Deletion

If cleanup is needed, implement soft deletion:

```python
class AnalyticsSnapshot:
    is_archived = Column(Boolean, default=False)
    archived_at = Column(DateTime, nullable=True)
    
    # Add to queries: .filter(is_archived == False)
```

### Retention Policies

Implement automatic archival after N days:

```python
def archive_old_snapshots(days_threshold=365):
    """Archive snapshots older than threshold."""
    cutoff_date = date.today() - timedelta(days=days_threshold)
    
    db.query(AnalyticsSnapshot).filter(
        AnalyticsSnapshot.created_at < cutoff_date,
        AnalyticsSnapshot.is_archived == False
    ).update({"is_archived": True, "archived_at": datetime.utcnow()})
```

## Summary

- ✅ **Snapshots are immutable** (create new, never update)
- ✅ **Snapshots are versioned** by `timeline_version`
- ✅ **Re-running creates new snapshot** (non-overwriting)
- ✅ **Guards enforce immutability** at application level
- ✅ **Tests verify behavior** comprehensively

**Key Takeaway:** Treat AnalyticsSnapshot as a write-once, read-many model. Always create new snapshots rather than modifying existing ones.
