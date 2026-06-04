"""Idempotent loader from local CSVs into Neo4j.

Reads ``data/sample.csv`` and ``data/similarity.csv``, then runs the Cypher
files in ``cypher/`` (schema, song load, edge load) in batches.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import pandas as pd

from src.config import (
    CYPHER_DIR,
    SAMPLE_CSV,
    SIMILARITY_CSV,
    get_database,
    get_driver,
)

log = logging.getLogger(__name__)

SCHEMA_FILE = CYPHER_DIR / "00_schema.cypher"
SONG_FILE = CYPHER_DIR / "10_load_songs.cypher"
EDGE_FILE = CYPHER_DIR / "20_load_edges.cypher"

SONG_BATCH = 500
EDGE_BATCH = 1000


def _read_cypher(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _chunked(records: list[dict], size: int) -> Iterator[list[dict]]:
    for i in range(0, len(records), size):
        yield records[i : i + size]


def _execute_schema(session) -> None:
    """Run each statement in the schema file individually."""
    for stmt in [s.strip() for s in _read_cypher(SCHEMA_FILE).split(";") if s.strip()]:
        session.run(stmt)
    log.info("schema constraints ensured")


def _load_songs(session, rows: list[dict]) -> None:
    query = _read_cypher(SONG_FILE)
    total = 0
    for batch in _chunked(rows, SONG_BATCH):
        session.run(query, rows=batch)
        total += len(batch)
    log.info("loaded %s song rows (with artists + genres)", total)


def _load_edges(session, rows: list[dict]) -> None:
    query = _read_cypher(EDGE_FILE)
    total = 0
    for batch in _chunked(rows, EDGE_BATCH):
        session.run(query, rows=batch)
        total += len(batch)
    log.info("loaded %s similarity edges", total)


def _song_rows() -> list[dict]:
    df = pd.read_csv(SAMPLE_CSV, dtype={"track_id": str})
    keep = [
        "track_id", "track_name", "album_name", "artists", "track_genre",
        "popularity", "duration_ms",
        "danceability", "energy", "loudness", "speechiness",
        "acousticness", "instrumentalness", "liveness", "valence", "tempo",
    ]
    return df[keep].to_dict(orient="records")


def _edge_rows() -> list[dict]:
    df = pd.read_csv(SIMILARITY_CSV, dtype={"src_track_id": str, "dst_track_id": str})
    return df[["src_track_id", "dst_track_id", "distance", "score"]].to_dict(orient="records")


def build_graph() -> None:
    """Run schema + node load + edge load against Neo4j."""
    songs = _song_rows()
    edges = _edge_rows()
    driver = get_driver()
    try:
        with driver.session(database=get_database()) as session:
            _execute_schema(session)
            _load_songs(session, songs)
            _load_edges(session, edges)
            _report_counts(session)
    finally:
        driver.close()


def _report_counts(session) -> None:
    n_song = session.run("MATCH (s:Song) RETURN count(s) AS n").single()["n"]
    n_artist = session.run("MATCH (a:Artist) RETURN count(a) AS n").single()["n"]
    n_genre = session.run("MATCH (g:Genre) RETURN count(g) AS n").single()["n"]
    n_rel = session.run("MATCH ()-[r:SIMILAR_TO]->() RETURN count(r) AS n").single()["n"]
    density = (n_rel * 1.0) / max(1, n_song * (n_song - 1))
    log.info(
        "graph state: songs=%s artists=%s genres=%s similar_to=%s directed_density=%.5f",
        n_song,
        n_artist,
        n_genre,
        n_rel,
        density,
    )
    if density > 0.05:
        log.warning("density %.4f exceeds 0.05 guardrail; consider lowering K", density)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    build_graph()


if __name__ == "__main__":
    main()
