# Automated Newspaper Downloader & Emailer (Simplified)

A robust, automated pipeline designed to download your daily newspaper, process it, and email it to you. This solution is built for reliability and portability, capable of running in various environments (local, cloud, CI/CD) with minimal dependencies.

## Architecture

The system operates as a linear pipeline orchestrated by `main.py`.

1.  **Configuration**: Centralized settings management (`config.py`) loads parameters from `config.yaml` and environment variables (`.env`).
2.  **Download**: The `website` module authenticates (if necessary) and downloads the newspaper edition for the target date.
3.  **Storage**: The `storage` module handles interactions with S3-compatible cloud storage (e.g., AWS S3, Cloudflare R2).
4.  **Processing**: The `thumbnail` module generates a preview image of the newspaper's front page (PDF only).
5.  **Notification**: The `email_sender` module constructs an HTML email with download links and the inline thumbnail, sending it via SMTP.
6.  **Cleanup**: Old files are automatically purged from storage based on retention policy.

## Features

-   **Daily Automation**: targets specific dates or defaults to "today".
-   **Resilient Downloading**: Includes a robust fallback for the `requests` library to ensure functionality in restricted environments.
-   **Cloud Storage**: Stateless design using S3-compatible storage for archives.
-   **Rich Emails**: HTML templates with Jinja2 support and inline visual previews.
-   **Health Checks**: Integrated diagnostics to verify environment integrity.

## Setup

### Prerequisites

-   Python 3.8+
-   SMTP credentials (for sending emails)
-   S3-compatible storage credentials (AWS, R2, MinIO, etc.)

### Installation

1.  Clone the repository.
2.  Create a virtual environment:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # Linux/Mac
    # or .venv\Scripts\activate  # Windows
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
    *Note: If running in a restricted environment, the system can operate with reduced functionality using built-in fallbacks.*

### Configuration

✨ **New! Interactive Setup Wizard**

We provide an interactive wizard to help you generate your configuration files easily.

```bash
python configure.py
```

Alternatively, you can manually configure the system:

Configuration is hierarchical: **YAML** < **Environment Variables**.

1.  **`config.yaml`**: Copy `config.yaml` (if not present) and set your defaults.
2.  **`.env`**: Create a `.env` file for secrets. This file is excluded from version control.

**Required Secrets (.env example):**
```env
NEWSPAPER_URL="https://example.com"
STORAGE_ACCESS_KEY_ID="your_key_id"
STORAGE_SECRET_ACCESS_KEY="your_secret_key"
EMAIL_SMTP_PASS="your_smtp_password"
```

**Key Configuration Options (`config.yaml`):**
```yaml
newspaper:
  url: "https://example.com"
  download_path_pattern: "newspaper/download/{date}"

storage:
  endpoint_url: "https://<account>.r2.cloudflarestorage.com"
  bucket: "newspaper-archive"

email:
  sender: "bot@example.com"
  recipients: ["user@example.com"]
  smtp_host: "smtp.example.com"
```

## Usage

### Manual Run

To run the pipeline for today's date:
```bash
python main.py
```

To run a dry-run (simulates actions without network/storage side-effects):
```bash
export MAIN_PY_DRY_RUN=true
python main.py
```

To target a specific date:
```bash
export MAIN_PY_TARGET_DATE="2023-10-27"
python main.py
```

### Automation

Schedule `main.py` using cron or a Task Scheduler.
Example cron (daily at 6:00 AM):
```cron
0 6 * * * /path/to/.venv/bin/python /path/to/repo/main.py
```

## Development

-   **Running Tests**: `python run_tests.py` performs static analysis and structure checks.
-   **Health Check**: `python healthcheck.py` runs a full diagnostic suite including a dry-run of the pipeline.
-   **Docstrings**: All code is documented using Google Style Python Docstrings.

## License

MIT
