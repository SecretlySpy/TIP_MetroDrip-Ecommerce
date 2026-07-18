"""HTTP contracts for process liveness and database readiness probes."""

from unittest.mock import MagicMock, patch

from django.db import DatabaseError


def test_liveness_returns_json_without_touching_the_database(client):
    """A database outage must not make the platform restart a healthy web process."""
    with patch(
        "config.views.connection.cursor",
        side_effect=AssertionError("liveness must remain database-independent"),
    ) as cursor:
        response = client.get("/healthz/live/")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.json() == {"status": "ok"}
    cursor.assert_not_called()


def test_readiness_executes_a_minimal_database_query(client):
    """A ready response must prove query execution, not merely import Django."""
    cursor = MagicMock()
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor

    with patch("config.views.connection.cursor", return_value=cursor_context) as open_cursor:
        response = client.get("/healthz/ready/")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.json() == {"status": "ok"}
    open_cursor.assert_called_once_with()
    cursor.execute.assert_called_once_with("SELECT 1")
    cursor.fetchone.assert_called_once_with()


def test_readiness_returns_service_unavailable_when_the_query_fails(client):
    """Database failures should fail readiness without leaking driver details to clients."""
    cursor = MagicMock()
    cursor.execute.side_effect = DatabaseError("secret database topology")
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor

    with patch("config.views.connection.cursor", return_value=cursor_context):
        response = client.get("/healthz/ready/")

    assert response.status_code == 503
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.json() == {"status": "unavailable"}
    assert b"secret database topology" not in response.content
    cursor.execute.assert_called_once_with("SELECT 1")


def test_health_probes_reject_mutating_methods_without_database_access(client):
    """Operational probes are read-only and POST must not open a database cursor."""
    with patch("config.views.connection.cursor") as open_cursor:
        for path in ("/healthz/live/", "/healthz/ready/"):
            response = client.post(path)

            assert response.status_code == 405
            assert response.headers["Allow"] == "GET"

    open_cursor.assert_not_called()
