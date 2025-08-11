# Automated Newspaper Downloader & Emailer (Simplified)

A lean solution that automatically downloads your daily newspaper and emails links to recipients. This version uses a single, straightforward implementation with no fallbacks or optional UIs.

## Features

- Simple daily download via HTTP GET from your newspaper site
- Cloud storage upload to any S3-compatible service (AWS S3, Cloudflare R2)
- SMTP email with a Jinja2 HTML template and optional inline thumbnail (from PDF first page)
- Clean configuration via `config.yaml` and `.env`

## Stack

- Download: requests (simple GET to a predictable URL)
- Storage: boto3 (S3-compatible)
- Email: SMTP only (no SendGrid API)
- Thumbnail: PyMuPDF + Pillow (PDF only)

## Setup

1. Create and fill in `config.yaml` and `.env` (see Configuration below).
2. Ensure your S3-compatible storage credentials and SMTP credentials are valid.
3. Install dependencies in a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

4. Run a dry test:

```bash
python3 main.py
```

By default, the script targets today. Use environment variables to override behavior if needed.

## Configuration

All settings come from `config.yaml` (non-secrets) and `.env` (secrets). You can also use environment variables to override any key.

Minimum required keys in `config.yaml`:

```yaml
newspaper:
  url: "https://example.com"  # Base site URL
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

Notes:
- Only SMTP is supported (no SendGrid/Mailgun API). Put SMTP secrets in `.env`.
- Thumbnail generation is PDF-only. If the site serves HTML, the email will be sent without a thumbnail.

## How it works

1. Build a download URL at `<base_url>/newspaper/download/<YYYY-MM-DD>`
2. Download the file via requests and save to `paths.download_dir`
3. Generate a PDF thumbnail (if applicable)
4. Upload the newspaper and thumbnail to S3-compatible storage
5. Email the recipients with links and an inline thumbnail (if present)
6. Clean up old files in storage beyond `retention_days`

## Automation

Use your system scheduler (cron, Task Scheduler) to run daily. Example cron:

```
0 6 * * * /path/to/.venv/bin/python /path/to/main.py
```

## Troubleshooting

- Check the logs in `logs/newspaper_emailer.log`
- Verify storage credentials and bucket permissions
- Verify SMTP credentials and that your sender is allowed to send
- Ensure the expected download URL is valid for your newspaper site

### Offline-friendly 'requests' fallback

- In restricted environments where installing packages is not possible, this repo includes a minimal local `requests.py` fallback.
- Behavior:
  - If the real `requests` library is installed, it is used automatically.
  - If not, the fallback provides a minimal `requests.get()` and `Response` to allow tests and dry-runs to pass. When offline, it may return a synthetic HTTP 200 response with empty content.
- Production recommendation: install real `requests` via `pip install -r requirements.txt`. You may remove `requests.py` if you prefer to avoid the fallback.
- To see which implementation is active:

```bash
python -c "import requests, inspect; print(getattr(requests, '__file__', 'builtin'))"
```

- Environment toggles:
  - `REQUESTS_FALLBACK_DISABLE=1` → Do not use the fallback; raise ImportError if the real library is absent.
  - `REQUESTS_FALLBACK_FORCE=1` → Force using the fallback even if the real library is installed (useful for testing).

## Customizing the email template

- The HTML template lives at `templates/email_template.html` and is rendered with Jinja2.
- You can reference these variables in the template:
  - `recipient`: optional recipient name or email
  - `date`: formatted date string
  - `today_paper_url`: public URL to today’s file
  - `past_papers`: list of `(date_str, url)` tuples
  - `thumbnail_cid`: inline image content-id for the thumbnail (if present)
  - `archive_summary`: short summary text under the list
- To use a different template file, set `email.template` in `config.yaml` and place your file under `paths.template_dir` (default `templates`).
- Basic styles can be added inline in the `<style>` section to improve email client compatibility.

## License

MIT