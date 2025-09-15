#!/usr/bin/env python3
import re, sys
from pathlib import Path
from docx import Document
from docx.oxml.shared import OxmlElement, qn
from docx.shared import Pt
from docx.text.run import Run

URL_RE = re.compile(r"(https?://\S+)", re.IGNORECASE)

def add_hyperlink(paragraph, url, text=None):
    """Create a clickable hyperlink in a paragraph."""
    if text is None:
        text = url
    # This part (rId) is handled by docx relationship
    part = paragraph.part
    r_id = part.relate_to(url,  # type: ignore[attr-defined]
                          reltype="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                          is_external=True)
    # Build w:hyperlink
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    # Build w:r
    new_run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")

    # Style: blue + underline like a link
    u = OxmlElement("w:u"); u.set(qn("w:val"), "single")
    color = OxmlElement("w:color"); color.set(qn("w:val"), "0000FF")
    r_pr.append(u); r_pr.append(color)
    new_run.append(r_pr)

    # The text node
    t = OxmlElement("w:t")
    t.text = text
    new_run.append(t)
    hyperlink.append(new_run)

    paragraph._p.append(hyperlink)  # noqa

def write_paragraph_with_links(doc, line: str):
    """Write a line, converting URLs to active hyperlinks."""
    p = doc.add_paragraph()
    pos = 0
    for m in URL_RE.finditer(line):
        # text before the URL
        if m.start() > pos:
            p.add_run(line[pos:m.start()])
        url = m.group(1).rstrip(").,;]")  # trim common trailing punct
        add_hyperlink(p, url)
        pos = m.end()
    # trailing text
    if pos < len(line):
        p.add_run(line[pos:])

def main():
    if len(sys.argv) < 3:
        print("Usage: make_docx.py <input.txt> <output.docx>", file=sys.stderr)
        sys.exit(1)

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    txt = in_path.read_text(encoding="utf-8", errors="ignore")

    doc = Document()
    # Optional: slightly nicer base font
    style = doc.styles["Normal"].font
    style.name = "Calibri"
    style.size = Pt(11)

    # Basic rule: preserve blank lines as paragraph breaks
    for line in txt.splitlines():
        if line.strip() == "":
            doc.add_paragraph("")  # blank line
        else:
            write_paragraph_with_links(doc, line)

    doc.save(out_path)
    print(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
