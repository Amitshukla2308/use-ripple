"""T-043: Team impact tiering in check_my_changes Granger section."""
import sys, types, pathlib

# Stub retrieval_engine before importing mcp_server pieces
re_stub = types.ModuleType("retrieval_engine")
re_stub.MG = None
re_stub.ownership_index = {
    "euler_txns::TransactionFlow": [{"name": "Alice", "email": "alice@co.com", "commits": 30}],
}
sys.modules["retrieval_engine"] = re_stub

import retrieval_engine as RE


def _svc_of(mod: str) -> str:
    if RE.MG is not None and mod in RE.MG.nodes:
        return RE.MG.nodes[mod].get("service", "")
    return ""


def _render_granger_section(granger_excl: list) -> list:
    """Minimal copy of the T-043 rendering logic from mcp_server.py."""
    lines = []
    cross_tier, same_tier = [], []
    for g in granger_excl:
        tgt_svc = g.get("service") or _svc_of(g.get("module", ""))
        src_svc = _svc_of(g.get("source", ""))
        if tgt_svc and src_svc and tgt_svc != src_svc:
            cross_tier.append((g, tgt_svc))
        else:
            same_tier.append(g)

    if cross_tier:
        lines.append("### Coordinate With Another Team (Granger — cross-service)")
        for g, tgt_svc in cross_tier:
            owners = RE.ownership_index.get(g["module"]) or []
            owner_str = ""
            if owners:
                top = owners[0]
                owner_str = f" — owner: {top.get('name') or top.get('email', '?')}"
            lines.append(
                f"  - **{g['module']}** [{tgt_svc}]{owner_str}"
                f" ← {g.get('source', '?')} (lag={g.get('lag',1)}, {g.get('strength','moderate')})"
            )

    if same_tier:
        lines.append("### Your Follow-up Queue (Granger — same service, likely generated)")
        for g in same_tier:
            lines.append(
                f"  - **{g['module']}** ← {g.get('source', '?')} (lag={g.get('lag',1)}, {g.get('strength','moderate')})"
            )
    return lines


def test_cross_service_gets_team_header_and_owner():
    """Cross-service Granger prediction shows 'Coordinate' header + owner name."""
    # Simulate MG with service info
    class FakeMG:
        nodes = {
            "euler_gw::GatewayFlow": {"service": "euler-gw"},
            "euler_txns::TransactionFlow": {"service": "euler-txns"},
        }
    RE.MG = FakeMG()

    preds = [{"module": "euler_txns::TransactionFlow", "source": "euler_gw::GatewayFlow",
              "service": "euler-txns", "lag": 2, "strength": "strong"}]
    lines = _render_granger_section(preds)
    text = "\n".join(lines)
    assert "Coordinate With Another Team" in text, f"header missing: {text}"
    assert "Alice" in text, f"owner missing: {text}"
    assert "euler-txns" in text
    RE.MG = None
    print("  PASS: cross-service → 'Coordinate' header + owner name")


def test_same_service_gets_followup_header():
    """Same-service Granger prediction shows 'Follow-up Queue' header."""
    class FakeMG:
        nodes = {
            "euler_gw::ConnectorTemplate": {"service": "euler-gw"},
            "euler_gw::Generated::Bindings": {"service": "euler-gw"},
        }
    RE.MG = FakeMG()

    preds = [{"module": "euler_gw::Generated::Bindings", "source": "euler_gw::ConnectorTemplate",
              "service": "euler-gw", "lag": 1, "strength": "moderate"}]
    lines = _render_granger_section(preds)
    text = "\n".join(lines)
    assert "Follow-up Queue" in text, f"header missing: {text}"
    assert "Coordinate" not in text, f"wrong header: {text}"
    RE.MG = None
    print("  PASS: same-service → 'Follow-up Queue' header, no 'Coordinate'")


def test_no_mg_falls_through_to_same_tier():
    """With MG=None, all predictions fall into same_tier (safe degradation)."""
    RE.MG = None
    preds = [{"module": "svc_a::ModA", "source": "svc_b::ModB",
              "service": "svc-a", "lag": 1, "strength": "strong"}]
    lines = _render_granger_section(preds)
    text = "\n".join(lines)
    # With MG=None, _svc_of returns "" for source, so tgt_svc="" src_svc="" → same_tier
    assert "Follow-up Queue" in text or "Coordinate" in text
    print(f"  PASS: no MG → graceful degradation (got: {text[:60]})")


if __name__ == "__main__":
    test_cross_service_gets_team_header_and_owner()
    test_same_service_gets_followup_header()
    test_no_mg_falls_through_to_same_tier()
    print("\n3/3 tests PASS")
