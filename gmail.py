#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

# Remove current directory from path to avoid shadowing stdlib email module.
# The project directory is itself named "gmail.py", so a bare `import email`
# would resolve to this repo rather than the stdlib. Several modules are pulled
# in below (email.parser, email.policy, email.header, email.utils) and every one
# of them would break. Do not remove or reorder this block.
import sys
from pathlib import Path as _Path
_script_dir = str(_Path(__file__).parent.resolve())
sys.path = [p for p in sys.path if p not in ("", ".", _script_dir)]

import argparse
import email.utils
import imaplib
import os
import re
import smtplib
import textwrap
from datetime import datetime
from email import encoders
from email import policy
from email.header import decode_header, make_header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# Folder aliases map to IMAP special-use flags rather than names, because the
# real names are localized per account ("[Gmail]/All Mail" in English) and must
# be discovered from the LIST response.
FOLDER_FLAGS = {
    "sent": "\\Sent",
    "all": "\\All",
    "trash": "\\Trash",
    "drafts": "\\Drafts",
    "spam": "\\Junk",
}
FOLDER_ALIASES = ["inbox"] + list(FOLDER_FLAGS)
SPECIAL_USE_FLAGS = {flag.lower() for flag in FOLDER_FLAGS.values()} | {"\\important", "\\flagged"}

BODY_TRUNCATE = 4000
WRAP_WIDTH = 92

CLI_EPILOG = '''\
Examples:
  gmail.py send --to "friend@example.com" --subject "Hello" --body "How are you?"
  gmail.py send --to "team@work.com" --subject "Update" --html "<h1>Status</h1><p>All good</p>"
  gmail.py send --to "boss@work.com" --subject "Report" --body "See attached" --attach report.pdf
  gmail.py send --to "a@ex.com,b@ex.com" --cc "c@ex.com" --subject "FYI" --body "Info"
  gmail.py send --to "user@ex.com" --subject "Doc" --body-file message.txt --attach doc.pdf
  gmail.py send --to "user@ex.com" --subject "Newsletter" --body "Plain text fallback" --html-file newsletter.html
  gmail.py inbox --limit 10 --unread
  gmail.py search --raw "from:bob has:attachment newer_than:7d"
  gmail.py search --from "bob@example.com" --since 2026-09-01 --folder all
  gmail.py read 4821
  gmail.py read 4821 --full --save-attachments ./downloads
  gmail.py thread 4821

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


class _TextExtractor(HTMLParser):
    '''Collapse HTML into readable plain text using only the stdlib.'''

    SKIP_TAGS = {"script", "style", "head", "title"}
    BLOCK_TAGS = {
        "p", "div", "br", "tr", "table", "blockquote", "ul", "ol", "pre",
        "h1", "h2", "h3", "h4", "h5", "h6", "hr", "section", "article",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self.skipping += 1
        elif tag == "li":
            self.chunks.append("\n- ")
        elif tag in self.BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self.skipping:
            self.skipping -= 1
        elif tag != "li" and tag in self.BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.chunks.append(data)

    def text(self) -> str:
        raw = "".join(self.chunks)
        # Collapse runs of spaces within lines, and runs of blank lines
        lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in raw.splitlines()]
        out: list[str] = []
        for line in lines:
            if line or (out and out[-1]):
                out.append(line)
        return "\n".join(out).strip()


def html_to_text(html: str) -> str:
    '''Render an HTML body as readable plain text.'''
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    return parser.text()


def decode_header_value(raw: str | None) -> str:
    '''Decode an RFC 2047 encoded header into a readable string.'''
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw))).strip()
    except Exception:
        return str(raw).strip()


def format_address(raw: str | None, name_only: bool = False) -> str:
    '''Format an address header as a readable display string.'''
    if not raw:
        return ""
    parts = []
    for name, addr in email.utils.getaddresses([decode_header_value(raw)]):
        name = decode_header_value(name)
        if name_only:
            parts.append(name or addr)
        elif name and addr:
            parts.append(f"{name} <{addr}>")
        else:
            parts.append(name or addr)
    return ", ".join(p for p in parts if p)


def address_list(raw: str | None) -> list[str]:
    '''Return the bare email addresses in an address header.'''
    if not raw:
        return []
    return [a for _, a in email.utils.getaddresses([decode_header_value(raw)]) if a]


def format_date(raw: str | None, fmt: str = "%b %d %H:%M") -> str:
    '''Format a Date header for display, falling back to the raw value.'''
    if not raw:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(raw)
    except Exception:
        return raw.strip()
    if dt is None:
        return raw.strip()
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.strftime(fmt)


def decode_part(part) -> str:
    '''Decode a MIME part payload to text, honoring its declared charset.'''
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def is_attachment(part) -> bool:
    '''True when a MIME part is an attachment rather than body content.'''
    disposition = (part.get("Content-Disposition") or "").lower()
    if disposition.startswith("attachment"):
        return True
    return bool(part.get_filename())


def extract_bodies(msg) -> tuple[str, str]:
    '''Walk a message and return its (plain text, html) bodies.'''
    text = ""
    html = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart" or is_attachment(part):
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and not text:
                text = decode_part(part)
            elif ctype == "text/html" and not html:
                html = decode_part(part)
    else:
        if msg.get_content_type() == "text/html":
            html = decode_part(msg)
        else:
            text = decode_part(msg)
    return text, html


def message_text(msg) -> str:
    '''Best-effort readable body: prefer text/plain, fall back to html.'''
    text, html = extract_bodies(msg)
    if text.strip():
        return text
    if html.strip():
        return html_to_text(html)
    return ""


def list_attachments(msg) -> list[dict]:
    '''Return the attachment manifest for a message.'''
    attachments = []
    if not msg.is_multipart():
        return attachments
    for part in msg.walk():
        if part.get_content_maintype() == "multipart" or not is_attachment(part):
            continue
        payload = part.get_payload(decode=True) or b""
        attachments.append({
            "filename": decode_header_value(part.get_filename()) or "(unnamed)",
            "content_type": part.get_content_type(),
            "size": len(payload),
        })
    return attachments


def format_size(size: int) -> str:
    '''Format a byte count for display.'''
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def quote_folder(name: str) -> str:
    '''Quote a mailbox name for SELECT; names with spaces fail unquoted.'''
    return imap_quote(name)


LIST_RE = re.compile(r'^\((?P<flags>[^)]*)\)\s+(?P<delim>"[^"]*"|NIL)\s+(?P<name>.*)$')


def parse_list_line(line: str) -> tuple[list[str], str] | None:
    '''Parse one LIST response line into (flags, mailbox name).'''
    match = LIST_RE.match(line.strip())
    if not match:
        return None
    flags = match.group("flags").split()
    name = match.group("name").strip()
    if name.startswith('"') and name.endswith('"'):
        name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return flags, name


def folder_alias(name: str, flags_map: dict, names: list) -> str:
    '''Resolve a folder alias to the real mailbox name discovered via LIST.'''
    key = (name or "inbox").strip()
    lower = key.lower()
    if lower == "inbox":
        return "INBOX"
    if lower in FOLDER_FLAGS:
        real = flags_map.get(FOLDER_FLAGS[lower].lower())
        if not real:
            raise GmailError(f"No {lower} folder found on this account")
        return real
    # Accept a literal mailbox name as long as the account actually has it
    for candidate in names:
        if candidate.lower() == lower:
            return candidate
    raise GmailError(
        f"Unknown folder {name!r} (use one of: {', '.join(FOLDER_ALIASES)}, "
        "or an exact mailbox name)"
    )


FETCH_UID_RE = re.compile(rb"UID (\d+)")
FETCH_FLAGS_RE = re.compile(rb"FLAGS \(([^)]*)\)")
FETCH_THRID_RE = re.compile(rb"X-GM-THRID (\d+)")
FETCH_MSGID_RE = re.compile(rb"X-GM-MSGID (\d+)")

SUMMARY_ITEMS = "(UID FLAGS X-GM-THRID X-GM-MSGID BODY.PEEK[])"


def imap_quote(value: str) -> str:
    '''Quote a string as an IMAP quoted-string.'''
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def require_ascii(value: str, label: str) -> str:
    '''IMAP command arguments are ASCII; fail loudly rather than silently.'''
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        raise GmailError(f"{label} must be ASCII (IMAP search does not accept non-ASCII terms)")
    return value


def imap_date(value: str) -> str:
    '''Convert YYYY-MM-DD to the DD-Mon-YYYY form IMAP SEARCH expects.'''
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").strftime("%d-%b-%Y")
    except ValueError:
        raise GmailError(f"Invalid date {value!r}, expected YYYY-MM-DD")


def build_criteria(
    sender: str | None = None,
    to: str | None = None,
    subject: str | None = None,
    unread: bool = False,
    since: str | None = None,
    before: str | None = None,
) -> list[str]:
    '''Build IMAP SEARCH criteria from the structured search flags.'''
    criteria: list[str] = []
    if sender:
        criteria += ["FROM", imap_quote(require_ascii(sender, "--from"))]
    if to:
        criteria += ["TO", imap_quote(require_ascii(to, "--to"))]
    if subject:
        criteria += ["SUBJECT", imap_quote(require_ascii(subject, "--subject"))]
    if unread:
        criteria.append("UNSEEN")
    if since:
        criteria += ["SINCE", imap_date(since)]
    if before:
        criteria += ["BEFORE", imap_date(before)]
    return criteria or ["ALL"]


def parse_fetch(data) -> list[dict]:
    '''Parse a FETCH response into per-message dicts of metadata and raw bytes.'''
    messages = []
    for part in data or []:
        if not isinstance(part, tuple) or len(part) < 2:
            continue
        meta, raw = part[0], part[1]
        uid = FETCH_UID_RE.search(meta)
        flags = FETCH_FLAGS_RE.search(meta)
        thrid = FETCH_THRID_RE.search(meta)
        msgid = FETCH_MSGID_RE.search(meta)
        messages.append({
            "uid": int(uid.group(1)) if uid else None,
            "flags": flags.group(1).decode(errors="replace").split() if flags else [],
            "thrid": thrid.group(1).decode() if thrid else None,
            "msgid": msgid.group(1).decode() if msgid else None,
            "raw": raw,
        })
    return messages


def snippet_of(msg, width: int = 240) -> str:
    '''One-line preview of a message body for list views.'''
    text = " ".join(message_text(msg).split())
    if len(text) > width:
        text = text[:width].rstrip() + "..."
    return text


def summarize(entry: dict) -> dict:
    '''Build a message summary dict from a parsed FETCH entry.'''
    msg = BytesParser().parsebytes(entry["raw"])
    return {
        "uid": entry["uid"],
        "thrid": entry["thrid"],
        "msgid": entry["msgid"],
        "flags": entry["flags"],
        "seen": "\\Seen" in entry["flags"],
        "date": format_date(msg.get("Date")),
        "date_raw": msg.get("Date"),
        "from": format_address(msg.get("From"), name_only=True),
        "from_full": format_address(msg.get("From")),
        "to": format_address(msg.get("To")),
        "cc": format_address(msg.get("Cc")),
        "subject": decode_header_value(msg.get("Subject")) or "(no subject)",
        "message_id": (msg.get("Message-ID") or "").strip(),
        "snippet": snippet_of(msg),
        "attachments": list_attachments(msg),
        "message": msg,
    }


def truncate(value: str, width: int) -> str:
    '''Truncate a column value with an ellipsis.'''
    if len(value) <= width:
        return value
    return value[:width - 3].rstrip() + "..."


def imap_error_text(err: Exception) -> str:
    '''Readable text for an imaplib error, whose args are often bytes.'''
    parts = []
    for arg in getattr(err, "args", ()):
        if isinstance(arg, bytes):
            parts.append(arg.decode(errors="replace"))
        else:
            parts.append(str(arg))
    return " ".join(parts) or str(err)


def imap_response_text(data) -> str:
    '''Readable text for an imaplib response payload.'''
    parts = []
    for item in data or []:
        if isinstance(item, bytes):
            parts.append(item.decode(errors="replace"))
        elif isinstance(item, tuple):
            parts.append(" ".join(
                x.decode(errors="replace") if isinstance(x, bytes) else str(x) for x in item
            ))
        else:
            parts.append(str(item))
    return " ".join(parts)


class GmailClient:
    '''Gmail client carrying both transports: SMTP for sending, IMAP for reading.

    Both connect lazily. They live on one object because `reply` needs to read
    a message and send a new one within a single invocation.
    '''

    def __init__(self, user: str, app_password: str):
        self.user = user
        self.app_password = app_password
        self._imap_conn = None
        self._capabilities: set[str] = set()
        self._folder_flags: dict | None = None
        self._folder_names: list = []

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

    # ── IMAP ──────────────────────────────────────────────────────────────────

    def _imap(self) -> imaplib.IMAP4_SSL:
        '''Connect and authenticate to IMAP, caching the connection.'''
        if self._imap_conn is not None:
            return self._imap_conn

        try:
            conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        except OSError as e:
            raise GmailError(f"IMAP connection failed: {e}")

        try:
            conn.login(self.user, self.app_password)
        except imaplib.IMAP4.error as e:
            detail = imap_error_text(e)
            upper = detail.upper()
            if "AUTHENTICATIONFAILED" in upper or "INVALID CREDENTIALS" in upper:
                raise GmailError(
                    "IMAP authentication failed. Check GMAIL_USER and GMAIL_APP_PASSWORD, "
                    "and confirm IMAP is enabled in Gmail settings "
                    "(Settings > Forwarding and POP/IMAP > Enable IMAP)."
                )
            if "IMAP ACCESS IS DISABLED" in upper or "IMAP IS DISABLED" in upper:
                raise GmailError(
                    "IMAP is disabled for this account. Enable it in Gmail settings "
                    "(Settings > Forwarding and POP/IMAP > Enable IMAP)."
                )
            raise GmailError(f"IMAP login failed: {detail}")

        # imaplib caches the pre-auth greeting, which under-reports Gmail's
        # capabilities (it claims MOVE and UIDPLUS are absent). Re-query now
        # that we are authenticated.
        typ, data = conn.capability()
        if typ == "OK" and data:
            self._capabilities = set(data[0].decode(errors="replace").upper().split())

        self._imap_conn = conn
        return conn

    def _folders(self) -> tuple[dict, list]:
        '''LIST all mailboxes once; return (special-use flag -> name, all names).'''
        if self._folder_flags is not None:
            return self._folder_flags, self._folder_names

        conn = self._imap()
        typ, data = conn.list()
        if typ != "OK":
            raise GmailError("Could not list mailboxes")

        flags_map: dict[str, str] = {}
        names: list[str] = []
        for line in data or []:
            if isinstance(line, tuple):
                line = b" ".join(part for part in line if isinstance(part, bytes))
            parsed = parse_list_line(line.decode(errors="replace"))
            if not parsed:
                continue
            flags, name = parsed
            names.append(name)
            # Keyed lowercase: Gmail's capitalization of special-use flags is
            # not guaranteed, and neither is the mailbox name.
            for flag in flags:
                if flag.lower() in SPECIAL_USE_FLAGS:
                    flags_map[flag.lower()] = name

        self._folder_flags = flags_map
        self._folder_names = names
        return flags_map, names

    def _select(self, folder: str = "inbox", readonly: bool = True) -> str:
        '''Resolve a folder alias, SELECT it, and return the real mailbox name.'''
        flags_map, names = self._folders()
        name = folder_alias(folder, flags_map, names)
        conn = self._imap()
        typ, data = conn.select(quote_folder(name), readonly=readonly)
        if typ != "OK":
            raise GmailError(f"Could not open folder {name!r}: {imap_response_text(data)}")
        return name

    def _uid_search(self, criteria: list[str] | None, raw: str | None) -> list[int]:
        '''Run a UID SEARCH and return matching UIDs, ascending.'''
        conn = self._imap()
        if raw:
            args = ["X-GM-RAW", imap_quote(require_ascii(raw, "--raw"))]
        else:
            args = list(criteria or ["ALL"])
        typ, data = conn.uid("SEARCH", None, *args)
        if typ != "OK":
            raise GmailError(f"Search failed: {imap_response_text(data)}")
        return [int(uid) for uid in (data[0] or b"").split()]

    def _fetch_summaries(self, uids: list[int]) -> list[dict]:
        '''Fetch and summarize a specific set of UIDs in the order given.'''
        if not uids:
            return []
        conn = self._imap()
        typ, data = conn.uid("FETCH", ",".join(str(u) for u in uids), SUMMARY_ITEMS)
        if typ != "OK":
            raise GmailError(f"Fetch failed: {imap_response_text(data)}")
        by_uid = {entry["uid"]: entry for entry in parse_fetch(data)}
        return [summarize(by_uid[uid]) for uid in uids if uid in by_uid]

    def search(
        self,
        criteria: list[str] | None = None,
        raw: str | None = None,
        folder: str = "inbox",
        limit: int = 20,
    ) -> list[dict]:
        '''Search a folder and return message summaries, newest first.'''
        self._select(folder, readonly=True)
        uids = self._uid_search(criteria, raw)
        # SEARCH returns ascending UIDs; reverse for newest-first and slice
        # before fetching so we never pull the whole result set.
        uids = list(reversed(uids))
        if limit:
            uids = uids[:limit]
        return self._fetch_summaries(uids)

    def fetch(self, uid: int, folder: str = "inbox") -> dict:
        '''Fetch one message by UID from a folder.'''
        self._select(folder, readonly=True)
        messages = self._fetch_summaries([uid])
        if not messages:
            raise GmailError(f"No message with UID {uid} in folder {folder!r}")
        messages[0]["folder"] = folder
        return messages[0]

    def thread(self, uid: int, folder: str = "inbox") -> list[dict]:
        '''Return the full conversation for a UID, oldest first.

        The search runs against All Mail on purpose: your own replies live in
        Sent, so anything narrower cannot show both sides of a conversation.
        '''
        base = self.fetch(uid, folder)
        if not base["thrid"]:
            return [base]
        self._select("all", readonly=True)
        conn = self._imap()
        typ, data = conn.uid("SEARCH", None, "X-GM-THRID", base["thrid"])
        if typ != "OK":
            raise GmailError(f"Thread search failed: {imap_response_text(data)}")
        uids = sorted(int(u) for u in (data[0] or b"").split())
        messages = self._fetch_summaries(uids)
        # UIDs are per-folder: these are All Mail UIDs, so say so
        for message in messages:
            message["folder"] = "all"
        return messages or [base]

    def close(self) -> None:
        '''Log out of IMAP if connected.'''
        conn, self._imap_conn = self._imap_conn, None
        if conn is None:
            return
        try:
            if conn.state == "SELECTED":
                conn.close()
            conn.logout()
        except Exception:
            pass

    def __enter__(self) -> "GmailClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


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


def save_attachments(msg, directory: Path) -> list[Path]:
    '''Write a message's attachments into a directory and return the paths.'''
    directory.mkdir(parents=True, exist_ok=True)
    saved = []
    if not msg.is_multipart():
        return saved
    for index, part in enumerate(msg.walk(), start=1):
        if part.get_content_maintype() == "multipart" or not is_attachment(part):
            continue
        name = decode_header_value(part.get_filename()) or f"attachment-{index}"
        # Never let a message name a path outside the target directory
        name = Path(name.replace("\\", "/")).name or f"attachment-{index}"
        target = directory / name
        counter = 1
        while target.exists():
            target = directory / f"{Path(name).stem}-{counter}{Path(name).suffix}"
            counter += 1
        target.write_bytes(part.get_payload(decode=True) or b"")
        saved.append(target)
    return saved


def wrap_body(text: str, indent: str = "  ") -> str:
    '''Wrap body text to the display width, preserving paragraph breaks.'''
    lines = []
    for line in text.splitlines():
        if not line.strip():
            # Collapse runs of blank lines; mail bodies are full of them
            if lines and lines[-1] == "":
                continue
            lines.append("")
        else:
            lines.append(textwrap.fill(
                line, width=len(indent) + WRAP_WIDTH,
                initial_indent=indent, subsequent_indent=indent,
            ))
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def render_list(messages: list[dict]) -> None:
    '''Print message summaries as an aligned table with body snippets.'''
    rows = []
    for m in messages:
        rows.append({
            "uid": str(m["uid"]),
            "date": m["date"],
            "from": truncate(m["from"] or "(unknown)", 28),
            "subject": truncate(m["subject"], 50),
            "status": "read" if m["seen"] else "unread",
            "snippet": m["snippet"],
        })

    uid_w = max(max(len(r["uid"]) for r in rows), len("UID"))
    date_w = max(max(len(r["date"]) for r in rows), len("DATE"))
    from_w = max(max(len(r["from"]) for r in rows), len("FROM"))
    subj_w = max(max(len(r["subject"]) for r in rows), len("SUBJECT"))
    stat_w = max(max(len(r["status"]) for r in rows), len("STATUS"))

    header = (
        f"{'UID':>{uid_w}}  {'DATE':<{date_w}}  {'FROM':<{from_w}}  "
        f"{'SUBJECT':<{subj_w}}  {'STATUS':<{stat_w}}"
    )
    indent = "  "
    print(header.rstrip())
    print("-" * max(len(header), 2 + WRAP_WIDTH))
    for r in rows:
        print(
            f"{r['uid']:>{uid_w}}  {r['date']:<{date_w}}  {r['from']:<{from_w}}  "
            f"{r['subject']:<{subj_w}}  {r['status']:<{stat_w}}".rstrip()
        )
        if r["snippet"]:
            print(textwrap.fill(
                r["snippet"], width=2 + WRAP_WIDTH,
                initial_indent=indent, subsequent_indent=indent,
                max_lines=2, placeholder="...",
            ))
        print()
    print(f"{len(rows)} message(s)")


def cmd_inbox(client: GmailClient, args: argparse.Namespace) -> int:
    '''List messages in the inbox.'''
    criteria = build_criteria(unread=args.unread)
    messages = client.search(criteria=criteria, folder="inbox", limit=args.limit)
    if not messages:
        print("No messages found")
        return 0
    render_list(messages)
    return 0


def cmd_search(client: GmailClient, args: argparse.Namespace) -> int:
    '''Search for messages.'''
    structured = any([args.sender, args.to, args.subject, args.unread, args.since, args.before])
    if args.raw and structured:
        print("Error: --raw cannot be combined with the structured search flags", file=sys.stderr)
        return 1
    if not args.raw and not structured:
        print("Error: provide --raw or at least one structured search flag", file=sys.stderr)
        return 1

    criteria = None if args.raw else build_criteria(
        sender=args.sender,
        to=args.to,
        subject=args.subject,
        unread=args.unread,
        since=args.since,
        before=args.before,
    )
    messages = client.search(
        criteria=criteria, raw=args.raw, folder=args.folder, limit=args.limit,
    )
    if not messages:
        print("No messages found")
        return 0
    render_list(messages)
    return 0


def render_message(message: dict, full: bool = False) -> None:
    '''Print a single message as a detail view.'''
    print(message["subject"])
    print()

    fields = [
        ("From", message["from_full"]),
        ("To", message["to"]),
        ("Cc", message["cc"]),
        ("Date", format_date(message["date_raw"], "%a %b %d %Y %H:%M")),
        ("Folder", message.get("folder") or ""),
        ("Status", "read" if message["seen"] else "unread"),
    ]
    label_w = max(len(f[0]) for f in fields)
    for label, value in fields:
        if value:
            print(f"  {label:<{label_w}}  {value}")

    body = message_text(message["message"])
    if body.strip():
        print()
        if not full and len(body) > BODY_TRUNCATE:
            remaining = len(body) - BODY_TRUNCATE
            body = body[:BODY_TRUNCATE]
            print(wrap_body(body))
            print()
            print(f"  ... ({remaining} more characters, use --full to see all)")
        else:
            print(wrap_body(body))

    if message["attachments"]:
        print()
        print("  Attachments")
        name_w = max(len(a["filename"]) for a in message["attachments"])
        for a in message["attachments"]:
            print(f"    {a['filename']:<{name_w}}  {format_size(a['size'])}  {a['content_type']}")

    print()
    print(f"  UID: {message['uid']}")


def cmd_read(client: GmailClient, args: argparse.Namespace) -> int:
    '''Read a single message.'''
    message = client.fetch(args.uid, folder=args.folder)

    if args.html:
        text, html = extract_bodies(message["message"])
        if not html.strip():
            print("No HTML body in this message", file=sys.stderr)
            return 1
        print(html)
        return 0

    render_message(message, full=args.full)

    if args.save_attachments:
        saved = save_attachments(message["message"], Path(args.save_attachments))
        print()
        if saved:
            for path in saved:
                print(f"  Saved: {path}")
        else:
            print("  No attachments to save")
    return 0


def cmd_thread(client: GmailClient, args: argparse.Namespace) -> int:
    '''Show a conversation, oldest first.'''
    messages = client.thread(args.uid, folder=args.folder)

    print(f"{messages[0]['subject']} — {len(messages)} message(s)")
    for message in messages:
        print()
        print("-" * (2 + WRAP_WIDTH))
        render_message(message, full=args.full)
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

    # Inbox command
    inbox_parser = subparsers.add_parser("inbox", help="List messages in the inbox")
    inbox_parser.add_argument(
        "--limit", "-n",
        type=int,
        default=20,
        help="Maximum number of messages (default: 20)"
    )
    inbox_parser.add_argument(
        "--unread",
        action="store_true",
        help="Show only unread messages"
    )

    # Search command
    search_parser = subparsers.add_parser("search", help="Search for messages")
    search_parser.add_argument(
        "--raw", "-q",
        help="Gmail search query, e.g. \"from:bob has:attachment newer_than:7d\""
    )
    search_parser.add_argument(
        "--from", "-f",
        dest="sender",
        help="Match sender"
    )
    search_parser.add_argument(
        "--to",
        help="Match recipient"
    )
    search_parser.add_argument(
        "--subject", "-s",
        help="Match subject"
    )
    search_parser.add_argument(
        "--unread",
        action="store_true",
        help="Match unread messages only"
    )
    search_parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="Match messages on or after this date"
    )
    search_parser.add_argument(
        "--before",
        metavar="YYYY-MM-DD",
        help="Match messages before this date"
    )
    search_parser.add_argument(
        "--folder",
        default="inbox",
        help=f"Folder to search: {', '.join(FOLDER_ALIASES)} (default: inbox)"
    )
    search_parser.add_argument(
        "--limit", "-n",
        type=int,
        default=20,
        help="Maximum number of messages (default: 20)"
    )

    # Read command
    read_parser = subparsers.add_parser("read", help="Read a single message by UID")
    read_parser.add_argument("uid", type=int, help="Message UID (from inbox or search)")
    read_parser.add_argument(
        "--folder",
        default="inbox",
        help=f"Folder holding the message: {', '.join(FOLDER_ALIASES)} (default: inbox)"
    )
    read_parser.add_argument(
        "--full",
        action="store_true",
        help="Show the full body without truncation"
    )
    read_parser.add_argument(
        "--html",
        action="store_true",
        help="Dump the raw HTML body"
    )
    read_parser.add_argument(
        "--save-attachments",
        metavar="DIR",
        help="Save attachments to a directory"
    )

    # Thread command
    thread_parser = subparsers.add_parser("thread", help="Show a conversation by UID")
    thread_parser.add_argument("uid", type=int, help="Message UID (from inbox or search)")
    thread_parser.add_argument(
        "--folder",
        default="inbox",
        help=f"Folder holding the message: {', '.join(FOLDER_ALIASES)} (default: inbox)"
    )
    thread_parser.add_argument(
        "--full",
        action="store_true",
        help="Show full bodies without truncation"
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
    commands = {
        "send": cmd_send,
        "inbox": cmd_inbox,
        "search": cmd_search,
        "read": cmd_read,
        "thread": cmd_thread,
    }
    handler = commands.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    with GmailClient(user, password) as client:
        try:
            return handler(client, args)
        except GmailError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
