// Drop any prior named projection so reruns are clean, then project
// SIMILAR_TO as an undirected weighted graph for PageRank.
CALL gds.graph.drop('songs', false) YIELD graphName;

CALL gds.graph.project(
  'songs',
  'Song',
  {
    SIMILAR_TO: {
      properties: 'score',
      orientation: 'UNDIRECTED'
    }
  }
);
