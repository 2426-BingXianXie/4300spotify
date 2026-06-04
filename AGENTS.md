# AGENTS.md — Spotify Graph Music Recommender (DS 4300)

Authoritative project guide for any AI agent (Cursor, Claude Code, Codex, etc.)
working in this repo. Read this file end-to-end before making changes.

## 1. Project Overview

Build a **general-purpose song recommendation system** on top of a Neo4j
graph database derived from a Kaggle Spotify dataset (~114,000 songs). The
recommender is tested by producing **five song recommendations for Prof.
Rachlin**, who likes:

- The Strokes (especially the album *Is This It*)
- Regina Spektor (especially the song *Us*)

**Hard rules from the assignment:**

1. The system must be **general-purpose**, not hand-tuned to Prof. Rachlin.
2. The final five recommendations **must NOT contain any songs by The
   Strokes or Regina Spektor**.
3. All preprocessing/sampling code AND every Cypher query used to build the
   graph and generate recommendations must be committed and reproducible.

Source documents:

- Assignment spec: [`graph_music_rec.pdf`](graph_music_rec.pdf)
- Raw data: [`spotify.csv`](spotify.csv) (114,000 rows)

## 2. Dataset Notes

`spotify.csv` columns (first column is an unnamed pandas index):

```
track_id, artists, album_name, track_name, popularity, duration_ms,
explicit, danceability, energy, key, loudness, mode, speechiness,
acousticness, instrumentalness, liveness, valence, tempo,
time_signature, track_genre
```

Important characteristics:

- `artists` is a `;`-separated string for collaborations
  (e.g. `Ingrid Michaelson;ZAYN`).
- Many tracks are duplicated across genres (same `track_name + artists` may
  appear with different `track_genre` values). De-dupe on
  `(track_name, artists)` after sampling, or merge genre lists into a list
  property.
- Confirmed counts in the raw CSV:
  - The Strokes: **~52–54 rows** (all *Is This It* tracks present).
  - Regina Spektor: **~3 rows**.
- A full pairwise similarity graph on 114k songs would be ~13B edges. **Do
  not build it.** Sample first.

## 3. Recommended Technical Approach

This is the approach the rest of the documents (`plan.md`, `cursor.md`)
assume. Don't deviate without updating both.

- **Stack:** Python 3.11+, `pandas`, `numpy`, `scikit-learn`, `neo4j`
  (official driver), `python-dotenv`, optional `matplotlib` for sanity
  plots.
- **Database:** **local Neo4j** (Neo4j Desktop or Docker), version 5.x,
  with the **Graph Data Science (GDS) plugin** installed.
- **Sampling:** stratified across `track_genre` (~2,000–5,000 songs) with
  **forced inclusion** of every Strokes row and every Regina Spektor row.
  De-dupe by `(track_name, artists)`.
- **Audio features (standardized with z-scores):** `danceability`,
  `energy`, `loudness`, `speechiness`, `acousticness`, `instrumentalness`,
  `liveness`, `valence`, `tempo`.
- **Graph model:**
  - Nodes: `(:Song {track_id, name, popularity, duration_ms, ...features})`,
    `(:Artist {name})`, `(:Genre {name})`.
  - Edges:
    - `(:Artist)-[:PERFORMED]->(:Song)`
    - `(:Song)-[:IN_GENRE]->(:Genre)`
    - `(:Song)-[:SIMILAR_TO {score, distance}]->(:Song)`
- **Similarity edges:** **kNN** in standardized feature space (each song
  links to its `k` nearest neighbors by Euclidean distance). kNN controls
  density better than a fixed global threshold. Tune `k` (start at
  `k = 10`) for a connected-but-sparse graph.
- **Recommendation algorithm (the "creative" part):** Neo4j GDS
  **personalized PageRank** over `SIMILAR_TO`, **seeded** with the user's
  liked songs (here: *Is This It* tracks + Regina Spektor tracks).
  Post-filter to exclude any Strokes/Spektor songs, then take the top 5.
  This is general-purpose: swap the seed set for any user.
- **Poster metrics:** report N (nodes), E (edges), and graph density
  `D = 2E / (N(N - 1))` for an undirected view of `SIMILAR_TO`.

## 4. Proposed Repo Layout

```
.
├── AGENTS.md              # this file
├── plan.md                # phased implementation checklist
├── cursor.md              # Cursor-specific working rules
├── README.md              # human-facing quick start (create when implementing)
├── requirements.txt       # pinned Python deps
├── .env.example           # NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD template
├── spotify.csv            # raw Kaggle dataset (do not modify)
├── graph_music_rec.pdf    # assignment spec (do not modify)
├── data/
│   ├── sample.csv         # stratified sample written by preprocess.py
│   └── similarity.csv     # kNN edges (src, dst, distance, score)
├── src/
│   ├── __init__.py
│   ├── config.py          # env loading, constants (SEED, K, SAMPLE_SIZE)
│   ├── preprocess.py      # sample + standardize + write data/sample.csv
│   ├── similarity.py      # kNN over standardized features → data/similarity.csv
│   ├── build_graph.py     # load CSVs into Neo4j via the driver
│   └── recommend.py       # run GDS personalized PageRank and print top 5
└── cypher/
    ├── 00_schema.cypher       # constraints / indexes
    ├── 10_load_songs.cypher   # MERGE songs/artists/genres from sample.csv
    ├── 20_load_edges.cypher   # MERGE :SIMILAR_TO from similarity.csv
    ├── 30_gds_project.cypher  # gds.graph.project for SIMILAR_TO subgraph
    ├── 40_recommend.cypher    # personalized PageRank + exclusion + top 5
    └── 99_metrics.cypher      # nodes, edges, density for the poster
```

## 5. Environment Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
```

`requirements.txt` (minimum):

```
pandas>=2.1
numpy>=1.26
scikit-learn>=1.4
neo4j>=5.18
python-dotenv>=1.0
```

Neo4j:

1. Install Neo4j Desktop (or run `neo4j:5` via Docker).
2. Create a local database; install the **Graph Data Science** plugin from
   the database's "Plugins" tab.
3. Start the database. Default bolt URI is `bolt://localhost:7687`.
4. Put credentials in `.env` (never commit `.env`).

## 6. How to Run End-to-End

```bash
# 1. Sample + standardize features
python -m src.preprocess

# 2. Compute kNN similarity edges
python -m src.similarity

# 3. Load nodes and edges into Neo4j (runs cypher/00..20)
python -m src.build_graph

# 4. Generate recommendations for Prof. Rachlin
python -m src.recommend
```

`recommend.py` must print:

- N, E, density (the poster metrics).
- The five recommended `(artist, album, track)` tuples.
- The Cypher it executed (for the submission).

## 7. Hard Constraints (do not violate)

- **Never** include songs by The Strokes or Regina Spektor in the final
  five recommendations. Filter both in the Cypher query and validate again
  in Python.
- The sample **must include** every Strokes row and every Regina Spektor
  row from the raw CSV; otherwise the seed set is empty.
- All code paths must be reproducible: pin `random_state`/`SEED`, write
  intermediate CSVs to `data/`, and check them in only if small enough.
- Every Cypher query used at any stage of the pipeline lives in
  [`cypher/`](cypher/) — the assignment requires submitting them.
- Do not hardcode Neo4j credentials. Load from `.env`.
- Do not modify `spotify.csv` or `graph_music_rec.pdf`.

## 8. Submission Checklist (from the PDF)

- Documented preprocessing/sampling code.
- All Cypher queries used to build the graph and generate recommendations.
- One-slide PDF poster with:
  - Graph visualization connecting Strokes songs to the 5 recommendations.
  - 1-paragraph description of the recommendation approach.
  - Total graph size: # nodes, # edges, graph density.
  - The five recommendations (Artist, Album, Title).
  - The similarity rule used to connect songs (and artists, if modeled).
- Post the five recommendations to the shared Google Sheet on Canvas.
