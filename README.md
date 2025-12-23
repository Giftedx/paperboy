# Automated Newspaper Downloader & Emailer (Simplified)

A robust, automated pipeline designed to download your daily newspaper, process it, and email it to you. This solution is built for reliability and portability, capable of running in various environments (local, cloud, CI/CD) with minimal dependencies.

## Project Goals

**Primary Goal:** To provide a reliable, "set-and-forget" tool for self-hosters to automate the daily retrieval, archival, and delivery of digital newspaper editions (PDFs).

**Target Users:** Home lab enthusiasts, digital archivists, and subscribers who prefer offline or email-based reading workflows.

**Key Features:**
*   **Automated Delivery:** Fetches the daily edition, generates a visual thumbnail, and emails it to your inbox.
*   **Flexible Storage:** Supports stateless cloud storage (S3, Cloudflare R2) or persistent local storage.
*   **Security First:** Includes an interactive wizard (`configure.py`) that encrypts sensitive credentials (SMTP passwords, API keys) at rest.
*   **Resilience:** Features robust error handling, retries, and a fallback HTTP client for restricted network environments.
*   **Observability:** Integrated health checks and rich CLI status reporting.

**Non-Goals:**
*   This is not a general-purpose web scraper. It is designed for specific, predictable URL patterns.
*   It does not bypass paywalls; users must provide valid URLs or authentication for their content.

## Architecture

The system operates as a linear pipeline orchestrated by `main.py`.

1.  **Configuration**: Centralized settings management (`config.py`) loads parameters from `config.yaml` and environment variables (`.env`).
2.  **Download**: The `website` module authenticates (if necessary) and downloads the newspaper edition for the target date.
3.  **Storage**: The `storage` module handles interactions with S3-compatible cloud storage or the local filesystem.
4.  **Processing**: The `thumbnail` module generates a preview image of the newspaper's front page (PDF only).
5.  **Notification**: The `email_sender` module constructs an HTML email with download links and the inline thumbnail, sending it via SMTP.
6.  **Cleanup**: Old files are automatically purged from storage based on retention policy.

## Installation

### Prerequisites

*   **Python 3.8+**
*   **SMTP Credentials**: Access to an SMTP server (e.g., Gmail, SendGrid, or self-hosted) for sending emails.
*   **(Optional) S3 Credentials**: Access Key ID and Secret Key for S3-compatible storage (AWS S3, Cloudflare R2, MinIO). *Local storage is also supported.*

### Setup Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/newspaper-emailer.git
    cd newspaper-emailer
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # Linux/macOS
    # .venv\Scripts\activate   # Windows
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### Configuration

You can configure the application using the interactive wizard (recommended) or manually.

**Option A: Interactive Wizard (Recommended)**
Run the setup script to generate `config.yaml` and a secure `.env` file with encrypted credentials.
```bash
python configure.py
```

**Option B: Manual Configuration**
1.  **`config.yaml`**: Copy `config.yaml` to configure defaults.
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

2.  **`.env`**: Copy `.env.example` to `.env` and fill in your secrets.
    ```bash
    cp .env.example .env
    nano .env
    ```
    *Note: The system supports both plain text and encrypted credentials (using `_ENC` suffix) in `.env`.*

**Key Environment Variables (.env):**
*   `NEWSPAPER_URL`: Base URL for the publication.
*   `STORAGE_TYPE`: `s3` (default) or `local`.
*   `EMAIL_SMTP_HOST` / `EMAIL_SMTP_PASS`: SMTP server details.

### Verification

1.  **Run Health Check:**
    Verify your environment, dependencies, and configuration validity.
    ```bash
    python healthcheck.py
    ```

2.  **Manual Dry-Run:**
    Simulate a run without downloading or sending emails.
    ```bash
    export MAIN_PY_DRY_RUN=true
    python main.py
    ```

## Usage

### Manual Run

To run the pipeline for today's date:
```bash
python main.py
```

To target a specific date:
```bash
export MAIN_PY_TARGET_DATE="2023-10-27"
python main.py
```

### Automation

Schedule `main.py` using `cron` (Linux) or Task Scheduler (Windows).

**Example Cron Job (Daily at 6:00 AM):**
```cron
0 6 * * * /path/to/repo/.venv/bin/python /path/to/repo/main.py >> /path/to/repo/logs/cron.log 2>&1
```

## Development

-   **Running Tests**: `python run_tests.py` performs static analysis and structure checks.
-   **Health Check**: `python healthcheck.py` runs a full diagnostic suite.
-   **Docstrings**: All code is documented using Google Style Python Docstrings.

## License

MIT
