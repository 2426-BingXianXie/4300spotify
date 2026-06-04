// Uniqueness constraints. Required for idempotent MERGE-based loads.
CREATE CONSTRAINT song_id IF NOT EXISTS
FOR (s:Song) REQUIRE s.track_id IS UNIQUE;

CREATE CONSTRAINT artist_name IF NOT EXISTS
FOR (a:Artist) REQUIRE a.name IS UNIQUE;

CREATE CONSTRAINT genre_name IF NOT EXISTS
FOR (g:Genre) REQUIRE g.name IS UNIQUE;
