"""Builds PDF versions of the sample contracts so page-number grounding is
exercised for real, not just asserted on a single-page text file.

Run: python samples/make_pdfs.py
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

HERE = Path(__file__).parent
WIDTH, HEIGHT = 595, 842          # A4 portrait
MARGIN, LEAD = 54, 15


def build(text: str) -> pymupdf.PdfDocument:
    doc = pymupdf.open()
    lines: list[str] = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        while len(para) > 88:
            cut = para.rfind(" ", 0, 88)
            cut = cut if cut > 40 else 88
            lines.append(para[:cut])
            para = para[cut + 1:]
        lines.append(para)

    page = doc.new_page(width=WIDTH, height=HEIGHT)
    y = MARGIN
    for line in lines:
        if y > HEIGHT - MARGIN:
            page = doc.new_page(width=WIDTH, height=HEIGHT)
            y = MARGIN
        if line.strip():
            page.insert_text((MARGIN, y), line, fontsize=9.5, fontname="helv")
        y += LEAD
    return doc


def main() -> None:
    for src in sorted(HERE.glob("*.txt")):
        text = src.read_text()
        out = src.with_suffix(".pdf")
        doc = build(text)
        doc.save(out, garbage=3, deflate=True)
        print(f"{src.name} -> {out.name} ({doc.page_count} pages)")
        doc.close()


if __name__ == "__main__":
    main()
