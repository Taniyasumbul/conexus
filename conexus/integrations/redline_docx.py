"""Export a contract as a Word document whose redlines are real tracked changes.

Open it in Word / Google Docs / LibreOffice: every CoNexus redline shows as a tracked
deletion + insertion (Accept / Reject works), and each flagged clause carries a margin
comment with the reason. This is the file a sales or legal team sends to the customer.
"""
from __future__ import annotations

import difflib
import io
import re
from datetime import datetime, timezone

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from ..models import ClauseRisk, NegotiationState, RiskLevel

AUTHOR = "CoNexus Legal/Risk Agent"
INK = RGBColor(0x14, 0x1B, 0x2D)
MUTED = RGBColor(0x73, 0x7C, 0x8F)


def _diff(a: str, b: str) -> list[tuple[str, str]]:
    """Word-level diff; a mostly rewritten clause becomes one deletion + one insertion."""
    A, B = re.split(r"(\s+)", a), re.split(r"(\s+)", b)
    sm = difflib.SequenceMatcher(a=A, b=B, autojunk=False)
    if sm.ratio() < 0.5:
        return [("del", a), ("same", " "), ("ins", b)]
    out: list[tuple[str, str]] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.append(("same", "".join(A[i1:i2])))
        if op in ("delete", "replace"):
            out.append(("del", "".join(A[i1:i2])))
        if op in ("insert", "replace"):
            out.append(("ins", "".join(B[j1:j2])))
    return [p for p in out if p[1]]


class _Revisions:
    def __init__(self):
        self.next_id = 1000  # keep clear of comment ids
        self.date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _wrap(self, tag: str, text: str):
        el = OxmlElement(tag)
        el.set(qn("w:id"), str(self.next_id))
        el.set(qn("w:author"), AUTHOR)
        el.set(qn("w:date"), self.date)
        self.next_id += 1
        r = OxmlElement("w:r")
        t = OxmlElement("w:delText" if tag == "w:del" else "w:t")
        t.set(qn("xml:space"), "preserve")
        t.text = text
        r.append(t)
        el.append(r)
        return el

    def write(self, paragraph, original: str, proposed: str) -> None:
        for kind, text in _diff(original, proposed):
            if kind == "same":
                paragraph.add_run(text)
            else:
                paragraph._p.append(self._wrap("w:del" if kind == "del" else "w:ins", text))


def _redline_targets(st: NegotiationState) -> dict[str, ClauseRisk]:
    """Redlines still on the table: proposed (or, before negotiation, proposable), not rejected,
    and not cleared as drafted by a human reviewer."""
    risks = {r.clause_id: r for r in st.risks}
    candidates = st.pending_redlines or [r.clause_id for r in st.risks if r.redlinable and r.level != RiskLevel.LOW]
    return {cid: risks[cid] for cid in candidates
            if cid in risks and risks[cid].redline and st.redline_results.get(cid) is not False
            and cid not in st.reviewed_clauses}


def build_redline_docx(st: NegotiationState, prepared_by: str, audit_head: str) -> bytes:
    doc = Document()
    base = doc.styles["Normal"]
    base.font.name, base.font.size = "Calibri", Pt(11)
    rev = _Revisions()
    targets = _redline_targets(st)
    risks = {r.clause_id: r for r in st.risks}
    ctx = st.context

    title = doc.add_paragraph()
    run = title.add_run("Subscription Agreement — Proposed Redline")
    run.bold, run.font.size, run.font.color.rgb = True, Pt(18), INK
    sub = doc.add_paragraph()
    sr = sub.add_run(f"{ctx.customer}  ·  {st.contract_id}  ·  prepared {datetime.now().strftime('%d %b %Y')} by {prepared_by}")
    sr.font.size, sr.font.color.rgb = Pt(9), MUTED

    terms = st.agreed_terms or st.last_our_offer or (st.plan.anchor if st.plan else None)
    table = doc.add_table(rows=0, cols=2)
    table.style = "Light Grid Accent 1"
    rows = [("Customer", ctx.customer), ("Product", f"{ctx.product.title()} × {ctx.seats} seats"),
            ("List price", f"USD {ctx.list_price:,.0f} per year")]
    if terms:
        label = "Agreed commercial terms" if st.agreed_terms else "Our current proposal"
        rows.append((label, f"USD {terms.price:,.0f} per year · payment net {terms.payment_days} days · {terms.term_months}-month term"))
    rows.append(("Redlines in this draft", str(len(targets))))
    for k, v in rows:
        cells = table.add_row().cells
        cells[0].text, cells[1].text = k, v
    doc.add_paragraph()

    for c in st.clauses:
        r = risks.get(c.id)
        head = doc.add_paragraph()
        hr = head.add_run(c.heading or c.type.value.replace("_", " ").title())
        hr.bold, hr.font.color.rgb = True, INK
        body = doc.add_paragraph()
        body.paragraph_format.space_after = Pt(10)
        if c.id in targets:
            rev.write(body, c.text, targets[c.id].redline)
            reason = "; ".join(x for x in targets[c.id].reasons if not x.startswith("Safe harbour")) or "Off-market term"
            doc.add_comment(hr, text=f"Proposed change. Why: {reason}.", author=AUTHOR, initials="CX")
        else:
            body.add_run(c.text)
            if r and r.requires_human and c.id in st.reviewed_clauses:
                doc.add_comment(hr, text="Accepted as drafted after legal review.", author=AUTHOR, initials="CX")
            elif r and st.redline_results.get(c.id) is False:
                doc.add_comment(hr, text="Our proposed change was declined by the customer.", author=AUTHOR, initials="CX")

    foot = doc.add_paragraph()
    foot.alignment = WD_ALIGN_PARAGRAPH.LEFT
    fr = foot.add_run(f"Generated by CoNexus. Every change is recorded in the audit ledger (head {audit_head[:16]}…).")
    fr.font.size, fr.font.color.rgb, fr.italic = Pt(8), MUTED, True

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
