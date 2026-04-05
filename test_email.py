"""
Resend email smoke-test.

Usage (from project root):
    python test_email.py

Loads RESEND_API_KEY from .env and sends a plain-text test email to
lhamza1020@gmail.com via the Resend HTTPS API.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import resend

api_key = os.getenv("RESEND_API_KEY", "")
to      = "lhamza1020@gmail.com"

print(f"RESEND_API_KEY set: {bool(api_key)} (length {len(api_key)})")
print(f"Sending to: {to}")
print()

if not api_key:
    print("ERROR: RESEND_API_KEY is not set in .env")
    sys.exit(1)

resend.api_key = api_key

try:
    response = resend.Emails.send({
        "from":    "Financial Pipeline <onboarding@resend.dev>",
        "to":      [to],
        "subject": "Resend Test — Finpipe",
        "text":    (
            "This is a test email from the Finpipe financial pipeline.\n\n"
            "If you received this, Resend delivery is working correctly."
        ),
    })
    print("SUCCESS — email sent, Resend id:", response["id"])
except Exception as exc:
    print(f"FAILED: {exc}")
    sys.exit(1)
