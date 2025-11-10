#!/usr/bin/env python3
import json
from pathlib import Path
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
import base64
import datetime as dt
import pytz

AUDIO_DIR = Path("audio")

def today_short():
    tz = pytz.timezone("America/Denver")
    d = dt.datetime.now(tz).date()
    return d.strftime("%d %b %y")  # 09 Nov 25

def load_latest_json() -> Path:
    files = sorted(AUDIO_DIR.glob("ai_news_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise SystemExit("No ai_news_*.json found. Run generate_brief.py first.")
    return files[0]

def html_superscript(ids):
    if not ids: return ""
    return f"<sup>{','.join(str(i) for i in ids)}</sup>"

def join_sentences(sentences):
    return " ".join([s.get("text","").strip() for s in sentences if s.get("text")]).strip()

def build_email_html(sections, footnotes):
    parts = ['<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial,sans-serif;font-size:15px;line-height:1.6;color:#111;">']

    # Intro line mirrors the audio open, then the five sections
    # Each section -> one or two <p> blocks (paragraphs)
    for sec in sections:
        # Optional small bold section label for readability (keeps it professional)
        parts.append(f'<p style="margin:0 0 8px 0;"><strong>{sec.get("title","").title()}</strong></p>')
        for para in sec.get("paragraphs", []):
            s_html = []
            for s in para.get("sentences", []):
                text = (s.get("text") or "").strip()
                if not text: continue
                s_html.append(text + html_superscript(s.get("sources") or []))
            if s_html:
                parts.append(f'<p style="margin:0 0 18px 0;">{" ".join(s_html)}</p>')

    # Footnotes
    if footnotes:
        parts.append('<hr style="border:none;border-top:1px solid #e5e7eb;margin:10px 0 12px 0;">')
        parts.append('<p style="margin:0 0 6px 0;"><strong>Sources</strong></p>')
        parts.append('<ul style="margin:0 0 18px 18px;padding:0;">')
        for f in footnotes:
            iid = f.get("id"); ttl = (f.get("title") or "").strip(); url = (f.get("url") or "").strip()
            if not url: continue
            label = f"[{iid}]" if iid is not None else "-"
            safe_ttl = ttl if ttl else url
            parts.append(f'<li style="margin-bottom:6px;">{label} {safe_ttl} — <a href="{url}">{url}</a></li>')
        parts.append('</ul>')

    parts.append("</div>")
    return "\n".join(parts)

def build_docx(docx_path: Path, sections, footnotes):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style._element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri')
    style.font.size = Pt(11)

    def pformat(p):
        pf = p.paragraph_format
        pf.space_after = Pt(18)
        pf.line_spacing = 1.2

    # Sections and paragraphs
    for sec in sections:
        title = (sec.get("title") or "").title()
        if title:
            p = doc.add_paragraph()
            pformat(p)
            r = p.add_run(title)
            r.bold = True

        for para in sec.get("paragraphs", []):
            p = doc.add_paragraph()
            pformat(p)
            # sentence runs with superscript numbers
            for idx, s in enumerate(para.get("sentences", [])):
                text = (s.get("text") or "").strip()
                if not text: continue
                if idx > 0:
                    docx_run = p.add_run(" ")
                r = p.add_run(text)
                srcs = s.get("sources") or []
                if srcs:
                    r2 = p.add_run(" " + ",".join(str(i) for i in srcs))
                    r2.font.superscript = True

    if footnotes:
        p = doc.add_paragraph()
        pformat(p)
        r = p.add_run("Sources")
        r.bold = True
        for f in footnotes:
            iid = f.get("id"); ttl = (f.get("title") or "").strip(); url = (f.get("url") or "").strip()
            if not url: continue
            p = doc.add_paragraph(f"[{iid}] {ttl or url} — {url}")
            pformat(p)

    doc.save(docx_path)

def main():
    jpath = load_latest_json()
    data = json.loads(jpath.read_text(encoding="utf-8"))
    sections = data.get("sections", [])
    footnotes = data.get("footnotes", [])

    short = today_short()
    base_friendly = f"AI Exec Brief (transcript) - {short}"
    html_path = AUDIO_DIR / (jpath.stem + ".html")  # keep an html artifact with stamp name
    docx_path = AUDIO_DIR / f"{base_friendly}.docx"

    html = build_email_html(sections, footnotes)
    html_path.write_text(html, encoding="utf-8")
    build_docx(docx_path, sections, footnotes)

    # Print for workflow step parsing
    print(f"HTML_BODY_PATH={html_path}")
    print(f"DOCX_PATH={docx_path}")
    print(f"SUBJECT_LINE={base_friendly}")

if __name__ == "__main__":
    main()
