"""Stratified-by-genre sample of spotify.csv with forced inclusion of the
liked artists, plus z-score standardization of audio features.

Outputs ``data/sample.csv`` containing the raw audio features plus standardized
``feat_*`` columns used downstream by the kNN similarity step.
"""

from __future__ import annotations

import logging
import math
import re

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from src.config import (
    FEATURE_COLS,
    LIKED_ARTISTS,
    RAW_CSV,
    SAMPLE_CSV,
    SAMPLE_SIZE,
    SEED,
    STANDARDIZED_PREFIX,
    ensure_data_dir,
)

log = logging.getLogger(__name__)


def _liked_mask(df: pd.DataFrame) -> pd.Series:
    """True for rows whose ``artists`` field contains a ``LIKED_ARTISTS`` name.

    Returns: Boolean Series aligned with ``df`` index.
    """
    pattern = "|".join(re.escape(a) for a in LIKED_ARTISTS)
    return df["artists"].fillna("").str.contains(pattern, case=False, regex=True)


def load_raw() -> pd.DataFrame:
    """Load ``spotify.csv`` and drop rows with missing features or identifiers.

    Returns: Cleaned DataFrame (all ``FEATURE_COLS`` and key columns present).
    """
    df = pd.read_csv(RAW_CSV, index_col=0)
    before = len(df)
    df = df.dropna(subset=list(FEATURE_COLS) + ["track_id", "artists", "track_name"])
    log.info("loaded %s rows from %s (dropped %s with NaN)", len(df), RAW_CSV.name, before - len(df))
    return df


def stratified_sample(df: pd.DataFrame, sample_size: int, seed: int) -> pd.DataFrame:
    """Draw an equal per-genre random sample totaling about ``sample_size`` rows.

    Returns: Concatenated sample (may exceed ``sample_size`` before dedupe).
    """
    genres = df["track_genre"].dropna().unique()
    per_genre = max(1, math.ceil(sample_size / len(genres)))
    parts = []
    for genre, group in df.groupby("track_genre", sort=False):
        take = min(per_genre, len(group))
        parts.append(group.sample(n=take, random_state=seed))
    out = pd.concat(parts, ignore_index=True)
    log.info(
        "stratified sample: %s rows across %s genres (~%s/genre)",
        len(out),
        len(genres),
        per_genre,
    )
    return out


def force_include_liked(df: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """Append every Strokes/Spektor row from ``raw`` so seeds are never dropped.

    Returns: ``df`` concatenated with all liked-artist rows from ``raw``.
    Raises: ``RuntimeError`` if no liked-artist rows exist in ``raw``.
    """
    liked = raw[_liked_mask(raw)]
    if liked.empty:
        raise RuntimeError(
            "No liked-artist rows found in the raw CSV; cannot seed recommendations."
        )
    log.info(
        "force-including %s liked-artist rows (target artists=%s)",
        len(liked),
        list(LIKED_ARTISTS),
    )
    return pd.concat([df, liked], ignore_index=True)


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """Keep one row per ``(track_name, artists)`` pair.

    Returns: De-duplicated DataFrame (first occurrence kept).
    """
    before = len(df)
    out = df.drop_duplicates(subset=["track_name", "artists"], keep="first").reset_index(drop=True)
    log.info("deduped %s -> %s rows", before, len(out))
    return out


def standardize_features(df: pd.DataFrame) -> pd.DataFrame:
    """Z-score ``FEATURE_COLS`` in-place and add ``feat_<col>`` columns.

    Returns: Same ``df`` with standardized feature columns attached.
    """
    scaler = StandardScaler()
    arr = scaler.fit_transform(df[list(FEATURE_COLS)].astype(float).to_numpy())
    for i, col in enumerate(FEATURE_COLS):
        df[f"{STANDARDIZED_PREFIX}{col}"] = arr[:, i].astype(np.float32)
    return df


def assert_liked_present(df: pd.DataFrame) -> None:
    """Verify every ``LIKED_ARTISTS`` name appears in the sample.

    Raises: ``AssertionError`` if any liked artist is missing.
    """
    artists_lower = df["artists"].fillna("").str.lower()
    missing = [a for a in LIKED_ARTISTS if not artists_lower.str.contains(a.lower()).any()]
    if missing:
        raise AssertionError(f"Sample is missing liked artists: {missing}")


def build_sample() -> pd.DataFrame:
    """Run stratified sampling, force-include seeds, standardize, and write CSV.

    Returns: Final sample DataFrame.
    Side effects: Writes ``data/sample.csv``.
    """
    raw = load_raw()
    sample = stratified_sample(raw, SAMPLE_SIZE, SEED)
    sample = force_include_liked(sample, raw)
    sample = dedupe(sample)
    sample = standardize_features(sample)
    assert_liked_present(sample)

    ensure_data_dir()
    sample.to_csv(SAMPLE_CSV, index=False)

    strokes = int(sample["artists"].str.contains("The Strokes", case=False, na=False).sum())
    spektor = int(sample["artists"].str.contains("Regina Spektor", case=False, na=False).sum())
    log.info(
        "wrote %s (%s rows, %s genres, Strokes=%s, Spektor=%s)",
        SAMPLE_CSV,
        len(sample),
        sample["track_genre"].nunique(),
        strokes,
        spektor,
    )
    return sample


def main() -> None:
    """CLI entry point: configure logging and run ``build_sample()``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    build_sample()


if __name__ == "__main__":
    main()
