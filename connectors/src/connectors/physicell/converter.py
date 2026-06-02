# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Convert PhysiCell .mat + XML snapshot to CSVs.

Ported from an R script using xml2 + R.matlab. Uses scipy.io.loadmat
for MATLAB v4/v5 binary files and lxml for MultiCellDS XML parsing.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.io as sio

from .xml_parser import (
    expand_labels_to_columns,
    is_physicell_xml,
    parse_snapshot_xml,
)

logger = logging.getLogger(__name__)


def convert(xml_path: str, output_dir: str) -> list[str]:
    """Convert a PhysiCell snapshot to CSV files.

    Produces up to two CSVs:
      - ``{stem}_cells.csv`` — one row per cell, columns from XML labels
      - ``{stem}_microenvironment.csv`` — one row per voxel, columns:
        x, y, z, volume, then one per substrate

    Args:
        xml_path: Absolute path to the PhysiCell ``output*.xml`` file.
        output_dir: Directory where CSVs will be written.

    Returns:
        List of absolute paths to the generated CSV files.
    """
    snapshot = parse_snapshot_xml(xml_path)
    xml_dir = os.path.dirname(xml_path)
    stem = Path(xml_path).stem
    output_paths: list[str] = []

    # --- Cells ---
    if snapshot.cell_mat_filename:
        cells_mat_path = os.path.join(xml_dir, snapshot.cell_mat_filename)
        if os.path.isfile(cells_mat_path):
            cells_csv = _convert_cells(
                cells_mat_path, snapshot, stem, output_dir
            )
            if cells_csv:
                output_paths.append(cells_csv)
        else:
            logger.warning("Cells .mat not found: %s", cells_mat_path)

    # --- Microenvironment ---
    if snapshot.microenv_mat_filename:
        env_mat_path = os.path.join(xml_dir, snapshot.microenv_mat_filename)
        if os.path.isfile(env_mat_path):
            env_csv = _convert_microenvironment(
                env_mat_path, snapshot, stem, output_dir
            )
            if env_csv:
                output_paths.append(env_csv)
        else:
            logger.warning("Microenvironment .mat not found: %s", env_mat_path)

    return output_paths


def detect(filenames: list[str]) -> bool:
    """Check if a set of filenames looks like a PhysiCell snapshot.

    Returns True if there is at least one ``.xml`` and one ``_cells.mat``.
    """
    has_xml = any(f.lower().endswith(".xml") for f in filenames)
    has_cells_mat = any("_cells.mat" in f.lower() for f in filenames)
    return has_xml and has_cells_mat


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_mat_matrix(mat_path: str) -> np.ndarray | None:
    """Load the first non-metadata variable from a .mat file.

    PhysiCell .mat files contain a single data variable (e.g. ``cells``
    or ``multiscale_microenvironment``). This function finds it by
    skipping keys that start with ``__``.
    """
    raw = sio.loadmat(mat_path)
    for key, value in raw.items():
        if not key.startswith("__"):
            return np.asarray(value)
    return None


def _convert_cells(
    mat_path: str,
    snapshot,
    stem: str,
    output_dir: str,
) -> str | None:
    """Convert cells .mat to CSV with column names from XML labels."""
    matrix = _load_mat_matrix(mat_path)
    if matrix is None:
        logger.error("No data variable found in %s", mat_path)
        return None

    # PhysiCell stores as [features × cells] — transpose to [cells × features]
    df = pd.DataFrame(matrix.T)

    # Apply column names from XML labels
    col_names = expand_labels_to_columns(snapshot.cell_labels)
    if df.shape[1] == len(col_names):
        df.columns = col_names
    else:
        logger.warning(
            "Column count mismatch: data has %d cols, XML defines %d labels. "
            "Using generic names.",
            df.shape[1],
            len(col_names),
        )

    csv_path = os.path.join(output_dir, f"{stem}_cells.csv")
    df.to_csv(csv_path, index=False)
    logger.info("Saved cells CSV: %s (%d rows, %d cols)", csv_path, len(df), df.shape[1])
    return csv_path


def _convert_microenvironment(
    mat_path: str,
    snapshot,
    stem: str,
    output_dir: str,
) -> str | None:
    """Convert microenvironment .mat to CSV with spatial + substrate columns."""
    matrix = _load_mat_matrix(mat_path)
    if matrix is None:
        logger.error("No data variable found in %s", mat_path)
        return None

    # PhysiCell stores as [features × voxels] — transpose to [voxels × features]
    df = pd.DataFrame(matrix.T)

    # Standard columns: x, y, z, volume, then one per substrate
    env_cols = ["x", "y", "z", "volume"]
    substrate_names = [v.name for v in snapshot.substrate_variables]
    env_cols.extend(substrate_names)

    if df.shape[1] >= len(env_cols):
        col_names = list(env_cols)
        # Name any extra columns generically
        for i in range(len(env_cols), df.shape[1]):
            col_names.append(f"extra_{i - len(env_cols) + 1}")
        df.columns = col_names
    else:
        logger.warning(
            "Microenvironment has fewer columns (%d) than expected (%d). "
            "Assigning partial names.",
            df.shape[1],
            len(env_cols),
        )
        df.columns = env_cols[: df.shape[1]]

    csv_path = os.path.join(output_dir, f"{stem}_microenvironment.csv")
    df.to_csv(csv_path, index=False)
    logger.info("Saved microenvironment CSV: %s (%d rows, %d cols)", csv_path, len(df), df.shape[1])
    return csv_path
