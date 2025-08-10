import os
from pathlib import Path
import website


def test_login_and_download_dry_run_returns_simulated_path(tmp_path):
    target_date = "2025-01-02"
    save_path_base = tmp_path / f"{target_date}_newspaper"

    success, result = website.login_and_download(
        base_url="https://example.com",
        save_path=str(save_path_base),
        target_date=target_date,
        dry_run=True,
        force_download=False,
    )

    assert success is True
    assert result == str(save_path_base.with_suffix('.pdf'))