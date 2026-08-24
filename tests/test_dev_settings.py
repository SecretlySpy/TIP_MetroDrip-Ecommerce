"""Fail-fast contracts for the environment-driven development payment provider."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _import_dev_settings(*, provider, secret):
    """Import development settings in a clean child process.

    Empty strings are intentionally present in the child environment. That
    prevents an untracked repository ``.env`` from changing these assertions
    while exercising the same automatic-selection branch as an unset value.
    """
    environment = os.environ.copy()
    environment.update(
        {
            "PAYMENT_PROVIDER": provider,
            "PAYMONGO_SECRET_KEY": secret,
        }
    )
    command = [
        sys.executable,
        "-c",
        (
            "import json; import config.settings.dev as s; "
            "print(json.dumps({'payment_provider': s.PAYMENT_PROVIDER, "
            "'paymongo_secret': s.PAYMONGO_SECRET_KEY}))"
        ),
    ]
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("secret", "expected_provider"),
    [
        ("", "simulated"),
        ("sk_test_example", "paymongo"),
    ],
)
def test_dev_payment_provider_uses_secret_based_fallback(secret, expected_provider):
    """A blank selection keeps zero-config development while supporting sandbox keys."""
    result = _import_dev_settings(provider="", secret=secret)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["payment_provider"] == expected_provider


@pytest.mark.parametrize(
    ("provider", "secret"),
    [
        ("simulated", ""),
        ("simulated", "sk_test_example"),
        ("simulated", "sk_live_ignored_by_explicit_simulator"),
        ("paymongo", "sk_test_example"),
        ("  simulated  ", "sk_test_example"),
    ],
)
def test_dev_payment_provider_honors_an_explicit_valid_selection(provider, secret):
    """Explicit selections must override automatic key-based provider inference."""
    result = _import_dev_settings(provider=provider, secret=secret)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["payment_provider"] == provider.strip()


def test_dev_payment_provider_rejects_explicit_paymongo_without_a_secret():
    """A deliberate PayMongo selection cannot boot into a broken checkout."""
    result = _import_dev_settings(provider="paymongo", secret="   ")

    assert result.returncode != 0
    assert "PAYMENT_PROVIDER=paymongo requires PAYMONGO_SECRET_KEY" in result.stderr


@pytest.mark.parametrize(
    ("provider", "secret"),
    [
        ("", "sk_live_example"),
        ("", "pk_test_public_key"),
        ("", "malformed-secret"),
        ("paymongo", "sk_live_example"),
    ],
)
def test_dev_payment_provider_rejects_non_sandbox_keys(provider, secret):
    """Development must never infer or explicitly select live PayMongo."""
    result = _import_dev_settings(provider=provider, secret=secret)

    assert result.returncode != 0
    assert "requires a sandbox PAYMONGO_SECRET_KEY starting with sk_test_" in result.stderr


def test_dev_payment_provider_normalizes_sandbox_secret_whitespace():
    """Validation and the provider must use the same normalized credential."""
    result = _import_dev_settings(provider="paymongo", secret="  sk_test_example  ")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["paymongo_secret"] == "sk_test_example"


@pytest.mark.parametrize("provider", ["stripe", "SIMULATED", "pay-mongo"])
def test_dev_payment_provider_rejects_unrecognized_values(provider):
    """Provider typos should fail during configuration rather than at checkout."""
    result = _import_dev_settings(provider=provider, secret="sk_test_example")

    assert result.returncode != 0
    assert f"PAYMENT_PROVIDER={provider} is not recognized" in result.stderr
