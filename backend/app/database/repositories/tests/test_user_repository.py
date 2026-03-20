"""Tests for UserRepository using the canonical DB-backed store."""

from unittest.mock import patch


class TestUserRepositoryCanonicalStore:
    """Verify repository behavior is DB-only for canonical user state."""

    def _make_repo(self):
        from app.database.repositories.user_repository import UserRepository

        UserRepository._instance = None
        return UserRepository()

    def test_get_user_by_email_without_db_returns_none(self):
        with patch("app.database.repositories.user_repository.get_supabase_client", return_value=None):
            repo = self._make_repo()
            assert repo.get_user_by_email("unknown@nowhere.com") is None

    def test_list_users_without_db_returns_empty(self):
        with patch("app.database.repositories.user_repository.get_supabase_client", return_value=None):
            repo = self._make_repo()
            assert repo.list_users() == []

    def test_create_user_without_db_returns_none(self):
        with patch("app.database.repositories.user_repository.get_supabase_client", return_value=None):
            repo = self._make_repo()
            assert repo.create_user("new@test.com", "New User", "developer") is None

    def test_case_insensitive_lookup_uses_db_row(self):
        fake_client = type(
            "FakeClient",
            (),
            {
                "table": lambda self, _name: type(
                    "FakeQuery",
                    (),
                    {
                        "select": lambda self, *_args, **_kwargs: self,
                        "eq": lambda self, *_args, **_kwargs: self,
                        "limit": lambda self, *_args, **_kwargs: self,
                        "execute": lambda self: type(
                            "Resp",
                            (),
                            {
                                "data": [
                                    {
                                        "id": "u1",
                                        "email": "alice@test.com",
                                        "full_name": "Alice",
                                        "role": "admin",
                                        "is_active": True,
                                    }
                                ]
                            },
                        )(),
                    },
                )(),
            },
        )()
        with patch("app.database.repositories.user_repository.get_supabase_client", return_value=fake_client):
            repo = self._make_repo()
            user = repo.get_user_by_email("ALICE@TEST.COM")
            assert user is not None
            assert user["email"] == "alice@test.com"
