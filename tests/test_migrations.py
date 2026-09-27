"""Exercise the 001-to-002 upgrade in a throwaway schema of the marked test DB."""
import os
import secrets
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict


TEST_DB=os.environ.get('TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not TEST_DB,reason='TEST_DATABASE_URL is not set')


def test_resolved_create_submission_upgrade():
    database_name=conninfo_to_dict(TEST_DB).get('dbname','')
    if not database_name.endswith('_test'):
        raise RuntimeError('Upgrade test requires a dedicated *_test database')
    schema='migration_'+secrets.token_hex(6)
    with psycopg.connect(TEST_DB) as conn:
        marker=conn.execute("SELECT to_regclass('public.iyosi_integration_test_guard')").fetchone()[0]
        if not marker or not conn.execute("SELECT 1 FROM public.iyosi_integration_test_guard WHERE purpose='iyosi dedicated integration tests'").fetchone():
            raise RuntimeError('Dedicated test database marker is missing')
        try:
            conn.execute(f'CREATE SCHEMA {schema}')
            conn.execute(f'SET search_path TO {schema},public')
            conn.execute(Path('migrations/001_initial.sql').read_text())
            conn.execute("INSERT INTO accounts(id,email,password_hash,adult_attested_at) VALUES ('acct_upgrade','upgrade@example.com','test',now())")
            conn.execute("""INSERT INTO places(id,name,kind,advisory_status,location)
                         VALUES ('plc_upgrade','Upgraded place','informal_outdoor','community_reported',
                         ST_SetSRID(ST_MakePoint(121,14.6),4326))""")
            conn.execute("""INSERT INTO place_submissions(id,account_id,intent,name,kind,location,basis)
                         VALUES ('sub_upgrade','acct_upgrade','create','Upgraded place','informal_outdoor',
                         ST_SetSRID(ST_MakePoint(121,14.6),4326),'Reviewed fixture')""")
            conn.execute(Path('migrations/002_resolved_create_submission_place.sql').read_text())
            conn.execute("UPDATE place_submissions SET state='published',place_id='plc_upgrade' WHERE id='sub_upgrade'")
            assert conn.execute("SELECT state,place_id FROM place_submissions WHERE id='sub_upgrade'").fetchone()==('published','plc_upgrade')
        finally:
            # Everything above, including the schema, is transaction-local.
            conn.rollback()
