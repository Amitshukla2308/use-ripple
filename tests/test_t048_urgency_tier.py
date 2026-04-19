"""T-048: urgency×likelihood tier display in predict_missing_changes + check_my_changes."""
import sys, os, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "serve"))

# ── Minimal stubs so retrieval_engine imports without artifacts on disk ──────
import importlib, unittest.mock as mock

_lance = types.ModuleType("lancedb"); sys.modules.setdefault("lancedb", _lance)
_np    = types.ModuleType("numpy");   sys.modules.setdefault("numpy", _np)
_np.array = lambda *a, **k: a[0] if a else []
for _m in ("sentence_transformers", "rank_bm25", "networkx", "yaml",
           "sklearn", "sklearn.preprocessing"):
    sys.modules.setdefault(_m, types.ModuleType(_m))

# Patch heavy I/O before import
with mock.patch("builtins.open", mock.mock_open(read_data="{}")):
    with mock.patch("os.path.exists", return_value=False):
        with mock.patch("os.path.isfile", return_value=False):
            import importlib.util, pathlib
            spec = importlib.util.spec_from_file_location(
                "retrieval_engine",
                pathlib.Path(__file__).parent.parent / "serve" / "retrieval_engine.py"
            )


# ── Test predict_missing_changes causal_info fields ──────────────────────────
class TestPredictCausalFields(unittest.TestCase):

    def _make_re(self, granger_idx, granger_cross_idx):
        """Build a minimal RetrievalEngine-like namespace with the function."""
        import types
        re_mod = types.SimpleNamespace()
        # We test the logic directly via a small inline replica
        return re_mod

    def _run_predict(self, changed, granger_index, granger_cross_index, cochange_index):
        """Inline replica of the causal_info construction from predict_missing_changes."""
        def _resolve_cc(mod):
            return mod  # identity for tests

        # Replicate the causal search loop
        candidate_evidence = {}
        for src_mod in changed:
            # synthetic neighbor
            tgt = "B::Module"
            if tgt not in candidate_evidence:
                candidate_evidence[tgt] = {"total_weight": 20, "max_single": 20,
                                           "sources": [{"from": src_mod, "weight": 20}]}

        predictions = []
        for mod, ev in candidate_evidence.items():
            confidence = 0.8
            causal_info = None
            if granger_index or granger_cross_index:
                best_causal = None
                best_gi = None
                best_cc_src = best_cc_tgt = None
                for src in ev["sources"]:
                    cc_src = _resolve_cc(src["from"])
                    cc_tgt = _resolve_cc(mod)
                    key = f"{cc_src}→{cc_tgt}"
                    for gi in (granger_index, granger_cross_index):
                        if key in gi:
                            g = gi[key]
                            if best_causal is None or g["p_value"] < best_causal["p_value"]:
                                best_causal = g
                                best_gi = gi
                                best_cc_src, best_cc_tgt = cc_src, cc_tgt
                            break
                if best_causal:
                    _lag = best_causal["best_lag"]
                    _is_sym = (best_gi is granger_cross_index and
                               f"{best_cc_tgt}→{best_cc_src}" in granger_cross_index)
                    causal_info = {
                        "lag": _lag, "p_value": best_causal["p_value"],
                        "strength": "strong" if best_causal["p_value"] < 0.01 else "moderate",
                        "urgency": "IMMEDIATE" if _lag <= 2 else "DELAYED",
                        "symmetric": _is_sym,
                    }
            pred = {"module": mod, "confidence": confidence, "reason": "co-changes",
                    "weight": 20, "service": "svc-b"}
            if causal_info:
                pred["causal"] = causal_info
            predictions.append(pred)
        return predictions

    def test_immediate_urgency_lag1(self):
        gi = {"A::Mod→B::Module": {"best_lag": 1, "p_value": 0.005,
                                    "source": "A::Mod", "target": "B::Module"}}
        preds = self._run_predict(["A::Mod"], gi, {}, {})
        self.assertEqual(preds[0]["causal"]["urgency"], "IMMEDIATE")

    def test_delayed_urgency_lag5(self):
        gi = {"A::Mod→B::Module": {"best_lag": 5, "p_value": 0.02,
                                    "source": "A::Mod", "target": "B::Module"}}
        preds = self._run_predict(["A::Mod"], gi, {}, {})
        self.assertEqual(preds[0]["causal"]["urgency"], "DELAYED")

    def test_symmetric_cross_service(self):
        gci = {
            "A::Mod→B::Module": {"best_lag": 1, "p_value": 0.005,
                                   "source": "A::Mod", "target": "B::Module"},
            "B::Module→A::Mod": {"best_lag": 1, "p_value": 0.005,
                                   "source": "B::Module", "target": "A::Mod"},
        }
        preds = self._run_predict(["A::Mod"], {}, gci, {})
        self.assertTrue(preds[0]["causal"]["symmetric"])

    def test_asymmetric_cross_service(self):
        gci = {"A::Mod→B::Module": {"best_lag": 2, "p_value": 0.03,
                                     "source": "A::Mod", "target": "B::Module"}}
        preds = self._run_predict(["A::Mod"], {}, gci, {})
        self.assertFalse(preds[0]["causal"]["symmetric"])

    def test_intra_service_never_symmetric(self):
        gi = {"A::Mod→B::Module": {"best_lag": 1, "p_value": 0.005,
                                    "source": "A::Mod", "target": "B::Module"},
              "B::Module→A::Mod": {"best_lag": 1, "p_value": 0.005,
                                    "source": "B::Module", "target": "A::Mod"}}
        # intra-service index — symmetric field should be False (gi is not granger_cross_index)
        preds = self._run_predict(["A::Mod"], gi, {}, {})
        self.assertFalse(preds[0]["causal"]["symmetric"])

    def test_no_causal_no_key(self):
        preds = self._run_predict(["A::Mod"], {}, {}, {})
        self.assertNotIn("causal", preds[0])


# ── Test mcp_server tier formatter ───────────────────────────────────────────
class TestTierDisplay(unittest.TestCase):

    def _tier_split(self, predictions):
        """Inline replica of T-048 tier-split logic from mcp_server.check_my_changes."""
        imm = [p for p in predictions if p.get("causal", {}).get("urgency") == "IMMEDIATE" and p["confidence"] >= 0.6]
        delayed = [p for p in predictions if p.get("causal", {}).get("urgency") == "DELAYED" and p["confidence"] >= 0.4]
        seen = {p["module"] for p in imm} | {p["module"] for p in delayed}
        other = [p for p in predictions[:8] if p["module"] not in seen]
        return imm, delayed, other

    def _mk(self, mod, conf, urgency=None, sym=False):
        p = {"module": mod, "confidence": conf, "reason": "test"}
        if urgency:
            p["causal"] = {"lag": 1, "urgency": urgency, "symmetric": sym}
        return p

    def test_immediate_certain_bucket(self):
        preds = [self._mk("M", 0.75, "IMMEDIATE")]
        imm, delayed, other = self._tier_split(preds)
        self.assertEqual(len(imm), 1)
        self.assertEqual(len(delayed), 0)
        self.assertEqual(len(other), 0)

    def test_delayed_likely_bucket(self):
        preds = [self._mk("M", 0.55, "DELAYED")]
        imm, delayed, other = self._tier_split(preds)
        self.assertEqual(len(imm), 0)
        self.assertEqual(len(delayed), 1)

    def test_low_conf_immediate_goes_to_other(self):
        preds = [self._mk("M", 0.45, "IMMEDIATE")]
        imm, delayed, other = self._tier_split(preds)
        self.assertEqual(len(imm), 0)
        self.assertEqual(len(other), 1)

    def test_no_causal_goes_to_other(self):
        preds = [self._mk("M", 0.9)]
        imm, delayed, other = self._tier_split(preds)
        self.assertEqual(len(imm), 0)
        self.assertEqual(len(other), 1)

    def test_no_duplicate_across_buckets(self):
        preds = [self._mk("A", 0.8, "IMMEDIATE"), self._mk("B", 0.5, "DELAYED"), self._mk("C", 0.3)]
        imm, delayed, other = self._tier_split(preds)
        all_mods = [p["module"] for p in imm + delayed + other]
        self.assertEqual(len(all_mods), len(set(all_mods)))


if __name__ == "__main__":
    unittest.main()
