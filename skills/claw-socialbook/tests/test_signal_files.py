from __future__ import annotations

import json
import os
from pathlib import Path

from phases.sentry import _write_signal_file
from phases.alert import load_signal_files, delete_signal_file


def test_signal_file_written_atomically(tmp_path):
    """File must arrive via tmp→rename, never as a partial write."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    payload = {"mailbox_id": "mb-1", "test": True}

    _write_signal_file(inbox, "mb-1", payload)

    final = inbox / "mb-1.json"
    tmp = inbox / "mb-1.json.tmp"
    assert final.exists()
    assert not tmp.exists()
    assert json.loads(final.read_text())["mailbox_id"] == "mb-1"


def test_load_signal_files_reads_all(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _write_signal_file(inbox, "mb-1", {"mailbox_id": "mb-1"})
    _write_signal_file(inbox, "mb-2", {"mailbox_id": "mb-2"})

    signals = load_signal_files(inbox)
    ids = {s["mailbox_id"] for s in signals}
    assert ids == {"mb-1", "mb-2"}


def test_load_signal_files_empty_inbox(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    signals = load_signal_files(inbox)
    assert signals == []


def test_delete_signal_file(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _write_signal_file(inbox, "mb-1", {"mailbox_id": "mb-1"})
    assert (inbox / "mb-1.json").exists()

    delete_signal_file("mb-1", inbox)
    assert not (inbox / "mb-1.json").exists()


def test_delete_signal_file_noop_when_missing(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    # Should not raise
    delete_signal_file("nonexistent", inbox)


def test_alert_rerun_with_no_signal_files_is_noop(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    signals = load_signal_files(inbox)
    assert signals == []
