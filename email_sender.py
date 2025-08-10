#!/usr/bin/env python3
"""
Email sending module (simplified)
Single implementation: SMTP only with inline thumbnail CID.
"""

import os
import logging
import smtplib
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formataddr
from jinja2 import Environment, FileSystemLoader, select_autoescape
import config

logger = logging.getLogger(__name__)


def _get_jinja_env():
    template_dir = config.config.get(('paths', 'template_dir'), 'templates')
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(['html', 'xml'])
    )


def _is_valid_email(addr: str) -> bool:
    import re
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", addr))


def send_email(target_date, today_paper_url, past_papers, thumbnail_path=None, dry_run=False):
    sender = config.config.get(('email', 'sender'))
    recipients = config.config.get(('email', 'recipients'), [])
    subject_template = config.config.get(('email', 'subject_template'), 'Your Daily Newspaper - {{ date }}')
    template_name = config.config.get(('email', 'template'), 'email_template.html')

    valid_recipients = [r for r in recipients if _is_valid_email(r)]
    if not valid_recipients:
        logger.error("No valid recipients found in config.")
        return False

    recipient_name = None
    if recipients and isinstance(recipients[0], str) and '@' in recipients[0]:
        recipient_name = recipients[0].split('@')[0].replace('.', ' ').title()

    archive_summary = f"You have access to the last {len(past_papers)} days of newspapers."

    env = _get_jinja_env()
    template = env.get_template(template_name)
    subject = env.from_string(subject_template).render(date=target_date.strftime('%Y-%m-%d'), recipient=recipient_name)
    html_body = template.render(
        date=target_date.strftime('%Y-%m-%d'),
        today_paper_url=today_paper_url,
        past_papers=past_papers,
        thumbnail_cid="thumbnail",
        recipient=recipient_name,
        archive_summary=archive_summary
    )

    thumbnail_data = None
    if thumbnail_path:
        if os.path.isfile(thumbnail_path):
            with open(thumbnail_path, 'rb') as f:
                thumbnail_data = f.read()
        elif thumbnail_path.startswith(('http://', 'https://')):
            try:
                response = requests.get(thumbnail_path, timeout=30)
                response.raise_for_status()
                thumbnail_data = response.content
                logger.info("Downloaded thumbnail from URL: %s", thumbnail_path)
            except Exception as e:
                logger.warning("Failed to download thumbnail from URL %s: %s", thumbnail_path, e)
        else:
            logger.warning("Invalid thumbnail_path: %s (not a file or URL)", thumbnail_path)

    if dry_run:
        logger.info("[Dry Run] Would send email to: %s", valid_recipients)
        logger.info("Subject: %s", subject)
        logger.info("Body: %s", html_body[:200] + '...')
        if thumbnail_data:
            logger.info("[Dry Run] Would attach thumbnail: %s (size: %d bytes)", thumbnail_path, len(thumbnail_data))
        return True

    try:
        return _send_via_smtp(sender, valid_recipients, subject, html_body, thumbnail_data)
    except Exception as e:
        logger.error("Error sending email: %s", e)
        return False


def _send_via_smtp(sender, recipients, subject, html_body, thumbnail_data):
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