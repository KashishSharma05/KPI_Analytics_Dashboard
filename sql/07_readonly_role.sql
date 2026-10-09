-- Read-only database user for the AI assistant.
--
-- The assistant runs SQL written by an LLM. Even if a bad query got past
-- the checks in the code, this user CANNOT change anything: it can only
-- SELECT, and only from the mart schema. This is the last line of defence.
--
-- Run this after the mart schema is built (grants are lost when mart is rebuilt).

-- Create the role only if it does not exist yet.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst_readonly') THEN
        CREATE ROLE analyst_readonly LOGIN;
    END IF;
END
$$;

-- No access to the raw or clean layers, and no creating objects anywhere.
REVOKE ALL ON SCHEMA raw, clean FROM analyst_readonly;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Read access to the mart schema only.
GRANT USAGE ON SCHEMA mart TO analyst_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO analyst_readonly;

-- Any query from this user is stopped after 10 seconds.
ALTER ROLE analyst_readonly SET statement_timeout = '10s';

-- Table names without a schema are looked up in mart only.
ALTER ROLE analyst_readonly SET search_path = mart;

-- Tables added to mart later (anomalies, review_themes) are readable too.
ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO analyst_readonly;
