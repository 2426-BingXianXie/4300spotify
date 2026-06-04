// Load similarity edges from data/similarity.csv.
// Invoked from src/build_graph.py with $rows = list of edge dicts.
UNWIND $rows AS row
MATCH (a:Song {track_id: row.src_track_id})
MATCH (b:Song {track_id: row.dst_track_id})
MERGE (a)-[r:SIMILAR_TO]->(b)
  SET r.distance = toFloat(row.distance),
      r.score    = toFloat(row.score);
