# Local Setup for Newspaper Downloader (Simplified)

This guide helps you set up the simplified daily newspaper downloader locally.

## Prerequisites

- Python 3.8 or higher
- A newspaper subscription with web login
- Cloudflare R2 (S3-compatible) or AWS S3
- SMTP credentials (no SendGrid/Mailgun API usage)

## Step 1: Configure Storage Provider

### Option A: Cloudflare R2 (Recommended)

1. Create an R2 bucket (e.g., `newspaper-storage`)
2. Create an API token with read/write access
3. Note your Account ID, Access Key ID, and Secret Access Key

Endpoint template: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`

### Option B: AWS S3

1. Create an S3 bucket with appropriate permissions
2. Create an IAM user with programmatic access and S3 permissions
3. Note your Access Key ID and Secret Access Key

## Step 2: Configure Email (SMTP)

Collect these details from your provider:
- SMTP host, port
- SMTP user, password
- Sender email (must be authorized)

## Step 3: Create Configuration Files

Create `config.yaml` and `.env` in the project root. Minimum keys in `config.yaml`:

```yaml
newspaper:
  url: "https://example.com"
  username: "your_username"
  password: "your_password"
  download_path_pattern: "newspaper/download/{date}"

storage:
  endpoint_url: "https://<ACCOUNT_ID>.r2.cloudflarestorage.com"
  access_key_id: "your-access-key-id"
  secret_access_key: "your-secret-access-key"
  region: "auto"
  bucket: "newspaper-storage"

general:
  retention_days: 7
  date_format: "%Y-%m-%d"
  filename_template: "{date}_newspaper.{format}"
  thumbnail_filename_template: "{date}_thumbnail.{format}"

email:
  sender: "sender@example.com"
  recipients:
    - "recipient1@example.com"
  subject_template: "Your Daily Newspaper - {{ date }}"
  template: "email_template.html"
  smtp_host: "smtp.example.com"
  smtp_port: 587
  smtp_user: "smtp_user@example.com"
  smtp_pass: "your-smtp-password"
  smtp_tls: 1
  alert_recipient: "admin@example.com"

paths:
  download_dir: "downloads"
  template_dir: "templates"
```

Note: Secrets can be stored in `.env` and read as environment variables. You may override paths with:
- `NEWSPAPER_CONFIG` for `config.yaml`
- `NEWSPAPER_ENV` for `.env`

## Step 4: Install and Test

Create a virtual environment and install dependencies:

```bash
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

Run the pipeline for today:

```bash
python3 main.py
```

This will:
1. Download the newspaper via a simple GET to `<base_url>/newspaper/download/<YYYY-MM-DD>`
2. Generate a PDF thumbnail (if PDF)
3. Upload files to S3-compatible storage
4. Send an email with links

## Step 5: Schedule Daily Execution

### Windows (Task Scheduler)
Run the provided PowerShell script (as Administrator):

```powershell
powershell -ExecutionPolicy Bypass -File schedule_task.ps1
```

### Linux/macOS (cron)

```bash
crontab -e
# Add:
0 6 * * * /path/to/venv/bin/python /path/to/main.py
```

## Troubleshooting

- Check logs under `logs/` and `newspaper_emailer.log`
- Verify the download URL pattern is valid for your site
- Verify storage and SMTP credentials

## Notes

- This simplified version uses a single implementation with no fallbacks or GUI.
- PDF-only thumbnails (PyMuPDF + Pillow). If HTML is served, email is sent without a thumbnail. 