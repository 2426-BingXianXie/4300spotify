# codex.md — Mission: Finish the Homework Submission

Brief for a Codex session that takes the project from "pipeline works"
to "submitted on Canvas". The full project context lives in
[`AGENTS.md`](AGENTS.md); this file is the operational checklist for the
last mile.

## Submission requirements (from graph_music_rec.pdf, "What to Submit")

1. **Documented code** — preprocessing/sampling code AND every Cypher
   query used to build the graph and produce the recommendations,
   "sufficient to reproduce your results".
2. **One-slide PDF poster** containing (a) graph visualization linking
   Strokes songs to the recommendations, (b) one-paragraph approach
   summary, (c) total graph size (# nodes, # edges, density), (d) the
   five recommendations (Artist, Album, Title), (e) the similarity
   rule. **PDF only — not PPTX.**
3. **Post the five recommendations on the shared Google Sheet** linked
   from the Canvas assignment page.

## Phase A — Build the poster (primary task)

Produce **`poster.pdf`** at the repo root — a **single-page, landscape**
PDF slide that meets every requirement in "What to Submit" item 2.

The slide must contain:

1. **Graph visualization** connecting The Strokes' songs to the five
   recommendations (a subgraph of `Song`/`SIMILAR_TO`).
2. **One-paragraph** description of the recommendation approach.
3. **Total graph size**: # nodes, # edges, graph density.
4. **List of the five recommendations** (Artist, Album, Title).
5. **Similarity rule** (how two songs are connected by an edge).

## State of play (do not redo)

The pipeline is already running. You do **not** need to re-sample, recompute
similarity, or reload Neo4j. Just read the existing graph.

- Neo4j is running locally at `bolt://localhost:7687` (creds in `.env`).
- A Docker container `spotify-neo4j` is up; if it isn't:
  `docker start spotify-neo4j`.
- The graph contains 3045 `Song`, 3252 `Artist`, 114 `Genre`, and 42,384
  `:SIMILAR_TO` relationships.
- Recommendation results (latest run) live in `README.md` under
  "Results" and are reproduced verbatim below.

## Implementation plan

Create **one** new file, `src/poster.py`, that builds the PDF using
`neo4j`, `networkx`, and `matplotlib`. Do not introduce new top-level
deps without updating `requirements.txt` — networkx and matplotlib are
the only additions; pin in `requirements.txt` as:

```
matplotlib>=3.8
networkx>=3.2
```

Then run:

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m src.poster
```

The script should:

1. Load env via `src.config.get_driver()`.
2. Run the **viz subgraph query** (below) and fetch nodes/edges.
3. Build a `networkx.Graph`, colour-code nodes:
   - The Strokes' songs: one colour (e.g. `tab:red`).
   - Recommendation songs: another (e.g. `tab:green`).
   - Bridge/neighbour songs along the paths: a third (e.g. `lightgray`).
4. Layout with `nx.spring_layout(seed=4300, k=0.45)` for determinism.
5. Render the page with `matplotlib` using `GridSpec` — one big axes
   for the graph, smaller axes/text blocks for the title, paragraph,
   metrics, recommendations table, and similarity rule.
6. `fig.savefig("poster.pdf", format="pdf", bbox_inches="tight")`.

Keep the script reproducible (no interactive viewers) and idempotent.

## Cypher: viz subgraph

Use this query to pull the subgraph for the visualization. It returns
the Strokes' songs, the five recommendation songs, and any `SIMILAR_TO`
edges that connect them within up to two hops. Bind `$recs` from Python
using the track names listed in "Recommendation set" below.

```cypher
// Strokes' songs (red), recommendation songs (green),
// and any SIMILAR_TO edges among songs reachable within 2 hops
// from a Strokes song to a recommendation song.
MATCH (a:Artist {name: 'The Strokes'})-[:PERFORMED]->(strokes:Song)
WITH collect(DISTINCT strokes) AS strokes_songs
MATCH (rec:Song) WHERE rec.name IN $recs
WITH strokes_songs, collect(DISTINCT rec) AS rec_songs
UNWIND strokes_songs AS s
UNWIND rec_songs AS r
MATCH path = (s)-[:SIMILAR_TO*1..2]-(r)
WITH strokes_songs, rec_songs,
     collect(DISTINCT path) AS paths
UNWIND paths AS p
UNWIND nodes(p)         AS n
UNWIND relationships(p) AS e
RETURN
  collect(DISTINCT { id: elementId(n), name: n.name,
                     is_strokes: n IN strokes_songs,
                     is_rec:     n IN rec_songs }) AS nodes,
  collect(DISTINCT { src: elementId(startNode(e)),
                     dst: elementId(endNode(e)),
                     score: e.score }) AS edges;
```

If the 2-hop subgraph is too dense to read, increase the hop limit only
as needed (`*1..3`) or sample a few representative Strokes songs (e.g.
the first 6 from *Is This It*) instead of all 43.

## Recommendation set (use these EXACT names for `$recs`)

```python
RECS = [
    "My Girlfriend's Girlfriend",
    "コンセプトの戦い",
    "You Will Payback! (Re-Recorded)",
    "To the South",
    "About You",
]
```

## Text blocks (copy verbatim into the slide)

### Title
`Spotify Graph Music Recommender — DS 4300`

### Approach paragraph (one paragraph)

> We sample ~3,000 Spotify tracks stratified by `track_genre`,
> force-including every song by The Strokes and Regina Spektor. After
> z-scoring nine audio features (`danceability, energy, loudness,
> speechiness, acousticness, instrumentalness, liveness, valence,
> tempo`), each song is connected to its **K = 10 nearest neighbours**
> by Euclidean distance, yielding a sparse `SIMILAR_TO` graph. Songs,
> artists, and genres are modelled as distinct nodes. To recommend, we
> run **personalized PageRank** (Neo4j GDS) over `SIMILAR_TO`, seeded
> with the user's liked songs and weighted by
> `score = 1 / (1 + distance)`. The top-ranked tracks are returned
> after excluding artists the user already likes. The approach
> generalises to any user — Prof. Rachlin is just one seed set.

### Graph size

- **Nodes (Song)**: 3,045 (plus 3,252 `Artist`, 114 `Genre`)
- **Edges (`SIMILAR_TO`)**: 42,384 directed (21,192 unique undirected pairs)
- **Density**: `(2 × 21,192) / (3,045 × 3,044) ≈ 0.00457`

### Five recommendations

| # | Artist | Album | Track |
|---|--------|-------|-------|
| 1 | Type O Negative | October Rust (Special Edition) | My Girlfriend's Girlfriend |
| 2 | Yuki Hayashi | Haikyu!! Karasuno vs Shiratorizawa OST | コンセプトの戦い |
| 3 | Confess | Back to My Future | You Will Payback! (Re-Recorded) |
| 4 | Motorama | Calendar | To the South |
| 5 | The 1975 | Being Funny In A Foreign Language | About You |

### Similarity rule

> Two songs are connected by a `SIMILAR_TO` edge iff one is among the
> other's **10 nearest neighbours** in z-scored audio-feature space,
> using Euclidean distance. Edges are symmetric and weighted by
> `score = 1 / (1 + distance)`.

## Constraints (do not violate)

- **No Strokes or Regina Spektor** in the recommendations row of the
  poster — they are the seeds, not outputs.
- **Single page**, **landscape**, **PDF** (the assignment says no PPTX).
- All five required elements above must be visible without scrolling.
- `poster.pdf` IS part of the submission → it **must be tracked by git**
  (do not add it to `.gitignore`). Update `.gitignore` only if you add
  new auxiliary files that should not ship.
- Do not modify `spotify.csv` or `graph_music_rec.pdf`.
- Do not change the pipeline logic in `src/preprocess.py`,
  `src/similarity.py`, `src/build_graph.py`, or `src/recommend.py`.
- Do not commit anything — the user will review and commit themselves.

## Acceptance criteria

- `poster.pdf` exists at the repo root.
- Opening it shows exactly one page in landscape orientation.
- The page contains the title, the approach paragraph, the metrics
  block, the five-row recommendations table, the similarity-rule
  sentence, and a readable graph visualization with at least one path
  from a Strokes song to each of the five recommendations.
- Neither "The Strokes" nor "Regina Spektor" appears in the
  recommendations row.
- `python -m src.poster` re-generates the file deterministically.

## Useful one-liners

```bash
# Confirm Neo4j is up before generating the poster
docker ps --filter "name=spotify-neo4j" --format "{{.Names}}\t{{.Status}}"

# Quick metrics check (matches the numbers above)
.venv/bin/python -c "
from src.config import get_driver, get_database
with get_driver() as d, d.session(database=get_database()) as s:
    print(s.run(open('cypher/99_metrics.cypher').read()).single().data())
"
```

---

## Phase B — Reproducibility dry-run

The PDF says the code must be "sufficient to reproduce your results".
Before submitting, prove that to yourself.

1. From a fresh shell (no in-memory state):
   ```bash
   docker ps --filter "name=spotify-neo4j"   # must show "Up"
   .venv/bin/python -m src.preprocess
   .venv/bin/python -m src.similarity
   .venv/bin/python -m src.build_graph
   .venv/bin/python -m src.recommend
   ```
2. The five recommendations printed by `src/recommend.py` must match
   what `poster.pdf` shows. (`SEED=4300` keeps it deterministic; if the
   list differs, something is off — investigate before submitting.)
3. Cypher coverage: every file under `cypher/` should be referenced
   from `src/build_graph.py` or `src/recommend.py`. Confirm with:
   ```bash
   ls cypher/   # 6 files: 00_schema, 10_load_songs, 20_load_edges,
                # 30_gds_project, 40_recommend, 99_metrics
   grep -R "cypher/" src/
   ```

## Phase C — Google Sheet post

Open the shared Google Sheet linked from the Canvas assignment page and
add a single row for Prof. Rachlin's recommendations. The five rows /
columns to enter:

| Artist | Album | Track |
|--------|-------|-------|
| Type O Negative | October Rust (Special Edition) | My Girlfriend's Girlfriend |
| Yuki Hayashi | Haikyu!! Karasuno vs Shiratorizawa OST | コンセプトの戦い |
| Confess | Back to My Future | You Will Payback! (Re-Recorded) |
| Motorama | Calendar | To the South |
| The 1975 | Being Funny In A Foreign Language | About You |

This is a manual step Codex cannot do — a human must sign in to Google
and edit the shared sheet. Do it before, not after, the Canvas upload.

## Phase D — Push code to GitHub

The code half of the submission is the **GitHub repo URL**, not a zip.
`.gitignore` is the only thing keeping junk out of that repo, so treat
every git command as load-bearing.

### D.1 — Pre-push sanity check (mandatory)

Run this and READ THE OUTPUT before doing anything else:

```bash
cd /path/to/Spotify
git status --ignored --porcelain | sort
```

Acceptance, exactly as printed (order may vary):

```
!! .env
!! .venv/
!! data/
!! src/__pycache__/
?? .env.example
?? .gitignore
?? AGENTS.md
?? README.md
?? codex.md
?? cursor.md
?? cypher/
?? graph_music_rec.pdf
?? plan.md
?? requirements.txt
?? spotify.csv
?? src/
```

If anything else shows up under `??` (untracked), STOP and add the
appropriate pattern to `.gitignore` before staging anything. Common
offenders to add immediately if they appear:

| If you see                  | Add to `.gitignore`                |
| --------------------------- | ---------------------------------- |
| `*.zip`, `*.tar.gz`         | already covered                    |
| `poster.png`, `poster.svg`  | already covered (`poster_*.png` etc.) |
| `*.ipynb`                   | already covered                    |
| `notes.txt`, scratch files  | add explicitly                     |
| anything personal/secret    | add explicitly, then `git rm --cached` if already added |

### D.2 — `poster.pdf` MUST be tracked

`poster.pdf` is the deliverable. After Phase A produces it:

```bash
git check-ignore -v poster.pdf || echo "OK: poster.pdf is NOT ignored"
```

If `git check-ignore` reports a match, fix `.gitignore` so it isn't
matched, then re-check.

### D.3 — First-time push (only if the repo isn't on GitHub yet)

```bash
# Inside the Spotify/ directory:
gh repo create Spotify --public --source . --remote origin --push
# or, manually:
#   create the repo on github.com (no README, no .gitignore, no license)
#   git remote add origin git@github.com:<you>/Spotify.git
#   git branch -M main
```

Then stage + commit. **Use `git add .` so `.gitignore` is the single
source of truth.** If you ever find yourself wanting `git add -f`, stop
and update `.gitignore` instead.

```bash
git add .
git status                  # SCAN this list — anything surprising?
git commit -m "DS4300 Spotify graph music recommender + poster"
git push -u origin main
```

### D.4 — Re-pushes (after Phase A produces poster.pdf, etc.)

```bash
git status                  # never skip this
git add .
git diff --cached --stat    # one last look at what's about to ship
git commit -m "Add poster.pdf and results"
git push
```

### D.5 — Continuously maintain `.gitignore`

Any time you add a new file type to the workflow (notebooks, plots,
local scratch files, model checkpoints, etc.), update `.gitignore` in
the SAME commit. The rule: if `git status` ever shows a file you'd
rather not push, the fix is always a `.gitignore` update — not a
`git add` exclusion.

### D.6 — Canvas submission

Submit on Canvas:

- `poster.pdf` — uploaded directly (PDF, single page, landscape).
- **GitHub URL** — paste the repo URL (e.g.
  `https://github.com/<you>/Spotify`) in the assignment text field.
- Confirm the repo is **Public** (or invite the grader if Canvas asks
  for a private collaborator).

The repo URL replaces any zip/folder upload of the source code.

## Phase E — Final teardown

After the upload is confirmed accepted on Canvas:

```bash
docker stop spotify-neo4j
docker rm   spotify-neo4j      # optional; only if you want the data wiped
docker volume prune -f         # optional; only if you're sure
deactivate                     # leave the venv
```

## Submission checklist (tick each before you click Submit)

- [ ] `poster.pdf` exists, opens in landscape, one page, contains all
      five required elements (viz, paragraph, metrics, 5-rec table,
      similarity rule).
- [ ] Neither "The Strokes" nor "Regina Spektor" appears in the
      recommendations row on the poster.
- [ ] Reproducibility dry-run (Phase B) produces the same five
      recommendations the poster shows.
- [ ] The five recommendations are posted to the shared Canvas Google
      Sheet.
- [ ] `git status --ignored --porcelain` matches the expected output in
      D.1 — nothing extra under `??`, `.env` / `.venv/` / `data/` /
      `__pycache__/` all under `!!`.
- [ ] `poster.pdf` is tracked (not ignored).
- [ ] `git log` on `main` includes a commit with `poster.pdf`.
- [ ] `git push` succeeded; the GitHub repo is browsable and Public
      (or grader added).
- [ ] Canvas assignment text field contains the GitHub repo URL.
- [ ] `poster.pdf` uploaded to the Canvas assignment.
- [ ] (Optional but recommended) docker container stopped so the
      laptop's RAM is freed.
