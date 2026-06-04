"""Shared configuration: paths, constants, and Neo4j driver factory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

ROOT: Final[Path] = Path(__file__).resolve().parent.parent
DATA_DIR: Final[Path] = ROOT / "data"
CYPHER_DIR: Final[Path] = ROOT / "cypher"

RAW_CSV: Final[Path] = ROOT / "spotify.csv"
SAMPLE_CSV: Final[Path] = DATA_DIR / "sample.csv"
SIMILARITY_CSV: Final[Path] = DATA_DIR / "similarity.csv"

SEED: Final[int] = 4300
SAMPLE_SIZE: Final[int] = 3000
K: Final[int] = 10

LIKED_ARTISTS: Final[tuple[str, ...]] = ("The Strokes", "Regina Spektor")

FEATURE_COLS: Final[tuple[str, ...]] = (
    "danceability",
    "energy",
    "loudness",
    "speechiness",
    "acousticness",
    "instrumentalness",
    "liveness",
    "valence",
    "tempo",
)

STANDARDIZED_PREFIX: Final[str] = "feat_"


def get_driver() -> Driver:
    """Create a Neo4j driver from ``NEO4J_URI``, ``NEO4J_USER``, and ``NEO4J_PASSWORD``.

    Returns: Connected ``Driver`` instance (caller must ``close()`` it).
    Side effects: Loads ``ROOT/.env`` via ``python-dotenv``.
    """
    load_dotenv(ROOT / ".env")
    uri = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USER"]
    password = os.environ["NEO4J_PASSWORD"]
    return GraphDatabase.driver(uri, auth=(user, password))


def get_database() -> str:
    """Return the Neo4j database name from ``NEO4J_DATABASE`` (default ``neo4j``).

    Returns: Database name string for ``session(database=...)``.
    Side effects: Loads ``ROOT/.env`` via ``python-dotenv``.
    """
    load_dotenv(ROOT / ".env")
    return os.environ.get("NEO4J_DATABASE", "neo4j")


def ensure_data_dir() -> None:
    """Ensure ``DATA_DIR`` exists before writing pipeline CSVs.

    Side effects: Creates ``data/`` (and parents) if missing.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
