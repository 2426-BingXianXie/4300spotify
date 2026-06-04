# cursor.md — Cursor Working Rules for This Repo

Working conventions specifically for Cursor (and any other coding agent)
when implementing the Spotify graph music recommender. Read this in
addition to [`AGENTS.md`](AGENTS.md) and [`plan.md`](plan.md).

## 1. Coding Conventions (Python)

- Python 3.11+. Use type hints on every public function.
- Use `pathlib.Path` for filesystem paths; never raw string-concatenated
  paths.
- Prefer pure functions; keep `if __name__ == "__main__":` thin and only
  for orchestration.
- Docstrings: one-line summary + a short "Returns" / "Side effects" line
  when applicable. No verbose narrative.
- No `print` debugging in committed code beyond intentional progress
  messages (sample size, edge count, top-5 results). Use `logging` if
  output gets noisy.
- Logging format: `logging.basicConfig(level=logging.INFO,
  format="%(asctime)s %(levelname)s %(name)s: %(message)s")`.
- Do **not** add narration comments (`# import pandas`, `# load csv`).
  Comments may only explain non-obvious intent.

## 2. Reproducibility Rules

- One canonical seed: `SEED = 4300`, exported from `src/config.py`.
- Every randomized call (`pandas.sample`, sklearn estimators that accept
  it, etc.) must pass `random_state=SEED`.
- All intermediate artifacts go under `data/`:
  - `data/sample.csv` (from `preprocess.py`)
  - `data/similarity.csv` (from `similarity.py`)
- Re-running any phase script must be idempotent: rerunning
  `build_graph.py` on the same inputs must not duplicate nodes/edges
  (always use `MERGE`, never `CREATE` for shared keys).
- Pin dependency versions in `requirements.txt` with `>=` lower bounds
  matching what was tested.

## 3. Secrets and Config

- Neo4j credentials live in `.env` only. Required keys:
  `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`.
- `.env` is gitignored. `.env.example` is committed with placeholder
  values.
- Read env via `python-dotenv` inside `src/config.py`; never call
  `os.getenv` scattered across modules.
- No credentials, full bolt URIs, or PII in commit messages or printed
  output.

## 4. Cypher Conventions

- All Cypher used by the pipeline must live in `cypher/` as `.cypher`
  files, numbered to indicate execution order
  (`00_schema.cypher`, `10_load_songs.cypher`, ...). The assignment
  requires submitting these.
- Use **parameterized** queries via `tx.run(query, rows=batch, ...)`.
  Never string-format values into Cypher.
- Loads must be idempotent: `MERGE` on unique keys (`track_id`,
  `Artist.name`, `Genre.name`). Use `SET` after `MERGE` to update
  properties.
- Batch sizes: ~500 rows for node loads, ~1,000 rows for edge loads.
- Always `CALL gds.graph.drop('songs', false)` before re-projecting so
  reruns are clean.
- Prefer named graph projections (`'songs'`) over anonymous projections
  so they can be inspected and dropped.

## 5. Graph Model Guardrails

- `:Song.track_id` is the only key for songs (artist + name can collide).
- Always create `:Artist` nodes from the **split-on-`;`** form of the
  `artists` column. Do not store the raw `;`-separated string as a single
  artist name.
- `:Genre.name` is the lowercase string from `track_genre`.
- `SIMILAR_TO` carries `score` (preferred for PageRank) and `distance`
  (raw Euclidean) so both views are queryable.

## 6. Hard Guardrails (do not violate)

1. **Strokes/Spektor inclusion in sample**: after `preprocess.py` runs,
   assert that the sample contains every Strokes row and every Regina
   Spektor row from `spotify.csv`. Fail the script if not.
2. **Strokes/Spektor exclusion in recs**: filter inside the Cypher AND
   re-check in Python. If a recommendation contains either artist
   (case-insensitive substring on any artist in the list), raise an
   exception. No silent passes.
3. **Density sanity**: after edge load, compute and log `N`, `E`,
   `density`. If density > 0.05, abort and ask the operator to lower `K`.
4. **Reproducibility**: any successful run must be re-runnable from a
   clean DB by executing the four scripts in order without manual edits.
5. **Do not modify** `spotify.csv` or `graph_music_rec.pdf`.

## 7. Verification Before Declaring Done

Run, in order, on a fresh database:

```bash
python -m src.preprocess
python -m src.similarity
python -m src.build_graph
python -m src.recommend
```

Then confirm all of the following:

- `data/sample.csv` exists and contains all Strokes + Regina Spektor rows.
- `data/similarity.csv` row count ≈ `2 * N * K` (after symmetrize + dedupe).
- In Neo4j:
  - `MATCH (s:Song) RETURN count(s)` equals the sample row count.
  - `MATCH (a:Artist {name: 'The Strokes'})-[:PERFORMED]->(s) RETURN count(s)` ≥ 50.
  - `MATCH (a:Artist {name: 'Regina Spektor'})-[:PERFORMED]->(s) RETURN count(s)` ≥ 3.
  - `CALL gds.graph.exists('songs') YIELD exists` returns `true`.
- `src/recommend.py` prints:
  - `N`, `E`, and density (matches `cypher/99_metrics.cypher`).
  - A 5-row table of `(artists, album, track, score)`.
  - No Strokes or Regina Spektor entries anywhere in those 5 rows.
- All Cypher files in `cypher/` are committed.
- `.env` is NOT committed; `.env.example` IS committed.

If any of those fail, do not mark the work complete — fix and re-run.

## 8. Cursor-Specific Tips

- When generating Python, prefer editing existing files in `src/` over
  creating new ones; don't sprawl utility modules.
- When editing Cypher, keep each file focused on one concern (schema,
  load nodes, load edges, GDS project, recommend, metrics).
- Before running anything against Neo4j, read `cypher/00_schema.cypher`
  to confirm constraints exist.
- Don't write tests for the data scripts unless explicitly requested;
  the verification steps above are the acceptance test.
- If you need to deviate from the approach in `AGENTS.md` (e.g. switch
  from kNN to a global threshold), update `AGENTS.md` and `plan.md` in
  the same change.
