CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE ncr_boundary (id int PRIMARY KEY CHECK (id=1), geom geometry(MultiPolygon,4326) NOT NULL, source text NOT NULL, loaded_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX ncr_boundary_geom_idx ON ncr_boundary USING gist(geom);
CREATE TABLE accounts (
 id text PRIMARY KEY, email text NOT NULL UNIQUE, password_hash text NOT NULL,
 adult_attested_at timestamptz NOT NULL, role text NOT NULL DEFAULT 'contributor' CHECK(role IN ('contributor','admin')),
 created_at timestamptz NOT NULL DEFAULT now(), disabled_at timestamptz
);
CREATE TABLE places (
 id text PRIMARY KEY, name text NOT NULL, kind text NOT NULL CHECK(kind IN ('public_designated','venue_designated','informal_outdoor','venue_claim')),
 advisory_status text NOT NULL CHECK(advisory_status IN ('verified_designated','community_reported','disputed','prohibited','closed')),
 publication_state text NOT NULL DEFAULT 'published' CHECK(publication_state IN ('published','hidden','merged')),
 location geometry(Point,4326) NOT NULL, access_point geometry(Point,4326), address_label text, access_notes text,
 inside_venue boolean, verification_reviewed_at timestamptz, verification_public_source text, verification_evidence text,
 merged_into text REFERENCES places(id), version int NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK (kind <> 'venue_designated' OR inside_venue IS NOT NULL),
 CHECK (advisory_status <> 'verified_designated' OR (kind IN ('public_designated','venue_designated') AND verification_reviewed_at IS NOT NULL AND verification_public_source IS NOT NULL AND verification_evidence IS NOT NULL))
);
CREATE INDEX places_location_idx ON places USING gist(location);
CREATE INDEX places_geography_idx ON places USING gist((location::geography));
CREATE INDEX places_public_idx ON places (publication_state,advisory_status,kind,id);
CREATE TABLE place_submissions (
 id text PRIMARY KEY, account_id text NOT NULL REFERENCES accounts(id), intent text NOT NULL CHECK(intent IN ('create','correct')),
 place_id text REFERENCES places(id), name text NOT NULL, kind text NOT NULL CHECK(kind IN ('public_designated','venue_designated','informal_outdoor','venue_claim')),
 location geometry(Point,4326) NOT NULL, access_point geometry(Point,4326), address_label text, access_notes text, inside_venue boolean,
 basis text NOT NULL, state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','published','rejected','merged')),
 decision_reason text, created_at timestamptz NOT NULL DEFAULT now(), decided_at timestamptz,
 CHECK ((intent='create' AND place_id IS NULL) OR (intent='correct' AND place_id IS NOT NULL)),
 CHECK (kind <> 'venue_designated' OR inside_venue IS NOT NULL)
);
CREATE INDEX submissions_location_idx ON place_submissions USING gist(location);
CREATE TABLE confirmations (
 id text PRIMARY KEY, place_id text NOT NULL REFERENCES places(id), account_id text NOT NULL REFERENCES accounts(id),
 observation text NOT NULL CHECK(observation IN ('still_there','changed','gone')),
 observed_at timestamptz NOT NULL, access_note_suggestion text, hidden_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX confirmations_place_idx ON confirmations(place_id,observed_at DESC,id DESC);
CREATE TABLE reviews (
 id text PRIMARY KEY, place_id text NOT NULL REFERENCES places(id), account_id text NOT NULL REFERENCES accounts(id),
 stars int NOT NULL CHECK(stars BETWEEN 1 AND 5), body text, hidden_at timestamptz, deleted_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(place_id,account_id)
);
CREATE INDEX reviews_place_idx ON reviews(place_id,created_at DESC,id DESC) WHERE hidden_at IS NULL AND deleted_at IS NULL;
CREATE TABLE reports (
 id text PRIMARY KEY, account_id text NOT NULL REFERENCES accounts(id), target_type text NOT NULL CHECK(target_type IN ('place','review')),
 target_id text NOT NULL, reason text NOT NULL CHECK(reason IN ('wrong_status','closed','access_notes','privacy','harassment','spam','other')),
 detail text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE deletion_requests (id text PRIMARY KEY, account_id text NOT NULL REFERENCES accounts(id), state text NOT NULL DEFAULT 'pending', created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE moderation_cases (
 id text PRIMARY KEY, source_type text NOT NULL CHECK(source_type IN ('submission','confirmation','report','deletion_request','manual')),
 source_id text NOT NULL, state text NOT NULL DEFAULT 'open' CHECK(state IN ('open','resolved')),
 priority int NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz
);
CREATE INDEX moderation_queue_idx ON moderation_cases(state,priority DESC,created_at,id);
CREATE TABLE moderation_decisions (
 id text PRIMARY KEY, case_id text NOT NULL REFERENCES moderation_cases(id), actor_id text NOT NULL REFERENCES accounts(id),
 action text NOT NULL, target_type text NOT NULL, target_id text NOT NULL, reason text NOT NULL,
 old_state jsonb NOT NULL, new_state jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE idempotency_records (
 account_id text NOT NULL REFERENCES accounts(id), route text NOT NULL, key text NOT NULL,
 request_hash text NOT NULL, response_status int NOT NULL, response_body jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(account_id,route,key)
);
CREATE TABLE rate_buckets (bucket text PRIMARY KEY, count int NOT NULL, expires_at timestamptz NOT NULL);

CREATE FUNCTION prevent_decision_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'moderation decisions are append-only';
END;
$$;
CREATE TRIGGER moderation_decisions_append_only BEFORE UPDATE OR DELETE ON moderation_decisions
FOR EACH ROW EXECUTE FUNCTION prevent_decision_mutation();
