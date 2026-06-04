"""Compute kNN audio-feature similarity edges for the sampled songs.

Reads ``data/sample.csv``, fits a Euclidean kNN over the standardized ``feat_*``
columns, and writes symmetric ``src_track_id, dst_track_id, distance, score``
edges to ``data/similarity.csv`` (score = 1 / (1 + distance)).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors

from src.config import (
    FEATURE_COLS,
    K,
    SAMPLE_CSV,
    SIMILARITY_CSV,
    STANDARDIZED_PREFIX,
    ensure_data_dir,
)

log = logging.getLogger(__name__)


def feature_matrix(df: pd.DataFrame) -> np.ndarray:
    """Stack standardized ``feat_*`` columns into a float32 matrix for kNN.

    Returns: ``(n_songs, len(FEATURE_COLS))`` numpy array.
    Raises: ``RuntimeError`` if any expected ``feat_*`` column is missing.
    """
    cols = [f"{STANDARDIZED_PREFIX}{c}" for c in FEATURE_COLS]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise RuntimeError(f"Standardized columns missing from sample: {missing}")
    return df[cols].to_numpy(dtype=np.float32)


def knn_edges(df: pd.DataFrame, k: int) -> pd.DataFrame:
    """Build symmetric kNN ``SIMILAR_TO`` edges with Euclidean distance and score.

    Returns: DataFrame with columns ``src_track_id``, ``dst_track_id``,
    ``distance``, ``score`` (score = 1 / (1 + distance)); one row per directed edge.
    Raises: ``RuntimeError`` if ``len(df) <= k``.
    """
    if len(df) <= k:
        raise RuntimeError(f"Sample size {len(df)} must exceed k={k}.")

    x = feature_matrix(df)
    nn = NearestNeighbors(n_neighbors=k + 1, metric="euclidean").fit(x)
    distances, indices = nn.kneighbors(x)

    ids = df["track_id"].to_numpy()
    src_idx = np.repeat(np.arange(len(df)), k)
    dst_idx = indices[:, 1:].ravel()
    dist = distances[:, 1:].ravel().astype(np.float32)
    src_ids = ids[src_idx]
    dst_ids = ids[dst_idx]

    # Canonicalize each unordered pair (low_id, high_id) so we can dedupe.
    low = np.where(src_ids < dst_ids, src_ids, dst_ids)
    high = np.where(src_ids < dst_ids, dst_ids, src_ids)
    canon = pd.DataFrame({"low": low, "high": high, "distance": dist})
    canon = canon[canon["low"] != canon["high"]]
    canon = canon.sort_values("distance").drop_duplicates(subset=["low", "high"], keep="first")

    forward = pd.DataFrame(
        {
            "src_track_id": canon["low"].to_numpy(),
            "dst_track_id": canon["high"].to_numpy(),
            "distance": canon["distance"].to_numpy(),
        }
    )
    backward = pd.DataFrame(
        {
            "src_track_id": canon["high"].to_numpy(),
            "dst_track_id": canon["low"].to_numpy(),
            "distance": canon["distance"].to_numpy(),
        }
    )
    sym = pd.concat([forward, backward], ignore_index=True)
    sym = sym.drop_duplicates(subset=["src_track_id", "dst_track_id"], keep="first")
    sym["score"] = (1.0 / (1.0 + sym["distance"].to_numpy())).astype(np.float32)
    return sym.reset_index(drop=True)


def build_similarity() -> pd.DataFrame:
    """Read ``data/sample.csv``, compute kNN edges, and write similarity CSV.

    Returns: Edge DataFrame written to disk.
    Side effects: Writes ``data/similarity.csv``.
    """
    df = pd.read_csv(SAMPLE_CSV)
    edges = knn_edges(df, K)
    ensure_data_dir()
    edges.to_csv(SIMILARITY_CSV, index=False)
    avg_degree = (2.0 * len(edges)) / max(1, len(df))
    log.info(
        "wrote %s (%s edges, ~avg degree %.2f, k=%s, distance min/mean/max=%.4f/%.4f/%.4f)",
        SIMILARITY_CSV,
        len(edges),
        avg_degree / 2,
        K,
        float(edges["distance"].min()),
        float(edges["distance"].mean()),
        float(edges["distance"].max()),
    )
    return edges


def main() -> None:
    """CLI entry point: configure logging and run ``build_similarity()``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    build_similarity()


if __name__ == "__main__":
    main()
