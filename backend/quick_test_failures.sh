#!/bin/bash

# Quick Setup and Test Script for Failure Path Tests
# This script starts PostgreSQL via docker-compose and runs the tests

set -e

echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║               FAILURE PATH TESTS - QUICK SETUP & RUN                       ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Navigate to project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose not found"
    echo ""
    echo "Please install Docker and docker-compose, then run this script again."
    exit 1
fi

echo "Step 1: Starting PostgreSQL via docker-compose..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Start only PostgreSQL service
docker-compose up -d postgres

echo ""
echo "Step 2: Waiting for PostgreSQL to be ready..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Wait for PostgreSQL to be healthy
timeout=30
counter=0
while [ $counter -lt $timeout ]; do
    if docker-compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
        echo "✓ PostgreSQL is ready!"
        break
    fi
    counter=$((counter + 1))
    if [ $counter -eq $timeout ]; then
        echo "❌ PostgreSQL failed to start within ${timeout} seconds"
        echo ""
        echo "Check Docker logs: docker-compose logs postgres"
        exit 1
    fi
    sleep 1
    echo -n "."
done

echo ""
echo ""
echo "Step 3: Setting environment variables..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

export DATABASE_URL='postgresql://postgres:password@localhost:5432/phd_timeline_db'
export SECRET_KEY='test-secret-key-for-testing'

echo "✓ DATABASE_URL set"
echo "✓ SECRET_KEY set"
echo ""

echo "Step 4: Running failure path tests..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd backend

# Run the tests
python -m pytest tests/test_failure_paths.py -v -s --tb=short --color=yes

# Capture exit code
test_exit_code=$?

echo ""
if [ $test_exit_code -eq 0 ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ ALL TESTS PASSED!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Summary:"
    echo "  ✓ No partial writes on failures"
    echo "  ✓ All errors raised loudly"
    echo "  ✓ DecisionTrace audit trail preserved"
    echo "  ✓ Database rollback working"
    echo "  ✓ System remains consistent"
    echo ""
    echo "Cleanup: To stop PostgreSQL, run: docker-compose down"
    echo ""
else
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "❌ SOME TESTS FAILED"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Check the output above for details."
    echo ""
    echo "Debug tips:"
    echo "  • Check PostgreSQL logs: docker-compose logs postgres"
    echo "  • Verify DATABASE_URL: echo \$DATABASE_URL"
    echo "  • Run specific test: pytest tests/test_failure_paths.py::TestClass::test_name -v"
    echo ""
    exit 1
fi
