#!/bin/bash
# Run state transition validation tests

export DATABASE_URL="sqlite:///:memory:"
export SECRET_KEY="test-secret-key-for-testing-only"

cd "/Users/advaitdharmadhikari/Documents/Personal Projects/Phdpeer-Backend/backend"

echo "=================================================================================="
echo "PhD TRACKING SYSTEM - STATE TRANSITION VALIDATION"
echo "=================================================================================="
echo ""
echo "Running comprehensive state transition validation tests..."
echo ""

python -m pytest tests/test_state_transitions_validation.py -v -s --tb=short

exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo "=================================================================================="
    echo "✅ ALL STATE TRANSITION VALIDATIONS PASSED"
    echo "=================================================================================="
else
    echo "=================================================================================="
    echo "❌ SOME TESTS FAILED - See output above"
    echo "=================================================================================="
fi

exit $exit_code
