---
name: email
description: Send emails via Gmail SMTP. Use when the user wants to send an email, compose a message, share files via email, or notify someone by email. Supports plain text, HTML, attachments, and multiple recipients.
compatibility: Requires 'email.py' script in PATH with GMAIL_USER and GMAIL_APP_PASSWORD environment variables set.
---

# Gmail Email Tool

Send emails using the `email.py` CLI powered by Gmail SMTP. Supports plain text, HTML, attachments, and multiple recipients.

## Authentication

Credentials are loaded from environment variables:
```bash
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
```

Or passed directly: `email.py --user EMAIL --password PASSWORD send ...`

App Passwords are required (not regular Gmail passwords). Generate at: https://myaccount.google.com/apppasswords

## Commands Reference

### Send Plain Text Email
```bash
email.py send --to "recipient@example.com" --subject "Hello" --body "Message content here"
```

### Send HTML Email
```bash
email.py send --to "recipient@example.com" --subject "Update" --html "<h1>Title</h1><p>Rich content</p>"
```

### Send Multipart Email (Text + HTML)
```bash
email.py send --to "recipient@example.com" --subject "Newsletter" \
  --body "Plain text fallback for old email clients" \
  --html "<h1>Newsletter</h1><p>Rich HTML version</p>"
```

Email clients will display HTML if supported, otherwise fall back to plain text.

### Send with Attachments
```bash
# Single attachment
email.py send --to "recipient@example.com" --subject "Report" \
  --body "Please see attached." --attach report.pdf

# Multiple attachments
email.py send --to "recipient@example.com" --subject "Files" \
  --body "Here are the requested files." \
  --attach document.pdf --attach spreadsheet.xlsx --attach image.png
```

### Send from Files
```bash
# Text body from file
email.py send --to "recipient@example.com" --subject "Message" --body-file message.txt

# HTML body from file
email.py send --to "recipient@example.com" --subject "Newsletter" --html-file template.html

# Both from files
email.py send --to "recipient@example.com" --subject "Update" \
  --body-file plain.txt --html-file rich.html
```

### Multiple Recipients
```bash
# Comma-separated To recipients
email.py send --to "alice@example.com,bob@example.com" --subject "Team Update" --body "Info for everyone"

# With CC
email.py send --to "primary@example.com" --cc "copy@example.com" --subject "FYI" --body "Content"

# With BCC (hidden recipients)
email.py send --to "visible@example.com" --bcc "hidden@example.com" --subject "Notice" --body "Content"

# Full example
email.py send \
  --to "main@example.com,other@example.com" \
  --cc "manager@example.com" \
  --bcc "archive@example.com" \
  --subject "Project Update" \
  --body "Status update for everyone"
```

### Dry Run (Preview Without Sending)
```bash
email.py send --to "test@example.com" --subject "Test" --body "Hello" --dry-run
```

Shows full email preview including headers and MIME structure without actually sending.

## Command Options

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

## Example Workflows

### Quick Message
```bash
email.py send --to "friend@example.com" --subject "Quick note" --body "Just wanted to say hi!"
```

### Professional Email with Signature
```bash
email.py send --to "client@company.com" --subject "Meeting Follow-up" \
  --body "Thank you for your time today. I've attached the proposal we discussed.

Best regards,
Your Name" \
  --attach proposal.pdf
```

### HTML Newsletter
```bash
email.py send --to "subscribers@example.com" --subject "Weekly Update" \
  --body "This email requires HTML support to view properly." \
  --html "<html><body><h1>Weekly Update</h1><p>Here's what happened this week...</p></body></html>"
```

### Send Report to Multiple Stakeholders
```bash
email.py send \
  --to "team-lead@company.com" \
  --cc "manager@company.com,director@company.com" \
  --subject "Q4 Report" \
  --body "Please find the Q4 report attached." \
  --attach q4-report.pdf --attach financials.xlsx
```

### Compose from Files (For Long Content)
```bash
# Create content files first, then send
email.py send --to "recipient@example.com" --subject "Detailed Update" \
  --body-file ~/drafts/update.txt \
  --attach ~/documents/supporting-data.pdf
```

## Tips

- Use `--dry-run` first to preview complex emails before sending
- For long messages, write content to a file and use `--body-file`
- Always provide `--body` with `--html` for maximum compatibility
- BCC recipients cannot see each other or be seen by To/CC recipients
- Attachment file paths can be relative or absolute
- Subject lines should be concise (under 60 characters ideal)
- Gmail has a 25MB attachment limit per email
