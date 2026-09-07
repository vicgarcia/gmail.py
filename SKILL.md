---
name: gmail
description: Read, search, and send email via Gmail (IMAP + SMTP). Use when the user wants to check their email, find a message, read or summarize a message or conversation, archive or mark mail, reply to someone, send an email, compose a message, share files by email, or notify someone by email.
compatibility: Requires 'gmail.py' script in PATH with GMAIL_USER and GMAIL_APP_PASSWORD environment variables set, and IMAP enabled in Gmail settings (Settings > Forwarding and POP/IMAP > Enable IMAP).
---

# Gmail Email Tool

Read, search, and send email using the `gmail.py` CLI. Reading is IMAP, sending is
SMTP, and both use the same App Password.

## Authentication

Credentials are loaded from environment variables:
```bash
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxxxxxxxxxxxxxx"
```

Or passed directly: `gmail.py --user EMAIL --password PASSWORD send ...`

App Passwords are required (not regular Gmail passwords). Generate at: https://myaccount.google.com/apppasswords

## Commands

| Command | Description |
|---------|-------------|
| `inbox` | List messages in the inbox |
| `search` | Find messages by Gmail query or structured flags |
| `read` | Show one message in full |
| `thread` | Show a whole conversation, oldest first |
| `mark` | Mark read/unread, archive, or trash |
| `reply` | Reply to a message, preserving the thread |
| `send` | Send a new email |

Every list view prints a `UID` column. UIDs are how commands chain: search for a
message, then read, reply to, or mark it by its UID.

**UIDs are per-folder.** A UID from `--folder all` is not the same message's UID in
the inbox. Always pass the same `--folder` you found the message in. `thread` prints
`Folder: all` because it searches All Mail, so follow-up commands on those UIDs need
`--folder all`.

## Reading Email

```bash
# Most recent 20 inbox messages
gmail.py inbox

# Just the unread ones, capped at 10
gmail.py inbox --limit 10 --unread
```

Each row shows UID, date, sender, subject, and read status, followed by a short
snippet of the body.

## Searching

Two mutually exclusive modes. `--raw` takes a real Gmail search query and is the
more capable one; the structured flags are convenience wrappers over IMAP SEARCH.

```bash
# Gmail query syntax (recommended)
gmail.py search --raw "from:bob has:attachment newer_than:7d"
gmail.py search --raw "is:unread label:receipts" --limit 10

# Structured flags
gmail.py search --from "bob@example.com" --unread
gmail.py search --subject "invoice" --since 2026-09-01 --folder all
```

### Gmail query syntax for `--raw`

| Operator | Example |
|----------|---------|
| `from:` | `from:bob@example.com` |
| `to:` | `to:me` |
| `subject:` | `subject:invoice` |
| `has:attachment` | `has:attachment` |
| `filename:` | `filename:pdf` |
| `newer_than:` | `newer_than:7d` (also `m`, `y`) |
| `older_than:` | `older_than:1y` |
| `is:unread` | `is:unread`, `is:starred`, `is:important` |
| `label:` | `label:receipts` |
| `in:` | `in:anywhere`, `in:sent` |
| quoting | `"exact phrase"` |
| boolean | `from:bob OR from:alice`, `-subject:newsletter` |

`has:attachment`, `label:`, and `newer_than:` have no IMAP equivalent and are
available only through `--raw`.

Search terms must be ASCII; IMAP search does not accept non-ASCII arguments.

### Folders

`--folder` accepts `inbox` (default), `sent`, `all`, `trash`, `drafts`, `spam`, or an
exact mailbox name. Real folder names are discovered from the account, so localized
mailbox names work too.

## Reading a Message

```bash
gmail.py read 4821                                  # header block, body, attachments
gmail.py read 4821 --full                           # no body truncation
gmail.py read 4821 --html                           # raw HTML body
gmail.py read 4821 --save-attachments ./downloads   # write attachments to disk
gmail.py read 902 --folder all                      # message found in All Mail
```

Bodies prefer `text/plain` and fall back to `text/html` rendered as readable text.
Bodies are truncated at 4000 characters unless `--full` is passed.

Reading never marks a message as read — the fetch uses `BODY.PEEK`. Use
`gmail.py mark <uid> --read` when the user actually wants it marked.

## Threads

```bash
gmail.py thread 4821
gmail.py thread 4821 --full
```

Renders the whole conversation oldest-first, searching All Mail so that both sides
appear — your own replies live in Sent, so a thread view is the only way to see who
spoke last and whether the ball is in the user's court. Read the thread before
drafting a reply.

## Marking

```bash
gmail.py mark 4821 --read
gmail.py mark 4821 --unread
gmail.py mark 4821 --archive     # moves out of the inbox, keeps it in All Mail
gmail.py mark 4821 --trash       # destructive
```

Exactly one action flag is required. After the change the tool re-queries the message
and prints the state it actually observed (new UID, destination folder, whether the
message left the source folder, read status), because Gmail returns `OK` for some
operations that do nothing.

Archive preserves read/unread state and is reversible in the Gmail UI. **Trash is
destructive: confirm with the user before running it.**

## Replying

```bash
# Simple reply to the sender
gmail.py reply 4821 --body "Sounds good, shipping today."

# Quote the original beneath the reply
gmail.py reply 4821 --body "See below." --quote

# Reply to everyone on the original
gmail.py reply 4821 --all --body "Looping in the team."

# Preview before sending
gmail.py reply 4821 --body "Draft text" --dry-run
```

`reply` sets `In-Reply-To` and `References` from the original, prefixes the subject
with `Re:` when needed, and addresses the reply to the original `Reply-To` (falling
back to `From`). `--all` adds the original To recipients to To and the original Cc to
Cc, minus your own address. `--quote` appends an attribution line and a `> `-prefixed
copy of the original to the plain text body.

Accepts the same content flags as `send`: `--body`, `--body-file`, `--html`,
`--html-file`, `--attach`, `--cc`, `--bcc`, `--dry-run`.

**`reply` sends real mail.** When replying on the user's behalf, show them the text
first or run `--dry-run` before sending.

## Sending

### Send Plain Text Email
```bash
gmail.py send --to "recipient@example.com" --subject "Hello" --body "Message content here"
```

### Send HTML Email
```bash
gmail.py send --to "recipient@example.com" --subject "Update" --html "<h1>Title</h1><p>Rich content</p>"
```

### Send Multipart Email (Text + HTML)
```bash
gmail.py send --to "recipient@example.com" --subject "Newsletter" \
  --body "Plain text fallback for old email clients" \
  --html "<h1>Newsletter</h1><p>Rich HTML version</p>"
```

Email clients will display HTML if supported, otherwise fall back to plain text.

### Send with Attachments
```bash
# Single attachment
gmail.py send --to "recipient@example.com" --subject "Report" \
  --body "Please see attached." --attach report.pdf

# Multiple attachments
gmail.py send --to "recipient@example.com" --subject "Files" \
  --body "Here are the requested files." \
  --attach document.pdf --attach spreadsheet.xlsx --attach image.png
```

### Send from Files
```bash
# Text body from file
gmail.py send --to "recipient@example.com" --subject "Message" --body-file message.txt

# HTML body from file
gmail.py send --to "recipient@example.com" --subject "Newsletter" --html-file template.html
```

### Multiple Recipients
```bash
gmail.py send --to "alice@example.com,bob@example.com" --subject "Team Update" --body "Info for everyone"
gmail.py send --to "primary@example.com" --cc "copy@example.com" --subject "FYI" --body "Content"
gmail.py send --to "visible@example.com" --bcc "hidden@example.com" --subject "Notice" --body "Content"
```

### Dry Run (Preview Without Sending)
```bash
gmail.py send --to "test@example.com" --subject "Test" --body "Hello" --dry-run
```

## Command Options

### inbox

| Option | Required | Description |
|--------|----------|-------------|
| `--limit`, `-n` | No | Maximum messages (default: 20) |
| `--unread` | No | Only unread messages |

### search

| Option | Required | Description |
|--------|----------|-------------|
| `--raw`, `-q` | No* | Gmail search query |
| `--from`, `-f` | No* | Match sender |
| `--to` | No* | Match recipient |
| `--subject`, `-s` | No* | Match subject |
| `--unread` | No* | Only unread messages |
| `--since` | No* | On or after YYYY-MM-DD |
| `--before` | No* | Before YYYY-MM-DD |
| `--folder` | No | inbox (default), sent, all, trash, drafts, spam |
| `--limit`, `-n` | No | Maximum messages (default: 20) |

*Provide either `--raw` or one or more structured flags; they cannot be combined

### read

| Option | Required | Description |
|--------|----------|-------------|
| `uid` | Yes | Message UID |
| `--folder` | No | Folder holding the message (default: inbox) |
| `--full` | No | Show the full body without truncation |
| `--html` | No | Dump the raw HTML body |
| `--save-attachments` | No | Directory to save attachments into |

### thread

| Option | Required | Description |
|--------|----------|-------------|
| `uid` | Yes | Message UID |
| `--folder` | No | Folder holding the message (default: inbox) |
| `--full` | No | Show full bodies without truncation |

### mark

| Option | Required | Description |
|--------|----------|-------------|
| `uid` | Yes | Message UID |
| `--read` / `--unread` / `--archive` / `--trash` | Yes | Exactly one action |
| `--folder` | No | Folder holding the message (default: inbox) |

### reply

| Option | Required | Description |
|--------|----------|-------------|
| `uid` | Yes | Message UID |
| `--body`, `-b` | No* | Plain text body |
| `--body-file` | No* | Read plain text body from file |
| `--html` | No* | HTML body |
| `--html-file` | No* | Read HTML body from file |
| `--all` | No | Reply to all original recipients |
| `--quote` | No | Quote the original below the reply |
| `--folder` | No | Folder holding the message (default: inbox) |
| `--cc` / `--bcc` | No | Additional recipients, comma-separated |
| `--attach`, `-a` | No | File attachment (repeat for multiple) |
| `--dry-run` | No | Preview without sending |

*At least one content option required

### send

| Option | Required | Description |
|--------|----------|-------------|
| `--to`, `-t` | Yes | Recipient email(s), comma-separated |
| `--subject`, `-s` | Yes | Email subject line |
| `--body`, `-b` | No* | Plain text message body |
| `--body-file` | No* | Read plain text body from file path |
| `--html` | No* | HTML message body |
| `--html-file` | No* | Read HTML body from file path |
| `--cc` | No | CC recipient(s), comma-separated |
| `--bcc` | No | BCC recipient(s), comma-separated |
| `--attach`, `-a` | No | File to attach (repeat for multiple) |
| `--dry-run` | No | Preview email without sending |

*At least one content option required: `--body`, `--body-file`, `--html`, or `--html-file`

## Workflow Patterns

### Triage the inbox
```bash
gmail.py inbox --unread --limit 10       # scan snippets
gmail.py read 4821                       # open the one that matters
gmail.py mark 4821 --archive             # clear it out
```

### Find something specific, then act on it
```bash
gmail.py search --raw "from:bob subject:invoice newer_than:30d"
gmail.py read 4821 --save-attachments ./invoices
gmail.py reply 4821 --body "Received, thanks."
```

### Get conversation state before drafting
```bash
gmail.py search --raw "from:bob newer_than:14d" --limit 5
gmail.py thread 4821                     # who spoke last?
gmail.py reply 4821 --body "..." --quote
```

## Context Discipline

- Always pass `--limit`; inbox and search default to 20 and can be far larger.
- Prefer the snippets in list views over opening messages; open a message only when
  its body actually matters.
- Use `--full` sparingly — bodies are truncated at 4000 characters for a reason, and
  marketing email is mostly boilerplate.
- Use `thread` instead of reading each message in a conversation separately.
- `--html` dumps raw markup and is usually a waste of context; the default rendering
  already converts HTML to readable text.

## Safety

- `mark --trash` is destructive. Confirm with the user first.
- `reply` and `send` deliver real mail immediately. Preview with `--dry-run` or show
  the user the draft text before sending on their behalf.
- `mark --archive` is safe and reversible: it moves the message to All Mail and
  preserves its read/unread state.

## Tips

- For long messages, write content to a file and use `--body-file`
- Always provide `--body` with `--html` for maximum compatibility
- Attachment file paths can be relative or absolute
- Gmail has a 25MB attachment limit per email
- Gmail auto-files anything sent through SMTP into Sent, so replies show up in the
  thread with no extra work
