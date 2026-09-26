"""Operator-only bootstrap: promote an existing account in the private database."""
import os, sys
import psycopg
if len(sys.argv)!=2:
    raise SystemExit('Usage: python scripts/grant_admin.py EMAIL')
with psycopg.connect(os.environ['DATABASE_URL']) as conn:
    row=conn.execute("UPDATE accounts SET role='admin' WHERE email=%s AND disabled_at IS NULL RETURNING id",(sys.argv[1].lower(),)).fetchone()
    if not row: raise SystemExit('No active account with that email')
    print('Granted admin to',row[0])
