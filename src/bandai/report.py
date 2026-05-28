from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from bandai.io import OUTPUT_DIR


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _contract_id(contract: dict[str, Any]) -> str:
    return str(contract.get("canonical_contract_id") or contract.get("contract_id") or "N/A")


def _decision_counts(compliance_items: list[dict[str, Any]], no_go_items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"go": 0, "conditional": 0, "no_go": len(no_go_items)}
    for item in compliance_items:
        decision = str(item.get("verdict", {}).get("bid_decision", "")).upper()
        if decision == "GO":
            counts["go"] += 1
        elif decision == "CONDITIONAL-GO":
            counts["conditional"] += 1
        elif decision == "NO-GO":
            counts["no_go"] += 1
    return counts


def _approved_contract_ids(compliance_items: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for item in compliance_items:
        decision = str(item.get("verdict", {}).get("bid_decision", "")).upper()
        if decision not in {"GO", "CONDITIONAL-GO"}:
            continue
        contract = item.get("contract", {})
        if isinstance(contract, dict):
            ids.add(_contract_id(contract))
    return ids


def build_report_data(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    """Collect pipeline output JSON files into a report-friendly structure."""
    scout_data = _read_json(output_dir / "01_scout_results.json")
    contracts = _as_list(scout_data.get("contracts"))

    compliance: list[dict[str, Any]] = []
    for path in sorted(output_dir.glob("02_compliance_*.json")):
        data = _read_json(path)
        if data:
            data["source_file"] = path.name
            compliance.append(data)

    no_go_data = _read_json(output_dir / "02_no_go_review_required.json")
    no_go = _as_list(no_go_data.get("no_go_contracts"))
    approved_ids = _approved_contract_ids(compliance)
    no_go = [item for item in no_go if _contract_id(item.get("contract", {}) if isinstance(item, dict) else {}) not in approved_ids]

    proposals: list[dict[str, Any]] = []
    for path in sorted(output_dir.glob("03_proposal_*.json")):
        data = _read_json(path)
        if data:
            data["source_file"] = path.name
            proposals.append(data)

    counts = _decision_counts(compliance, no_go)
    return {
        "summary": {
            "contracts": len(contracts),
            "go": counts["go"],
            "conditional": counts["conditional"],
            "no_go": counts["no_go"],
            "proposals": len(proposals),
        },
        "contracts": contracts,
        "compliance": compliance,
        "no_go": no_go,
        "proposals": proposals,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _money(value: Any) -> str:
    try:
        return f"EUR {float(value):,.0f}"
    except (TypeError, ValueError):
        return "N/A"


def _score(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "N/A"


def _badge(decision: Any) -> str:
    text = str(decision or "N/A").upper()
    css = {"GO": "go", "CONDITIONAL-GO": "conditional", "NO-GO": "no-go"}.get(text, "neutral")
    return f'<span class="badge {css}">{_e(text)}</span>'


def _list(items: Any) -> str:
    values = _as_list(items)
    if not values:
        return '<p class="muted">Nessun elemento.</p>'
    return "<ul>" + "".join(f"<li>{_e(item)}</li>" for item in values) + "</ul>"


def _render_summary(summary: dict[str, Any]) -> str:
    cards = [
        ("Contratti", summary.get("contracts", 0)),
        ("GO", summary.get("go", 0)),
        ("Conditional", summary.get("conditional", 0)),
        ("NO-GO", summary.get("no_go", 0)),
        ("Proposte", summary.get("proposals", 0)),
    ]
    return "".join(f'<article class="metric"><span>{_e(label)}</span><strong>{_e(value)}</strong></article>' for label, value in cards)


def _render_contracts(contracts: list[dict[str, Any]]) -> str:
    if not contracts:
        return '<p class="empty">Nessun contratto trovato in output/01_scout_results.json.</p>'
    rows = []
    for contract in contracts:
        cpv = ", ".join(str(code) for code in _as_list(contract.get("cpv_codes"))) or "N/A"
        url = contract.get("canonical_url")
        link = f'<a href="{_e(url)}">Apri</a>' if url else "N/A"
        rows.append(
            "<tr>"
            f"<td>{_e(_contract_id(contract))}</td>"
            f"<td>{_e(contract.get('title', 'N/A'))}</td>"
            f"<td>{_e(contract.get('contracting_authority', 'N/A'))}</td>"
            f"<td>{_money(contract.get('value_eur'))}</td>"
            f"<td>{_e(contract.get('deadline', 'N/A'))}</td>"
            f"<td>{_e(cpv)}</td>"
            f"<td>{link}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th>ID</th><th>Titolo</th><th>Ente</th>'
        "<th>Valore</th><th>Scadenza</th><th>CPV</th><th>URL</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _render_compliance(items: list[dict[str, Any]]) -> str:
    if not items:
        return '<p class="empty">Nessun esito compliance trovato.</p>'
    blocks = []
    for item in items:
        contract = item.get("contract", {})
        verdict = item.get("verdict", {})
        blocks.append(
            '<article class="result-card">'
            '<div class="result-head">'
            f"<div><h3>{_e(contract.get('title', 'Contratto'))}</h3><p>{_e(_contract_id(contract))}</p></div>"
            f"<div>{_badge(verdict.get('bid_decision'))}<strong>{_score(verdict.get('compliance_score'))}</strong></div>"
            "</div>"
            f"<p>{_e(verdict.get('verdict_rationale', ''))}</p>"
            '<div class="split">'
            f"<section><h4>Punti di forza</h4>{_list(verdict.get('key_strengths'))}</section>"
            f"<section><h4>Rischi</h4>{_list(verdict.get('key_risks'))}</section>"
            "</div>"
            "</article>"
        )
    return "".join(blocks)


def _render_no_go(items: list[dict[str, Any]]) -> str:
    if not items:
        return '<p class="empty">Nessun NO-GO in revisione.</p>'
    blocks = []
    for item in items:
        contract = item.get("contract", {})
        verdict = item.get("verdict", {})
        blocks.append(
            '<article class="result-card">'
            '<div class="result-head">'
            f"<div><h3>{_e(contract.get('title', 'Contratto'))}</h3><p>{_e(contract.get('contract_id', 'N/A'))}</p></div>"
            f"<div>{_badge(verdict.get('bid_decision'))}<strong>{_score(verdict.get('compliance_score'))}</strong></div>"
            "</div>"
            f"<p>{_e(verdict.get('verdict_rationale', ''))}</p>"
            f"<h4>Rischi principali</h4>{_list(verdict.get('key_risks'))}"
            "</article>"
        )
    return "".join(blocks)


def _render_proposals(items: list[dict[str, Any]]) -> str:
    if not items:
        return '<p class="empty">Nessuna proposta generata.</p>'
    blocks = []
    for item in items:
        sections = item.get("sections", {})
        section_names = ", ".join(sections.keys()) if isinstance(sections, dict) else "N/A"
        blocks.append(
            '<article class="result-card">'
            '<div class="result-head">'
            f"<div><h3>{_e(item.get('tender_ref', 'Proposta'))}</h3><p>{_e(section_names)}</p></div>"
            f"<div><span class=\"badge go\">Quality {_score(item.get('quality_score'))}</span><strong>{_e(item.get('word_count', 0))} parole</strong></div>"
            "</div>"
            f"<p>{_e(item.get('executive_summary', ''))}</p>"
            "</article>"
        )
    return "".join(blocks)


def generate_report_html(data: dict[str, Any]) -> str:
    """Render a standalone stakeholder-ready HTML report."""
    summary = data.get("summary", {})
    return f"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BandAI Report</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8f5; --panel: #ffffff; --text: #17201a; --muted: #667067;
      --line: #dfe5dd; --green: #138a43; --red: #c53232; --white: #ffffff;
      --gold: #b69245; --shadow: 0 10px 30px rgba(23, 32, 26, .08);
    }}
    [data-theme="dark"] {{
      color-scheme: dark;
      --bg: #101411; --panel: #171d19; --text: #eef4ef; --muted: #aeb8b0;
      --line: #2b352e; --green: #4fc87b; --red: #ff6b6b; --white: #f4f7f2;
      --gold: #d7b96c; --shadow: 0 10px 30px rgba(0, 0, 0, .24);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }}
    .italy {{ display: grid; grid-template-columns: 1fr 1fr 1fr; height: 8px; }}
    .italy span:nth-child(1) {{ background: var(--green); }} .italy span:nth-child(2) {{ background: var(--white); }} .italy span:nth-child(3) {{ background: var(--red); }}
    header, main {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; }}
    header {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 28px 0 18px; }}
    h1 {{ margin: 0; font-size: 32px; line-height: 1.1; letter-spacing: 0; }}
    h2 {{ margin: 34px 0 14px; font-size: 20px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 4px; font-size: 16px; letter-spacing: 0; }}
    h4 {{ margin: 16px 0 8px; font-size: 13px; text-transform: uppercase; color: var(--muted); letter-spacing: 0; }}
    p {{ line-height: 1.55; }}
    a {{ color: var(--green); font-weight: 700; }}
    .muted, .empty, header p, .result-head p {{ color: var(--muted); margin: 4px 0 0; }}
    .theme-toggle {{ border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 8px; padding: 10px 12px; cursor: pointer; box-shadow: var(--shadow); }}
    .metrics {{ display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 10px; }}
    .metric, .result-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); }}
    .metric {{ padding: 16px; }}
    .metric span {{ color: var(--muted); display: block; font-size: 13px; }}
    .metric strong {{ font-size: 28px; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); box-shadow: var(--shadow); }}
    table {{ width: 100%; border-collapse: collapse; min-width: 920px; }}
    th, td {{ text-align: left; padding: 12px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    th {{ font-size: 12px; color: var(--muted); text-transform: uppercase; }}
    .result-card {{ padding: 18px; margin-bottom: 12px; }}
    .result-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }}
    .result-head > div:last-child {{ text-align: right; display: grid; gap: 8px; justify-items: end; }}
    .badge {{ display: inline-block; border-radius: 999px; padding: 5px 9px; font-size: 12px; font-weight: 800; border: 1px solid var(--line); }}
    .badge.go {{ color: var(--green); background: color-mix(in srgb, var(--green) 12%, transparent); }}
    .badge.conditional {{ color: var(--gold); background: color-mix(in srgb, var(--gold) 16%, transparent); }}
    .badge.no-go {{ color: var(--red); background: color-mix(in srgb, var(--red) 12%, transparent); }}
    .badge.neutral {{ color: var(--muted); }}
    .split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
    ul {{ margin: 0; padding-left: 18px; }}
    li {{ margin: 6px 0; }}
    footer {{ width: min(1180px, calc(100% - 32px)); margin: 36px auto 28px; color: var(--muted); font-size: 13px; }}
    @media (max-width: 760px) {{ header {{ align-items: flex-start; flex-direction: column; }} .metrics, .split {{ grid-template-columns: 1fr; }} h1 {{ font-size: 26px; }} }}
  </style>
</head>
<body>
  <div class="italy" aria-hidden="true"><span></span><span></span><span></span></div>
  <header>
    <div>
      <h1>BandAI Report</h1>
      <p>Generato il {_e(data.get('generated_at', ''))} dagli output della pipeline.</p>
    </div>
    <button id="theme-toggle" class="theme-toggle" type="button">Light / Dark</button>
  </header>
  <main>
    <section class="metrics">{_render_summary(summary)}</section>
    <section><h2>Contratti individuati</h2>{_render_contracts(_as_list(data.get('contracts')))}</section>
    <section><h2>Esiti compliance</h2>{_render_compliance(_as_list(data.get('compliance')))}</section>
    <section><h2>NO-GO da rivedere</h2>{_render_no_go(_as_list(data.get('no_go')))}</section>
    <section><h2>Proposte generate</h2>{_render_proposals(_as_list(data.get('proposals')))}</section>
  </main>
  <script>
    const root = document.documentElement;
    const savedTheme = localStorage.getItem("bandai-report-theme");
    if (savedTheme) root.dataset.theme = savedTheme;
    document.getElementById("theme-toggle").addEventListener("click", () => {{
      const next = root.dataset.theme === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      localStorage.setItem("bandai-report-theme", next);
    }});
  </script>
</body>
</html>
"""


def write_report(output_dir: Path = OUTPUT_DIR, filename: str = "report.html") -> Path:
    """Generate and write the HTML report into the output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    data = build_report_data(output_dir)
    path = output_dir / filename
    path.write_text(generate_report_html(data), encoding="utf-8")
    return path
