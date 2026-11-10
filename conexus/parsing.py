"""Document ingestion: PDF / DOCX / TXT -> text -> numbered sections."""
from __future__ import annotations

import re
from pathlib import Path


def read_document(path: str | Path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if suffix == ".docx":
        import docx

        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    return path.read_text(encoding="utf-8", errors="replace")


# "12. Limitation of Liability" / "12.1 Indemnity." / "ARTICLE 5 - PAYMENT"
_HEADING = re.compile(
    r"^\s*(?:(?:article|section|clause)\s+)?(\d+(?:\.\d+)*)[.)]?\s*[-–:]?\s+([A-Z][A-Za-z &/,'-]{2,80}?)[.:]?\s*$",
    re.IGNORECASE,
)


def split_sections(text: str) -> list[tuple[str, str]]:
    """Return [(heading, body)]. Falls back to paragraph blocks if no numbered headings."""
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    for line in lines:
        m = _HEADING.match(line)
        if m and len(line.strip()) < 90:
            sections.append((f"{m.group(1)} {m.group(2).strip()}", []))
        elif sections:
            sections[-1][1].append(line)
    out = [(h, "\n".join(b).strip()) for h, b in sections if "\n".join(b).strip()]
    if len(out) >= 2:
        return out
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 40]
    return [("", p) for p in paras]
