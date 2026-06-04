// Load songs, artists (split on ';'), and genres from data/sample.csv.
// Invoked from src/build_graph.py with $rows = list of CSV row dicts.
UNWIND $rows AS row
MERGE (s:Song {track_id: row.track_id})
  SET s.name             = row.track_name,
      s.album            = row.album_name,
      s.popularity       = toInteger(row.popularity),
      s.duration_ms      = toInteger(row.duration_ms),
      s.danceability     = toFloat(row.danceability),
      s.energy           = toFloat(row.energy),
      s.valence          = toFloat(row.valence),
      s.tempo            = toFloat(row.tempo),
      s.acousticness     = toFloat(row.acousticness),
      s.instrumentalness = toFloat(row.instrumentalness),
      s.speechiness      = toFloat(row.speechiness),
      s.liveness         = toFloat(row.liveness),
      s.loudness         = toFloat(row.loudness)
WITH s, row
UNWIND split(row.artists, ';') AS artist_raw
WITH s, row, trim(artist_raw) AS artist_name
WHERE artist_name <> ''
MERGE (a:Artist {name: artist_name})
MERGE (a)-[:PERFORMED]->(s)
WITH s, row
MERGE (g:Genre {name: row.track_genre})
MERGE (s)-[:IN_GENRE]->(g);
