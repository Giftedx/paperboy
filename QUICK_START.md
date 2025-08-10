# Quick Start Guide

Get the Newspaper Emailer running in 5 minutes!

## Prerequisites

- Python 3.8 or higher
- A newspaper subscription with web login
- Cloudflare R2 account (free) or AWS S3
- SendGrid account (free) or Mailgun account

## 1. Clone and Setup

```bash
git clone <your-repo-url>
cd newspaper-emailer
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements_basic.txt
```

## 2. Run Onboarding

```bash
python3 run_newspaper.py --onboarding
```

This creates `config.yaml` and `.env` files. Edit them with your credentials.

## 3. Test Your Setup

```bash
python3 run_newspaper.py --health
```

This checks your configuration, storage, and email setup.

## 4. Run a Test Download

```bash
python3 run_newspaper.py --dry-run
```

This simulates the full pipeline without actually downloading or sending emails.

## 5. Start the GUI (Optional)

```bash
python3 gui_app.py
```

Open http://localhost:5000 in your browser for the web interface.

## 6. Set Up Automation

### Option A: System Scheduler
- **Windows**: Use `schedule_task.ps1` (run as administrator)
- **Linux/macOS**: Add to crontab: `0 6 * * * /path/to/run_newspaper.py`

### Option B: GUI Scheduler
Use the built-in scheduler in the web interface.

## Configuration Files

- `config.yaml` - General settings (newspaper URL, email templates, etc.)
- `.env` - Sensitive credentials (passwords, API keys)

## Troubleshooting

1. **Configuration errors**: Check `newspaper_emailer.log`
2. **Import errors**: Install missing packages with `pip install -r requirements.txt`
3. **Storage errors**: Verify your R2/S3 credentials and bucket permissions
4. **Email errors**: Check your SendGrid/Mailgun configuration

## Next Steps

- Read `README.md` for detailed setup instructions
- Read `LOCAL_SETUP.md` for advanced configuration
- Check `CODEBASE_ANALYSIS.md` for development insights

## Support

- Check the logs in `newspaper_emailer.log`
- Review the test files in the `tests/` directory
- Use `python3 run_newspaper.py --health` for diagnostics