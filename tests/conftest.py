"""Réglages communs : les tests marqués ``jericho`` sautent si Jericho ou la ROM manquent."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROM = ROOT / "roms" / "zork1.z5"


def _jericho_ready() -> bool:
    try:
        import jericho  # noqa: F401
    except ImportError:
        return False
    return ROM.is_file()


def pytest_collection_modifyitems(config, items):
    if _jericho_ready():
        return
    skip = pytest.mark.skip(reason="Jericho ou roms/zork1.z5 absents : lancez scripts/setup_wsl.sh")
    for item in items:
        if "jericho" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def rom_path() -> Path:
    return ROM
