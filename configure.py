#!/usr/bin/env python3
"""
Interactive configuration wizard for the Newspaper Downloader.
"""
import os
import yaml
from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.panel import Panel
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet
import base64
import os as _os
import getpass

console = Console()

def main():
    console.print(Panel.fit("[bold blue]Newspaper Downloader Setup Wizard[/bold blue]\n\nThis wizard will generate your [yellow]config.yaml[/yellow] and [yellow].env[/yellow] files."))

    # --- Newspaper Settings ---
    console.rule("[bold]Newspaper Settings[/bold]")
    newspaper_url = Prompt.ask("Newspaper Base URL", default="https://example.com")
    download_pattern = Prompt.ask("Download Path Pattern", default="newspaper/download/{date}")

    # --- Storage Settings ---
    console.rule("[bold]Cloud Storage (S3/R2)[/bold]")
    storage_endpoint = Prompt.ask("Storage Endpoint URL")
    storage_bucket = Prompt.ask("Bucket Name", default="newspaper-storage")
    access_key = Prompt.ask("Access Key ID")
    secret_key = Prompt.ask("Secret Access Key", password=True)

    # --- Email Settings ---
    console.rule("[bold]Email Settings (SMTP)[/bold]")
    sender_email = Prompt.ask("Sender Email Address")
    recipient_email = Prompt.ask("Recipient Email Address")
    smtp_host = Prompt.ask("SMTP Host", default="smtp.example.com")
    smtp_port = IntPrompt.ask("SMTP Port", default=587)
    smtp_user = Prompt.ask("SMTP Username", default=sender_email)
    smtp_pass = Prompt.ask("SMTP Password", password=True)
    smtp_tls = Confirm.ask("Use TLS?", default=True)

    # --- Secret Encryption ---
    console.rule("[bold]Encrypting Secrets[/bold]")
    while True:
        passphrase1 = getpass.getpass("Master passphrase for encrypting secrets: ")
        passphrase2 = getpass.getpass("Confirm master passphrase: ")
        if passphrase1 != passphrase2:
            console.print("[red]Passphrases do not match. Try again.[/red]")
        elif passphrase1.strip() == '':
            console.print("[red]Passphrase cannot be empty.[/red]")
        else:
            break
    # Derive key from passphrase with new random salt
    salt = _os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
        backend=default_backend()
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase1.encode()))
    fernet = Fernet(key)
    encrypted_secret_key = fernet.encrypt(secret_key.encode()).decode()
    encrypted_smtp_pass = fernet.encrypt(smtp_pass.encode()).decode()
    salt_b64 = base64.urlsafe_b64encode(salt).decode()
    console.rule("[bold]Generating Files[/bold]")

    config_data = {
        'newspaper': {
            'url': newspaper_url,
            'download_path_pattern': download_pattern
        },
        'storage': {
            'endpoint_url': storage_endpoint,
            'bucket': storage_bucket,
            # Keys will be in .env, but config needs references or we rely on env vars
            # The app reads env vars if config keys are missing, OR we can leave them out of config.yaml
            # and let the app pick them up from env vars entirely.
            # However, config.py looks for keys in config.yaml then env vars.
            # To be safe, we can put placeholders or just omit them from yaml if the app supports it.
            # Let's check config.py: it does `env_key = '_'.join(str(k).upper() for k in key_tuple)`
            # So storage.access_key_id -> STORAGE_ACCESS_KEY_ID
        },
        'email': {
            'sender': sender_email,
            'recipients': [recipient_email],
            'smtp_host': smtp_host,
            'smtp_port': smtp_port,
            'smtp_user': smtp_user,
            'smtp_tls': 1 if smtp_tls else 0,
            'subject_template': "🗞️ Your Daily Edition is Ready: {{ date }}", # Improved subject
            'template': "email_template.html",
            'alert_recipient': sender_email
        },
        'general': {
            'retention_days': 7,
            'date_format': "%Y-%m-%d",
            'filename_template': "{date}_newspaper.{format}",
            'thumbnail_filename_template': "{date}_thumbnail.{format}",
            'retention_days_for_email_links': 7
        },
        'paths': {
            'download_dir': "downloads",
            'template_dir': "templates",
            'log_file': "newspaper_emailer.log",
            'status_file': "pipeline_status.json"
        }
    }

    # Write config.yaml
    if os.path.exists('config.yaml'):
        if not Confirm.ask("[yellow]config.yaml[/yellow] already exists. Overwrite?"):
            console.print("[red]Aborted.[/red]")
            return

    with open('config.yaml', 'w') as f:
        yaml.dump(config_data, f, default_flow_style=False)
    console.print("[green]✔ config.yaml created.[/green]")

    # Write .env
    env_content = f"""# Auto-generated .env file
# The following secrets are encrypted with Fernet (AES-GCM, passphrase-based)
STORAGE_ACCESS_KEY_ID="{access_key}"
STORAGE_SECRET_ACCESS_KEY_ENC="{encrypted_secret_key}"
EMAIL_SMTP_PASS_ENC="{encrypted_smtp_pass}"
SECRETS_ENC_SALT="{salt_b64}"
# To decrypt, prompt user for the master passphrase gathered during config.
"""
    if os.path.exists('.env'):
        if not Confirm.ask("[yellow].env[/yellow] already exists. Overwrite?"):
             console.print("[yellow]Skipping .env creation (secrets not saved).[/yellow]")
        else:
            with open('.env', 'w') as f:
                f.write(env_content)
            console.print("[green]✔ .env created.[/green]")
    else:
        with open('.env', 'w') as f:
            f.write(env_content)
        console.print("[green]✔ .env created.[/green]")

    console.print(Panel.fit("[bold green]Setup Complete![/bold green]\n\nRun [bold white]python main.py[/bold white] to test."))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[red]Setup cancelled.[/red]")
