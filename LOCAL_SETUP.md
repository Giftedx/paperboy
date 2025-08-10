# Local Setup for Newspaper Downloader

This guide will help you set up the newspaper downloader to run on your local machine.

## Prerequisites

- Python 3.8 or higher
- A newspaper subscription with web login
- A Cloudflare R2 account (free tier) or AWS S3 account
- A SendGrid account (free tier) or Mailgun account
- Poppler Utilities: Required if `pdf2image` is used as a fallback for PDF thumbnail generation. Installation varies by OS (e.g., `poppler-utils` on Debian/Ubuntu, `poppler` on macOS via Homebrew).

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
   Note: Mailgun is used via generic SMTP settings in this project. For dedicated Mailgun API usage, further customization of `email_sender.py` would be required.

## Step 3: Configure the Application

1. Configure the application using one of these methods:

   **Option A: Use the onboarding wizard (Recommended)**
   ```bash
   python3 run_newspaper.py --onboarding
   ```
   This will create initial `config.yaml` and `.env` files in the project root.

   **Option B: Manual configuration**
   Edit the configuration files in the project root:
   - `config.yaml` - General settings (see example in the file)
   - `.env` - Sensitive credentials (create this file)

   Required settings:
   - Newspaper website URL, username, and password
   - Storage provider settings (R2 or S3)
   - Email service settings (SendGrid or Mailgun)
   - Recipient email addresses

**Environment Variable Overrides:**
You can override configuration file paths using environment variables:
- `NEWSPAPER_CONFIG` - Path to config.yaml file
- `NEWSPAPER_ENV` - Path to .env file

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

2. Add a line to run the script daily at 6:00 AM:
   ```
   0 6 * * * /usr/bin/python /path/to/your/run_newspaper.py
   ```

### Alternative: Use the Built-in GUI Scheduler

The application includes a web-based GUI with a built-in scheduler:

1. Start the GUI:
   ```bash
   python3 gui_app.py
   ```

2. Open your browser to `http://localhost:5000`

3. Navigate to the "Schedule" section to configure automated runs

**Note:** For production environments, system-level schedulers (cron/Task Scheduler) are recommended for better reliability.

## Troubleshooting

- Check the log file at `newspaper_emailer.log` in the project root for detailed error messages
- Ensure your newspaper website hasn't changed its login or download process
- Verify your cloud storage credentials have proper permissions
- Check your email service dashboard for errors or limits

## Important Notes

- Ensure your automation complies with the Terms of Service of your newspaper subscription
- Keep your credentials secure and never share them
- Cloud storage and email services are used within their free tiers
- The system keeps the last 7 days of newspapers (including today) 