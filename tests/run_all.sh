#!/bin/bash
# run_all.sh — Run the full test suite in correct order.
#
# Tests are layered:
#   T1: Artifact integrity   (no services needed)
#   T2: Retrieval logic      (no services needed — import stubs)
#   T3: Canary functions     (no services, reads source files)
#   T4: Retrieval accuracy   (data loaded, no GPU)
#   T5: Integration          (requires embed_server:8001 + mcp_server:8002)
#   T6: Auto eval            (LLM-powered, requires LLM API key)
#
# Usage:
#   bash tests/run_all.sh                   # T1+T2+T3+T4+T5 (no LLM)
#   bash tests/run_all.sh --fast            # T1+T2+T3 only (no data load)
#   bash tests/run_all.sh --integration     # T4+T5 only
#   bash tests/run_all.sh --llm            # T1-T5 + T6 auto eval (needs LLM key)
#   bash tests/run_all.sh --mindmap        # also generate mindmap.html after tests
#
# Run from pipeline dir:
#   cd /home/beast/projects/mindmap/pipeline && bash tests/run_all.sh

set -eo pipefail

PY=$(command -v python3 || echo "python3")
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE_DIR="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

passed=0
failed=0
run_fast=false
run_integration_only=false
run_llm=false
run_mindmap=false

for arg in "$@"; do
    case "$arg" in
        --fast)        run_fast=true ;;
        --integration) run_integration_only=true ;;
        --llm)         run_llm=true ;;
        --mindmap)     run_mindmap=true ;;
    esac
done

run_test() {
    local name="$1"
    local file="$2"
    shift 2
    echo ""
    echo "════════════════════════════════════════════════════════"
    echo "  $name"
    echo "════════════════════════════════════════════════════════"
    if $PY "$PIPELINE_DIR/$file" "$@"; then
        echo -e "${GREEN}  PASSED: $name${NC}"
        passed=$((passed + 1))
    else
        echo -e "${RED}  FAILED: $name${NC}"
        failed=$((failed + 1))
    fi
}

cd "$PIPELINE_DIR"

if ! $run_integration_only; then
    run_test "T1: Artifact Integrity"   "tests/test_01_artifacts.py"
    run_test "T2: Retrieval Logic"      "tests/test_02_retrieval_logic.py"
    run_test "T3: Canary Functions"     "tests/test_03_canary.py"
fi

if ! $run_fast; then
    run_test "T4: Retrieval Accuracy"   "tests/test_04_retrieval_accuracy.py"
    run_test "T5: Integration"          "tests/test_05_integration.py"
fi

if $run_llm; then
    run_test "T6: Auto Eval (LLM)"      "tests/test_06_auto_eval.py"
fi

# ── Mindmap generation (not a test — always succeeds or warns) ──────────────
if $run_mindmap || $run_llm; then
    echo ""
    echo "════════════════════════════════════════════════════════"
    echo "  Mindmap: Generating visual graph..."
    echo "════════════════════════════════════════════════════════"
    if $PY "$PIPELINE_DIR/tools/generate_mindmap.py"; then
        echo -e "${CYAN}  Mindmap written → demo_artifact/mindmap.html${NC}"
    else
        echo -e "${RED}  Mindmap generation failed (non-blocking)${NC}"
    fi
fi

echo ""
echo "════════════════════════════════════════════════════════"
if [ "$failed" -eq 0 ]; then
    echo -e "${GREEN}  ALL TESTS PASSED: $passed/$((passed+failed))${NC}"
else
    echo -e "${RED}  FAILURES: $failed/$((passed+failed)) test suites failed${NC}"
    exit 1
fi
