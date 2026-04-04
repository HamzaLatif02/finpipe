"""
Standalone SMTP smoke-test.

Usage (from project root):
    python test_email.py

Loads credentials from .env and attempts to send a plain-text email
to lhamza1020@gmail.com via Gmail SMTP with STARTTLS on port 587.

Common failure causes:
  - SMTP_PASSWORD is your regular Gmail password → must be a 16-char
    App Password (Google Account → Security → 2-Step Verification →
    App Passwords).  2FA must be enabled first.
  - SMTP_USER / SMTP_PASSWORD not set in .env at all.
  - Port 587 blocked by a firewall (try SMTP_PORT=465 + smtplib.SMTP_SSL).
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

HOST     = os.getenv("SMTP_HOST",     "smtp.gmail.com")
PORT     = int(os.getenv("SMTP_PORT", 587))
USER     = os.getenv("SMTP_USER",     "")
PASSWORD = os.getenv("SMTP_PASSWORD", "")
TO       = "lhamza1020@gmail.com"

print(f"SMTP_HOST : {HOST}")
print(f"SMTP_PORT : {PORT}")
print(f"SMTP_USER : {USER!r}")
print(f"SMTP_PASSWORD set: {bool(PASSWORD)} (length {len(PASSWORD)})")
print(f"Sending to: {TO}")
print()

if not USER or not PASSWORD:
    print("ERROR: SMTP_USER or SMTP_PASSWORD is not set in .env")
    raise SystemExit(1)

msg            = MIMEMultipart()
msg["From"]    = USER
msg["To"]      = TO
msg["Subject"] = "SMTP Test — Finpipe"
msg.attach(MIMEText(
    "This is a test email from the Finpipe financial pipeline.\n\n"
    "If you received this, SMTP delivery is working correctly.",
    "plain",
))

try:
    print("Connecting …")
    with smtplib.SMTP(HOST, PORT, timeout=30) as server:
        server.set_debuglevel(1)       # print SMTP conversation
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(USER, PASSWORD)
        server.send_message(msg)
    print("\nSUCCESS — email sent to", TO)
except smtplib.SMTPAuthenticationError as exc:
    print(f"\nAUTH FAILED: {exc}")
    print(
        "\nMost likely cause: SMTP_PASSWORD is your regular Gmail password.\n"
        "You need a 16-character App Password:\n"
        "  Google Account → Security → 2-Step Verification → App Passwords\n"
        "2FA must be enabled on the account first."
    )
    raise SystemExit(1)
except Exception as exc:
    print(f"\nFAILED: {exc}")
    raise SystemExit(1)
