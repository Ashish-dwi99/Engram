import os

from dhee.configs.base import _dhee_data_dir
from dhee.simple import Engram, _get_data_dir


def test_dhee_data_dir_expands_tilde(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DHEE_DATA_DIR", "~/clear-water")

    expected = home / "clear-water"

    assert _dhee_data_dir() == os.path.abspath(str(expected))
    assert _get_data_dir() == expected.absolute()


def test_engram_expands_explicit_data_dir_tilde(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    memory = Engram(provider="mock", data_dir="~/explicit-dhee", in_memory=True)

    try:
        assert memory.data_dir == (home / "explicit-dhee").absolute()
    finally:
        memory.close()
