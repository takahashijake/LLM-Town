import sys

import pytest

import main


def test_batched_cli_accepts_positive_batch_size(monkeypatch):
    monkeypatch.setattr(sys, "argv", [
        "main.py", "--conversation-execution", "batched",
        "--conversation-batch-size", "8",
    ])
    args = main.parse_args()
    assert args.conversation_execution == "batched"
    assert args.conversation_batch_size == 8


def test_batched_cli_rejects_nonpositive_batch_size(monkeypatch):
    monkeypatch.setattr(sys, "argv", [
        "main.py", "--conversation-batch-size", "0",
    ])
    with pytest.raises(SystemExit):
        main.parse_args()
