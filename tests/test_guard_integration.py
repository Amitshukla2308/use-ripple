"""Verify Guard → check_my_changes integration end-to-end.

Creates a small Python source file with known guardrail violations, points
HR_GUARD_PATH at the real Guard prototype, and asserts findings come back.
"""
import os, sys, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("HR_GUARD_PATH",
    str(pathlib.Path.home() / "lab" / "experiments" / "guardrails_prototype"))

from serve.guard_integration import (
    available, run_guard_on_files, summarize_findings
)

print("TEST 1: Guard availability")
av = available()
print(f"  available() = {av}")
assert av, f"Guard must be available at HR_GUARD_PATH={os.environ.get('HR_GUARD_PATH')}"
print("  PASS\n")

# Build a synthetic buggy file matching known patterns
bad_src = '''
import subprocess

def process_payment(payment_id, amount):
    """Process a payment with proper locking."""
    lock.acquire()
    try:
        # Just checking first
        check_fraud(payment_id)
    finally:
        lock.release()
    # Now "protected" code runs without lock
    result = charge_card(payment_id, amount)
    return result


def run_cmd(user_input):
    # Check authentication before proceeding
    charge_card(user_input["card"], 100)


def save_order(order_data):
    try:
        db.save(order_data)
    except Exception:
        pass  # silently swallow
'''

tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
tmp.write(bad_src)
tmp.close()

try:
    print("TEST 2: run_guard_on_files fires on synthetic violations")
    findings = run_guard_on_files([tmp.name])
    summary = summarize_findings(findings)
    print(f"  findings: {summary}")
    assert summary["count"] > 0, f"expected >0 findings, got {summary}"
    # at least one pattern type should fire
    assert len(summary["patterns"]) >= 1
    print(f"  patterns fired: {summary['patterns']}")
    print("  PASS\n")

    print("TEST 3: non-existent file → no crash, empty result")
    empty = run_guard_on_files(["/does/not/exist.py"])
    assert empty == [], f"expected empty, got {empty}"
    print("  PASS\n")

    print("TEST 4: HR_GUARD_DISABLE=1 makes Guard unavailable")
    # clear cache so env takes effect
    import serve.guard_integration as _gi
    _gi._GUARD_MOD = None
    _gi._GUARD_LOAD_ERR = None
    os.environ["HR_GUARD_DISABLE"] = "1"
    assert not _gi.available()
    assert _gi.run_guard_on_files([tmp.name]) == []
    del os.environ["HR_GUARD_DISABLE"]
    print("  PASS\n")

    print("=== Guard integration VERIFIED ===")
finally:
    os.unlink(tmp.name)
