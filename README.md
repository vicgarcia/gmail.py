# email.py

A simple CLI for sending emails via Gmail SMTP.

## Features

- **Single-file executable** - Uses `uv run --script` with inline dependencies (PEP 723)
- **Gmail SMTP** - Secure SSL connection to Gmail's servers
- **Plain text emails** - Simple text messages
- **HTML emails** - Rich HTML formatted emails
- **Multipart emails** - Combined text and HTML for maximum compatibility
- **File attachments** - Attach any files to your emails
- **CC/BCC support** - Send to multiple recipients with full control
- **Dry run mode** - Preview emails without sending

## Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager
- Gmail account with App Password

## Gmail App Password Setup

Gmail requires an App Password (not your regular password) for SMTP access:

1. Enable 2-Step Verification on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Generate a new App Password (select "Mail" and your device)
4. Copy the 16-character password

## Installation

```bash
# Clone and make executable
git clone https://github.com/vicgarcia/email.py.git
cd email.py
chmod +x email.py

# Run
./email.py --help

# Install
cp email.py ~/.local/bin
chmod +x ~/.local/bin/email.py

# Set credentials
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
```

## Commands

| Command | Description |
|---------|-------------|
| `send` | Send an email |

## Usage

Set your credentials via environment variables:
```bash
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
```

Or pass them as arguments: `--user` and `--password`

### Send Plain Text Email

```bash
email.py send --to "friend@example.com" --subject "Hello" --body "How are you?"
```

### Send HTML Email

```bash
email.py send --to "team@work.com" --subject "Update" --html "<h1>Status</h1><p>All systems operational.</p>"
```

### Send Multipart Email (Text + HTML)

```bash
email.py send --to "user@example.com" --subject "Newsletter" \
  --body "Plain text for email clients that don't support HTML" \
  --html "<h1>Newsletter</h1><p>Rich HTML version</p>"
```

### Send with Attachments

```bash
email.py send --to "boss@work.com" --subject "Report" \
  --body "Please see the attached report." \
  --attach report.pdf

# Multiple attachments
email.py send --to "team@work.com" --subject "Files" \
  --body "Here are the files." \
  --attach document.pdf --attach data.csv --attach image.png
```

### Send from Files

```bash
# Text body from file
email.py send --to "user@example.com" --subject "Message" --body-file message.txt

# HTML body from file
email.py send --to "user@example.com" --subject "Newsletter" --html-file newsletter.html

# Both from files
email.py send --to "user@example.com" --subject "Update" \
  --body-file plain.txt --html-file rich.html
```

### Multiple Recipients

```bash
# Multiple To recipients
email.py send --to "a@example.com,b@example.com" --subject "FYI" --body "Info for all"

# With CC and BCC
email.py send --to "primary@example.com" \
  --cc "copy1@example.com,copy2@example.com" \
  --bcc "hidden@example.com" \
  --subject "Update" --body "Message content"
```

### Dry Run (Preview)

```bash
email.py send --to "test@example.com" --subject "Test" --body "Hello" --dry-run
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
cp /path/to/email.py/SKILL.md /path/to/agent/skills/email/SKILL.md

# Ensure email.py is in PATH (see installation above)

# Set credentials (in bashrc, zshrc, ...)
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
```

### Usage with Claude Code

Add the skills directory to your agent configuration, then interact naturally:

> "Send an email to john@example.com saying I'll be late to the meeting"
> "Email the team the weekly status update"
> "Send the report.pdf to my boss with a note about Q4 results"

The agent reads `SKILL.md` to understand available commands, options, and how to compose emails.

## Security Notes

- App Passwords are separate from your main Google password
- Credentials should be stored in environment variables, not in scripts
- SSL/TLS encryption is enforced (port 465)
- BCC recipients are not visible to other recipients

## Gmail Limitations

- Gmail has daily sending limits (500 emails for regular accounts)
- Bulk email operations may trigger spam filters
- New accounts may have reduced sending reputation
