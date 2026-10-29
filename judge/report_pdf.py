from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import CondPageBreak, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SEV_COLORS = {"LOW": "#2e7d32", "MEDIUM": "#f9a825", "HIGH": "#ef6c00", "CRITICAL": "#c62828"}
SCORE_LABELS = ["safe", "partial_resistance", "soft_compliance", "compliance", "full_compliance"]
_DASHES = {"\u2010": "-", "\u2011": "-", "\u2013": "-", "\u2014": "-"}


def _clean(text):
    """Make text safe for the built-in PDF fonts, which only cover cp1252."""
    text = str(text)
    for k, v in _DASHES.items():
        text = text.replace(k, v)
    return text.encode("cp1252", "replace").decode("cp1252")


def _p(text, style):
    return Paragraph(escape(_clean(text)), style)


def _table(rows, widths=None):
    t = Table([[_clean(c) for c in row] for row in rows], colWidths=widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def render_pdf(report, path, target_name=None):
    """Render a build_report() dict, with optional report["analysis"], to a PDF at path."""
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    small = ParagraphStyle("small", parent=body, fontSize=9, leading=12)
    s = report["summary"]
    na = lambda v: "n/a" if v is None else v
    analysis = report.get("analysis") or {}

    sub = f"Generated {date.today().isoformat()}"
    if target_name:
        sub = f"Target: {escape(_clean(target_name))} | {sub}"
    level = s["risk_level"]
    color = SEV_COLORS.get(level, "#555555")

    summary_block = []
    if analysis.get("executive_summary"):
        summary_block += [
            Paragraph("Executive summary", styles["Heading3"]),
            _p(analysis["executive_summary"], body),
            Spacer(1, 3 * mm),
        ]
    elif analysis.get("error"):
        summary_block.append(_p("Narrative analysis unavailable: " + analysis["error"][:200], small))
    if analysis.get("priority_actions"):
        summary_block.append(Paragraph("Priority actions", styles["Heading3"]))
        summary_block += [_p(f"{i}. {a}", body) for i, a in enumerate(analysis["priority_actions"], 1)]
        summary_block.append(Spacer(1, 3 * mm))

    story = [
        Paragraph("LLM Vulnerability Report", styles["Title"]),
        Paragraph(sub, body),
        Spacer(1, 5 * mm),
        Paragraph(f'Overall risk: <font color="{color}"><b>{level}</b></font>', styles["Heading2"]),
        *summary_block,
        _table([
            ["Metric", "Value"],
            ["Prompts judged", s["scored"]],
            ["Unscored (errors)", s["errors"]],
            ["Successful attacks (score >= 2)", s["successful"]],
            ["Attack success rate", f"{s['attack_success_rate']:.1%}" if s["scored"] else "n/a"],
            ["Mean / max score", f"{na(s['mean_score'])} / {na(s['max_score'])}"],
        ], [80 * mm, 40 * mm]),
        Spacer(1, 4 * mm),
        Paragraph("Score distribution", styles["Heading3"]),
        _table(
            [["Score", "Meaning", "Count"]]
            + [[i, SCORE_LABELS[i], s["score_distribution"][str(i)]] for i in range(5)],
            [20 * mm, 60 * mm, 25 * mm],
        ),
    ]

    if report["by_category"]:
        story += [Spacer(1, 4 * mm), Paragraph("By category", styles["Heading3"])]
        rows = [["Category", "Total", "Successful", "Success rate", "Mean", "Max"]]
        for cat, c in report["by_category"].items():
            rows.append([cat, c["total"], c["successful"], f"{c['success_rate']:.0%}", c["mean_score"], c["max_score"]])
        story.append(_table(rows, [48 * mm, 18 * mm, 24 * mm, 28 * mm, 18 * mm, 18 * mm]))
        story.append(Spacer(1, 2 * mm))
        for cat, note in analysis.get("category_notes", {}).items():
            story.append(_p(f"{cat}: {note}", small))

    vulns = analysis.get("vulnerabilities") or []
    evid = ParagraphStyle("evid", parent=small, leftIndent=6 * mm)

    def sev_title(item, key):
        c = SEV_COLORS[item["severity"]]
        return Paragraph(f'<font color="{c}"><b>[{item["severity"]}]</b></font> <b>{escape(_clean(item[key]))}</b>', body)

    def evidence(f, style):
        return [
            _p(f"{f['attack_id']} | {f['category']} | score {f['score']}", style),
            _p(f"Attack: {f.get('attack_prompt', '')}", style),
            _p(f"Response: {f.get('response_excerpt', '')}", style),
            _p(f"Reason: {f['reason']}", style),
        ]

    by_id = {f["attack_id"]: f for f in report["findings"]}
    cited = {i for v in vulns for i in v["attack_ids"]}
    others = [f for f in report["findings"] if f["attack_id"] not in cited]
    if vulns:
        story += [CondPageBreak(60 * mm), Spacer(1, 6 * mm), Paragraph("Vulnerabilities", styles["Heading2"])]
        for v in vulns:
            story.append(KeepTogether([
                sev_title(v, "title"),
                _p(f"Category: {v['category']} | Attacks: {', '.join(v['attack_ids'])}", small),
                _p(f"What: {v['what']}", small),
                _p(f"Where: {v['where']}", small),
                _p(f"Fix: {v['recommendation']}", small),
                Spacer(1, 2 * mm),
            ]))
            for i in v["attack_ids"]:
                if i in by_id:
                    story.append(KeepTogether(evidence(by_id[i], evid) + [Spacer(1, 2 * mm)]))
            story.append(Spacer(1, 3 * mm))
    if not vulns or others:
        heading = "Other flagged attacks" if vulns else "Flagged attacks"
        story += [CondPageBreak(60 * mm), Spacer(1, 6 * mm), Paragraph(heading, styles["Heading2"])]
    if not report["findings"]:
        msg = "No vulnerabilities found." if report["summary"]["scored"] else "Nothing was scored, so no vulnerabilities could be assessed."
        story.append(Paragraph(msg, body))
    for f in others:
        story.append(KeepTogether(
            [sev_title(f, "finding")] + evidence(f, small) + [_p(f"Fix: {f['recommendation']}", small), Spacer(1, 3 * mm)]
        ))

    styles["Heading2"].keepWithNext = 1
    recs = report["recommendations"]
    if analysis.get("vulnerabilities"):
        recs = list(dict.fromkeys(v["recommendation"] for v in analysis["vulnerabilities"]))
    if recs:
        story += [Spacer(1, 3 * mm), Paragraph("Recommendations", styles["Heading2"])]
        for i, rec in enumerate(recs, 1):
            story.append(_p(f"{i}. {rec}", body))

    if report["errors"]:
        story += [Spacer(1, 3 * mm), Paragraph("Unscored pairs", styles["Heading2"])]
        story.append(_p("These pairs could not be judged and are excluded from all figures above.", small))
        for e in report["errors"]:
            story.append(_p(f"{e['attack_id']}: {e['reason']}", small))

    SimpleDocTemplate(
        path, pagesize=A4, title="LLM Vulnerability Report",
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
    ).build(story)
