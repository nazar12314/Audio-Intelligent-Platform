from audio_platform.core.logging import redact


def test_redact_masks_sensitive_keys() -> None:
    assert redact({"password": "p", "api_key": "k", "Authorization": "Bearer x", "user": "u"}) == {
        "password": "***",
        "api_key": "***",
        "Authorization": "***",
        "user": "u",
    }


def test_redact_masks_credentials_in_urls() -> None:
    assert redact("connect postgresql+asyncpg://app:secret@db:5432/x") == "connect postgresql+asyncpg://***@db:5432/x"


def test_redact_walks_nested_structures() -> None:
    assert redact({"outer": [{"token": "t"}, "https://u:p@h/"]}) == {"outer": [{"token": "***"}, "https://***@h/"]}


def test_redact_leaves_plain_values_alone() -> None:
    assert redact(42) == 42
    assert redact("https://example.com/path") == "https://example.com/path"
