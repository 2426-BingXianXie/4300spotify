// Total graph size for the poster slide.
// N = song nodes, E (directed) = SIMILAR_TO relationships,
// E (undirected) = directed / 2, density = 2*E_undirected / (N*(N-1)).
MATCH (s:Song)
WITH count(s) AS N
MATCH ()-[r:SIMILAR_TO]->()
WITH N, count(r) AS E_directed
RETURN N,
       E_directed                                  AS E_directed,
       E_directed / 2                              AS E_undirected,
       (2.0 * (E_directed / 2.0)) / (N * (N - 1))  AS density;
