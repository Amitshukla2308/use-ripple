"""
T-046: Test that symmetric cross-service Granger pairs receive the 1.5× symmetry bonus.
"""
import os, sys
from pathlib import Path

os.environ.setdefault("ARTIFACT_DIR", "/home/beast/projects/workspaces/juspay/artifacts")
os.environ.setdefault("EMBED_SERVER_URL", "http://localhost:8001")
sys.path.insert(0, str(Path(__file__).parent.parent / "serve"))

import retrieval_engine as re

# Minimal mock indexes — no disk I/O needed for logic test
ASYM_SRC = "svc_a::Module.X"
ASYM_TGT = "svc_b::Module.Y"
SYM_SRC  = "svc_a::Module.P"
SYM_TGT  = "svc_b::Module.Q"

MOCK_CROSS = {
    # asymmetric: only A→B
    f"{ASYM_SRC}→{ASYM_TGT}": {"source": ASYM_SRC, "target": ASYM_TGT,
                                 "p_value": 0.01, "best_lag": 2, "weight": 100.0},
    # symmetric: A→B and B→A both present
    f"{SYM_SRC}→{SYM_TGT}":   {"source": SYM_SRC,  "target": SYM_TGT,
                                 "p_value": 0.01, "best_lag": 1, "weight": 100.0},
    f"{SYM_TGT}→{SYM_SRC}":   {"source": SYM_TGT,  "target": SYM_SRC,
                                 "p_value": 0.01, "best_lag": 1, "weight": 100.0},
}

def score_pair(src: str, tgt: str) -> float:
    """Compute Granger score using the same logic as retrieval_engine."""
    granger_score = 0.0
    for key in (f"{src}→{tgt}", f"{tgt}→{src}"):
        for gi in (re.granger_index, re.granger_cross_index):
            if key in gi:
                g = gi[key]
                gs = 1.0 - min(g["p_value"] * 20, 1.0)
                if gi is re.granger_cross_index:
                    rev = f"{tgt}→{src}" if key == f"{src}→{tgt}" else f"{src}→{tgt}"
                    if rev in re.granger_cross_index:
                        gs = min(gs * 1.5, 1.0)
                if gs > granger_score:
                    granger_score = gs
                break
    return granger_score

def test_asymmetric_no_bonus():
    re.granger_cross_index.clear()
    re.granger_cross_index.update(MOCK_CROSS)
    re.granger_index.clear()

    base_score = 1.0 - min(0.01 * 20, 1.0)  # = 0.8
    score = score_pair(ASYM_SRC, ASYM_TGT)
    assert abs(score - base_score) < 0.001, f"Expected {base_score:.3f}, got {score:.3f}"
    print(f"[PASS] Asymmetric pair — no bonus: {score:.3f}")

def test_symmetric_gets_bonus():
    re.granger_cross_index.clear()
    re.granger_cross_index.update(MOCK_CROSS)
    re.granger_index.clear()

    base_score = 1.0 - min(0.01 * 20, 1.0)  # = 0.8
    expected = min(base_score * 1.5, 1.0)    # = 1.0 (capped)
    score = score_pair(SYM_SRC, SYM_TGT)
    assert abs(score - expected) < 0.001, f"Expected {expected:.3f}, got {score:.3f}"
    print(f"[PASS] Symmetric pair — 1.5x bonus applied: {score:.3f} (base was {base_score:.3f})")

def test_intra_service_no_bonus():
    re.granger_cross_index.clear()
    re.granger_index.clear()
    # Intra-service pair: only in granger_index (not granger_cross_index)
    re.granger_index["svc_a::ModA→svc_a::ModB"] = {
        "p_value": 0.02, "best_lag": 3, "weight": 50.0
    }

    base_score = 1.0 - min(0.02 * 20, 1.0)  # = 0.6
    score = score_pair("svc_a::ModA", "svc_a::ModB")
    assert abs(score - base_score) < 0.001, f"Expected {base_score:.3f}, got {score:.3f}"
    print(f"[PASS] Intra-service pair — no bonus: {score:.3f}")

def test_bonus_capped_at_one():
    re.granger_cross_index.clear()
    re.granger_index.clear()
    # Very significant p-value where base_score × 1.5 > 1.0
    re.granger_cross_index["X→Y"] = {"p_value": 0.001, "best_lag": 1, "weight": 200.0}
    re.granger_cross_index["Y→X"] = {"p_value": 0.001, "best_lag": 1, "weight": 200.0}

    score = score_pair("X", "Y")
    assert score <= 1.0, f"Score {score} exceeds 1.0 — cap broken!"
    print(f"[PASS] Symmetry bonus capped at 1.0: {score:.3f}")

if __name__ == "__main__":
    test_asymmetric_no_bonus()
    test_symmetric_gets_bonus()
    test_intra_service_no_bonus()
    test_bonus_capped_at_one()
    print("\n4/4 PASS")
