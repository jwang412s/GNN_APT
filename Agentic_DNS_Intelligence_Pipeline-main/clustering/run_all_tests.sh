#!/bin/bash

echo "【Phase 2 Testing Suite】"
echo "=================================================================="

tests=(
    "tests/test_01_imports.py"
    "tests/test_02_config.py"
    "tests/test_03_data_loading.py"
    "tests/test_04_quality.py"
    "tests/test_05_integration.py"
    "tests/test_06_end_to_end.py"
)

passed=0
failed=0

for test in "${tests[@]}"; do
    echo ""
    echo "【Running $(basename $test)】"
    echo "=================================================================="
    
    if python3 "$test"; then
        ((passed++))
    else
        ((failed++))
    fi
done

echo ""
echo "=================================================================="
echo "【Test Summary】"
echo "Passed: $passed"
echo "Failed: $failed"
echo "Total:  $((passed + failed))"
echo "=================================================================="

if [ $failed -eq 0 ]; then
    echo "✅ All tests passed!"
    exit 0
else
    echo "❌ Some tests failed"
    exit 1
fi

