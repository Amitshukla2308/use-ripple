# test_01_artifacts.py is a standalone integration script (uses sys.exit).
# Exclude it from pytest collection to prevent INTERNALERROR.
# Run it directly: python3 tests/test_01_artifacts.py
collect_ignore = [
    "test_01_artifacts.py",         # standalone script, uses sys.exit
    "bench_blast_radius_recall.py", # standalone benchmark, uses argparse
    "run_chat_eval.py",             # standalone eval script, uses argparse
    "test_06_auto_eval.py",         # standalone eval, uses argparse
    "test_04_retrieval_accuracy.py", # requires serve/demo_artifact (large data)
    "test_05_integration.py",        # requires serve/demo_artifact (large data)
]
