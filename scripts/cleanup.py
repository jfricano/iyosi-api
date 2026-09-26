"""Run daily from an operator scheduler; only ephemeral request metadata is removed."""
import os
import psycopg
with psycopg.connect(os.environ['DATABASE_URL']) as conn:
    conn.execute("DELETE FROM idempotency_records WHERE created_at < now()-interval '24 hours'")
    conn.execute('DELETE FROM rate_buckets WHERE expires_at < now()')
