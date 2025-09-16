#!/usr/bin/env python3
import os
import sys
import ssl
import smtplib
import base64
import mimetypes
from pathlib import Path
from email.utils import formatdate, make_msgid
from email.headerregistry import Address
from email.message import EmailMessage

def get_env(name: str, default: str = "") -> str:
    v = os.getenv(name, default)
    return v.strip() if isinstance(v, str) else v

def coerce_port(val: str, fallback: int = 587) -> int:
    try:
        return int(str(val).strip())
    except Exception:
        return fallback

def build_body() -> str:
    """Prefer BODY; fall back to BODY_B64 (base64-encoded UTF-8 transcript)."""
    body = get_env("BODY", "")
    b64 = get_env("BODY_B64", "")
    if not body and b64:
        try:
            body = base64.b64decode(b64).decode("utf-8", errors="ignore")
        except Exception:
            body = "(Failed to decode transcript body.)"
    if not body:
        body = "(No transcript content provided.)"
    return body

def to_address(addr: str) -> str:
    # Accept 'Name <email>' or plain email; leave as-is for EmailMessage
    return addr.strip()

def attach_file(msg: EmailMessage, path: Path) -> None:
    ctype, encoding = mimetypes.guess_type(str(path))
    if ctype is None or encoding is not None:
        ctype = "application/octet-stream"
    maintype, subtype = ctype.split("/", 1)
    with path.open("rb") as f:
        data = f.read()
    msg.add_attachment(
        data,
        maintype=maintype,
        subtype=subtype,
        filename=path.name,
    )

def main() -> int:
    SMTP_SERVER   = get_env("SMTP_SERVER")
    SMTP_PORT     = coerce_port(get_env("SMTP_PORT", "587"))
    SMTP_USERNAME = get_env("SMTP_USERNAME")
    SMTP_PASSWORD = get_env("SMTP_PASSWORD")

    EMAIL_FROM    = get_env("EMAIL_FROM")
    EMAIL_TO_RAW  = get_env("EMAIL_TO")
    SUBJECT       = get_env("SUBJECT", "AI Executive Brief transcript")
    ATTACH_PATH   = get_env("ATTACH_PATH", "")

    if not (SMTP_SERVER and SMTP_USERNAME and SMTP_PASSWORD and EMAIL_FROM and EMAIL_TO_RAW):
        print("Missing required email environment variables.", file=sys.stderr)
        return 2

    recipients = [to_address(x) for x in EMAIL_TO_RAW.replace(";", ",").split(",") if x.strip()]
    if not recipients:
        print("No recipients parsed from EMAIL_TO.", file=sys.stderr)
        return 2

    html_body = build_body()

    # Build message
    msg = EmailMessage()
    msg["Subject"] = SUBJECT
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    # Provide both plain and HTML (simple plain fallback)
    plain_body = html_body
    # Very light fallback strip for obvious tags (keeps it simple)
    plain_body = (plain_body
                  .replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
                  .replace("</p>", "\n\n").replace("<p>", "").replace("</p>", "")
                  .replace("&nbsp;", " "))

    msg.set_content(plain_body, charset="utf-8")
    msg.add_alternative(html_body, subtype="html", charset="utf-8")

    # Optional attachment
    if ATTACH_PATH:
        p = Path(ATTACH_PATH)
        if p.exists() and p.is_file():
            attach_file(msg, p)
        else:
            print(f"Warning: attachment not found: {ATTACH_PATH}", file=sys.stderr)

    # Send
    try:
        if SMTP_PORT == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)

        print(f"Email sent to {', '.join(recipients)}")
        return 0

    except Exception as e:
        print(f"Email send failed: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
