"""T-045: bus_factor_warning in get_why_context."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import serve.retrieval_engine as re_mod


def _setup(owners, cc_neighbors):
    re_mod.ownership_index.clear()
    re_mod.cochange_index.clear()
    re_mod.ownership_index["test::Module"] = owners
    re_mod.cochange_index["test::Module"] = cc_neighbors


def test_warning_fires_solo_high_blast():
    """Single author (100%), blast_radius=10 → warning present."""
    _setup(
        [{"name": "Alice", "email": "a@x.com", "commits": 50}],
        [{"module": f"other_{i}", "weight": 5} for i in range(10)],
    )
    result = re_mod.get_why_context("test::Module")
    assert result["bus_factor_warning"] is not None
    bfw = result["bus_factor_warning"]
    assert bfw["dominant_author"] == "Alice"
    assert bfw["dominance_pct"] == 100
    assert bfw["blast_radius"] == 10


def test_warning_suppressed_shared_ownership():
    """Two authors split 60/40, blast_radius=10 → no warning (Gini < 0.90)."""
    _setup(
        [
            {"name": "Alice", "email": "a@x.com", "commits": 60},
            {"name": "Bob", "email": "b@x.com", "commits": 40},
        ],
        [{"module": f"other_{i}", "weight": 5} for i in range(10)],
    )
    result = re_mod.get_why_context("test::Module")
    assert result["bus_factor_warning"] is None


def test_warning_suppressed_low_blast():
    """Single author but blast_radius=3 (≤5) → no warning."""
    _setup(
        [{"name": "Alice", "email": "a@x.com", "commits": 100}],
        [{"module": f"other_{i}", "weight": 5} for i in range(3)],
    )
    result = re_mod.get_why_context("test::Module")
    assert result["bus_factor_warning"] is None


def test_warning_threshold_91pct():
    """91% concentration is above 90% threshold → warning fires."""
    _setup(
        [
            {"name": "Alice", "email": "a@x.com", "commits": 91},
            {"name": "Bob", "email": "b@x.com", "commits": 9},
        ],
        [{"module": f"other_{i}", "weight": 5} for i in range(8)],
    )
    result = re_mod.get_why_context("test::Module")
    assert result["bus_factor_warning"] is not None
    assert result["bus_factor_warning"]["dominance_pct"] == 91


def test_no_owners_no_warning():
    """No ownership data → no warning, no crash."""
    re_mod.ownership_index.clear()
    re_mod.cochange_index.clear()
    result = re_mod.get_why_context("ghost::Module")
    assert result["bus_factor_warning"] is None


if __name__ == "__main__":
    tests = [
        test_warning_fires_solo_high_blast,
        test_warning_suppressed_shared_ownership,
        test_warning_suppressed_low_blast,
        test_warning_threshold_91pct,
        test_no_owners_no_warning,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
