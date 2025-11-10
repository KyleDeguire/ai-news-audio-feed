#!/usr/bin/env python3
import json, os, re
from pathlib import Path
from typing import List, Dict, Any
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn

AUDIO_DIR = Path("audio")

# ---------- helpers ----------
def denver_date_today():
    import pytz, datetime as dt
    tz = pytz.timezone('America/Denver')
    return dt.datetime.now(tz).date()

def short_date_for_subject(d):
    return d.strftime("%d %b %y")

def latest_json():
    files = sorted(AUDIO_DIR.glob("ai_news_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def flatten_paragraph(para_obj):
    """
    Handle multiple formats:
    - {"text": "...", "sources": [1,2]}
    - {"sentences": [{"text":"...", "sources":[]}]}
    - "plain string"
    Returns: (text, sources_list)
    """
    if isinstance(para_obj, str):
        return para_obj.strip(), []
    
    if not isinstance(para_obj, dict):
        return "", []
    
    # Format 1: {"sentences": [...]}
    if "sentences" in para_obj:
        sentences = para_obj.get("sentences", [])
        if not isinstance(sentences, list):
            return "", []
        
        all_text = []
        all_sources = []
        for sent in sentences:
            if isinstance(sent, dict):
                txt = (sent.get("text") or "").strip()
                srcs = sent.get("sources") or []
                if txt:
                    all_text.append(txt)
                if srcs:
                    all_sources.extend([int(x) for x in srcs if str(x).isdigit()])
            elif isinstance(sent, str):
                txt = sent.strip()
                if txt:
                    all_text.append(txt)
        
        combined = " ".join(all_text)
        unique_sources = sorted(set(all_sources))
        return combined, unique_sources
    
    # Format 2: {"text": "...", "sources": [...]}
    text = (para_obj.get("text") or "").strip()
    srcs = para_obj.get("sources") or []
    try:
        srcs = [int(x) for x in srcs if str(x).isdigit()]
    except:
        srcs = []
    return text, srcs

def normalize_sections(data: Dict[str, Any]) -> (List[Dict[str, Any]], List[Dict[str, Any]]):
    """
    Returns (sections, footnotes).
    Handles both array and dict formats for sections.
    """
    footnotes = data.get("footnotes") or []
    sections = data.get("sections")

    # Handle dict-style sections: {"TITLE": [paragraphs], ...}
    if isinstance(sections, dict):
        normalized = []
        for title, paras in sections.items():
            if not isinstance(paras, list):
                paras = []
            normalized.append({"title": title, "paragraphs": paras})
        return normalized, footnotes

    # Handle array-style sections: [{"title": "...", "paragraphs": [...]}, ...]
    if isinstance(sections, list):
        normalized = []
        for sec in sections:
            if isinstance(sec, dict):
                title = (sec.get("title") or "").strip()
                paras = sec.get("paragraphs") or []
            else:
                title = str(sec).strip()
                paras = []
            normalized.append({"title": title, "paragraphs": paras})
        return normalized, footnotes

    # Fallback: no sections, try spoken text
    spoken = (data.get("spoken") or "").strip()
    paras = [p.strip() for p in re.split(r"\n\s*\n", spoken) if p.strip()]
    return [{"title": "", "paragraphs": paras}], footnotes

# ---------- HTML / DOCX builders ----------
def build_email_html(sections, footnotes):
    parts = []
    parts.append("<div style=\"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:15px;line-height:1.6;\">")

    for sec in sections:
        title = (sec.get("title") or "").strip()
        if title:
            parts.append(f'<p style="margin:0 0 8px 0;"><strong>{title}</strong></p>')
        
        for para_obj in sec.get("paragraphs", []):
            text, srcs = flatten_paragraph(para_obj)
            if not text:
                continue
            sup = f"<sup>{','.join(str(i) for i in srcs)}</sup>" if srcs else ""
            parts.append(f'<p style="margin:0 0 18px 0;">{text}{sup}</p>')

    if footnotes:
        parts.append('<hr style="border:none;border-top:1px solid #e5e7eb;margin:10px 0 12px;">')
        parts.append('<p style="margin:0 0 6px 0;"><strong>Sources</strong></p>')
        parts.append('<ul style="margin:0 0 18px 18px; padding:0;">')
        for f in footnotes:
            iid = f.get("id")
            ttl = (f.get("title") or "").strip()
            url = (f.get("url") or "").strip()
            if not url:
                continue
            label = f"[{iid}]" if iid is not None else "-"
            if ttl:
                parts.append(f'<li style="margin:0 0 6px 0;">{label} {ttl} — <a href="{url}">{url}</a></li>')
            else:
                parts.append(f'<li style="margin:0 0 6px 0;">{label} <a href="{url}">{url}</a></li>')
        parts.append('</ul>')

    parts.append("</div>")
    return "".join(parts)

def build_docx(docx_path: Path, sections, footnotes):
    doc = Document()
    base = doc.styles['Normal']
    base.font.name = 'Calibri'
    base._element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri')
    base.font.size = Pt(11)

    def apply_pfmt(p):
        pf = p.paragraph_format
        pf.space_after = Pt(18)
        pf.line_spacing = 1.2

    for sec in sections:
        title = (sec.get("title") or "").strip()
        if title:
            ptitle = doc.add_paragraph()
            r = ptitle.add_run(title)
            r.bold = True
            apply_pfmt(ptitle)
        
        for para_obj in sec.get("paragraphs", []):
            text, srcs = flatten_paragraph(para_obj)
            if not text:
                continue
            p = doc.add_paragraph()
            r = p.add_run(text)
            if srcs:
                r2 = p.add_run(" " + ",".join(str(i) for i in srcs))
                r2.font.superscript = True
            apply_pfmt(p)

    if footnotes:
        p = doc.add_paragraph()
        r = p.add_run("Sources")
        r.bold = True
        apply_pfmt(p)
        for f in footnotes:
            iid = f.get("id")
            ttl = (f.get("title") or "").strip()
            url = (f.get("url") or "").strip()
            if not url:
                continue
            line = f"[{iid}] {ttl} — {url}" if ttl else f"[{iid}] {url}"
            p = doc.add_paragraph(line)
            apply_pfmt(p)

    doc.save(docx_path)

def main():
    jpath = latest_json()
    if not jpath:
        raise SystemExit("No JSON transcript found in audio/. Run generate_brief.py first.")

    data = json.loads(jpath.read_text(encoding="utf-8"))
    sections, footnotes = normalize_sections(data)

    today = denver_date_today()
    subject = f"AI Exec Brief (transcript) - {short_date_for_subject(today)}"

    out_base = f"AI Exec Brief (transcript) - {short_date_for_subject(today)}"
    html_path = AUDIO_DIR / (out_base + ".html")
    docx_path = AUDIO_DIR / (out_base + ".docx")

    html = build_email_html(sections, footnotes)
    html_path.write_text(html, encoding="utf-8")
    build_docx(docx_path, sections, footnotes)

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
