import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from app.main import app

client = TestClient(app)


def test_path_traversal_blocked_env():
    """Verify that requests attempting to escape frontend/dist cannot read .env or outside files."""
    traversal_paths = [
        "/../../.env",
        "/..%2F..%2F.env",
        "/..%2f..%2f.env",
        "/../data/space_sentiment.db",
        "/..%2Fdata%2Fspace_sentiment.db",
        "/../../app/config.py",
        "/..%2F..%2Fapp%2Fconfig.py",
    ]
    for path in traversal_paths:
        response = client.get(path)
        # Should be 404 Not Found, never 200 with sensitive content
        assert response.status_code == 404, f"Failed for path {path}: returned {response.status_code}"
        assert "X_PASSWORD" not in response.text
        assert "DATABASE_URL" not in response.text
