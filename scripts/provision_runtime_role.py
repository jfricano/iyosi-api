"""Grant an application login data access without schema or role administration."""
import os

import psycopg
from psycopg import sql

APP_TABLES = (
    'accounts', 'places', 'place_submissions', 'confirmations', 'reviews',
    'reports', 'deletion_requests', 'moderation_cases', 'moderation_decisions',
    'idempotency_records', 'rate_buckets',
)


def provision(conn, role: str, password: str) -> None:
    if not role or not password:
        raise ValueError('Runtime database role and password are required')
    database = conn.execute('SELECT current_database()').fetchone()[0]
    owner = conn.execute('SELECT current_user').fetchone()[0]
    if role == owner:
        raise ValueError('Runtime role must differ from the migration role')
    exists = conn.execute('''SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls
                             FROM pg_roles WHERE rolname=%s''', (role,)).fetchone()
    if exists and any(exists):
        raise ValueError('Runtime role must not have administrative privileges')
    if not exists:
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN').format(sql.Identifier(role)))
    conn.execute(sql.SQL('ALTER ROLE {} WITH LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(password)))
    conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(database), sql.Identifier(role)))
    conn.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(role)))
    # Replace earlier broad grants as well as making repeat deployments idempotent.
    conn.execute(sql.SQL('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}').format(sql.Identifier(role)))
    conn.execute(sql.SQL('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}').format(sql.Identifier(role)))
    conn.execute(sql.SQL('ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {}').format(sql.Identifier(owner), sql.Identifier(role)))
    conn.execute(sql.SQL('ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {}').format(sql.Identifier(owner), sql.Identifier(role)))
    conn.execute(sql.SQL('GRANT SELECT ON TABLE public.ncr_boundary TO {}').format(sql.Identifier(role)))
    for table in APP_TABLES:
        conn.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{} TO {}').format(sql.Identifier(table), sql.Identifier(role)))


if __name__ == '__main__':
    with psycopg.connect(os.environ['DATABASE_URL']) as connection:
        provision(connection, os.environ['IYOSI_APP_DB_USER'], os.environ['IYOSI_APP_DB_PASSWORD'])
