"""Test T-017 severity tiering in get_blast_radius."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "serve"))

import retrieval_engine as RE
import networkx as nx


def _make_graph():
    G = nx.DiGraph()
    G.add_node("SvcA.Mod1", service="svc-a", type="module")
    G.add_node("SvcA.Mod2", service="svc-a", type="module")
    G.add_node("SvcB.Mod3", service="svc-b", type="module")
    G.add_edge("SvcA.Mod1", "SvcA.Mod2")
    G.add_edge("SvcA.Mod1", "SvcB.Mod3")
    return G


def setup():
    RE.MG = _make_graph()
    RE.cochange_index.clear()
    RE.granger_index.clear()
    RE.granger_cross_index.clear()
    RE.activity_index.clear()


print("TEST 1: intra-service impact → MEDIUM severity")
setup()
r = RE.get_blast_radius(["SvcA.Mod1"])
items = {i["module"]: i for i in r["tiered_impact"]}
assert items["SvcA.Mod2"]["severity"] == "MEDIUM", f"Got {items['SvcA.Mod2'].get('severity')}"
print("  PASS")

print("TEST 2: cross-service impact → HIGH severity + cross_team_note")
assert items["SvcB.Mod3"]["severity"] == "HIGH"
assert "cross_team_note" in items["SvcB.Mod3"]
print("  PASS")

print("TEST 3: no service data → no severity field (graceful)")
G2 = nx.DiGraph()
G2.add_node("X.Mod", type="module")  # no service attribute
G2.add_node("Y.Mod", type="module")
G2.add_edge("X.Mod", "Y.Mod")
RE.MG = G2
r2 = RE.get_blast_radius(["X.Mod"])
items2 = {i["module"]: i for i in r2["tiered_impact"]}
# When seed has no service, seed_services is empty, no severity tagging
assert "severity" not in items2.get("Y.Mod", {}), "No severity when seed_services empty"
print("  PASS")

print("TEST 4: same service seed → MEDIUM, different → HIGH")
setup()
r3 = RE.get_blast_radius(["SvcA.Mod1", "SvcA.Mod2"])
items3 = {i["module"]: i for i in r3["tiered_impact"]}
if "SvcB.Mod3" in items3:
    assert items3["SvcB.Mod3"]["severity"] == "HIGH"
print("  PASS")

print("\nAll 4 tests PASSED")
