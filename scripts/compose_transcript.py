#!/usr/bin/env python3
import json, os, re
from pathlib import Path
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn

AUDIO_DIR = Path("audio")

SECTION_HEADERS = [
    "Introduction:",
    "New Products & Capabilities:",
    "Strategic Business Impact:",
    "Implementation Opportunities:",
    "Market Dynamics:",
    "Talent Market Shifts:"
]

def denver_date_today():
    import pytz, datetime as dt
    return dt.datetime.now(pytz.timezone('America/Denver')).date()

def short_date_for_subject(d):
    return d.strftime("%d %b %y")

def latest_json():
    files = sorted(AUDIO_DIR.glob("ai_news_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def parse_citations_for_html(text):
    def add_spaces(match):
        nums = match.group(1).replace(',', ', ')
        return f'<sup>{nums}</sup>'
    return re.sub(r'\[(\d+(?:,\d+)*)\]', add_spaces, text)

def parse_citations_for_docx(text):
    parts = []
    last_end = 0
    for match in re.finditer(r'\[(\d+(?:,\d+)*)\]', text):
        if match.start() > last_end:
            parts.append((text[last_end:match.start()], False))
        citation_text = match.group(1).replace(',', ', ')
        parts.append((citation_text, True))
        last_end = match.end()
    if last_end < len(text):
        parts.append((text[last_end:], False))
    return parts

def is_section_header(text):
    """Check if text is exactly a section header"""
    return text.strip() in SECTION_HEADERS

def build_email_html(spoken, footnotes):
    parts = []
    parts.append('<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,sans-serif;font-size:15px;line-height:1.6;">')
    
    paragraphs = [p.strip() for p in spoken.split('\n\n') if p.strip()]
    
    for para in paragraphs:
        if not para:
            continue
        
        # Check if this paragraph is ONLY a header
        if is_section_header(para):
            parts.append(f'<p style="margin:0 0 8px 0;"><strong>{para}</strong></p>')
        else:
            # Regular paragraph (might have citations)
            para_html = parse_citations_for_html(para)
            parts.append(f'<p style="margin:0 0 18px 0;">{para_html}</p>')
    
    if footnotes:
        parts.append('<hr style="border:none;border-top:1px solid #e5e7eb;margin:10px 0 12px;">')
        parts.append('<p style="margin:0 0 6px 0;"><strong>Sources</strong></p>')
        parts.append('<ul style="margin:0 0 18px 18px; padding:0;">')
        for f in footnotes:
            sid = f.get("id", "?")
            title = (f.get("title") or "").strip()
            url = (f.get("url") or "").strip()
            if url:
                if title:
                    parts.append(f'<li style="margin:0 0 6px 0;">[{sid}] {title} — <a href="{url}">{url}</a></li>')
                else:
                    parts.append(f'<li style="margin:0 0 6px 0;">[{sid}] <a href="{url}">{url}</a></li>')
        parts.append('</ul>')
    
    parts.append('</div>')
    return ''.join(parts)

def build_docx(docx_path, spoken, footnotes):
    doc = Document()
    base = doc.styles['Normal']
    base.font.name = 'Calibri'
    base._element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri')
    base.font.size = Pt(11)
    
    def apply_pfmt(p):
        pf = p.paragraph_format
        pf.space_after = Pt(18)
        pf.line_spacing = 1.2
    
    paragraphs = [p.strip() for p in spoken.split('\n\n') if p.strip()]
    
    for para_text in paragraphs:
        if not para_text:
            continue
        
        # Check if this is ONLY a section header
        if is_section_header(para_text):
            # Header paragraph - make it bold
            p = doc.add_paragraph()
            r = p.add_run(para_text)
            r.bold = True
            apply_pfmt(p)
        else:
            # Regular content paragraph - NO bold
            p = doc.add_paragraph()
            parts = parse_citations_for_docx(para_text)
            for text, is_citation in parts:
                r = p.add_run(text)
                if is_citation:
                    r.font.superscript = True
                # DO NOT set bold here
            apply_pfmt(p)
    
    if footnotes:
        p = doc.add_paragraph()
        r = p.add_run("Sources")
        r.bold = True
        apply_pfmt(p)
        
        for f in footnotes:
            sid = f.get("id", "?")
            title = (f.get("title") or "").strip()
            url = (f.get("url") or "").strip()
            if url:
                line = f"[{sid}] {title} — {url}" if title else f"[{sid}] {url}"
                p = doc.add_paragraph(line)
                apply_pfmt(p)
    
    doc.save(docx_path)

def main():
    jpath = latest_json()
    if not jpath:
        raise SystemExit("No JSON transcript found in audio/")
    
    data = json.loads(jpath.read_text(encoding="utf-8"))
    spoken = data.get("spoken", "").strip()
    footnotes = data.get("footnotes", [])
    
    if not spoken:
        raise SystemExit("Empty transcript in JSON")
    
    today = denver_date_today()
    subject = f"AI Exec Brief (transcript) - {short_date_for_subject(today)}"
    out_base = f"AI Exec Brief (transcript) - {short_date_for_subject(today)}"
    
    html_path = AUDIO_DIR / (out_base + ".html")
    docx_path = AUDIO_DIR / (out_base + ".docx")
    
    html = build_email_html(spoken, footnotes)
    html_path.write_text(html, encoding="utf-8")
    build_docx(docx_path, spoken, footnotes)
    
    lines = [
        f"HTML_BODY={html_path}",
        f"DOCX_PATH={docx_path}",
        f"SUBJECT_LINE={subject}",
    ]
    print("\n".join(lines))
    
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")

if __name__ == "__main__":
    main()
