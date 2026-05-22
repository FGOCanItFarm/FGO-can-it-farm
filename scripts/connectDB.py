import os
import sys
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from dotenv import load_dotenv

load_dotenv()

_DATABASE_URL = os.getenv('DATABASE_URL')
if not _DATABASE_URL:
    raise ValueError("No DATABASE_URL environment variable set")

# Min 1, max 10 connections — sufficient for the update script and
# FastAPI's background thread running concurrently.
_pool = ThreadedConnectionPool(1, 10, _DATABASE_URL)


@contextmanager
def get_cursor():
    """Yield a RealDictCursor, commit on success, rollback on error."""
    conn = _pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


sys.stdout.reconfigure(encoding='utf-8')
