# scripts/send_email.py
import os, mimetypes, smtplib, re
from pathlib import Path
from email.message import EmailMessage

SMTP_SERVER   = os.environ["SMTP_SERVER"]
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ["SMTP_USERNAME"]
SMTP_PASSWORD = os.environ["SMTP_PASSWORD"]
EMAIL_FROM    = os.environ["EMAIL_FROM"]
EMAIL_TO      = os.environ["EMAIL_TO"]
SUBJECT       = os.environ["EMAIL_SUBJECT"]
TXT_PATH      = Path(os.environ["TRANSCRIPT_TXT"])
DOCX_PATH     = Path(os.environ["TRANSCRIPT_DOCX"])
AUDIO_URL     = os.environ["AUDIO_URL"]
FEED_URL      = os.environ["FEED_URL"]
DATE_READABLE = os.environ["DATE_READABLE"]

# Read full transcript
body_text = TXT_PATH.read_text(encoding="utf-8", errors="replace")

def linkify_html(text: str) -> str:
    # basic escaping
    text = (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
    # turn URLs into links
    return re.sub(r'(https?://[^\s)]+)', r'<a href="\1">\1</a>', text)

header_text = (
    f"New episode transcript (.docx attached)\n\n"
    f"Episode date: {DATE_READABLE}\n"
    f"Feed: {FEED_URL}\n"
    f"Audio: {AUDIO_URL}\n\n"
    f"---- Transcript ----\n"
)

html_body = (
    "<p>New episode transcript (.docx attached)</p>"
    f"<p><strong>Episode date:</strong> {DATE_READABLE}<br>"
    f"<strong>Feed:</strong> <a href=\"{FEED_URL}\">{FEED_URL}</a><br>"
    f"<strong>Audio:</strong> <a href=\"{AUDIO_URL}\">{AUDIO_URL}</a></p>"
    "<hr>"
    "<pre style='white-space:pre-wrap;font-family:ui-monospace,Menlo,Consolas,monospace;'>"
    + linkify_html(body_text) +
    "</pre>"
)

msg = EmailMessage()
msg["From"] = EMAIL_FROM
msg["To"] = EMAIL_TO
msg["Subject"] = SUBJECT
msg.set_content(header_text + body_text)       # plain text
msg.add_alternative(html_body, subtype="html") # HTML

# attach .docx
mime, _ = mimetypes.guess_type(str(DOCX_PATH))
maintype, subtype = (mime or "application/octet-stream").split("/", 1)
with open(DOCX_PATH, "rb") as f:
    msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=DOCX_PATH.name)

# send
if SMTP_PORT == 465:
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as s:
        s.login(SMTP_USERNAME, SMTP_PASSWORD)
        s.send_message(msg)
else:
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USERNAME, SMTP_PASSWORD)
        s.send_message(msg)
