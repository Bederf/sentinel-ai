"""
Tests for UserRepository — 3-tier fallback (Supabase → JSON → None).
"""

import json
from pathlib import Path
from unittest.mock import patch


class TestUserRepositoryJsonFallback:
    """Verify JSON fallback works when Supabase is unavailable."""

    def _make_repo(self, tmp_path: Path):
        """Create a fresh UserRepository pointing at a temp JSON file."""
        from app.database.repositories.user_repository import UserRepository

        # Reset singleton so each test gets fresh state
        UserRepository._instance = None
        repo = UserRepository()

        # Point at temp JSON
        users_json = tmp_path / "users.json"
        users_json.write_text(
            json.dumps(
                {
                    "users": [
                        {"email": "alice@test.com", "full_name": "Alice", "role": "admin", "is_active": True},
                        {"email": "bob@test.com", "full_name": "Bob", "role": "operator", "is_active": True},
                        {"email": "inactive@test.com", "full_name": "Gone", "role": "auditor", "is_active": False},
                    ]
                }
            )
        )

        # Monkey-patch module-level path
        import app.database.repositories.user_repository as mod

        mod._USERS_JSON = users_json

        return repo

    def test_get_user_by_email_found(self, tmp_path):
        with patch("app.database.repositories.user_repository.get_supabase_client", return_value=None):
            repo = self._make_repo(tmp_path)
            user = repo.get_user_by_email("alice@test.com")

            assert user is not None
            assert user["email"] == "alice@test.com"
            assert user["role"] == "admin"
            assert user["full_name"] == "Alice"

    def test_get_user_by_email_not_found(self, tmp_path):
        with patch("app.database.repositories.user_repository.get_supabase_client", return_value=None):
            repo = self._make_repo(tmp_path)
            user = repo.get_user_by_email("unknown@nowhere.com")
            assert user is None

    def test_get_user_by_email_inactive_excluded(self, tmp_path):
        with patch("app.database.repositories.user_repository.get_supabase_client", return_value=None):
            repo = self._make_repo(tmp_path)
            user = repo.get_user_by_email("inactive@test.com")
            assert user is None

    def test_list_users(self, tmp_path):
        with patch("app.database.repositories.user_repository.get_supabase_client", return_value=None):
            repo = self._make_repo(tmp_path)
            users = repo.list_users()
            emails = [u["email"] for u in users]
            assert "alice@test.com" in emails
            assert "bob@test.com" in emails
            assert "inactive@test.com" not in emails

    def test_create_user_json_fallback(self, tmp_path):
        with patch("app.database.repositories.user_repository.get_supabase_client", return_value=None):
            repo = self._make_repo(tmp_path)
            result = repo.create_user("new@test.com", "New User", "developer")
            assert result is not None
            assert result["email"] == "new@test.com"
            assert result["role"] == "developer"

            # Verify persisted
            found = repo.get_user_by_email("new@test.com")
            assert found is not None

    def test_ensure_admin_emails_creates_missing(self, tmp_path):
        with patch("app.database.repositories.user_repository.get_supabase_client", return_value=None):
            repo = self._make_repo(tmp_path)
            repo.ensure_admin_emails(["new-admin@test.com"])
            user = repo.get_user_by_email("new-admin@test.com")
            assert user is not None
            assert user["role"] == "admin"

    def test_case_insensitive_lookup(self, tmp_path):
        with patch("app.database.repositories.user_repository.get_supabase_client", return_value=None):
            repo = self._make_repo(tmp_path)
            user = repo.get_user_by_email("ALICE@TEST.COM")
            assert user is not None
            assert user["email"] == "alice@test.com"
