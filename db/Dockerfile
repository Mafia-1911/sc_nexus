# Postgres 16 + PostGIS 3 + pgvector (02 §3). The official image (Debian bookworm) already has
# the PGDG apt repository, which ships both extensions. (The postgis/postgis:16-3.5 image is
# built on bullseye, which PGDG no longer serves.)
FROM postgres:16-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      postgresql-16-postgis-3 postgresql-16-postgis-3-scripts postgresql-16-pgvector \
 && rm -rf /var/lib/apt/lists/*
COPY init/ /docker-entrypoint-initdb.d/
