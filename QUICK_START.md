# Quick Start Guide

Get the Newspaper Emailer running in 5 minutes (simplified version).

## Prerequisites
- Python 3.8 or higher
- S3-compatible storage (Cloudflare R2 or AWS S3)
- SMTP account (no SendGrid/Mailgun API usage)

## 1. Clone and Setup
```bash
git clone <your-repo-url>
cd newspaper-emailer
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Configure
Create `config.yaml` and `.env` in the project root. Minimal example:
```yaml
newspaper:
  url: "https://example.com"
  download_path_pattern: "newspaper/download/{date}"

storage:
  endpoint_url: "https://<ACCOUNT_ID>.r2.cloudflarestorage.com"
  access_key_id: "..."
  secret_access_key: "..."
  region: "auto"
  bucket: "newspaper-storage"

email:
  sender: "sender@example.com"
  recipients: ["you@example.com"]
  smtp_host: "smtp.example.com"
  smtp_port: 587
  smtp_user: "user"
  smtp_pass: "pass"
  smtp_tls: 1
```

## 3. Dry Run
```bash
python3 main.py
```
This will load configuration and run the pipeline. Logs go to `logs/newspaper_emailer.log`.

## 4. Schedule (Optional)
- Linux/macOS (cron): `0 6 * * * /path/to/.venv/bin/python /path/to/main.py`
- Windows (Task Scheduler): See `schedule_task.ps1`

## Troubleshooting
- Check logs: `logs/newspaper_emailer.log`
- Verify the download URL pattern resolves for your newspaper site
- Verify storage bucket permissions and SMTP credentials

## Next Steps
- Read `README.md` for details
- See `templates/email_template.html` to customize the email
- Explore `config.yaml` options such as retention and filename templates