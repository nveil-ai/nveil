# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Connector registry — simple dict mapping connector IDs to metadata.

The file_service reads this to answer frontend queries about which
connectors can handle a given set of file extensions.
"""

CONNECTOR_REGISTRY = {
    "physicell": {
        "label": "PhysiCell",
        "description": "PhysiCell cell simulation snapshot (MultiCellDS)",
        "accepts": [".xml", ".mat"],
        "required": [".xml", ".mat"],
        "convert": "connectors.physicell.convert",
    },
    "dicom": {
        "label": "DICOM Series",
        "description": "DICOM medical imaging series (CT, MRI)",
        "accepts": [".dcm"],
        "required": [".dcm"],
        "convert": None,
    },
}
