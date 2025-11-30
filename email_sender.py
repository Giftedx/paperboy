#!/usr/bin/env python3
"""
Email sending module (simplified).

Single implementation: SMTP only with inline thumbnail CID.
"""

import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formataddr
import config

logger = logging.getLogger(__name__)


def _get_jinja_env():
    """Initializes the Jinja2 environment for template rendering.

    Returns:
        jinja2.Environment | None: The Jinja2 environment, or None if jinja2 is not installed.
    """
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape  # type: ignore
    except Exception:
        return None
    template_dir = config.config.get(('paths', 'template_dir'), 'templates')
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(['html', 'xml'])
    )


def _is_valid_email(addr: str) -> bool:
    """Basic email validation regex.

    Args:
        addr (str): The email address to validate.

    Returns:
        bool: True if the address matches the basic pattern.
    """
    import re
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", addr))


def _render_email_content(target_date, today_paper_url, past_papers, subject_template, template_name):
    """Renders the email subject and body.

    Uses Jinja2 if available, otherwise falls back to a simple HTML string.

    Args:
        target_date (date): The date of the newspaper.
        today_paper_url (str): The URL of today's downloaded newspaper.
        past_papers (list): List of tuples (date_str, url) for past newspapers.
        subject_template (str): Jinja2 template for the subject line.
        template_name (str): The filename of the HTML body template.

    Returns:
        tuple: (subject (str), html_body (str))
    """
    env = _get_jinja_env()
    date_str = target_date.strftime('%Y-%m-%d')
    recipient_name = None
    # subject
    if env is not None:
        try:
            subject = env.from_string(subject_template).render(date=date_str, recipient=recipient_name)
        except Exception:
            subject = f"Your Daily Newspaper - {date_str}"
        try:
            template = env.get_template(template_name)
            html_body = template.render(
                date=date_str,
                today_paper_url=today_paper_url,
                past_papers=past_papers,
                thumbnail_cid="thumbnail",
                recipient=recipient_name,
                archive_summary=f"You have access to the last {len(past_papers)} days of newspapers."
            )
            return subject, html_body
        except Exception:
            pass
    # Fallback simple HTML
    subject = f"Your Daily Newspaper - {date_str}"
    links_html = ''.join(f"<li><a href='{url}'>{d}</a></li>" for d, url in past_papers)
    html_body = f"""
    <html>
      <body>
        <p>Good day!</p>
        <p>Your newspaper for {date_str} is ready: <a href="{today_paper_url}">Download</a></p>
        <p>Recent archive:</p>
        <ul>{links_html}</ul>
      </body>
    </html>
    """
    return subject, html_body


def send_email(target_date, today_paper_url, past_papers, thumbnail_path=None, dry_run=False):
    """Prepares and sends the daily newspaper email.

    Args:
        target_date (date): The date of the newspaper.
        today_paper_url (str): Cloud URL for the newspaper file.
        past_papers (list): List of (date, url) tuples for previous editions.
        thumbnail_path (str | None): Path to local file or URL of the thumbnail image.
        dry_run (bool): If True, simulate sending without network usage.

    Returns:
        bool: True if sent (or simulated) successfully, False otherwise.
    """
    sender = config.config.get(('email', 'sender'))
    recipients = config.config.get(('email', 'recipients'), [])
    subject_template = config.config.get(('email', 'subject_template'), 'Your Daily Newspaper - {{ date }}')
    template_name = config.config.get(('email', 'template'), 'email_template.html')

    valid_recipients = [r for r in recipients if _is_valid_email(r)]
    if not valid_recipients:
        logger.error("No valid recipients found in config.")
        return False

    subject, html_body = _render_email_content(
        target_date, today_paper_url, past_papers, subject_template, template_name
    )

    # In dry_run mode, do not perform any network or file I/O for thumbnail fetching
    if dry_run:
        logger.info("[Dry Run] Would send email to: %s", valid_recipients)
        logger.info("Subject: %s", subject)
        logger.info("Body: %s", html_body[:200] + '...')
        if thumbnail_path:
            logger.info("[Dry Run] Would attach thumbnail reference: %s", thumbnail_path)
        return True

    thumbnail_data = None
    if thumbnail_path:
        if os.path.isfile(thumbnail_path):
            with open(thumbnail_path, 'rb') as f:
                thumbnail_data = f.read()
        elif thumbnail_path.startswith(('http://', 'https://')):
            try:
                try:
                    import requests  # pylint: disable=import-outside-toplevel
                except Exception:
                    logger.warning("requests not available; skipping thumbnail download from URL: %s", thumbnail_path)
                    requests = None  # type: ignore
                if requests:
                    response = requests.get(thumbnail_path, timeout=30)
                    response.raise_for_status()
                    thumbnail_data = response.content
                    logger.info("Downloaded thumbnail from URL: %s", thumbnail_path)
            except Exception as e:
                logger.warning("Failed to download thumbnail from URL %s: %s", thumbnail_path, e)
        else:
            logger.warning("Invalid thumbnail_path: %s (not a file or URL)", thumbnail_path)

    try:
        return _send_via_smtp(sender, valid_recipients, subject, html_body, thumbnail_data)
    except Exception as e:
        logger.error("Error sending email: %s", e)
        return False


def _send_via_smtp(sender, recipients, subject, html_body, thumbnail_data):
    """Sends the constructed email via SMTP.

    Args:
        sender (str): The 'From' address.
        recipients (list): List of 'To' addresses.
        subject (str): Email subject.
        html_body (str): HTML content of the email.
        thumbnail_data (bytes | None): Raw image data for inline attachment.

    Returns:
        bool: True on success.

    Raises:
        Exception: On SMTP failure.
    """
    smtp_host = config.config.get(('email', 'smtp_host'))
    smtp_port = int(config.config.get(('email', 'smtp_port'), 587))
    smtp_user = config.config.get(('email', 'smtp_user'))
    smtp_pass = config.config.get(('email', 'smtp_pass'))
    use_tls = bool(int(config.config.get(('email', 'smtp_tls'), 1)))

    msg = MIMEMultipart('related')
    msg['Subject'] = subject
    msg['From'] = formataddr(('Newspaper', sender))
    msg['To'] = ', '.join(recipients)

    msg.attach(MIMEText(html_body, 'html'))

    if thumbnail_data:
        image = MIMEImage(thumbnail_data)
        image.add_header('Content-ID', '<thumbnail>')
        msg.attach(image)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if use_tls:
                server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.sendmail(sender, recipients, msg.as_string())
        logger.info("Email sent via SMTP to %s", recipients)
        return True
    except Exception as e:
        logger.error("SMTP send failed: %s", e)
        return False


def send_alert_email(subject, message, dry_run=False):
    """Sends a plain text alert email to the admin.

    Args:
        subject (str): The subject line.
        message (str): The plain text message body.
        dry_run (bool): If True, simulate sending.

    Returns:
        bool: True if sent successfully, False otherwise.
    """
    sender = config.config.get(('email', 'sender'))
    alert_recipient = config.config.get(('email', 'alert_recipient'), sender)
    if not _is_valid_email(alert_recipient):
        logger.error("Invalid alert recipient: %s", alert_recipient)
        return False

    if dry_run:
        logger.info("[Dry Run] Would send alert to %s: %s", alert_recipient, subject)
        return True

    try:
        smtp_host = config.config.get(('email', 'smtp_host'))
        smtp_port = int(config.config.get(('email', 'smtp_port'), 587))
        smtp_user = config.config.get(('email', 'smtp_user'))
        smtp_pass = config.config.get(('email', 'smtp_pass'))
        use_tls = bool(int(config.config.get(('email', 'smtp_tls'), 1)))
        msg = MIMEText(message, 'plain')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = alert_recipient
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if use_tls:
                server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.sendmail(sender, [alert_recipient], msg.as_string())
        logger.info("Alert email sent to %s", alert_recipient)
        return True
    except Exception as e:
        logger.error("Failed to send alert email: %s", e)
        return False
