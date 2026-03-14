#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

# Remove current directory from path to avoid shadowing stdlib email module
import sys
from pathlib import Path as _Path
_script_dir = str(_Path(__file__).parent.resolve())
sys.path = [p for p in sys.path if p not in ("", ".", _script_dir)]

import argparse
import os
import smtplib
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

CLI_EPILOG = '''\
Examples:
  email.py send --to "friend@example.com" --subject "Hello" --body "How are you?"
  email.py send --to "team@work.com" --subject "Update" --html "<h1>Status</h1><p>All good</p>"
  email.py send --to "boss@work.com" --subject "Report" --body "See attached" --attach report.pdf
  email.py send --to "a@ex.com,b@ex.com" --cc "c@ex.com" --subject "FYI" --body "Info"
  email.py send --to "user@ex.com" --subject "Doc" --body-file message.txt --attach doc.pdf
  email.py send --to "user@ex.com" --subject "Newsletter" --body "Plain text fallback" --html-file newsletter.html

Setup:
  1. Enable 2-Step Verification on your Google account
  2. Generate an App Password at https://myaccount.google.com/apppasswords
  3. Set environment variables:
     export GMAIL_USER="you@gmail.com"
     export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
'''


class GmailError(Exception):
    '''Custom exception for Gmail errors.'''
    pass


class GmailClient:
    '''SMTP client for sending emails via Gmail.'''

    def __init__(self, user: str, app_password: str):
        self.user = user
        self.app_password = app_password

    def send(
        self,
        to: list[str],
        subject: str,
        body_text: str | None = None,
        body_html: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[Path] | None = None,
        dry_run: bool = False,
    ) -> dict:
        '''Send an email via Gmail SMTP.'''

        # Build the message
        if attachments or (body_text and body_html):
            # Multipart message needed
            if body_text and body_html:
                # Create alternative container for text/html
                msg = MIMEMultipart("mixed")
                alt_part = MIMEMultipart("alternative")
                alt_part.attach(MIMEText(body_text, "plain"))
                alt_part.attach(MIMEText(body_html, "html"))
                msg.attach(alt_part)
            elif body_html:
                msg = MIMEMultipart("mixed")
                msg.attach(MIMEText(body_html, "html"))
            else:
                msg = MIMEMultipart("mixed")
                if body_text:
                    msg.attach(MIMEText(body_text, "plain"))

            # Add attachments
            if attachments:
                for file_path in attachments:
                    self._attach_file(msg, file_path)
        else:
            # Simple message
            if body_html:
                msg = MIMEText(body_html, "html")
            else:
                msg = MIMEText(body_text or "", "plain")

        # Set headers
        msg["Subject"] = subject
        msg["From"] = self.user
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)

        # Build recipient list (To + Cc + Bcc)
        all_recipients = list(to)
        if cc:
            all_recipients.extend(cc)
        if bcc:
            all_recipients.extend(bcc)

        result = {
            "from": self.user,
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
            "recipients": all_recipients,
            "has_text": body_text is not None,
            "has_html": body_html is not None,
            "attachments": [str(a) for a in (attachments or [])],
        }

        if dry_run:
            result["status"] = "dry_run"
            result["message"] = msg.as_string()
            return result

        # Send the email
        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(self.user, self.app_password)
                server.sendmail(self.user, all_recipients, msg.as_string())
            result["status"] = "sent"
        except smtplib.SMTPAuthenticationError as e:
            raise GmailError(f"Authentication failed: {e.smtp_error.decode() if hasattr(e, 'smtp_error') else str(e)}")
        except smtplib.SMTPRecipientsRefused as e:
            raise GmailError(f"Recipients refused: {e.recipients}")
        except smtplib.SMTPException as e:
            raise GmailError(f"SMTP error: {e}")
        except ConnectionError as e:
            raise GmailError(f"Connection failed: {e}")

        return result

    def _attach_file(self, msg: MIMEMultipart, file_path: Path) -> None:
        '''Attach a file to the message.'''
        if not file_path.exists():
            raise GmailError(f"Attachment not found: {file_path}")

        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())

        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename=\"{file_path.name}\""
        )
        msg.attach(part)


def parse_recipients(value: str) -> list[str]:
    '''Parse comma-separated recipients into a list.'''
    return [r.strip() for r in value.split(",") if r.strip()]


def cmd_send(client: GmailClient, args: argparse.Namespace) -> int:
    '''Send an email.'''

    # Parse recipients
    to = parse_recipients(args.to)
    cc = parse_recipients(args.cc) if args.cc else None
    bcc = parse_recipients(args.bcc) if args.bcc else None

    # Get body content
    body_text = None
    body_html = None

    if args.body:
        body_text = args.body
    elif args.body_file:
        body_file = Path(args.body_file)
        if not body_file.exists():
            print(f"Error: Body file not found: {body_file}")
            return 1
        body_text = body_file.read_text()

    if args.html:
        body_html = args.html
    elif args.html_file:
        html_file = Path(args.html_file)
        if not html_file.exists():
            print(f"Error: HTML file not found: {html_file}")
            return 1
        body_html = html_file.read_text()

    # Must have at least some content
    if not body_text and not body_html:
        print("Error: Must provide --body, --body-file, --html, or --html-file")
        return 1

    # Parse attachments
    attachments = None
    if args.attach:
        attachments = [Path(a) for a in args.attach]

    # Send it
    try:
        result = client.send(
            to=to,
            subject=args.subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            dry_run=args.dry_run,
        )
    except GmailError as e:
        print(f"Error: {e}")
        return 1

    # Output
    if args.dry_run:
        print("DRY RUN - Email not sent")
        print("=" * 60)
        print(f"  From:        {result['from']}")
        print(f"  To:          {', '.join(result['to'])}")
        if result['cc']:
            print(f"  Cc:          {', '.join(result['cc'])}")
        if result['bcc']:
            print(f"  Bcc:         {', '.join(result['bcc'])}")
        print(f"  Subject:     {result['subject']}")
        print(f"  Text body:   {'Yes' if result['has_text'] else 'No'}")
        print(f"  HTML body:   {'Yes' if result['has_html'] else 'No'}")
        if result['attachments']:
            print(f"  Attachments: {', '.join(result['attachments'])}")
        print("=" * 60)
        print("\nRaw message preview:")
        print("-" * 60)
        # Show first 2000 chars of raw message
        raw = result['message']
        if len(raw) > 2000:
            print(raw[:2000])
            print(f"\n... ({len(raw) - 2000} more characters)")
        else:
            print(raw)
        print("-" * 60)
    else:
        print("Email sent successfully!")
        print(f"  To:          {', '.join(result['to'])}")
        if result['cc']:
            print(f"  Cc:          {', '.join(result['cc'])}")
        if result['bcc']:
            print(f"  Bcc:         {', '.join(result['bcc'])}")
        print(f"  Subject:     {result['subject']}")
        if result['attachments']:
            print(f"  Attachments: {', '.join(result['attachments'])}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gmail CLI - Send emails via Gmail SMTP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CLI_EPILOG,
    )

    parser.add_argument(
        "--user", "-u",
        help="Gmail address (or set GMAIL_USER env var)"
    )
    parser.add_argument(
        "--password", "-p",
        help="Gmail App Password (or set GMAIL_APP_PASSWORD env var)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Send command
    send_parser = subparsers.add_parser("send", help="Send an email")
    send_parser.add_argument(
        "--to", "-t",
        required=True,
        help="Recipient(s), comma-separated"
    )
    send_parser.add_argument(
        "--subject", "-s",
        required=True,
        help="Email subject"
    )
    send_parser.add_argument(
        "--body", "-b",
        help="Plain text body"
    )
    send_parser.add_argument(
        "--body-file",
        help="Read plain text body from file"
    )
    send_parser.add_argument(
        "--html",
        help="HTML body"
    )
    send_parser.add_argument(
        "--html-file",
        help="Read HTML body from file"
    )
    send_parser.add_argument(
        "--cc",
        help="CC recipient(s), comma-separated"
    )
    send_parser.add_argument(
        "--bcc",
        help="BCC recipient(s), comma-separated"
    )
    send_parser.add_argument(
        "--attach", "-a",
        action="append",
        help="File attachment (can be repeated)"
    )
    send_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview email without sending"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Get credentials
    user = args.user or os.environ.get("GMAIL_USER")
    password = args.password or os.environ.get("GMAIL_APP_PASSWORD")

    if not user:
        print("Error: Gmail user required")
        print("Set GMAIL_USER environment variable or use --user flag")
        return 1

    if not password:
        print("Error: Gmail App Password required")
        print("Set GMAIL_APP_PASSWORD environment variable or use --password flag")
        print("Generate an App Password at: https://myaccount.google.com/apppasswords")
        return 1

    # Create client and run command
    client = GmailClient(user, password)

    if args.command == "send":
        return cmd_send(client, args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
