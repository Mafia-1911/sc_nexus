-- Runs once when the compose `db` volume is created (docker-entrypoint-initdb.d).
-- The initial Alembic migration also creates them (IF NOT EXISTS), for non-Docker databases.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
