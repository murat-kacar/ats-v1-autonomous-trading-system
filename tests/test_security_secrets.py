from ats_security.secrets import MissingSecretsError, SecretManager, redact_secret


def test_secret_manager_fetch_and_mask() -> None:
    manager = SecretManager(
        required_keys=["A", "B"],
        env={"A": "supersecretvalue", "B": "tiny1234"},
    )

    values = manager.require_all()
    assert values["A"] == "supersecretvalue"
    assert values["B"] == "tiny1234"

    masked = manager.masked_snapshot()
    assert masked["A"].startswith("supe")
    assert masked["A"].endswith("alue")
    assert masked["B"] == "********"


def test_secret_manager_missing_raises() -> None:
    manager = SecretManager(required_keys=["A", "B"], env={"A": "ok"})

    try:
        manager.require_all()
    except MissingSecretsError as exc:
        assert "B" in str(exc)
    else:
        raise AssertionError("MissingSecretsError expected")


def test_redact_secret() -> None:
    assert redact_secret("") == ""
    assert redact_secret("short") == "*****"
    assert redact_secret("abcdefghijk") == "abcd...hijk"
