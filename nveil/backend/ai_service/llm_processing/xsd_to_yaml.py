# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Converts XSD schema content to a compact YAML representation for LLM prompts.

Uses xmlschema for structural introspection — types, attributes, enums,
inheritance, and xs:documentation annotations are all auto-discovered.
Any new types, attributes, or enums added to the XSD are automatically picked up.
"""

import re
from collections import OrderedDict

import xmlschema
import yaml


class _OrderedDumper(yaml.SafeDumper):
    """YAML dumper that serializes OrderedDict as plain mappings (preserving order)."""
    pass


_OrderedDumper.add_representer(
    OrderedDict,
    lambda dumper, data: dumper.represent_mapping("tag:yaml.org,2002:map", data.items()),
)


def convert_xsd_to_yaml(xsd_content: str) -> str:
    """Convert an XSD schema string to a compact YAML representation.

    Args:
        xsd_content: Raw XSD XML string.

    Returns:
        YAML string preserving all structural info (types, attributes, enums,
        inheritance, annotations).
    """
    schema = xmlschema.XMLSchema(xsd_content)
    result = OrderedDict()

    # Root elements
    root_elements = OrderedDict()
    for name, elem in schema.elements.items():
        entry = OrderedDict()
        type_name = elem.type.name if elem.type.name else None
        if type_name:
            entry["type"] = type_name
        base = getattr(elem.type, "base_type", None)
        if base and base.name and not base.name.startswith("{"):
            entry["extends"] = base.name
        if hasattr(elem.type, "attributes") and elem.type.attributes:
            attrs = _collect_attributes(elem.type, base)
            if attrs:
                entry["attributes"] = attrs
        # Inline children from the base type so the LLM sees them
        # as direct children of this root element (XSD extension semantics).
        children = _collect_children(elem.type)
        if not children and base:
            children = _collect_children(base)
        if children:
            entry["children"] = children
        root_elements[name] = entry
    if root_elements:
        result["root_elements"] = root_elements

    # Walk all named types
    for type_name, xsd_type in schema.types.items():
        if type_name.startswith("{"):
            continue  # skip built-in xs: types

        entry = _process_type(xsd_type, type_name)
        if entry:
            result[type_name] = entry

    return yaml.dump(
        result,
        Dumper=_OrderedDumper,
        default_flow_style=None,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )


def _process_type(xsd_type, type_name: str) -> OrderedDict | None:
    """Process a single XSD type into a compact dict representation."""
    entry = OrderedDict()

    # Union types (e.g. UndesiredableInteger)
    if hasattr(xsd_type, "is_union") and xsd_type.is_union():
        members = []
        for mt in xsd_type.member_types:
            if hasattr(mt, "enumeration") and mt.enumeration:
                members.extend(mt.enumeration)
            elif hasattr(mt, "base_type") and mt.base_type:
                base_name = _short_type_name(mt.base_type.name)
                members.append(base_name)
        entry["union"] = members
        return entry

    # Simple types with enumeration
    if hasattr(xsd_type, "enumeration") and xsd_type.enumeration:
        annotation_text = _get_annotation_text(xsd_type)
        if annotation_text:
            entry["doc"] = annotation_text
        entry["enum"] = list(xsd_type.enumeration)
        return entry

    # Complex types
    if hasattr(xsd_type, "attributes"):
        base = getattr(xsd_type, "base_type", None)
        if base and base.name and not base.name.startswith("{"):
            entry["extends"] = base.name

        # Annotation (documentation from xs:annotation)
        annotation_text = _get_annotation_text(xsd_type)
        if annotation_text:
            entry["doc"] = annotation_text

        # Attributes (only locally added for extended types)
        attrs = _collect_attributes(xsd_type, base)
        if attrs:
            entry["attributes"] = attrs

        # Child elements
        children = _collect_children(xsd_type)
        if children:
            entry["children"] = children

        # Appinfo (function metadata for TransformGraph)
        appinfo = _get_appinfo(xsd_type)
        if appinfo:
            entry.update(appinfo)

        if entry:
            return entry

    return None


def _collect_attributes(xsd_type, base_type) -> OrderedDict:
    """Collect attributes, only the delta from base_type if extended."""
    base_attr_names = set()
    if base_type and hasattr(base_type, "attributes"):
        base_attr_names = set(base_type.attributes.keys())

    attrs = OrderedDict()
    for attr_name, attr in xsd_type.attributes.items():
        if attr_name in base_attr_names:
            continue  # inherited, skip
        info = OrderedDict()
        if attr.type:
            info["type"] = _short_type_name(attr.type.name)
        if attr.use == "required":
            info["required"] = True
        if attr.default is not None:
            info["default"] = attr.default
        attrs[attr_name] = info
    return attrs


def _collect_children(xsd_type) -> list | dict | None:
    """Collect child elements from a complex type's content model."""
    content = getattr(xsd_type, "content", None)
    if content is None:
        return None

    model = getattr(content, "model", "sequence")
    children = []

    try:
        elements = list(content)
    except TypeError:
        return None

    if not elements:
        return None

    for child in elements:
        child_name = getattr(child, "name", None)
        if not child_name:
            continue
        child_type = child.type.name if child.type and child.type.name else None
        min_occ = getattr(child, "min_occurs", 1)
        max_occ = getattr(child, "max_occurs", 1)

        if child_type:
            child_type = _short_type_name(child_type)

        info = OrderedDict()
        if child_type:
            info["type"] = child_type
        if min_occ == 0:
            info["optional"] = True
        if max_occ is None or (isinstance(max_occ, int) and max_occ > 1):
            info["multiple"] = True

        if len(info) == 1 and "type" in info:
            children.append({child_name: child_type})
        elif info:
            children.append({child_name: dict(info)})
        else:
            children.append(child_name)

    if not children:
        return None

    if model == "choice":
        return OrderedDict([
            ("choice", children),
            ("min", content.min_occurs),
            ("max", "unbounded" if content.max_occurs is None else content.max_occurs),
        ])

    # For sequences with multiple elements, make ordering explicit so the LLM
    # knows the XSD enforces this exact element order.
    if len(children) > 1:
        return OrderedDict([
            ("sequence (order matters for XSD validity)", children),
        ])

    return children


def _short_type_name(name: str) -> str:
    """Strip XML Schema namespace prefix from type names."""
    if name and name.startswith("{http://www.w3.org/2001/XMLSchema}"):
        return name.split("}")[-1]
    return name


def _get_annotation_text(xsd_type) -> str | None:
    """Extract xs:documentation text from a type's annotation."""
    ann = getattr(xsd_type, "annotation", None)
    if ann is None:
        return None
    text = str(ann).strip() if ann else None
    if text:
        text = re.sub(r"\s+", " ", text).strip()
        return text if text else None
    return None


def _get_appinfo(xsd_type) -> dict | None:
    """Extract xs:appinfo function metadata (for TransformGraph)."""
    ann = getattr(xsd_type, "annotation", None)
    if ann is None or not hasattr(ann, "appinfo") or not ann.appinfo:
        return None
    result = {}
    for appinfo_elem in ann.appinfo:
        for child in appinfo_elem:
            if child.tag == "function" or child.tag.endswith("}function"):
                fn_name = child.get("name")
                fn_group = child.get("group")
                if fn_name:
                    result["function"] = fn_name
                if fn_group:
                    result["group"] = fn_group
    return result if result else None
