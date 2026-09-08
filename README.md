# gmail.py

A single-file CLI for reading, searching, and sending email via Gmail.

## Features

- **Single-file executable** - Uses `uv run --script` with inline dependencies (PEP 723)
- **Zero dependencies** - Standard library only
- **Gmail SMTP** - Secure SSL connection for sending
- **IMAP retrieval** - Browse the inbox, search, and read messages with the same App Password
- **Gmail search** - Full Gmail query syntax (`has:attachment`, `newer_than:`, `label:`) plus structured flags
- **Threads** - View a whole conversation oldest-first, across Inbox and Sent
- **Mark** - Read, unread, archive, and trash, each verified after the fact
- **Reply** - Proper `In-Reply-To`/`References` threading, `--all` and `--quote`
- **Plain text emails** - Simple text messages
- **HTML emails** - Rich HTML formatted emails
- **Multipart emails** - Combined text and HTML for maximum compatibility
- **File attachments** - Attach files when sending, save them when reading
- **CC/BCC support** - Send to multiple recipients with full control
- **Dry run mode** - Preview emails without sending

## Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager
- Gmail account with App Password

## Gmail Setup

Gmail requires an App Password (not your regular password) for SMTP and IMAP access:

1. Enable 2-Step Verification on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Generate a new App Password (select "Mail" and your device)
4. Copy the 16-character password

Reading mail also requires IMAP to be enabled:

5. In Gmail, go to Settings > See all settings > Forwarding and POP/IMAP
6. Select "Enable IMAP" and save

## Installation

```bash
# Clone and make executable
git clone https://github.com/vicgarcia/gmail.py.git
cd gmail.py
chmod +x gmail.py

# Run
./gmail.py --help

# Install
cp gmail.py ~/.local/bin
chmod +x ~/.local/bin/gmail.py

# Set credentials
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
```

## Commands

| Command | Description |
|---------|-------------|
| `inbox` | List messages in the inbox |
| `search` | Find messages by Gmail query or structured flags |
| `read` | Show one message in full |
| `thread` | Show a whole conversation, oldest first |
| `mark` | Mark read/unread, archive, or trash |
| `reply` | Reply to a message, preserving the thread |
| `send` | Send an email |

Messages are identified by IMAP UID, printed in every list view. UIDs are per-folder:
a UID found with `--folder all` needs `--folder all` on follow-up commands.

## Usage

Set your credentials via environment variables:
```bash
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
```

Or pass them as arguments: `--user` and `--password`

### Inbox

```bash
gmail.py inbox                       # 20 most recent messages
gmail.py inbox --limit 10 --unread   # 10 most recent unread
```

```
UID  DATE          FROM        SUBJECT                        STATUS
------------------------------------------------------------------------------
 68  Sep 06 14:22  Bob Chen    Re: Q3 invoice question        unread
  Thanks for sending that over - I had one question about line item 4 before...

1 message(s)
```

### Search

`--raw` takes a Gmail search query; the structured flags are a convenience layer over
IMAP SEARCH. The two modes cannot be combined.

```bash
gmail.py search --raw "from:bob has:attachment newer_than:7d"
gmail.py search --raw "is:unread label:receipts" --limit 10

gmail.py search --from "bob@example.com" --unread
gmail.py search --subject "invoice" --since 2026-09-01 --before 2026-10-01
gmail.py search --from "bob" --folder all --limit 5
```

`--folder` accepts `inbox` (default), `sent`, `all`, `trash`, `drafts`, `spam`, or an
exact mailbox name. Folder names are discovered from the account rather than
hardcoded, so localized mailboxes work.

Operators like `has:attachment`, `label:`, and `newer_than:` have no IMAP equivalent
and are available only through `--raw`. Search terms must be ASCII.

### Read a Message

```bash
gmail.py read 4821
gmail.py read 4821 --full                           # no truncation
gmail.py read 4821 --html                           # raw HTML body
gmail.py read 4821 --save-attachments ./downloads
gmail.py read 902 --folder all
```

Bodies prefer `text/plain` and fall back to `text/html` rendered as plain text, and
are truncated at 4000 characters unless `--full` is given. Reading never marks a
message as read: fetches use `BODY.PEEK`.

### Threads

```bash
gmail.py thread 4821
```

Searches All Mail by Gmail thread id and renders the conversation oldest-first, so
your own replies (which live in Sent) appear alongside the messages you received.

### Mark

```bash
gmail.py mark 4821 --read
gmail.py mark 4821 --unread
gmail.py mark 4821 --archive
gmail.py mark 4821 --trash
```

Exactly one action is required. Archive and trash are `UID MOVE` operations, and
every action re-queries the message afterwards and reports the state actually
observed, including the message's new UID in its destination folder:

```
Archived
  UID              69
  Folder           inbox
  Moved to         all ([Gmail]/All Mail)
  New UID          579
  Still in source  no
  Status           unread
```

Archiving preserves read/unread state. Trash is destructive.

### Reply

```bash
gmail.py reply 4821 --body "Sounds good, shipping today."
gmail.py reply 4821 --body "See below." --quote
gmail.py reply 4821 --all --body "Looping in the team."
gmail.py reply 4821 --body "Draft" --dry-run
```

Sets `In-Reply-To` and `References` from the original, prefixes the subject with `Re:`
when it isn't already, and replies to the original `Reply-To` (or `From`). `--all`
adds the original To and Cc recipients, minus your own address. `--quote` appends an
attribution line and a `> `-prefixed copy of the original. Accepts the same content
flags as `send`.

### Send Plain Text Email

```bash
gmail.py send --to "friend@example.com" --subject "Hello" --body "How are you?"
```

### Send HTML Email

```bash
gmail.py send --to "team@work.com" --subject "Update" --html "<h1>Status</h1><p>All systems operational.</p>"
```

### Send Multipart Email (Text + HTML)

```bash
gmail.py send --to "user@example.com" --subject "Newsletter" \
  --body "Plain text for email clients that don't support HTML" \
  --html "<h1>Newsletter</h1><p>Rich HTML version</p>"
```

### Send with Attachments

```bash
gmail.py send --to "boss@work.com" --subject "Report" \
  --body "Please see the attached report." \
  --attach report.pdf

# Multiple attachments
gmail.py send --to "team@work.com" --subject "Files" \
  --body "Here are the files." \
  --attach document.pdf --attach data.csv --attach image.png
```

### Send from Files

```bash
# Text body from file
gmail.py send --to "user@example.com" --subject "Message" --body-file message.txt

# HTML body from file
gmail.py send --to "user@example.com" --subject "Newsletter" --html-file newsletter.html

# Both from files
gmail.py send --to "user@example.com" --subject "Update" \
  --body-file plain.txt --html-file rich.html
```

### Multiple Recipients

```bash
# Multiple To recipients
gmail.py send --to "a@example.com,b@example.com" --subject "FYI" --body "Info for all"

# With CC and BCC
gmail.py send --to "primary@example.com" \
  --cc "copy1@example.com,copy2@example.com" \
  --bcc "hidden@example.com" \
  --subject "Update" --body "Message content"
```

### Dry Run (Preview)

```bash
gmail.py send --to "test@example.com" --subject "Test" --body "Hello" --dry-run
```

## Send Command Options

| Option | Required | Description |
|--------|----------|-------------|
| `--to`, `-t` | Yes | Recipient(s), comma-separated |
| `--subject`, `-s` | Yes | Email subject line |
| `--body`, `-b` | No* | Plain text body |
| `--body-file` | No* | Read plain text body from file |
| `--html` | No* | HTML body |
| `--html-file` | No* | Read HTML body from file |
| `--cc` | No | CC recipient(s), comma-separated |
| `--bcc` | No | BCC recipient(s), comma-separated |
| `--attach`, `-a` | No | File attachment (can be repeated) |
| `--dry-run` | No | Preview email without sending |

*At least one of `--body`, `--body-file`, `--html`, or `--html-file` is required

## Retrieval Command Options

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
| `--folder` | No | Folder to search (default: inbox) |
| `--limit`, `-n` | No | Maximum messages (default: 20) |

*Either `--raw` or one or more structured flags; the two cannot be combined

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
| `--attach`, `-a` | No | File attachment (can be repeated) |
| `--dry-run` | No | Preview without sending |

*At least one content option required

## Email Types

| Content Provided | Email Type |
|------------------|------------|
| `--body` only | Plain text email |
| `--html` only | HTML email |
| `--body` + `--html` | Multipart alternative (both versions) |
| Any + `--attach` | Multipart mixed with attachments |

## Agent Skill

This project includes a `SKILL.md` file for use with AI coding agents (Claude Code, etc.). The skill enables natural language email composition and sending.

### Installation

```bash
# Create skills directory
mkdir -p /path/to/agent/skills

# Copy SKILL.md
cp /path/to/gmail.py/SKILL.md /path/to/agent/skills/gmail/SKILL.md

# Ensure gmail.py is in PATH (see installation above)

# Set credentials (in bashrc, zshrc, ...)
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
```

### Usage with Claude Code

Add the skills directory to your agent configuration, then interact naturally:

> "Send an email to john@example.com saying I'll be late to the meeting"
> "Email the team the weekly status update"
> "Send the report.pdf to my boss with a note about Q4 results"
> "What's unread in my inbox?"
> "Find the invoice Bob sent last week and save the attachment"
> "What did Bob say about the invoice? Show me the whole thread"
> "Reply to that and tell him it's approved"

The agent reads `SKILL.md` to understand available commands, options, and how to compose emails.

## Security Notes

- App Passwords are separate from your main Google password
- Credentials should be stored in environment variables, not in scripts, and are never written to disk
- SSL/TLS encryption is enforced for both SMTP (port 465) and IMAP (port 993)
- BCC recipients are not visible to other recipients
- `mark --trash` is destructive; `mark --archive` is reversible and preserves read state

## Gmail Limitations

- Gmail has daily sending limits (500 emails for regular accounts)
- Bulk email operations may trigger spam filters
- New accounts may have reduced sending reputation
