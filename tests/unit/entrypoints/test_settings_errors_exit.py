import pytest

from audio_platform.core.config import Settings
from audio_platform.entrypoints import api


def test_missing_required_settings_exit_with_one_line_per_field(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("AUDIO_POSTGRES__DSN", "AUDIO_STORAGE__BUCKET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(api, "get_settings", lambda: Settings(_env_file=None))

    with pytest.raises(SystemExit) as exc_info:
        api.load_settings_or_exit()

    assert exc_info.value.code == 2
    lines = capsys.readouterr().err.strip().splitlines()
    assert any("AUDIO_POSTGRES__*" in line for line in lines)
    assert any("AUDIO_STORAGE__*" in line for line in lines)


def test_invalid_field_names_the_exact_env_var(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AUDIO_POSTGRES__DSN", "mysql://nope")
    monkeypatch.setenv("AUDIO_STORAGE__BUCKET", "b-recordings")
    monkeypatch.setattr(api, "get_settings", lambda: Settings(_env_file=None))

    with pytest.raises(SystemExit):
        api.load_settings_or_exit()

    err = capsys.readouterr().err
    assert "AUDIO_POSTGRES__DSN" in err
    assert "mysql://nope" not in err  # the rejected value (a secret) is never printed
