# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import posixpath
from lxml import etree
from pathlib import Path

import requests
from shared.secrets import get_secret
from viz_file_utils.characterization import analyse_csv
from logger import ERROR, INFO, logger

LOCAL = get_secret("LOCAL")

SERVER_HOST = "server"
if LOCAL == "1":
    SERVER_HOST = "localhost"


class XMLFileBuilder:
    def __init__(self, location):
        # Ensure location is a Path and resolved
        self.location = str(Path(location).resolve())
        self.xml_filepath = str(Path(self.location) / "specifications.xml")

    def xml_file_exists(self):
        """
        Check if the specifications.xml file exists at the specified location.
        Returns True if it exists, False otherwise.
        """
        return os.path.isfile(self.xml_filepath)

    def create_choregraph_file(self, file_paths):
        """Create a new XML choregraph file using the Choregraph library."""
        try:
            from choregraph import Choregraph
        except ImportError:
            logger().logp(ERROR, "Choregraph library not found. Cannot create choregraph file.")
            return

        # Initialize empty Choregraph with workspace_path = self.location (UserFile directory)
        # Note: self.location is the UserFile directory, NOT its parent
        cg = Choregraph(workspace_path=self.location)
        
        # Reset spec to clear any auto-loaded choregraph.xml from previous runs
        cg.reset_spec()
        
        # Collect all Excel filenames for file context (helps Cartographer LLM)
        excel_filenames = [
            Path(p).stem for p in file_paths
            if p and Path(p).suffix.lower() in ('.xlsx', '.xls', '.ods', '.xlsm')
        ]
        file_context = "\n".join(f"- {name}" for name in excel_filenames) if len(excel_filenames) > 1 else ""

        index_data = 1
        logger().debug("file_paths:", file_paths)
        for datafile_path in file_paths:
            if datafile_path is None:
                continue
            
            # Ensure path is string
            datafile_path_str = str(datafile_path)
            _, ext = os.path.splitext(datafile_path_str)
            fmt = ext.split(".")[-1].upper()
            options = {}
            
            if ext == ".csv":
                csv_characterization = analyse_csv(datafile_path_str)
                logger().logp(
                    INFO,
                    f'Characterization of "{posixpath.basename(datafile_path_str)}": {csv_characterization}',
                )
                fmt = "CSV"
                if csv_characterization:
                    options = {
                        "header": str(csv_characterization["header"]),
                        "fieldSeparator": str(csv_characterization["fieldSeparator"]),
                        "skipLines": str(csv_characterization["skipLines"]),
                    }
                else:
                    options = {
                        "header": "True",
                        "fieldSeparator": ",",
                        "skipLines": "0",
                    }
            elif ext == ".json":
                fmt = "JSON"
            if ext == ".xlsx" or ext == ".xls" or ext == ".ods" or ext == ".xlsm":
                # Add XLSX input
                input_id = index_data
                cg.add_input(
                    id=input_id,
                    location=datafile_path_str,
                    format="XLSX",
                    visibility=False,
                    **options
                )
                index_data += 1

                # Automatically add tidy_excel_data node
                try:
                    from choregraph.parser import InputPortSpec, OutputPortSpec
                    node_id = index_data
                    index_data += 1
                    out_id = index_data
                    index_data += 1

                    cg.add_node(
                        id=node_id,
                        type="tidy_excel_data",
                        input_ports=[
                            InputPortSpec(name="path_excel", value=datafile_path_str),
                            InputPortSpec(name="file_context", value=file_context),
                        ],
                        output_ports=[OutputPortSpec(id=out_id, name="result", label="", type="DICT", visibility=True)],
                        label=f"Excel Tidy Data {Path(datafile_path_str).stem}"
                    )

                except Exception as e:
                    logger().logp(ERROR, f"Failed to add tidy_excel_data node: {e}")

            else:
                # JSON inputs must be visibility=False: raw dict/list can't be
                # sent to DIVE. The AI will add flatten_json with a visible output.
                # CSV/other tabular formats can be visible immediately.
                is_json = (ext == ".json" or fmt == "JSON")
                cg.add_input(
                    id=str(index_data),
                    location=datafile_path_str,
                    format=fmt,
                    visibility=False if is_json else True,
                    **options
                )
                index_data += 1

        # Export to XML
        cg.export_to_xml(str(Path(self.location) / "choregraph.xml"))
        # Clean up the temporary Choregraph instance (stops any viz server that may have started)
        cg.close()


    def create_choregraph_file_from_urls(self, url_sources):
        """Create a choregraph XML file from URL data sources.

        Each entry in url_sources is a dict: {"url": "...", "label": "...", "format": "CSV"}
        Downloads each URL to the workspace, analyses CSVs, and builds choregraph.xml.
        """
        try:
            from choregraph import Choregraph
            from choregraph.fetcher import fetch_url
        except ImportError:
            logger().logp(ERROR, "Choregraph library not found. Cannot create choregraph file from URLs.")
            return []

        cg = Choregraph(workspace_path=self.location)
        cg.reset_spec()

        index_data = 1
        downloaded_files = []

        for source in url_sources:
            url = source.get("url")
            label = source.get("label") or None
            fmt = (source.get("format") or "").upper()

            if not url:
                continue

            try:
                from pathlib import Path as _Path
                dest_path, detected_fmt = fetch_url(url, _Path(self.location))
                # Use detected format if not explicitly specified or "AUTO"
                if not fmt or fmt == "AUTO":
                    fmt = detected_fmt

                datafile_path_str = str(dest_path)
                downloaded_files.append(datafile_path_str)
                options = {}

                if fmt == "CSV":
                    csv_characterization = analyse_csv(datafile_path_str)
                    logger().logp(
                        INFO,
                        f'URL CSV characterization "{label or url}": {csv_characterization}',
                    )
                    if csv_characterization:
                        options = {
                            "header": str(csv_characterization["header"]),
                            "fieldSeparator": str(csv_characterization["fieldSeparator"]),
                            "skipLines": str(csv_characterization["skipLines"]),
                        }
                    else:
                        options = {
                            "header": "True",
                            "fieldSeparator": ",",
                            "skipLines": "0",
                        }
                if not label:
                    label = dest_path.stem

                is_json = (fmt == "JSON")
                cg.add_input(
                    id=str(index_data),
                    location=datafile_path_str,
                    format=fmt,
                    label=label,
                    visibility=False if is_json else True,
                    url=url,
                    **options,
                )
                index_data += 1

            except Exception as e:
                logger().logp(ERROR, f"Failed to fetch URL source '{url}': {e}")

        cg.export_to_xml(str(Path(self.location) / "choregraph.xml"))
        cg.close()
        return downloaded_files

    def create_xml_file(self, file_paths):
        """Create a new XML specification file with default structure."""
        root = etree.Element("visuSpec", name="UserFile")
        coordinates = etree.SubElement(root, "coordinates")
        coordinates.text = "UNDEFINED"
        datas = etree.SubElement(root, "datas")


        color_palettes = etree.SubElement(root, "colorPalettes")
        etree.SubElement(color_palettes, "colorPalette", id="1", name="UNDEFINED")

        shape_palettes = etree.SubElement(root, "shapePalettes")
        shape_palette = etree.SubElement(shape_palettes, "shapePalette", id="1")
        etree.SubElement(shape_palette, "shape").text = "POINT"

        channels = etree.SubElement(root, "channels")
        etree.SubElement(channels, "undefinedChannels")
        etree.SubElement(channels, "numericChannels")
        etree.SubElement(channels, "colorChannels")
        etree.SubElement(channels, "shapeChannels")

        etree.SubElement(root, "marks")

        space = etree.SubElement(
            root,
            "space",
            xSpatialScaling="-1",
            ySpatialScaling="-1",
            zSpatialScaling="-1",
            sizeSpatialScaling="-1",
        )

        # Format the XML with indentation
        self.indent(root)

        tree = etree.ElementTree(root)
        tree.write(self.xml_filepath, encoding="utf-8", xml_declaration=True)

    def complete_xml_file_from_ai(self, file_path, xml_content):
        """
        Complete XML file by merging AI-generated content with original data.
        - Keep only the <datas> element from the original XML
        - Integrate AI-generated content after <datas>
        """
        # Parse the original XML file
        tree_orig = etree.parse(file_path)
        root_orig = tree_orig.getroot()
        datas_elem = root_orig.find("datas")
        if datas_elem is None:
            raise ValueError("No <datas> element found in the original XML.")

        # Clean AI-generated XML content
        # TODO: Better handling of HANDLED_BY_MODE
        xml_content = (
            xml_content.replace("```xml", "")
            .replace("```", "")
            .replace("HANDLED_BY_MODE", "UNDEFINED")
            .strip()
        )


        root_ai = etree.fromstring(xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content)
        if root_ai.tag == "visuSpecAI":
            root_ai.tag = "visuSpec"
        # Always force name="UserFile" so DIVE's backupVisuSpec saves to
        # the correct directory (UserFile/). The AI may set arbitrary names
        # like "Total_Points_per_Team" which would create wrong subdirectories.
        root_ai.set("name", "UserFile")
        
        # Always use <datas> from disk (written by choregraph with correct rows values)
        # The AI doesn't know actual row counts, so we must preserve the disk version
        datas_ai = root_ai.find("datas")
        if datas_ai is not None:
            root_ai.remove(datas_ai)
        
        # Insert the datas element from disk at the beginning
        root_ai.insert(0, datas_elem)
        # logger().logp(INFO, "Using <datas> from disk (preserving choregraph's rows values).")

        # Write the complete XML
        self.indent(root_ai)
        tree_new = etree.ElementTree(root_ai)
        tree_new.write(file_path, encoding="utf-8", xml_declaration=True)

    def extract_metadata_from_xml(self, xml_file_path):
        """Extract comprehensive metadata from all <rawData> elements in the XML file.
        
        Returns a list of datasets, each containing:
        - data_id: unique identifier
        - name: dataset name
        - rows: number of rows
        - filename: source filename
        - fields: list of field metadata (field_id, name, data_type, unit, field_min, field_max, distinct_count)
        """
        datasets = []
        
        try:
            tree = etree.parse(xml_file_path)
            root = tree.getroot()

            for raw_data in root.findall(".//rawData"):
                data_id = raw_data.get("id")
                data_name = raw_data.get("name", "")
                rows = raw_data.get("rows", "0")
                
                # Extract filename from file element's location attribute
                filename = ""
                file_element = raw_data.find("file")
                if file_element is not None:
                    file_location = file_element.get("location", "")
                    if file_location:
                        filename = os.path.basename(file_location)
                
                # Extract all field metadata
                fields_metadata = []
                for field in raw_data.findall(".//field"):
                    
                    field_info = {
                        "field_id": field.get("id"),
                        "name": field.get("name"),
                        "data_type": field.get("dataType"),
                        # "unit": field.get("unit", "UNITLESS"),
                        "field_min": field.get("fieldMin"),
                        "field_max": field.get("fieldMax"),
                        "distinct_count": field.get("distinctCount"),
                    }
                    fields_metadata.append(field_info)
                
                dataset_info = {
                    "data_id": data_id,
                    "name": data_name,
                    "rows": rows,
                    "filename": filename,
                    "fields": fields_metadata,
                }
                datasets.append(dataset_info)
                
        except Exception as e:
            logger().logp(ERROR, f"Error in extract_metadata_from_xml: [{e}]")
        
        return datasets

    def extract_datas_from_xml(self, xml_file_path):
        """Extract the datas element from XML file as string."""
        tree = etree.parse(xml_file_path)
        root = tree.getroot()
        fields = root.find(".//datas")
        fields = etree.tostring(fields, encoding="unicode")
        return fields

    def indent(self, elem, level=0):
        """Format XML with proper indentation."""
        i = "\n" + "  " * level
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for child in elem:
                self.indent(child, level + 1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

    def inject_custom_palette(self, root, custom_palette_data):
        """
        Inject a custom color palette from metadata into the XML.

        Args:
            root: The XML root element
            custom_palette_data: Dict containing:
                - name: Palette name (used for reference)
                - colors: List of hex color strings (legacy, sampled mode)
                - breaks: Optional list of {anchor, color} for anchored mode.
                  Each anchor is one of "min"/"max"/"NN%"/numeric-literal.
                - type: SEQUENTIAL, DIVERGING, or QUALITATIVE

        Returns:
            Modified root element with custom palette injected
        """
        if not custom_palette_data:
            return root

        breaks = custom_palette_data.get("breaks") or []
        colors = custom_palette_data.get("colors") or []
        if not breaks and not colors:
            return root

        def _norm_hex(h):
            return h if h.startswith("#") else f"#{h}"

        color_palettes = root.find("colorPalettes")
        if color_palettes is None:
            color_palettes = etree.SubElement(root, "colorPalettes")

        non_custom_palettes = [
            p for p in color_palettes.findall("colorPalette")
            if p.get("name") != "CUSTOM"
        ]
        existing_palette = color_palettes.find('colorPalette[@name="CUSTOM"]')
        if existing_palette is not None:
            custom_palette = existing_palette
            custom_palette.set("name", "CUSTOM")
            custom_palette.set("type", custom_palette_data.get("type", "SEQUENTIAL"))
            for color_elem in custom_palette.findall("color"):
                custom_palette.remove(color_elem)
        else:
            custom_palette = etree.SubElement(
                color_palettes,
                "colorPalette",
                id=str(len(non_custom_palettes) + 1),
                name="CUSTOM",
                type=custom_palette_data.get("type", "SEQUENTIAL"),
            )

        if breaks:
            custom_palette.set("size", str(len(breaks)))
            for brk in breaks:
                anchor = brk.get("anchor")
                hex_color = _norm_hex(brk.get("color", "#000000"))
                color_elem = etree.SubElement(custom_palette, "color")
                if anchor is not None:
                    color_elem.set("anchor", str(anchor))
                color_elem.text = hex_color
            n = len(breaks)
        else:
            custom_palette.set("size", str(len(colors)))
            for hex_color in colors:
                color_elem = etree.SubElement(custom_palette, "color")
                color_elem.text = _norm_hex(hex_color)
            n = len(colors)

        # Bind every colorChannel to the CUSTOM palette. Without this the
        # channels still carry colorPaletteId="UNDEFINED" from the AI and
        # ASP's user_color_palette rule never fires — theme-auto wins.
        # Doing it in the XML makes the binding visible to facts.py on the
        # same footing as AI-specified palettes.
        custom_id = custom_palette.get("id")
        channel_count = 0
        for cc in root.iter("colorChannel"):
            cc.set("colorPaletteId", str(custom_id))
            channel_count += 1

        logger().logp(
            INFO,
            f"Injected custom color palette (id={custom_id}) with {n} stops, "
            f"bound to {channel_count} colorChannel(s)",
        )
        return root

    def get_csv_characterization_from_api(
        self, file_path, api_url=f"https://{SERVER_HOST}:8000/ai/file/characterization"
    ):
        """
        Get CSV characterization by calling the AI service API
        """
        try:
            with open(file_path, "rb") as f:
                files = {"files": (os.path.basename(file_path), f)}
                response = requests.post(api_url, files=files, timeout=30, verify=True)

            if response.status_code == 200:
                data = response.json()
                if data and "results" in data and len(data["results"]) > 0:
                    return data["results"][0].get("characteristics")

            logger().logp(
                ERROR,
                f"Failed to get CSV characterization from API: {response.status_code}, {response.text}",
            )
            return None
        except Exception as e:
            logger().logp(ERROR, f"Error calling CSV characterization API: {e}")
            return None

    def print(self):
        """Print the XML file content for debugging."""
        try:
            tree = etree.parse(self.xml_filepath)
            root = tree.getroot()
            etree.dump(root)
        except Exception as e:
            logger().logp(ERROR, f"Error in print: [{e}]")
