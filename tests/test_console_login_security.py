"""Brute-force limits and TOTP 2FA on the back-office consoles (ADR-P3-029).

Before this, `/admin/` and `/merchant/` had neither. DRF's throttles are applied
per view class, so the 10/min credential budget protecting the mobile API never
touched the two surfaces that hold staff access to every order and customer
record — an attacker could guess a merchant password as fast as the network
allowed, and a stolen one was sufficient on its own.

The suite-wide cache is DummyCache (config/settings/test.py) so throttle state
cannot leak between unrelated tests. Every test here that exercises a counter
therefore has to opt back into a real locmem cache, and clear it, or it would
assert against a cache that silently stores nothing and pass for the wrong
reason.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from apps.accounts.roles import StaffRole

pytestmark = pytest.mark.django_db

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture()
def real_cache(settings):
    """Swap DummyCache for locmem so the counters actually count."""
    settings.CACHES = LOCMEM
    cache.clear()
    yield
    cache.clear()


@pytest.fixture()
def merchant():
    return get_user_model().objects.create_user(
        email="merchant@test.local",
        password=PASSWORD,
        name="Merchant",
        is_staff=True,
        role=StaffRole.MERCHANT,
    )


def _login(client, url, **extra):
    payload = {"username": "merchant@test.local", "password": "wrong-password"}
    payload.update(extra)
    return client.post(url, payload)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@override_settings(CONSOLE_LOGIN_MAX_ATTEMPTS_PER_USER=3, CONSOLE_LOGIN_WINDOW_SECONDS=900)
def test_repeated_failures_lock_the_account_out(client, merchant, real_cache):
    url = reverse("merchant:login")

    for _ in range(3):
        response = _login(client, url)
        assert response.status_code == 200

    # The 4th attempt is refused before authentication, so even the *correct*
    # password no longer works — that is what makes it a lockout rather than a
    # slow path an attacker can keep walking.
    response = _login(client, url, password=PASSWORD)
    assert response.status_code == 200
    assert b"Too many failed sign-in attempts" in response.content
    assert not response.wsgi_request.user.is_authenticated


@override_settings(CONSOLE_LOGIN_MAX_ATTEMPTS_PER_USER=3, CONSOLE_LOGIN_WINDOW_SECONDS=900)
def test_the_lockout_message_does_not_reveal_whether_the_account_exists(
    client, merchant, real_cache
):
    """A lockout must not become an account-enumeration oracle."""
    url = reverse("merchant:login")
    for _ in range(4):
        _login(client, url, username="nobody@test.local")
    ghost = _login(client, url, username="nobody@test.local")

    cache.clear()
    for _ in range(4):
        _login(client, url)
    real = _login(client, url)

    assert b"Too many failed sign-in attempts" in ghost.content
    assert b"Too many failed sign-in attempts" in real.content


@override_settings(CONSOLE_LOGIN_MAX_ATTEMPTS_PER_USER=3, CONSOLE_LOGIN_WINDOW_SECONDS=900)
def test_a_successful_login_clears_the_counter(client, merchant, real_cache):
    """Ordinary typo-then-correct traffic must never accumulate to a lockout."""
    url = reverse("merchant:login")
    _login(client, url)
    _login(client, url)

    response = client.post(url, {"username": "merchant@test.local", "password": PASSWORD})
    assert response.status_code == 302  # signed in

    client.logout()
    # Two more failures would have tripped a counter that survived the success.
    _login(client, url)
    _login(client, url)
    response = client.post(url, {"username": "merchant@test.local", "password": PASSWORD})
    assert response.status_code == 302


@override_settings(CONSOLE_LOGIN_MAX_ATTEMPTS_PER_USER=99, CONSOLE_LOGIN_MAX_ATTEMPTS_PER_IP=3)
def test_the_address_bucket_catches_probing_across_many_accounts(client, merchant, real_cache):
    """Per-username counting cannot see one address probing many accounts."""
    url = reverse("merchant:login")
    for index in range(3):
        _login(client, url, username=f"victim{index}@test.local")

    response = _login(client, url, username="merchant@test.local", password=PASSWORD)
    assert b"Too many failed sign-in attempts" in response.content


def test_x_forwarded_for_is_ignored_unless_a_proxy_depth_is_configured(rf):
    """Trusting the header by default would hand out unlimited fresh buckets."""
    from apps.accounts.login_throttle import client_address

    request = rf.post("/merchant/login/", REMOTE_ADDR="10.0.0.9")
    request.META["HTTP_X_FORWARDED_FOR"] = "1.2.3.4, 5.6.7.8"

    with override_settings(CONSOLE_LOGIN_TRUSTED_PROXY_DEPTH=0):
        assert client_address(request) == "10.0.0.9"

    # With one proxy of ours in front, the rightmost entry is the address that
    # proxy actually saw — the earliest hop a client cannot forge.
    with override_settings(CONSOLE_LOGIN_TRUSTED_PROXY_DEPTH=1):
        assert client_address(request) == "5.6.7.8"


# ---------------------------------------------------------------------------
# TOTP two-factor
# ---------------------------------------------------------------------------


@pytest.fixture()
def enrolled_merchant(merchant):
    """A merchant with a confirmed TOTP device."""
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device = TOTPDevice.objects.create(user=merchant, name="phone", confirmed=True)
    return merchant, device


def test_a_correct_password_alone_is_refused_once_a_device_is_enrolled(
    client, enrolled_merchant, real_cache
):
    """Enrollment must be a one-way door, not an optional extra."""
    _, _device = enrolled_merchant
    response = client.post(
        reverse("merchant:login"),
        {"username": "merchant@test.local", "password": PASSWORD},
    )
    assert response.status_code == 200
    assert not response.wsgi_request.user.is_authenticated


def test_password_plus_a_valid_token_signs_in(client, enrolled_merchant, real_cache):
    user, device = enrolled_merchant
    token = device.generate_challenge() or _current_token(device)

    response = client.post(
        reverse("merchant:login"),
        {"username": "merchant@test.local", "password": PASSWORD, "otp_token": token},
    )
    assert response.status_code == 302
    assert response.wsgi_request.user.is_authenticated


def _current_token(device):
    """The code an authenticator app would be showing right now."""
    from django_otp.oath import totp

    return totp(device.bin_key, device.step, device.t0, device.digits, device.drift)


def test_a_wrong_token_counts_toward_the_lockout(client, enrolled_merchant, real_cache):
    """Otherwise a stolen password buys unlimited guesses at six digits."""
    from apps.accounts.login_throttle import is_locked_out

    url = reverse("merchant:login")
    with override_settings(CONSOLE_LOGIN_MAX_ATTEMPTS_PER_USER=2):
        for _ in range(2):
            client.post(
                url,
                {"username": "merchant@test.local", "password": PASSWORD, "otp_token": "000000"},
            )
        request = type("R", (), {"META": {"REMOTE_ADDR": "127.0.0.1"}})()
        assert is_locked_out(username="merchant@test.local", request=request)


@override_settings(CONSOLE_REQUIRE_OTP=True)
def test_blanket_enforcement_refuses_an_unenrolled_account(client, merchant, real_cache):
    response = client.post(
        reverse("merchant:login"),
        {"username": "merchant@test.local", "password": PASSWORD},
    )
    assert response.status_code == 200
    assert b"two-factor authentication" in response.content
    assert not response.wsgi_request.user.is_authenticated


def test_an_unenrolled_account_still_signs_in_while_the_flag_is_off(client, merchant, real_cache):
    """The default posture must not lock out staff who have not enrolled yet."""
    response = client.post(
        reverse("merchant:login"),
        {"username": "merchant@test.local", "password": PASSWORD},
    )
    assert response.status_code == 302


def test_a_session_predating_enrollment_loses_console_access(client, enrolled_merchant, real_cache):
    """`has_permission` re-checks, so enrolling closes existing sessions too.

    Enforcing only at the login form would leave a session opened before
    enrollment unverified for its whole lifetime — exactly the window
    enrolling a device is meant to shut.
    """
    user, _ = enrolled_merchant
    client.force_login(user)  # a session that never presented a token

    response = client.get(reverse("merchant:index"))
    # `admin_view` bounces an unverified session to the login page rather than
    # rendering the console.
    assert response.status_code == 302
    assert reverse("merchant:login") in response["Location"]
