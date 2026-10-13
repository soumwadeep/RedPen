"""Clause segmentation and document ingest for RedPen.

Every finding must cite a real clause with a page number, so this module is
deliberately conservative: it never invents structure that is not in the text.
Each clause keeps its page number and its character span in the normalised
document, so the UI can highlight the source and a human can open the PDF and
check our work.

Inputs: PDF (PyMuPDF), DOCX (zip + document.xml), plain text / Markdown.
No cloud, no OCR service -- a scanned PDF is rejected with an explicit message
rather than silently returning nothing.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf  # PyMuPDF

fitz = pymupdf  # keep the short name local to this module

_TOP_LEVEL = re.compile(
    r"^\s*(?:section|article|clause)?\s*"
    r"(?P<num>\d+(?:\.\d+){0,2}|[IVXLCDM]{1,7})"
    r"\s*[).:]?\s+[-\u2013\u2014]?\s*(?P<head>.{0,90})$"
)
_ALLCAPS = re.compile(r"^\s*(?:SECTION|ARTICLE)\s+[0-9IVXLCDM]+\b", re.I)
_PARA_BREAK = re.compile(r"\n\s*\n+")

MIN_USEFUL_CHARS = 200


class DocumentTooShort(ValueError):
    """Raised when there is not enough text to review meaningfully."""


@dataclass
class Clause:
    cid: str
    number: str
    heading: str
    text: str
    page: int
    start: int
    end: int
    depth: int = 1

    def snippet(self, chars: int = 320) -> str:
        flat = " ".join(self.text.split())
        if len(flat) <= chars:
            return flat
        cut = flat.rfind(" ", 0, chars)
        return (flat[: cut if cut > 120 else chars]).rstrip() + " …"

    @property
    def label(self) -> str:
        head = f" {self.heading}" if self.heading else ""
        return f"Clause {self.number}{head}"

    def to_dict(self) -> dict:
        return {
            "cid": self.cid,
            "number": self.number,
            "heading": self.heading,
            "label": self.label,
            "text": self.text,
            "page": self.page,
            "start": self.start,
            "end": self.end,
            "depth": self.depth,
            "snippet": self.snippet(),
        }


@dataclass
class Contract:
    name: str
    source: str
    text: str
    pages: int
    clauses: list[Clause]
    warnings: list[str] = field(default_factory=list)

    def clause(self, cid: str) -> Clause | None:
        return next((c for c in self.clauses if c.cid == cid), None)

    @property
    def clause_count(self) -> int:
        return len(self.clauses)

    @property
    def norm(self) -> str:
        return normalise(self.text)


def normalise(text: str) -> str:
    """Lowercase and collapse so rule patterns can stay readable."""
    text = text.lower()
    for a, b in (
        ("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'),
        ("\u2013", "-"), ("\u2014", "-"), ("\u00a0", " "), ("\u2026", "..."),
    ):
        text = text.replace(a, b)
    return re.sub(r"[ \t]+", " ", text)


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #

def extract(path: str | Path) -> tuple[str, int]:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"no such file: {p}")
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return _from_pdf(p)
    if suffix == ".docx":
        return _from_docx(p), 1
    return p.read_text(errors="replace"), 1


def _from_pdf(p: Path) -> tuple[str, int]:
    doc = fitz.open(p)
    chunks = [page.get_text("text") for page in doc]
    total = doc.page_count
    doc.close()
    if not any(c.strip() for c in chunks):
        raise DocumentTooShort(
            "This PDF has no selectable text - it is a scan. RedPen does not "
            "send pages to an OCR service. Export the PDF with text, or paste "
            "the clauses you want checked."
        )
    return "\n\n".join(chunks), total


def _from_docx(p: Path) -> str:
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    xml = re.sub(r"<w:br[^>]*/>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


# --------------------------------------------------------------------------- #
# Segmentation
# --------------------------------------------------------------------------- #

def _unwrap(raw: str) -> str:
    """Rejoin PDF hard-wraps.

    PDF text puts one visual line per newline, including lines broken
    mid-sentence. A short line that does not end in punctuation and is followed
    by a lowercase start is a wrap, so we join it back.
    """
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    for line in lines:
        s = line.rstrip()
        if not s.strip():
            out.append("")
            continue
        prev = out[-1].strip() if out else ""
        wrapped = (
            prev
            and len(prev) > 45
            and not re.search(r"[.:;!?]$", prev)
            and not _TOP_LEVEL.match(prev)
            and not _ALLCAPS.match(prev)
            and re.match(r"^[a-z(\u201c\u2018]", s.strip())
        )
        if wrapped and out:
            joiner = "" if re.search(r"[-\u2013\u2014]$", out[-1].rstrip()) else " "
            out[-1] = out[-1].rstrip().rstrip("-\u2013\u2014") + joiner + s.strip()
            continue
        out.append(s)
    return "\n".join(out)


def _page_map(raw: str) -> list[int]:
    """Character offset at which each page's text begins (pages joined by \\n\\n)."""
    bounds: list[int] = []
    pos = 0
    for part in raw.split("\n\n"):
        if part.strip():
            bounds.append(pos)
        pos += len(part) + 2
    return bounds


def _page_for(offset: int, bounds: list[int], total: int) -> int:
    if len(bounds) <= 1:
        return 1
    page = 1
    for i, lo in enumerate(bounds):
        if offset >= lo:
            page = i + 1
    return min(page, max(total, 1))


def segment(text: str, total_pages: int = 1) -> list[Clause]:
    lines = _unwrap(text).split("\n")
    bounds = _page_map(text)

    heads: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or not (_ALLCAPS.match(s) or _TOP_LEVEL.match(s)):
            continue
        m = _TOP_LEVEL.match(s)
        num = (m.group("num") if m else "") or ""
        if not num:
            continue
        # Skip prose that merely starts with a number ("2024 was strong").
        if re.fullmatch(r"\d{4}", num):
            continue
        head = (m.group("head") or "").strip(" -–—.:") if m else ""
        heads.append((i, num, head))

    clauses: list[Clause] = []
    if len(heads) >= 3:
        for j, (start_line, num, head) in enumerate(heads):
            end_line = heads[j + 1][0] if j + 1 < len(heads) else len(lines)
            body = "\n".join(lines[start_line:end_line]).strip()
            if len(body) < 8:
                continue
            offset = max(text.find(body[:60]), 0)
            clauses.append(
                Clause(
                    cid=f"c{len(clauses) + 1}",
                    number=num,
                    heading=head or _guess_heading(body),
                    text=body,
                    page=_page_for(offset, bounds, total_pages),
                    start=offset,
                    end=offset + len(body),
                    depth=num.count(".") + 1,
                )
            )
        if len(clauses) >= 3:
            return clauses
    return _by_paragraph(text, bounds, total_pages)


def _guess_heading(body: str) -> str:
    for line in body.split("\n"):
        s = line.strip()
        if 3 < len(s) < 90 and not s.endswith("."):
            return re.sub(r"^[\d.]*\s*(section|article|clause)?\s*[\dIVXLCDM.]*\s*", "", s, flags=re.I).strip(" -–—.:")
    return ""


def _by_paragraph(text: str, bounds: list[int], total_pages: int) -> list[Clause]:
    paras = [p.strip() for p in _PARA_BREAK.split(text) if len(p.strip()) > 40]
    clauses: list[Clause] = []
    cursor = 0
    for p in paras:
        offset = text.find(p[:60], cursor)
        offset = cursor if offset < 0 else offset
        cursor = offset + len(p)
        clauses.append(
            Clause(
                cid=f"c{len(clauses) + 1}",
                number=str(len(clauses) + 1),
                heading=_guess_heading(p),
                text=p,
                page=_page_for(offset, bounds, total_pages),
                start=offset,
                end=offset + len(p),
            )
        )
    return clauses


def load(path: str | Path) -> Contract:
    p = Path(path)
    raw, pages = extract(p)
    if len(raw.strip()) < MIN_USEFUL_CHARS:
        raise DocumentTooShort(
            f"Only {len(raw.strip())} characters were extracted - too short to "
            "review. RedPen needs the full agreement, not a cover page."
        )
    clauses = segment(raw, pages)
    warnings: list[str] = []
    if len(clauses) < 3:
        warnings.append(
            "Clause numbering was not detected, so paragraphs were used as "
            "clauses. Check the boundaries before relying on them."
        )
    return Contract(name=p.stem, source=str(p), text=raw, pages=pages,
                    clauses=clauses, warnings=warnings)


def load_text(name: str, raw: str) -> Contract:
    """Review pasted text -- the path a freelancer on a phone would use."""
    if len(raw.strip()) < MIN_USEFUL_CHARS:
        raise DocumentTooShort(
            "Paste the whole agreement. There is not enough text here to review."
        )
    pages = 1
    clauses = segment(raw, pages)
    warnings: list[str] = []
    if len(clauses) < 3:
        warnings.append("Clause numbering was not detected; paragraph splits are approximate.")
    return Contract(name=name, source="pasted text", text=raw, pages=pages,
                    clauses=clauses, warnings=warnings)
