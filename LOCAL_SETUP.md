# Local Setup for Newspaper Downloader

This guide will help you set up the newspaper downloader to run on your local machine.

## Prerequisites

- Python 3.8 or higher
- A newspaper subscription with web login
- A Cloudflare R2 account (free tier) or AWS S3 account
- A SendGrid account (free tier) or Mailgun account
- Poppler utilities (if using `pdf2image` as a fallback for PDF thumbnails, e.g., `pdftoppm`).

## Step 1: Configure Storage Provider

### Option A: Cloudflare R2 (Recommended)

1. Sign up for a [Cloudflare account](https://dash.cloudflare.com/sign-up) if you don't have one
2. Navigate to R2 in the Cloudflare dashboard
3. Create a new R2 bucket (e.g., `newspaper-storage`)
4. Create an API token with read/write access to your bucket
5. Note your Account ID, Access Key ID, and Secret Access Key

For public access to your files, you'll need to set up:
- R2 bucket public access, or
- A Cloudflare Worker to serve files

### Option B: AWS S3

1. Create an AWS account if you don't have one
2. Create an S3 bucket with appropriate permissions
3. Create an IAM user with programmatic access and S3 permissions
4. Note your Access Key ID and Secret Access Key

## Step 2: Configure Email Service

### Option A: SendGrid (Recommended)

1. Sign up for a [SendGrid account](https://signup.sendgrid.com/) (free tier allows 100 emails/day)
2. Create an API key with mail send permissions
3. Verify a sender email address

### Option B: Mailgun

1. Sign up for a [Mailgun account](https://signup.mailgun.com/new/signup) (free tier allows sending to authorized recipients)
2. Get your API key and domain information
3. Add recipients to your authorized recipients list (for the sandbox domain)

## Step 3: Configure the Application

The primary configuration for the application is handled by `config.yaml` located in the project root. For sensitive credentials (like passwords and API keys), it's highly recommended to use a `.env` file, also in the project root.

**Preferred Method: Onboarding Script**

The easiest way to create your initial `config.yaml` and `.env` files is to use the onboarding command:

```bash
python run_newspaper.py --onboarding
```
This script will guide you through setting up the essential configurations.

**Manual Configuration:**

If you prefer to create or edit the files manually:

1.  **`config.yaml` (Project Root):**
    *   Create or edit `config.yaml` in the root of the project directory.
    *   This file stores general settings like newspaper URL, CSS selectors, storage provider choice (R2/S3), email delivery method (SMTP/SendGrid), retention days, paths, etc.
    *   Refer to the comments within `config.yaml` (if available) or the main `README.md` for details on each option.
2.  **`.env` (Project Root):**
    *   Create a `.env` file in the root of the project directory.
    *   This file should store all your secrets, such as:
        *   `NEWSPAPER_USERNAME="your_username"`
        *   `NEWSPAPER_PASSWORD="your_password"`
        *   `STORAGE_ENDPOINT_URL="your_r2_or_s3_endpoint"`
        *   `STORAGE_ACCESS_KEY_ID="your_storage_access_key"`
        *   `STORAGE_SECRET_ACCESS_KEY="your_storage_secret_key"`
        *   `EMAIL_SMTP_HOST="your_smtp_host"`
        *   `EMAIL_SMTP_USER="your_smtp_user"`
        *   `EMAIL_SMTP_PASS="your_smtp_password"`
        *   `EMAIL_SENDGRID_API_KEY="your_sendgrid_api_key"`
    *   The application will automatically load these variables from the `.env` file. Values set in `.env` (or as system environment variables) will override those in `config.yaml`.

**Custom Configuration Paths (Optional):**

You can specify custom paths for your configuration files using environment variables:
*   `NEWSPAPER_CONFIG`: Set this to the absolute path to your `config.yaml` file.
*   `NEWSPAPER_ENV`: Set this to the absolute path to your `.env` file.

**After configuration, ensure you update:**
*   Your newspaper website URL (in `config.yaml`), username (in `.env`), and password (in `.env`).
*   Your storage provider settings (choice in `config.yaml`, credentials in `.env`).
*   Your email service settings (choice in `config.yaml`, credentials in `.env`).
*   The recipient email addresses in `config.yaml`.

## Step 4: Test the Application

Run the application manually to test that everything is working:

```bash
python run_newspaper.py
```

This will:
1. Log into your newspaper website and download the daily edition
2. Generate a thumbnail of the first page
3. Upload the newspaper and thumbnail to cloud storage
4. Send an email with links to the current and past newspapers

## Step 5: Set Up Scheduled Execution

### For Windows:

Run the PowerShell script to create a scheduled task:

```powershell
# Run as administrator
powershell -ExecutionPolicy Bypass -File schedule_task.ps1
```

This will create a scheduled task that runs daily at 6:00 AM. You can modify the schedule in Task Scheduler if needed.

### For Linux/macOS:

Set up a cron job to run the script daily:

1. Open your crontab:
   ```bash
   crontab -e
   ```

2. Add a line to run the script daily at 6:00 AM. **Important:** Replace `/path/to/your/project_directory` with the actual absolute path to your project directory. The `run_newspaper.py` script is assumed to be in this directory.

   Example:
   ```cron
   0 6 * * * cd /home/user/newspaper-downloader && /usr/bin/python /home/user/newspaper-downloader/run_newspaper.py
   ```
   Using `cd` to the project directory first is recommended to ensure any relative paths used by the script (e.g., for templates, logs, or the `config.yaml` and `.env` files in the project root) resolve correctly.

### GUI Scheduler (Alternative)

The application also includes a basic scheduler accessible via its web GUI (`gui_app.py`).

*   **To Use:** Run `python gui_app.py` and navigate to the scheduler section in your web browser (usually at `http://127.0.0.1:5000/`).
*   **Functionality:** Allows you to set a schedule for the newspaper download task directly from the GUI.
*   **Limitations:**
    *   The GUI scheduler runs as part of the Python process hosting the web application. If the `gui_app.py` script is stopped, the scheduler will also stop.
    *   It may not be as robust for long-term, unattended execution as system-level schedulers like cron or Windows Task Scheduler. It's generally more suited for interactive use or testing.
*   **Recommendation:** For production environments or where high reliability is critical, using system schedulers (cron, Task Scheduler) is generally preferred. The GUI scheduler is provided as a convenience.

## Troubleshooting

- Check the log file at `logs/app.log` (this is the default path, it can be configured via the `log_file_path` setting in `config.yaml` or the `LOG_FILE_PATH` environment variable) for detailed error messages.
- Ensure your newspaper website hasn't changed its login or download process.
- Verify your cloud storage credentials have proper permissions.
- Check your email service dashboard for errors or limits.

## Important Notes

- Ensure your automation complies with the Terms of Service of your newspaper subscription.
- Keep your credentials secure and never share them.
- Cloud storage and email services are used within their free tiers.
- The system keeps the last 7 days of newspapers (including today), by default (configurable via `general.retention_days` in `config.yaml`).
