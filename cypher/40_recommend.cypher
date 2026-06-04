// Personalized PageRank seeded with the user's liked songs.
// $liked_artists is bound from src/recommend.py (default: Strokes + Spektor).
// $limit is the number of recommendations to return (default: 5).
MATCH (a:Artist)-[:PERFORMED]->(seed:Song)
WHERE a.name IN $liked_artists
WITH collect(DISTINCT seed) AS sourceNodes

CALL gds.pageRank.stream('songs', {
  sourceNodes: sourceNodes,
  relationshipWeightProperty: 'score',
  dampingFactor: 0.85,
  maxIterations: 40
})
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS song, score
MATCH (artist:Artist)-[:PERFORMED]->(song)
WITH song, score, collect(DISTINCT artist.name) AS artists
WHERE NONE(name IN artists WHERE name IN $liked_artists)
OPTIONAL MATCH (song)-[:IN_GENRE]->(g:Genre)
RETURN artists                    AS artist,
       song.album                 AS album,
       song.name                  AS track,
       collect(DISTINCT g.name)   AS genres,
       score
ORDER BY score DESC
LIMIT $limit;
