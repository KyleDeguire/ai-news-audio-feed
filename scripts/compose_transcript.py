#!/usr/bin/env python3
# scripts/compose_transcript.py
# Builds the HTML email body and the Word doc from the JSON produced by generate_brief.py

import json
import os
from pathlib import Path
from typing import Any, Dict, List
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from datetime import datetime
import pytz
import html

AUDIO_DIR = Path("audio")

# ---------- time helpers ----------
def denver_today():
    tz = pytz.timezone("America/Denver")
    return datetime.now(tz)

def short_date_for_subject(dt: datetime) -> str:
    # e.g., 10 Nov 25
    return dt.strftime("%d %b %y")

# ---------- loading ----------
def latest_json_path() -> Path:
    files = sorted(AUDIO_DIR.glob("ai_news_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))

# ---------- normalization ----------
def normalize_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    We accept any of these shapes and normalize to:
    {
      "sections":[
        {"title":"...", "paragraphs":[{"text":"...", "sources":[1,2]}, ...]}
      ],
      "footnotes":[{"id":1,"title":"...","url":"..."}]
    }
    Fallbacks:
      - if only 'spoken' string exists, split into paragraphs on blank lines.
      - if 'sections' entries are strings, treat as titles with no paragraphs.
      - if paragraph items are strings, wrap as {"text": "...", "sources":[]}
    """
    out = {"sections": [], "footnotes": []}

    # Footnotes
    fns = data.get("footnotes") or []
    cleaned_fns = []
    for i, f in enumerate(fns, start=1):
        if isinstance(f, dict):
            fid = f.get("id") if isinstance(f.get("id"), int) else i
            ttl = (f.get("title") or "").strip()
            url = (f.get("url") or "").strip()
            if url:
                cleaned_fns.append({"id": fid, "title": ttl, "url": url})
    out["footnotes"] = cleaned_fns

    # Sections (preferred)
    sections = data.get("sections")
    if isinstance(sections, list) and sections:
        norm_sections = []
        for sec in sections:
            if isinstance(sec, str):
                norm_sections.append({"title": sec, "paragraphs": []})
                continue
            if not isinstance(sec, dict):
                continue
            title = (sec.get("title") or "").strip()
            raw_paras = sec.get("paragraphs") or []
            paras = []
            for para in raw_paras:
                if isinstance(para, str):
                    text = para.strip()
                    if text:
                        paras.append({"text": text, "sources": []})
                elif isinstance(para, dict):
                    text = (para.get("text") or "").strip()
                    sources = para.get("sources") or []
                    if text:
                        # sanitize sources -> list[int]
                        norm_src = []
                        for s in sources:
                            try:
                                norm_src.append(int(s))
                            except Exception:
                                pass
                        paras.append({"text": text, "sources": norm_src})
            norm_sections.append({"title": title, "paragraphs": paras})
        out["sections"] = norm_sections

    # Fallback to 'spoken' if sections are empty
    if not out["sections"]:
        spoken = (data.get("spoken") or "").strip()
        if spoken:
            # split on blank lines into paragraphs
            chunks: List[str] = []
            buff: List[str] = []
            for line in spoken.splitlines():
                if line.strip():
                    buff.append(line.strip())
                else:
                    if buff:
                        chunks.append(" ".join(buff))
                        buff = []
            if buff:
                chunks.append(" ".join(buff))
            if not chunks:
                # single paragraph fallback
                chunks = [spoken]

            out["sections"] = [
                {
                    "title": "",  # no headings when we only have spoken text
                    "paragraphs": [{"text": c, "sources": []} for c in chunks],
                }
            ]

    return out

# ---------- HTML (email body) ----------
def build_email_html(sections: List[Dict[str, Any]], footnotes: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    parts.append("<div style=\"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:15px;line-height:1.6;\">")

    for sec in sections:
        title = (sec.get("title") or "").strip()
        if title:
            parts.append(f"<p style='margin:0 0 8px 0'><strong>{html.escape(title)}</strong></p>")
        for para in sec.get("paragraphs", []):
            text = (para.get("text") or "").strip()
            srcs = para.get("sources") or []
            sup = f"<sup>{','.join(str(int(s)) for s in srcs if isinstance(s,(int,str)))}</sup>" if srcs else ""
            if text:
                parts.append(f"<p style='margin:0 0 18px 0'>{html.escape(text)}{sup}</p>")

    if footnotes:
        parts.append("<hr style='margin:8px 0 8px 0;border:none;border-top:1px solid #e4e7ef'>")
        parts.append("<p style='margin:0 0 6px 0'><strong>Sources</strong></p>")
        parts.append("<ul style='margin:0 0 0 18px;padding:0'>")
        for f in footnotes:
            iid = f.get("id")
            ttl = (f.get("title") or "").strip()
            url = (f.get("url") or "").strip()
            if not url:
                continue
            label = f"[{iid}]" if iid is not None else "-"
            safe_t = html.escape(ttl) if ttl else ""
            safe_u = html.escape(url)
            if safe_t:
                parts.append(f"<li>{label} {safe_t} — <a href=\"{safe_u}\">{safe_u}</a></li>")
            else:
                parts.append(f"<li>{label} <a href=\"{safe_u}\">{safe_u}</a></li>")
        parts.append("</ul>")

    parts.append("</div>")
    return "".join(parts)

# ---------- DOCX ----------
def build_docx(docx_path: Path, sections: List[Dict[str, Any]], footnotes: List[Dict[str, Any]]):
    doc = Document()
    # Normal style
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    style.font.size = Pt(11)

    def apply_para_spacing(p):
        pf = p.paragraph_format
        pf.space_after = Pt(18)
        pf.line_spacing = 1.2

    # Body
    for sec in sections:
        title = (sec.get("title") or "").strip()
        if title:
            p = doc.add_paragraph()
            r = p.add_run(title)
            r.bold = True
            apply_para_spacing(p)

        for para in sec.get("paragraphs", []):
            text = (para.get("text") or "").strip()
            if not text:
                continue
            srcs = para.get("sources") or []
            p = doc.add_paragraph()
            r1 = p.add_run(text)
            if srcs:
                r2 = p.add_run(" " + ",".join(str(int(s)) for s in srcs if isinstance(s,(int,str))))
                r2.font.superscript = True
            apply_para_spacing(p)

    # Footnotes
    if footnotes:
        p = doc.add_paragraph()
        r = p.add_run("Sources")
        r.bold = True
        apply_para_spacing(p)

        for f in footnotes:
            iid = f.get("id")
            ttl = (f.get("title") or "").strip()
            url = (f.get("url") or "").strip()
            if not url:
                continue
            line = f"[{iid}] {ttl} — {url}" if ttl else f"[{iid}] {url}"
            p = doc.add_paragraph(line)
            apply_para_spacing(p)

    doc.save(docx_path)

# ---------- main ----------
def main():
    jpath = latest_json_path()
    if not jpath:
        raise SystemExit("No ai_news_*.json found in audio/. Run generate_brief.py first.")

    data = load_json(jpath)
    norm = normalize_payload(data)

    sections = norm["sections"]
    footnotes = norm["footnotes"]

    # Subject + filenames
    today = denver_today()
    subject = f"AI Exec Brief (transcript) - {short_date_for_subject(today)}"
    base_filename = f"AI Exec Brief (transcript) - {short_date_for_subject(today)}"
    html_path = AUDIO_DIR / f"{base_filename}.html"
    docx_path = AUDIO_DIR / f"{base_filename}.docx"

    # Build artifacts
    html_body = build_email_html(sections, footnotes)
    html_path.write_text(html_body, encoding="utf-8")
    build_docx(docx_path, sections, footnotes)

    # Emit outputs for the workflow step to pick up
    print(f"HTML_BODY={html_path}")
    print(f"DOCX_PATH={docx_path}")
    print(f"SUBJECT_LINE={subject}")

if __name__ == "__main__":
    main()
