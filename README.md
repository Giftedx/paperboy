# Automated Newspaper Downloader & Emailer

A GitHub Actions-powered solution that automatically downloads your daily newspaper subscription and emails it to a predefined list of recipients. This system runs completely free, leveraging GitHub Actions for scheduled execution and free tiers of cloud storage and email services.

## 🌟 Features

- **Automated Daily Downloads:** Logs into your newspaper subscription website, locates, and downloads the daily edition
- **Cloud Storage:** Stores the current and past 6 days' newspapers in Cloudflare R2 (or S3) with zero cost
- **Email Notifications:** Sends beautiful HTML emails with:
  - Embedded newspaper thumbnail
  - Direct link to the day's newspaper
  - Links to the past 6 days' papers
  - Compatible with multiple email providers (SendGrid, Mailgun)
- **Robust Design:**
  - Fallback mechanisms for JavaScript-heavy websites (Playwright)
  - Multiple thumbnail generation options (PyMuPDF, pdf2image)
  - Error handling and detailed logging

## 🛠️ Setup Instructions

### 1. Prerequisites

- A GitHub account (free)
- A newspaper subscription with web login
- A Cloudflare R2 account (free tier) or AWS S3
- A SendGrid account (free tier) or Mailgun account

### 2. Fork/Clone This Repository

Start by forking this repository to your GitHub account or creating a new repository and copying these files.

### 3. Set Up Cloud Storage

#### Option A: Cloudflare R2 (Recommended)

1. Sign up for a [Cloudflare account](https://dash.cloudflare.com/sign-up) if you don't have one
2. Navigate to R2 in the Cloudflare dashboard
3. Create a new R2 bucket (e.g., `newspaper-storage`)
4. Create an API token with read/write access to your bucket
5. Note your Account ID, Access Key ID, and Secret Access Key

For public access to your files, you'll need to set up a Cloudflare Worker or R2 bucket public access.

#### Option B: AWS S3

1. Create an AWS account if you don't have one
2. Create an S3 bucket with appropriate permissions
3. Create an IAM user with programmatic access and S3 permissions
4. Note your Access Key ID and Secret Access Key

### 4. Set Up Email Service

#### Option A: SendGrid (Recommended)

1. Sign up for a [SendGrid account](https://signup.sendgrid.com/) (free tier allows 100 emails/day)
2. Create an API key with mail send permissions
3. Verify a sender email address

#### Option B: Mailgun

1. Sign up for a [Mailgun account](https://signup.mailgun.com/new/signup) (free tier allows sending to authorized recipients)
2. Get your API key and domain information
3. Add recipients to your authorized recipients list (for the sandbox domain)

### 5. Configure GitHub Repository Secrets

In your GitHub repository, go to Settings → Secrets and variables → Actions, and add the following secrets:

**Required Secrets:**

| Secret Name | Description |
|-------------|-------------|
| `NEWSPAPER_URL` | URL of your newspaper login page |
| `NEWSPAPER_USERNAME` | Your username/email for the newspaper site |
| `NEWSPAPER_PASSWORD` | Your password for the newspaper site |
| `STORAGE_PROVIDER` | Set to `R2` or `S3` |
| `STORAGE_BUCKET_NAME` | Name of your storage bucket |
| `EMAIL_SERVICE` | Set to `sendgrid` or `mailgun` |
| `EMAIL_SENDER` | Your verified sender email |
| `MAILING_LIST` | Comma-separated list of recipient emails |

**Cloud Storage Secrets:**

For R2:
```
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_PUBLIC_URL_PREFIX (URL where files can be accessed)
```

For S3:
```
S3_ACCESS_KEY_ID
S3_SECRET_ACCESS_KEY
S3_REGION
S3_PUBLIC_URL_PREFIX (optional)
```

**Email Service Secrets:**

For SendGrid:
```
SENDGRID_API_KEY
```

For Mailgun:
```
MAILGUN_API_KEY
MAILGUN_DOMAIN
```

**Optional Secrets:**

```
NEWSPAPER_DOWNLOAD_PAGE (if different from login page)
DOWNLOAD_LINK_SELECTOR (CSS selector to find download link)
EMAIL_SUBJECT_PREFIX (default: "Daily Newspaper")
```

### 6. Customize the Email Template (Optional)

If you want to customize the email appearance, you can modify `templates/email_template.html`.

### 7. Enable GitHub Actions

Make sure GitHub Actions are enabled for your repository. The workflow is scheduled to run daily at 6:00 AM UTC, but you can modify this in `.github/workflows/daily_newspaper.yaml`.

### 8. Manual Testing

You can manually trigger the workflow from the "Actions" tab in your GitHub repository to test the setup before the scheduled run.

## 📋 Troubleshooting

If you encounter issues:

1. Check the GitHub Actions logs for detailed error messages
2. Ensure all secrets are correctly configured
3. Verify your newspaper website hasn't changed its login or download process
4. Confirm your cloud storage credentials have proper permissions
5. Verify your email service is properly set up

Common issues:

- **Login failures:** The newspaper site might use non-standard login forms; try setting `DOWNLOAD_LINK_SELECTOR` to a specific CSS selector
- **Download issues:** If the site uses complex JavaScript, the system will automatically try Playwright as a fallback
- **Storage errors:** Verify your bucket permissions and credentials
- **Email failures:** Check your email service dashboard for errors or limits

## 🔄 How It Works

1. The GitHub Action runs at the scheduled time (6:00 AM UTC daily)
2. The script logs into your newspaper website and downloads the daily edition
3. It generates a thumbnail of the first page
4. The newspaper and thumbnail are uploaded to cloud storage
5. Old newspapers (beyond 7 days) are automatically removed
6. An email with links to all available newspapers is sent to your mailing list

## 📝 License

This project is available under the MIT License - see the LICENSE file for details.

## 💡 Customization

- **Email Frequency:** Modify the cron schedule in the workflow file
- **Storage Duration:** Change the `RETENTION_DAYS` variable in `main.py` (default: 7 days)
- **Appearance:** Modify the HTML email template in `templates/email_template.html`

## ⚠️ Important Notes

- Ensure your automation complies with the Terms of Service of your newspaper subscription
- Keep your repository private to protect your credentials
- GitHub Actions provides 2,000 free minutes per month, which is more than sufficient for this automation
- Cloud storage and email services are used within their free tiers 