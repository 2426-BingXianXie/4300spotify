# plan.md — Implementation Plan

Phased, checkbox plan for building the Neo4j graph music recommender
described in [`graph_music_rec.pdf`](graph_music_rec.pdf) and scaffolded by
[`AGENTS.md`](AGENTS.md). Work through phases top-down; do not skip
verification steps.

Conventions:

- `[ ]` = todo, `[x]` = done.
- Code lives under `src/`, Cypher lives under `cypher/`.
- Treat `SEED = 4300`, `SAMPLE_SIZE = 3000`, `K = 10` as defaults to tune.

---

## Phase 0 — Environment and Neo4j Setup

- [ ] Create and activate Python venv (`python -m venv .venv`).
- [ ] Write `requirements.txt` with pinned deps:
      `pandas`, `numpy`, `scikit-learn`, `neo4j`, `python-dotenv`.
- [ ] `pip install -r requirements.txt`.
- [ ] Install Neo4j Desktop (or Docker `neo4j:5` with `apoc` + `gds`).
- [ ] Install the **Graph Data Science** plugin on the database.
- [ ] Start the database; confirm bolt URI `bolt://localhost:7687`.
- [ ] Create `.env.example` and `.env` with
      `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`. Add `.env` to `.gitignore`.
- [ ] Add `src/config.py` exporting `SEED`, `SAMPLE_SIZE`, `K`,
      `FEATURE_COLS`, and a `get_driver()` helper that reads `.env`.
- [ ] Smoke test the connection:
      `CALL gds.version()` returns a version string.

Exit criteria: `python -c "from src.config import get_driver; get_driver().verify_connectivity()"` succeeds and `gds.version()` works.

---

## Phase 1 — Preprocessing and Sampling (`src/preprocess.py`)

Goal: produce `data/sample.csv` containing ~3,000 songs, stratified by
`track_genre`, with every Strokes and Regina Spektor row force-included.

- [ ] Load `spotify.csv` with `pandas.read_csv("spotify.csv", index_col=0)`.
- [ ] Drop rows with NaN in any `FEATURE_COLS`.
- [ ] Identify "must include" rows where
      `artists.str.contains("The Strokes", case=False)` or
      `artists.str.contains("Regina Spektor", case=False)`.
      Assert both sets are non-empty.
- [ ] Stratified sample: for each `track_genre`, take
      `ceil(SAMPLE_SIZE / n_genres)` rows with `random_state=SEED`.
- [ ] Concatenate stratified sample + must-include rows.
- [ ] De-dupe on `(track_name, artists)` keeping first.
- [ ] Explode the `artists` column on `;` into a list column `artist_list`
      (for later per-artist nodes).
- [ ] Standardize `FEATURE_COLS` with `sklearn.preprocessing.StandardScaler`
      and store the standardized columns as `feat_<col>`.
- [ ] Write `data/sample.csv` (raw + standardized columns).
- [ ] Print summary: total rows, # Strokes rows, # Spektor rows, # genres.

Exit criteria: `data/sample.csv` exists, Strokes count >= 50, Spektor
count >= 3, total rows in `[2500, 4500]`.

---

## Phase 2 — kNN Similarity (`src/similarity.py`)

Goal: produce `data/similarity.csv` with columns
`src_track_id, dst_track_id, distance, score`.

- [ ] Load `data/sample.csv`.
- [ ] Build matrix `X` from the `feat_*` columns.
- [ ] Fit `sklearn.neighbors.NearestNeighbors(n_neighbors=K + 1,
      metric="euclidean").fit(X)`.
- [ ] `distances, indices = nn.kneighbors(X)`; drop the self-neighbor
      (column 0).
- [ ] For each `(i, j)` pair produce
      `score = 1.0 / (1.0 + distance)` (higher = more similar).
- [ ] Symmetrize: also write the reverse pair so the graph is
      effectively undirected when projected.
- [ ] De-dupe pairs.
- [ ] Write `data/similarity.csv`.
- [ ] Print summary: edge count, mean degree, min/max distance.

Notes:

- kNN keeps degree bounded (`~K` per node), avoiding the 13B-edge blowup.
- We're using kNN instead of a global Euclidean threshold because it
  guarantees connectivity proportional to `K`. The PDF's threshold idea is
  the alternative — document the choice in the poster.

Exit criteria: edge count ≈ `2 * N * K` (after symmetrize + de-dupe);
no isolated nodes.

---

## Phase 3 — Graph Load (`src/build_graph.py` + `cypher/00..20`)

Goal: idempotent load of nodes and edges into Neo4j.

### 3a. Schema (`cypher/00_schema.cypher`)

```cypher
CREATE CONSTRAINT song_id IF NOT EXISTS
FOR (s:Song) REQUIRE s.track_id IS UNIQUE;

CREATE CONSTRAINT artist_name IF NOT EXISTS
FOR (a:Artist) REQUIRE a.name IS UNIQUE;

CREATE CONSTRAINT genre_name IF NOT EXISTS
FOR (g:Genre) REQUIRE g.name IS UNIQUE;
```

- [ ] Execute schema via the driver.

### 3b. Load songs/artists/genres (`cypher/10_load_songs.cypher`)

Run per-row via `UNWIND $rows AS row`:

```cypher
UNWIND $rows AS row
MERGE (s:Song {track_id: row.track_id})
  SET s.name = row.track_name,
      s.album = row.album_name,
      s.popularity = toInteger(row.popularity),
      s.duration_ms = toInteger(row.duration_ms),
      s.danceability = toFloat(row.danceability),
      s.energy = toFloat(row.energy),
      s.valence = toFloat(row.valence),
      s.tempo = toFloat(row.tempo),
      s.acousticness = toFloat(row.acousticness),
      s.instrumentalness = toFloat(row.instrumentalness),
      s.speechiness = toFloat(row.speechiness),
      s.liveness = toFloat(row.liveness),
      s.loudness = toFloat(row.loudness)
WITH s, row
UNWIND split(row.artists, ';') AS artist_name
MERGE (a:Artist {name: trim(artist_name)})
MERGE (a)-[:PERFORMED]->(s)
WITH s, row
MERGE (g:Genre {name: row.track_genre})
MERGE (s)-[:IN_GENRE]->(g);
```

- [ ] Stream `data/sample.csv` in batches of 500 via `tx.run(..., rows=batch)`.

### 3c. Load similarity edges (`cypher/20_load_edges.cypher`)

```cypher
UNWIND $rows AS row
MATCH (a:Song {track_id: row.src_track_id})
MATCH (b:Song {track_id: row.dst_track_id})
MERGE (a)-[r:SIMILAR_TO]->(b)
  SET r.distance = toFloat(row.distance),
      r.score    = toFloat(row.score);
```

- [ ] Stream `data/similarity.csv` in batches of 1000.

Exit criteria:

```cypher
MATCH (s:Song)              RETURN count(s);  // == sample size
MATCH ()-[r:SIMILAR_TO]->()  RETURN count(r); // ≈ 2 * N * K (post-dedupe)
```

---

## Phase 4 — Recommendation via Personalized PageRank

Goal: produce five non-Strokes/non-Spektor recommendations for the
liked-songs seed set.

### 4a. Project the GDS subgraph (`cypher/30_gds_project.cypher`)

```cypher
CALL gds.graph.drop('songs', false) YIELD graphName;
CALL gds.graph.project(
  'songs',
  'Song',
  { SIMILAR_TO: { properties: 'score', orientation: 'UNDIRECTED' } }
);
```

- [ ] Execute once after loads (re-run when the graph changes).

### 4b. Run personalized PageRank (`cypher/40_recommend.cypher`)

```cypher
// Seed = Prof. Rachlin's liked songs (Strokes + Regina Spektor)
MATCH (seed:Song)<-[:PERFORMED]-(a:Artist)
WHERE a.name IN ['The Strokes', 'Regina Spektor']
WITH collect(seed) AS sourceNodes

CALL gds.pageRank.stream('songs', {
  sourceNodes: sourceNodes,
  relationshipWeightProperty: 'score',
  dampingFactor: 0.85,
  maxIterations: 40
})
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS song, score
MATCH (artist:Artist)-[:PERFORMED]->(song)
WITH song, score, collect(artist.name) AS artists
WHERE NONE(name IN artists WHERE name IN ['The Strokes', 'Regina Spektor'])
RETURN artists AS artist,
       song.album   AS album,
       song.name    AS track,
       score
ORDER BY score DESC
LIMIT 5;
```

- [ ] Implement `src/recommend.py` to run this and print results.
- [ ] **Double-filter in Python**: re-check that none of the 5 returned
      rows contain "The Strokes" or "Regina Spektor" (case-insensitive
      substring on the artists list). Fail loudly if violated.

Exit criteria: 5 rows returned, no Strokes/Spektor in `artist`.

---

## Phase 5 — Tuning (Density and Quality)

The poster requires "reasonably connected (but not overly dense)" — tune
`K` and optionally a min-score floor.

- [ ] Compute density after each load:
      `D = (2 * E) / (N * (N - 1))` (N = song count, E = SIMILAR_TO count
      treated as undirected).
- [ ] Sweep `K ∈ {5, 8, 10, 15, 20}`. For each, record
      `(N, E, D, avg_degree, n_connected_components)` and keep the
      smallest `K` that gives one giant component covering ≥ 95% of nodes.
- [ ] Optional: add a min-score floor (drop edges with `score < tau`) to
      prune obvious outliers; only if density still feels excessive.
- [ ] Re-run Phase 4 with the chosen `K`; compare top-5 stability.

Exit criteria: chosen `K` and `tau` documented in `README.md`, density
reported on the poster.

---

## Phase 6 — Poster Artifacts

- [ ] **Graph visualization**: in Neo4j Browser run something like

```cypher
MATCH p = (a:Artist {name: 'The Strokes'})-[:PERFORMED]->(:Song)
      -[:SIMILAR_TO*1..2]-(rec:Song)
WHERE NOT EXISTS {
  MATCH (rec)<-[:PERFORMED]-(:Artist {name: 'The Strokes'})
}
RETURN p LIMIT 100;
```

  Export the rendered graph as an image for the slide.

- [ ] **Metrics block** (`cypher/99_metrics.cypher`):

```cypher
MATCH (s:Song)             WITH count(s) AS N
MATCH ()-[r:SIMILAR_TO]->() WITH N, count(r) AS E_directed
RETURN N,
       E_directed / 2                          AS E_undirected,
       (2.0 * (E_directed / 2)) / (N * (N - 1)) AS density;
```

- [ ] **Recommendations table**: copy the 5 rows from Phase 4 into the
      slide (Artist, Album, Title).
- [ ] **One-paragraph approach summary** for the slide. Suggested wording
      to start from:

  > We sample ~3,000 Spotify tracks stratified by genre, force-including
  > every song by The Strokes and Regina Spektor. After z-scoring nine
  > audio features we connect each song to its K nearest neighbors by
  > Euclidean distance (kNN graph), yielding a sparse SIMILAR_TO network.
  > Songs, artists, and genres are modeled as distinct nodes. To
  > recommend, we run **personalized PageRank** (Neo4j GDS) over
  > SIMILAR_TO, seeded with the user's liked songs, then return the
  > top-ranked tracks after filtering out artists the user already
  > likes. This generalizes to any user — Prof. Rachlin is just one
  > seed set.

- [ ] **Similarity rule**: write one sentence stating exactly how edges
      are formed (kNN, K = chosen value, Euclidean on standardized audio
      features, `score = 1 / (1 + distance)`).
- [ ] Export the slide as **PDF** (not PPTX) per the spec.
- [ ] Post the 5 recommendations to the shared Google Sheet on Canvas.

---

## Reference: Density Formula

For an undirected graph projection of `SIMILAR_TO`:

```
D = (2 * E) / (N * (N - 1))
```

where `N` is the number of `Song` nodes and `E` is the number of unique
undirected `SIMILAR_TO` edges. Densities in the range `1e-3` to `1e-2`
are typical for a kNN graph at this scale.
