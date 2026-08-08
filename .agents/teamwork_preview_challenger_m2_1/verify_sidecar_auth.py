import os
import sys

from fastapi.testclient import TestClient

# Ensure project root is in sys.path
PROJECT_ROOT = "/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["SKIP_CREATE_ALL"] = "1"

# Import sidecar apps
from services.fulfillment.main import app as fulfillment_app
from services.inventory.main import app as inventory_app
from services.notifications.main import app as notifications_app


def test_unconfigured(app_name, app, env_var, protected_path, protected_method="post", payload=None):
    print(f"\n--- Testing Unconfigured Service: {app_name} ({env_var}) ---")
    # Ensure env var is cleared
    os.environ.pop(env_var, None)

    client = TestClient(app)

    # 1. Check /healthz/ready endpoint
    res_ready = client.get("/healthz/ready")
    print(f"GET /healthz/ready status: {res_ready.status_code}")
    print(f"GET /healthz/ready body: {res_ready.json()}")
    assert res_ready.status_code == 503, f"Expected 503, got {res_ready.status_code}"
    assert res_ready.json() == {"status": "unavailable", "auth": "unconfigured"}

    # 2. Check protected route call when unconfigured
    if protected_method == "post":
        res_prot = client.post(protected_path, json=payload or {})
    else:
        res_prot = client.get(protected_path)
    print(f"{protected_method.upper()} {protected_path} (unconfigured) status: {res_prot.status_code}")
    print(f"{protected_method.upper()} {protected_path} (unconfigured) body: {res_prot.json()}")
    assert res_prot.status_code == 503
    assert res_prot.json()["detail"]["error"]["code"] == "auth_not_configured"

def test_configured_auth_checks(app_name, app, env_var, protected_path, protected_method="post", payload=None):
    print(f"\n--- Testing Configured Auth Mechanics: {app_name} ({env_var}) ---")
    valid_token = f"secret-token-{app_name}"
    os.environ[env_var] = valid_token

    client = TestClient(app)

    # 1. Check /healthz/ready endpoint when configured
    res_ready = client.get("/healthz/ready")
    print(f"GET /healthz/ready (configured) status: {res_ready.status_code}")
    print(f"GET /healthz/ready (configured) body: {res_ready.json()}")
    if app_name == "inventory":
        # Inventory ready probe tries db connection
        assert res_ready.status_code in (200, 503)
        assert res_ready.json().get("auth") == "configured"
    else:
        assert res_ready.status_code == 200
        assert res_ready.json() == {"status": "ok", "auth": "configured"}

    # 2. Call protected endpoint with NO auth header
    if protected_method == "post":
        res_no_auth = client.post(protected_path, json=payload or {})
    else:
        res_no_auth = client.get(protected_path)
    print(f"No Header status: {res_no_auth.status_code}, body: {res_no_auth.json()}")
    assert res_no_auth.status_code == 401
    assert res_no_auth.json()["detail"]["error"]["code"] == "unauthorized"

    # 3. Call protected endpoint with INVALID auth header
    headers_invalid = {"Authorization": "Bearer wrong-token"}
    if protected_method == "post":
        res_inv_auth = client.post(protected_path, json=payload or {}, headers=headers_invalid)
    else:
        res_inv_auth = client.get(protected_path, headers=headers_invalid)
    print(f"Invalid Token status: {res_inv_auth.status_code}, body: {res_inv_auth.json()}")
    assert res_inv_auth.status_code == 401
    assert res_inv_auth.json()["detail"]["error"]["code"] == "unauthorized"

    # 4. Call protected endpoint with VALID auth header
    headers_valid = {"Authorization": f"Bearer {valid_token}"}
    if protected_method == "post":
        res_valid_auth = client.post(protected_path, json=payload or {}, headers=headers_valid)
    else:
        res_valid_auth = client.get(protected_path, headers=headers_valid)
    print(f"Valid Token status: {res_valid_auth.status_code}, body: {res_valid_auth.json()}")
    assert res_valid_auth.status_code in (200, 201, 404, 409, 422, 500) # Reaches inner endpoint code

    # Cleanup env
    os.environ.pop(env_var, None)

if __name__ == "__main__":
    test_unconfigured(
        "notifications",
        notifications_app,
        "NOTIFICATION_SERVICE_TOKEN",
        "/v1/email",
        "post",
        {"to": ["test@example.com"], "subject": "Hi", "body": "Body"}
    )
    test_configured_auth_checks(
        "notifications",
        notifications_app,
        "NOTIFICATION_SERVICE_TOKEN",
        "/v1/email",
        "post",
        {"to": ["test@example.com"], "subject": "Hi", "body": "Body"}
    )

    test_unconfigured(
        "fulfillment",
        fulfillment_app,
        "SHIPPING_SERVICE_TOKEN",
        "/v1/shipments/book",
        "post",
        {"order_no": "MD-100", "courier": "jnt"}
    )
    test_configured_auth_checks(
        "fulfillment",
        fulfillment_app,
        "SHIPPING_SERVICE_TOKEN",
        "/v1/shipments/book",
        "post",
        {"order_no": "MD-100", "courier": "jnt"}
    )

    test_unconfigured(
        "inventory",
        inventory_app,
        "INVENTORY_SERVICE_TOKEN",
        "/v1/reservations",
        "post",
        {"checkout_id": "test-checkout-123", "lines": [{"variant_id": 1, "qty": 1}]}
    )
    test_configured_auth_checks(
        "inventory",
        inventory_app,
        "INVENTORY_SERVICE_TOKEN",
        "/v1/reservations",
        "post",
        {"checkout_id": "test-checkout-123", "lines": [{"variant_id": 1, "qty": 1}]}
    )

    print("\n✅ ALL SIDECAR AUTH & READINESS EMPIRICAL CHECKS PASSED SUCCESSFULLY!")
