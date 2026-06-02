# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the XSD-to-YAML converter used in LLM prompts."""

import os
import re
from pathlib import Path

import pytest

from llm_processing.xsd_to_yaml import convert_xsd_to_yaml


def _find_xsd(relative_path: str) -> Path:
    """Resolve XSD path in both local dev and Docker container layouts."""
    # Try relative to repo root (local dev: unit -> tests -> ai_service -> backend -> nveil -> app)
    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
    local = repo_root / relative_path
    if local.exists():
        return local
    # Docker container: dive/ mounted at /dive, choregraph/ at /choregraph
    container = Path("/") / relative_path
    if container.exists():
        return container
    # Devcontainer layout
    devcontainer = Path("/workspaces/app") / relative_path
    if devcontainer.exists():
        return devcontainer
    raise FileNotFoundError(
        f"Cannot find {relative_path} in any known layout "
        f"(tried {local}, {container}, {devcontainer})"
    )


VISUSPEC_PATH = _find_xsd("dive/src/dive/VisuSpec.xsd")
TRANSFORMGRAPH_PATH = _find_xsd("choregraph/src/choregraph/TransformGraph.xsd")


@pytest.fixture(scope="module")
def visuspec_xsd():
    return VISUSPEC_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def transformgraph_xsd():
    return TRANSFORMGRAPH_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def visuspec_yaml(visuspec_xsd):
    return convert_xsd_to_yaml(visuspec_xsd)


@pytest.fixture(scope="module")
def transformgraph_yaml(transformgraph_xsd):
    return convert_xsd_to_yaml(transformgraph_xsd)


# ─── VisuSpec type names ────────────────────────────────────────────────

VISUSPEC_TYPES = [
    "spec", "spec_ai", "UndesiredableInteger", "CoordinatesType",
    "Mark", "PointMark", "BarMark", "LineMark", "UniGridMark", "Contour",
    "Surface", "Histogram", "BoxViolin", "Sector", "Choropleth", "Node",
    "Channel", "NumericChannel", "ColorChannel", "ShapeChannel",
    "ColorPalette", "ColorPaletteName", "ColorPaletteCategory",
    "Marks", "Channels", "Space", "Legend", "ReferenceLine",
]


@pytest.mark.parametrize("type_name", VISUSPEC_TYPES)
def test_visuspec_type_present(visuspec_yaml, type_name):
    assert re.search(rf"^{type_name}:", visuspec_yaml, re.MULTILINE), \
        f"Type '{type_name}' not found in YAML output"


# ─── VisuSpec enum values ───────────────────────────────────────────────

VISUSPEC_ENUMS = {
    "CoordinatesType": ["CARTESIAN", "POLAR", "GEO"],
    "ColorPaletteCategory": ["QUALITATIVE", "SEQUENTIAL", "DIVERGING"],
    "ScaleType": ["LINEAR", "LOGARITHMIC", "EXPONENTIAL"],
    "Shape": ["POINT", "CUSTOM"],
    "ReferenceLineStyle": ["DOTTED", "DASHED", "SOLID"],
    "interpolation": ["NONE", "GAUSSIAN", "SHEPARD"],
}


@pytest.mark.parametrize("type_name,values", VISUSPEC_ENUMS.items())
def test_visuspec_enums_preserved(visuspec_yaml, type_name, values):
    for val in values:
        assert val in visuspec_yaml, f"Enum value '{val}' for {type_name} not found"


# ─── VisuSpec inheritance ───────────────────────────────────────────────

VISUSPEC_INHERITANCE = {
    "BarMark": "Mark",
    "PointMark": "Mark",
    "LineMark": "Mark",
    "Histogram": "Mark",
    "Sector": "Mark",
    "Choropleth": "Mark",
    "Node": "PointMark",
    "ColorChannel": "Channel",
    "ShapeChannel": "Channel",
    "NumericChannel": "Channel",
    "RawData": "Data",
    "TransformedData": "Data",
}


@pytest.mark.parametrize("child,parent", VISUSPEC_INHERITANCE.items())
def test_visuspec_inheritance(visuspec_yaml, child, parent):
    # Check that child has "extends: parent"
    pattern = rf"^{child}:.*?extends:\s*{parent}"
    assert re.search(pattern, visuspec_yaml, re.MULTILINE | re.DOTALL), \
        f"Expected {child} extends {parent}"


# ─── VisuSpec union types ───────────────────────────────────────────────

def test_visuspec_union_undesirableinteger(visuspec_yaml):
    assert "union:" in visuspec_yaml
    assert "positiveInteger" in visuspec_yaml
    assert "HANDLED_BY_MODE" in visuspec_yaml
    assert "UNDESIRED" in visuspec_yaml


# ─── VisuSpec xs:documentation annotations ─────────────────────────────

VISUSPEC_DOC_KEYWORDS = [
    "colorblind",
    "Pie chart",
    "Sector mark",
    "HEATMAP",
    "Careful",
    "geographic",
]


@pytest.mark.parametrize("keyword", VISUSPEC_DOC_KEYWORDS)
def test_visuspec_docs_preserved(visuspec_yaml, keyword):
    assert keyword.lower() in visuspec_yaml.lower(), \
        f"Documentation keyword '{keyword}' not found in YAML output"


# Types that must have a doc: field from xs:documentation
VISUSPEC_ANNOTATED_TYPES = [
    "CoordinatesType", "ColorPaletteName", "Channel", "Mark",
    "Node", "LineMark", "UniGridMark", "Contour", "Surface",
    "BarMark", "Sector", "Choropleth", "Marks", "ReferenceLineAxis",
    "ReferenceLine", "File",
]


@pytest.mark.parametrize("type_name", VISUSPEC_ANNOTATED_TYPES)
def test_visuspec_type_has_doc(visuspec_yaml, type_name):
    pattern = rf"^{type_name}:.*?doc:\s*\S"
    assert re.search(pattern, visuspec_yaml, re.MULTILINE | re.DOTALL), \
        f"Type '{type_name}' should have a doc: field from xs:documentation"


# ─── TransformGraph type names ──────────────────────────────────────────

TRANSFORMGRAPH_TYPES = [
    "PortType", "TransformFunction", "JoinHow",
    "InputsType", "PipelineType", "InputPortElement", "OutputPortElement",
    "Melt", "ArithmeticOp", "ExtractDatePart", "RollingStatistics",
    "LagLead", "OffsetDatetime", "ForecastTimeSeries",
    "NormalizeColumn", "Discretize", "FlattenJson",
    "GeoScope", "GeocodeLocation", "GetCountryContours",
    "NlpBinarizeLabelsAuto", "NlpBinarizeLabelsHinted",
    "HierarchicalRollup", "ImageColorFormat", "ImageToDataframe",
    "ExtractChannel", "ImageMetadata", "ConcatPartitions",
]


@pytest.mark.parametrize("type_name", TRANSFORMGRAPH_TYPES)
def test_transformgraph_type_present(transformgraph_yaml, type_name):
    assert re.search(rf"^{type_name}:", transformgraph_yaml, re.MULTILINE), \
        f"Type '{type_name}' not found in YAML output"


# ─── TransformGraph function metadata ───────────────────────────────────

TRANSFORMGRAPH_FUNCTIONS = [
    "melt", "arithmetic_op", "discretize", "geocode_location",
    "nlp_binarize_labels_auto", "extract_date_part", "execute_code",
]


@pytest.mark.parametrize("fn_name", TRANSFORMGRAPH_FUNCTIONS)
def test_transformgraph_function_names(transformgraph_yaml, fn_name):
    assert fn_name in transformgraph_yaml, \
        f"Function name '{fn_name}' not found"


# ─── TransformGraph annotations ─────────────────────────────────────────

def test_transformgraph_annotations(transformgraph_yaml):
    # Discretize should have its doc string
    assert "discretize" in transformgraph_yaml.lower() or "bin" in transformgraph_yaml.lower()
    # GeocodeLocation should mention geocod
    assert "geocod" in transformgraph_yaml.lower() or "location" in transformgraph_yaml.lower()


# ─── Compression ratio ─────────────────────────────────────────────────

def test_visuspec_compression_ratio(visuspec_xsd, visuspec_yaml):
    ratio = len(visuspec_yaml) / len(visuspec_xsd)
    assert ratio < 0.55, f"VisuSpec compression ratio {ratio:.2f} > 0.55 (expected at least 45% reduction)"


def test_transformgraph_compression_ratio(transformgraph_xsd, transformgraph_yaml):
    ratio = len(transformgraph_yaml) / len(transformgraph_xsd)
    assert ratio < 0.55, f"TransformGraph compression ratio {ratio:.2f} > 0.55 (expected at least 45% reduction)"


# ─── Marks choice group ────────────────────────────────────────────────

def test_visuspec_marks_choice(visuspec_yaml):
    assert "choice:" in visuspec_yaml
    assert "unbounded" in visuspec_yaml


# ─── Root elements ──────────────────────────────────────────────────────

def test_visuspec_root_elements(visuspec_yaml):
    assert "visuSpecAI:" in visuspec_yaml
    assert "visuSpec:" in visuspec_yaml


def test_transformgraph_root_element(transformgraph_yaml):
    assert "choregraph:" in transformgraph_yaml
