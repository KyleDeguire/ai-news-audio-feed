#!/usr/bin/env python3
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
    return d.strftime("%d %b %y")  # e.g., 27 Sep 25

def latest_json():
    files = sorted(AUDIO_DIR.glob("ai_news_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def build_email_html(sentences, footnotes):
    # Create paragraphs with superscripts
    paras = []
    for s in sentences:
        text = (s.get("text") or "").strip()
        srcs = s.get("sources") or []
        sup = f"<sup>{','.join(str(i) for i in srcs)}</sup>" if srcs else ""
        if text:
            paras.append(f"<p>{text}{sup}</p>")

    # Footnotes list
    foot = []
    if footnotes:
        foot.append("<hr>")
        foot.append("<p><strong>Sources</strong></p>")
        foot.append("<ul>")
        for f in footnotes:
            iid = f.get("id"); ttl = (f.get("title") or "").strip(); url = (f.get("url") or "").strip()
            if not url: continue
            label = f"[{iid}]" if iid is not None else "-"
            if ttl:
                foot.append(f'<li>{label} {ttl} — <a href="{url}">{url}</a></li>')
            else:
                foot.append(f'<li>{label} <a href="{url}">{url}</a></li>')
        foot.append("</ul>")

    html = """<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:15px;line-height:1.6;">"""
    html += "\n".join(paras + foot)
    html += "</div>"
    return html

def build_docx(docx_path: Path, sentences, footnotes):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style._element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri')
    style.font.size = Pt(11)

    for s in sentences:
        text = (s.get("text") or "").strip()
        srcs = s.get("sources") or []
        if not text: continue
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_after = Pt(18)
        pf.line_spacing = 1.2
        r = p.add_run(text)
        if srcs:
            r2 = p.add_run(" " + ",".join(str(i) for i in srcs))
            r2.font.superscript = True

    if footnotes:
        doc.add_paragraph().add_run("Sources").bold = True
        for f in footnotes:
            iid = f.get("id"); ttl = (f.get("title") or "").strip(); url = (f.get("url") or "").strip()
            if not url: continue
            line = f"[{iid}] {ttl} — {url}" if ttl else f"[{iid}] {url}"
            p = doc.add_paragraph(line)
            p.paragraph_format.space_after = Pt(18)
            p.paragraph_format.line_spacing = 1.2

    doc.save(docx_path)

def main():
    jpath = latest_json()
    if not jpath:
        raise SystemExit("No JSON transcript found in audio/. Run generate_brief.py first.")
    data = json.loads(jpath.read_text(encoding="utf-8"))
    sentences = data.get("sentences") or []
    footnotes = data.get("footnotes") or []

    today = denver_date_today()
    short = short_date_for_subject(today)
    base = jpath.stem
    html_path = AUDIO_DIR / f"{base}.html"
    docx_path = AUDIO_DIR / f"{base}.docx"
    subject = f"AI Exec Brief (transcript) - {short}"

    html = build_email_html(sentences, footnotes)
    html_path.write_text(html, encoding="utf-8")
    build_docx(docx_path, sentences, footnotes)

    # Output info for GitHub Actions
    print(f"HTML_BODY={html_path}")
    print(f"DOCX_PATH={docx_path}")
    print(f"SUBJECT_LINE={subject}")

if __name__ == "__main__":
    main()
