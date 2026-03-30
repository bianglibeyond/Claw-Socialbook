from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

# Ensure the skill root is on the path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from commons import vault


@pytest.fixture
def tmp_vault(tmp_path):
    """Temporary vault DB and inbox dir for each test."""
    db_path = tmp_path / "test-vault.db"
    inbox_path = tmp_path / "inbox"
    vault.init_vault(db_path)
    inbox_path.mkdir()
    return db_path, inbox_path
