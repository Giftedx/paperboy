import os
import config as config_module


def test_env_int_casting_smtp_port(monkeypatch):
    cfg = config_module.Config()
    monkeypatch.setenv('EMAIL_SMTP_PORT', '2525')
    # Ensure YAML does not override by leaving cfg._config empty
    assert cfg.get(('email', 'smtp_port')) == 2525


def test_env_email_list_casting(monkeypatch):
    cfg = config_module.Config()
    monkeypatch.setenv('EMAIL_RECIPIENTS', 'a@example.com, b@example.com')
    assert cfg.get(('email', 'recipients')) == ['a@example.com', 'b@example.com']