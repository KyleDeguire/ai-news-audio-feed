#!/usr/bin/env python3
from pathlib import Path
import argparse
from docx import Document

def parse_args():
    p = argparse.ArgumentParser(description="Build a .docx from a transcript text file.")
    # Accept BOTH styles so YAML changes don’t break again.
    p.add_argument("--in", "--input", dest="input", required=True, help="Path to transcript .txt")
    p.add_argument("--out", "--output", dest="output", required=True, help="Path to write .docx")
    return p.parse_args()

def main():
    args = parse_args()
    in_path = Path(args.input)
    out_path = Path(args.output)

    if not in_path.exists():
        raise FileNotFoundError(f"Input transcript not found: {in_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    txt = in_path.read_text(encoding="utf-8", errors="ignore")

    doc = Document()
    doc.core_properties.title = out_path.stem
    # Simple, robust: one paragraph per line (URLs will be clickable in Word)
    for line in txt.splitlines():
        doc.add_paragraph(line)

    doc.save(out_path)

if __name__ == "__main__":
    main()
