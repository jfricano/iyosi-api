import os
from pathlib import Path
import psycopg

with psycopg.connect(os.environ['DATABASE_URL']) as conn:
    conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())')
    for path in sorted(Path('/workspace/migrations' if Path('/workspace/migrations').exists() else 'migrations').glob('*.sql')):
        if not conn.execute('SELECT 1 FROM schema_migrations WHERE version=%s', (path.name,)).fetchone():
            conn.execute(path.read_text())
            conn.execute('INSERT INTO schema_migrations(version) VALUES (%s)', (path.name,))
            print('Applied', path.name)
