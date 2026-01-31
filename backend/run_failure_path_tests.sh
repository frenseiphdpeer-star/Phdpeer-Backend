#!/bin/bash

# Failure Path Test Runner
# Runs comprehensive failure path tests that verify system error handling

set -e  # Exit on error

echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║                    FAILURE PATH TEST SUITE                                 ║"
echo "║                                                                            ║"
echo "║  Tests that deliberately break the system to verify:                      ║"
echo "║  • No partial writes occur (atomicity)                                    ║"
echo "║  • No silent failures (errors are raised loudly)                          ║"
echo "║  • DecisionTrace audit trail preserved even on failures                   ║"
echo "║  • Database rollback happens correctly                                    ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Check if PostgreSQL DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "❌ ERROR: DATABASE_URL environment variable is not set"
    echo ""
    echo "These tests require PostgreSQL (SQLite is not compatible due to UUID types)"
    echo ""
    echo "Option 1: Use docker-compose to start PostgreSQL"
    echo "  cd /path/to/Phdpeer-Backend"
    echo "  docker-compose up -d postgres"
    echo "  export DATABASE_URL='postgresql://phdpeer:phdpeer123@localhost:5432/phdpeer_db'"
    echo ""
    echo "Option 2: Use existing PostgreSQL"
    echo "  export DATABASE_URL='postgresql://user:password@host:port/database'"
    echo ""
    echo "Then run this script again."
    exit 1
fi

# Check if it's PostgreSQL
if [[ ! "$DATABASE_URL" =~ ^postgresql ]]; then
    echo "❌ ERROR: DATABASE_URL must be PostgreSQL (found: $DATABASE_URL)"
    echo ""
    echo "SQLite cannot be used due to UUID type incompatibility."
    echo "Please set a PostgreSQL connection string."
    exit 1
fi

# Set SECRET_KEY if not already set
if [ -z "$SECRET_KEY" ]; then
    export SECRET_KEY="test-secret-key-for-testing"
    echo "ℹ️  Using default SECRET_KEY for testing"
fi

echo "✓ PostgreSQL DATABASE_URL detected"
echo "✓ Environment configured"
echo ""

# Display database info (mask password)
masked_url=$(echo "$DATABASE_URL" | sed -E 's/:([^@]+)@/:***@/')
echo "Database: $masked_url"
echo ""

# Run tests with detailed output
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Running failure path tests..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Run pytest with verbose output and stop on first failure for debugging
python -m pytest tests/test_failure_paths.py \
    -v \
    -s \
    --tb=short \
    --color=yes \
    -x

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ ALL FAILURE PATH TESTS PASSED"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Verified:"
    echo "  ✓ No partial writes on failures"
    echo "  ✓ All errors raised loudly (no silent failures)"
    echo "  ✓ DecisionTrace audit trail preserved"
    echo "  ✓ Database rollback working correctly"
    echo "  ✓ System remains consistent after failures"
    echo ""
else
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "❌ SOME TESTS FAILED"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Check the output above for details."
    exit 1
fi
