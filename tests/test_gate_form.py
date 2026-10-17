"""Run: .venv/bin/python -m pytest tests (or python tests/test_gate_form.py)."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import gate_form as g, guard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COMMENTS = (ROOT / "outputs" / "auditor-comments.md").read_text()
REVIEW = (ROOT / "outputs" / "review.md").read_text()


def test_parse_finds_every_risk_including_empty_comments():
    p = g.parse_comments(COMMENTS)
    assert p["version"] == "v2" and len(p["rows"]) == 8
    assert [r["risk"] for r in p["rows"]][:2] == ["R-01", "R-04"]
    assert p["rows"][0]["comment"] == ""


def test_unchanged_roundtrip_is_identical_and_not_flagged_as_change():
    p = g.parse_comments(COMMENTS)
    d = [{k: r[k] for k in ("risk", "decision", "comment")} for r in p["rows"]]
    assert not g.decisions_changed(COMMENTS, d)
    assert g.validate(d, {r["risk"] for r in p["rows"]}) == []
    assert g.apply_decisions(COMMENTS, d).strip() == COMMENTS.strip()


def test_validation_rules():
    ids = {"R-01"}
    ok = lambda dec, com: g.validate([{"risk": "R-01", "decision": dec, "comment": com}], ids)
    assert ok("APPROVE", "") == [] and ok("REJECT", "") == []
    assert ok("OVERRIDE", "likelihood=3") == [] and ok("OVERRIDE", "impact=5 and likelihood=2") == []
    assert ok("OVERRIDE", "make it lower") and ok("OVERRIDE", "likelihood=9")
    assert ok("REVISE", "") and ok("APPROVE", "a|b") and ok("MAYBE", "")
    assert g.validate([], ids) == ["R-01: no decision given"]


def test_apply_changes_only_the_target_row():
    p = g.parse_comments(COMMENTS)
    d = [{k: r[k] for k in ("risk", "decision", "comment")} for r in p["rows"]]
    d[0].update(decision="OVERRIDE", comment="likelihood=3")
    new = g.apply_decisions(COMMENTS, d)
    diff = [(a, b) for a, b in zip(COMMENTS.splitlines(), new.splitlines()) if a != b]
    assert len(diff) == 1 and "R-01" in diff[0][1] and "OVERRIDE | likelihood=3" in diff[0][1]


def test_signoff():
    info = g.review_info(REVIEW)
    assert info["pack_version"] == "v3" and info["verdict"] == "READY FOR SIGN-OFF" and info["signed"] == "SIGNED OFF"
    assert g.validate_signoff(info, "SIGNED OFF", "A. Auditor", "ok", stale=False) == []
    assert g.validate_signoff(info, "SIGNED OFF", "A. Auditor", "ok", stale=True)
    assert g.validate_signoff({**info, "verdict": "BLOCKED"}, "SIGNED OFF", "A", "", False)
    assert g.validate_signoff({**info, "verdict": "BLOCKED"}, "RETURNED TO TEAM", "A", "", False) == []
    assert g.validate_signoff(info, "SIGNED OFF", "", "", False) and g.validate_signoff(info, "SIGNED OFF", "A", "x|y", False)
    out = g.apply_signoff(REVIEW, "RETURNED TO TEAM", "Test Name", "see notes", "v3", date(2030, 1, 2))
    assert "| Auditor name | Test Name |" in out and "| Date | 2030-01-02 |" in out
    assert out.split("## Auditor sign-off")[0].strip() == REVIEW.split("## Auditor sign-off")[0].strip()
    assert "| Decision (SIGNED OFF / RETURNED TO TEAM) | RETURNED TO TEAM |" in out


def test_guard():
    assert guard.redact("a sk-ant-abc123456789 b") == "a [REDACTED] b"
    w = Path("/w")
    deny = lambda c: guard.tool_denial("Bash", {"command": c}, w) is not None
    assert deny("printenv") and deny("cat .env") and deny("python -c 'import os; os.environ'") and deny("ls ../")
    assert not deny(".venv/bin/python .claude/skills/risk-assessment/build_register.py")
    assert guard.tool_denial("Read", {"file_path": "/etc/passwd"}, w)
    assert guard.tool_denial("Read", {"file_path": "outputs/rules.json"}, w) is None


def test_access_code_rate_limit():
    guard.ACCESS_CODE = "right-code"
    guard._fails.clear()
    assert guard.check_access("right-code", "ip1")[0]
    for _ in range(5):
        assert guard.check_access("wrong", "ip2")[1] == 401
    assert guard.check_access("right-code", "ip2")[1] == 429
    guard.ACCESS_CODE = ""
    assert guard.check_access("x", "ip3")[1] == 503


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
