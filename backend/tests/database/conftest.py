import psycopg2
import pytest
from uuid import UUID

from app.database.supabase_client import get_supabase_client

_DB_DSN = "postgresql://postgres:postgres@127.0.0.1:55322/postgres"


@pytest.fixture
def supabase_client():
    return get_supabase_client()


@pytest.fixture(scope="session")
def db_conn():
    conn = psycopg2.connect(_DB_DSN)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def real_site_id(db_conn) -> UUID:
    with db_conn.cursor() as cur:
        cur.execute("SELECT id FROM public.sites LIMIT 1")
        return UUID(str(cur.fetchone()[0]))


@pytest.fixture(scope="session")
def real_equipment_id(db_conn) -> UUID:
    with db_conn.cursor() as cur:
        cur.execute("SELECT id FROM public.equipment LIMIT 1")
        return UUID(str(cur.fetchone()[0]))
