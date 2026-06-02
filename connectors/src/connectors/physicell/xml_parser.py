# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Parse PhysiCell MultiCellDS output XML files.

Extracts cell column labels, microenvironment substrate variables,
and companion .mat file references from output*.xml snapshots.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree


# Labels with size=3 that represent spatial vectors (x, y, z suffixes)
_VECTOR_LABELS = frozenset({
    "position",
    "velocity",
    "orientation",
    "migration_bias_direction",
    "motility_vector",
})


@dataclass
class CellLabel:
    """A single label from the <labels> section."""
    name: str
    index: int
    size: int
    units: str


@dataclass
class SubstrateVariable:
    """A substrate variable from the <microenvironment> section."""
    name: str
    units: str
    id: int


@dataclass
class PhysiCellSnapshot:
    """Metadata extracted from a single output*.xml file."""
    cell_labels: list[CellLabel] = field(default_factory=list)
    cell_mat_filename: str = ""
    substrate_variables: list[SubstrateVariable] = field(default_factory=list)
    microenv_mat_filename: str = ""
    mesh_mat_filename: str = ""
    time: float = 0.0
    time_units: str = "min"


def parse_snapshot_xml(xml_path: str) -> PhysiCellSnapshot:
    """Parse a PhysiCell output*.xml and extract all metadata.

    Args:
        xml_path: Path to the output*.xml file.

    Returns:
        PhysiCellSnapshot with labels, variables, and file references.

    Raises:
        ValueError: If the XML is not a valid MultiCellDS snapshot.
    """
    tree = etree.parse(xml_path)
    root = tree.getroot()

    if root.tag != "MultiCellDS":
        raise ValueError(f"Not a MultiCellDS file: root element is <{root.tag}>")

    snapshot = PhysiCellSnapshot()

    # --- Metadata: time ---
    time_el = root.find(".//metadata/current_time")
    if time_el is not None and time_el.text:
        snapshot.time = float(time_el.text)
        snapshot.time_units = time_el.get("units", "min")

    # --- Microenvironment ---
    mesh_voxels = root.find(".//microenvironment/domain/mesh/voxels/filename")
    if mesh_voxels is not None and mesh_voxels.text:
        snapshot.mesh_mat_filename = mesh_voxels.text.strip()

    for var_el in root.findall(".//microenvironment/domain/variables/variable"):
        snapshot.substrate_variables.append(SubstrateVariable(
            name=var_el.get("name", ""),
            units=var_el.get("units", ""),
            id=int(var_el.get("ID", 0)),
        ))

    microenv_data = root.find(".//microenvironment/domain/data/filename")
    if microenv_data is not None and microenv_data.text:
        snapshot.microenv_mat_filename = microenv_data.text.strip()

    # --- Cellular information: labels + cells .mat ---
    simplified = root.find(".//cellular_information//simplified_data[@source='PhysiCell']")
    if simplified is not None:
        for label_el in simplified.findall("labels/label"):
            snapshot.cell_labels.append(CellLabel(
                name=label_el.text.strip() if label_el.text else "",
                index=int(label_el.get("index", 0)),
                size=int(label_el.get("size", 1)),
                units=label_el.get("units", "none"),
            ))

        cells_file = simplified.find("filename")
        if cells_file is not None and cells_file.text:
            snapshot.cell_mat_filename = cells_file.text.strip()

    return snapshot


def expand_labels_to_columns(labels: list[CellLabel]) -> list[str]:
    """Expand multi-column labels into individual column names.

    Rules:
      - size=1: name as-is
      - size=3 and name is a known vector: name_x, name_y, name_z
      - size=N otherwise: name_0, name_1, ..., name_{N-1}

    Args:
        labels: List of CellLabel from the XML.

    Returns:
        Flat list of column names matching the .mat matrix width.
    """
    columns: list[str] = []
    for label in labels:
        if label.size <= 1:
            columns.append(label.name)
        elif label.size == 3 and label.name in _VECTOR_LABELS:
            columns.extend([f"{label.name}_x", f"{label.name}_y", f"{label.name}_z"])
        else:
            columns.extend([f"{label.name}_{i}" for i in range(label.size)])
    return columns


def extract_time_from_xml(xml_path: str) -> tuple[float | None, str]:
    """Extract current_time and units from a PhysiCell XML.

    Returns (time_value, time_units). Returns (None, "min") if the file
    is not parseable or doesn't contain time metadata.
    """
    try:
        tree = etree.parse(xml_path)
        root = tree.getroot()
        if root.tag != "MultiCellDS":
            return None, "min"
        time_el = root.find(".//metadata/current_time")
        if time_el is not None and time_el.text:
            return float(time_el.text), time_el.get("units", "min")
    except Exception:
        pass
    return None, "min"



def is_physicell_xml(xml_path: str) -> bool:
    """Quick check whether a file is a PhysiCell MultiCellDS XML.

    Reads only the root element — does not parse the full file.
    """
    try:
        for _, el in etree.iterparse(xml_path, events=("start",)):
            return el.tag == "MultiCellDS"
    except Exception:
        return False
    return False
