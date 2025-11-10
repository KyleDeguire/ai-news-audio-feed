#!/usr/bin/env python3
"""
scripts/compose_transcript.py
Builds HTML + DOCX + subject line for transcript email.
"""

import json, os
from pathlib import Path
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn

AUDIO_DIR = Path("audio")

def denver_date_today():
    import pytz, datetime as dt
    tz = pytz.timezone('America/Denver')
    return dt.datetime.now(tz).date()

def short_date_for_subject(d):
    return d.strftime("%d %b %y")  # e.g., 09 Nov 25

def latest_json():
    files = sorted(AUDIO_DIR.glob("ai_news_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

# --------------------------------------------------
# HTML builder (email body)
# --------------------------------------------------

def build_email_html(sections, footnotes):
    html_parts = [
        "<div style=\"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:15px;line-height:1.6;color:#111;\">"
    ]

    for sec in sections:
        if isinstance(sec, str):
            # Just a string (malformed section) – skip or show safely
            html_parts.append(f"<p>{sec}</p>")
            continue

        if not isinstance(sec, dict):
            continue

        title = (sec.get("title") or "").strip()
        if title:
            html_parts.append(f"<p style='margin:0 0 8px 0;'><strong>{title.title()}</strong></p>")

        paragraphs = sec.get("paragraphs", [])
        if isinstance(paragraphs, str):
            html_parts.append(f"<p>{paragraphs.strip()}</p>")
            continue

        for para in paragraphs:
            if isinstance(para, str):
                html_parts.append(f"<p>{para.strip()}</p>")
                continue
            if not isinstance(para, dict):
                continue

            sentences = para.get("sentences", [])
            if not isinstance(sentences, list):
                sentences = [sentences]

            para_texts = []
            for s in sentences:
                if isinstance(s, dict):
                    txt = (s.get("text") or "").strip()
                    srcs = s.get("sources") or []
                    sup = f"<sup>{','.join(str(i) for i in srcs)}</sup>" if srcs else ""
                    if txt:
                        para_texts.append(f"{txt}{sup}")
                elif isinstance(s, str) and s.strip():
                    para_texts.append(s.strip())
            if para_texts:
                html_parts.append(f"<p>{' '.join(para_texts)}</p>")

    # ---- Sources ----
    if footnotes:
        html_parts.append("<hr><p><strong>Sources</strong></p><ul>")
        for f in footnotes:
            iid = f.get("id")
            ttl = (f.get("title") or "").strip()
            url = (f.get("url") or "").strip()
            if not url:
                continue
            label = f"[{iid}]" if iid else "-"
            if ttl:
                html_parts.append(f"<li>{label} {ttl} — <a href='{url}'>{url}</a></li>")
            else:
                html_parts.append(f"<li>{label} <a href='{url}'>{url}</a></li>")
        html_parts.append("</ul>")

    html_parts.append("</div>")
    return "\n".join(html_parts)

# --------------------------------------------------
# DOCX builder
# --------------------------------------------------

def build_docx(docx_path: Path, sections, footnotes, subject_title):
    doc = Document()
    doc.core_properties.title = subject_title
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style._element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri')
    style.font.size = Pt(11)

    for sec in sections:
        if isinstance(sec, str):
            p = doc.add_paragraph(sec)
            p.paragraph_format.space_after = Pt(18)
            p.paragraph_format.line_spacing = 1.2
            continue

        if not isinstance(sec, dict):
            continue

        title = (sec.get("title") or "").strip()
        if title:
            t = doc.add_paragraph(title.title())
            t.runs[0].bold = True
            t.paragraph_format.space_after = Pt(6)

        paragraphs = sec.get("paragraphs", [])
        if isinstance(paragraphs, str):
            p = doc.add_paragraph(paragraphs.strip())
            p.paragraph_format.space_after = Pt(18)
            p.paragraph_format.line_spacing = 1.2
            continue

        for para in paragraphs:
            if isinstance(para, str):
                p = doc.add_paragraph(para.strip())
                p.paragraph_format.space_after = Pt(18)
                p.paragraph_format.line_spacing = 1.2
                continue
            if not isinstance(para, dict):
                continue

            sentences = para.get("sentences", [])
            if not isinstance(sentences, list):
                sentences = [sentences]

            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(18)
            p.paragraph_format.line_spacing = 1.2
            for s in sentences:
                if isinstance(s, dict):
                    txt = (s.get("text") or "").strip()
                    srcs = s.get("sources") or []
                    if txt:
                        r = p.add_run(txt + " ")
                        if srcs:
                            r2 = p.add_run(",".join(str(i) for i in srcs))
                            r2.font.superscript = True
                elif isinstance(s, str) and s.strip():
                    p.add_run(s.strip() + " ")

    # ---- Sources ----
    if footnotes:
        doc.add_paragraph().add_run("Sources").bold = True
        for f in footnotes:
            iid = f.get("id")
            ttl = (f.get("title") or "").strip()
            url = (f.get("url") or "").strip()
            if not url:
                continue
            line = f"[{iid}] {ttl} — {url}" if ttl else f"[{iid}] {url}"
            p = doc.add_paragraph(line)
            p.paragraph_format.space_after = Pt(18)
            p.paragraph_format.line_spacing = 1.2

    doc.save(docx_path)

# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    jpath = latest_json()
    if not jpath:
        raise SystemExit("No JSON transcript found in audio/. Run generate_brief.py first.")

    data = json.loads(jpath.read_text(encoding="utf-8"))
    sections = data.get("sections") or []
    footnotes = data.get("footnotes") or []

    today = denver_date_today()
    short = short_date_for_subject(today)
    subject = f"AI Exec Brief (transcript) - {short}"

    html_path = AUDIO_DIR / f"ai_news_{short.replace(' ', '').lower()}.html"
    docx_path = AUDIO_DIR / f"{subject}.docx"

    html = build_email_html(sections, footnotes)
    html_path.write_text(html, encoding="utf-8")

    build_docx(docx_path, sections, footnotes, subject)

    print(f"HTML_BODY={html_path}")
    print(f"DOCX_PATH={docx_path}")
    print(f"SUBJECT_LINE={subject}")

if __name__ == "__main__":
    main()
