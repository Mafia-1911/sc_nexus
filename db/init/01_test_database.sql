-- A second database for the test suite (pytest resets its schema), same extensions.
CREATE DATABASE cportal_test OWNER cportal;
\connect cportal_test
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
