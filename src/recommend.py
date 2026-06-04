"""Generate top-N song recommendations via personalized PageRank.

Runs the GDS projection in ``cypher/30_gds_project.cypher`` and then the
personalized PageRank query in ``cypher/40_recommend.cypher``, seeded with the
user's liked artists. By default the seeds are the assignment's required
artists (``LIKED_ARTISTS`` from config). Excluded from results, both in Cypher
and again in Python as a defense-in-depth check.
"""

from __future__ import annotations

import logging
from typing import Sequence

from src.config import (
    CYPHER_DIR,
    LIKED_ARTISTS,
    get_database,
    get_driver,
)

log = logging.getLogger(__name__)

PROJECT_FILE = CYPHER_DIR / "30_gds_project.cypher"
RECOMMEND_FILE = CYPHER_DIR / "40_recommend.cypher"
METRICS_FILE = CYPHER_DIR / "99_metrics.cypher"

DEFAULT_LIMIT = 5


def _split_statements(text: str) -> list[str]:
    """Split a Cypher file into individual statements on semicolons.

    Returns: Non-empty stripped statement strings.
    """
    return [s.strip() for s in text.split(";") if s.strip()]


def _project_graph(session) -> None:
    """Drop and recreate the GDS named graph ``songs`` over ``SIMILAR_TO``.

    Side effects: Executes ``cypher/30_gds_project.cypher`` on Neo4j.
    """
    for stmt in _split_statements(PROJECT_FILE.read_text(encoding="utf-8")):
        session.run(stmt)
    log.info("GDS projection 'songs' ready (UNDIRECTED, weighted by score)")


def _recommend(session, liked_artists: Sequence[str], limit: int) -> list[dict]:
    """Run personalized PageRank and return top songs excluding liked artists.

    Returns: List of dicts with keys ``artist``, ``album``, ``track``, ``genres``, ``score``.
    """
    query = RECOMMEND_FILE.read_text(encoding="utf-8")
    result = session.run(query, liked_artists=list(liked_artists), limit=limit)
    return [record.data() for record in result]


def _report_metrics(session) -> None:
    """Log graph size metrics from ``cypher/99_metrics.cypher``.

    Side effects: Writes INFO log with N, E, and density.
    """
    for stmt in _split_statements(METRICS_FILE.read_text(encoding="utf-8")):
        record = session.run(stmt).single()
        if record is not None:
            log.info("metrics: %s", dict(record))


def _validate_exclusion(rows: list[dict], liked_artists: Sequence[str]) -> None:
    """Assert no recommendation row names a seed/liked artist (Python safety net).

    Raises: ``AssertionError`` if any blocked artist appears in a result row.
    """
    blocked = {a.lower() for a in liked_artists}
    for row in rows:
        for name in row.get("artist") or []:
            if name.lower() in blocked or any(b in name.lower() for b in blocked):
                raise AssertionError(
                    f"Recommendation contains blocked artist '{name}' in row {row}"
                )


def recommend(
    liked_artists: Sequence[str] = LIKED_ARTISTS,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Project the graph, run seeded PageRank, validate, and log metrics.

    Returns: Top-``limit`` recommendation dicts (no liked-artist songs).
    Side effects: Neo4j GDS projection + query; closes the driver when done.
    """
    driver = get_driver()
    try:
        with driver.session(database=get_database()) as session:
            _project_graph(session)
            rows = _recommend(session, liked_artists, limit)
            _validate_exclusion(rows, liked_artists)
            _report_metrics(session)
    finally:
        driver.close()
    return rows


def _format_table(rows: list[dict]) -> str:
    """Format recommendation rows as a fixed-width CLI table string.

    Returns: Multi-line table text for ``print`` in ``main()``.
    """
    if not rows:
        return "(no recommendations)"
    lines = ["#  Artist(s) | Album | Track | Genres | Score"]
    for i, row in enumerate(rows, 1):
        artists = ", ".join(row.get("artist") or [])
        genres = ", ".join(row.get("genres") or [])
        lines.append(
            f"{i:>2} {artists} | {row.get('album')} | {row.get('track')} | "
            f"{genres} | {row.get('score'):.5f}"
        )
    return "\n".join(lines)


def main() -> None:
    """CLI entry point: run ``recommend()`` and print the top-5 table."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    rows = recommend()
    print("\nTop recommendations (seeds: " + ", ".join(LIKED_ARTISTS) + ")")
    print(_format_table(rows))


if __name__ == "__main__":
    main()
