# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

import re
from lxml import etree

import xmlschema
from dive.xml import get_xsd_path
from logger import ERROR, SUCCESS, logger

_DEFAULT_XSD = str(get_xsd_path())


class XMLSpecProcessor:
    """Handles XML specification processing with XSD validation and channel management."""

    # Class-level cache for parsed XSD trees (keyed by filepath)
    _xsd_cache: dict[str, tuple] = {}  # filepath -> (xsd_tree, xsd_root)

    @classmethod
    def _get_xsd(cls, xsd_filepath: str):
        """Return cached (xsd_tree, xsd_root) for the given filepath."""
        if xsd_filepath not in cls._xsd_cache:
            tree = etree.parse(xsd_filepath)
            cls._xsd_cache[xsd_filepath] = (tree, tree.getroot())
        return cls._xsd_cache[xsd_filepath]

    def __init__(self, xml_content_str, xsd_filepath=_DEFAULT_XSD):
        """Initialize with XSD schema path."""
        self.xml_str = self.format_llm_response(xml_content_str)
        self.xsd_filepath = xsd_filepath
        xsd_tree, xsd_root = self._get_xsd(xsd_filepath)
        self.xsd_tree = xsd_tree
        self.xsd_root = xsd_root
        self.ns = {'xs': 'http://www.w3.org/2001/XMLSchema'}
        try:
            self.root_xml = etree.fromstring(self.xml_str.encode("utf-8") if isinstance(self.xml_str, str) else self.xml_str)
        except Exception as e:
            logger().logp(ERROR, f"XML parsing error: {e}")
            self.root_xml = ''
        self.errors = []
        
    @staticmethod
    def format_llm_response(raw_xml_str):
        """
        Formats the response from the LLM by removing unnecessary whitespace, code fences,
        XML declarations, processing instructions, and any text outside the root XML element.
        """
        response = raw_xml_str
        response = response.strip()
        response = response.replace("```xml", "").replace("```", "")
        response = response.strip()
        response = re.sub(r"<\?.*?\?>", "", response, flags=re.DOTALL)
        response = response.strip()
        match = re.search(r"<[^>]+>.*</[^>]+>", response, re.DOTALL)
        if match:
            return match.group(0).strip()
        start = response.find("<")
        end = response.rfind(">")
        if start != -1 and end != -1 and end > start:
            return response[start : end + 1].strip()
        return response

    def ensure_channel_attributed_is_not_undefined(self):
        """
        Invalidate the XML if a mark (x,y,z,color,time,shape) references an id absent from the corresponding group.
        """

        ids_by_type = {
            "numericChannels": set(),
            "colorChannels": set(),
            "shapeChannels": set(),
        }
        channels_element = self.root_xml.find(".//channels")
        if channels_element is not None:
            for channel_group in channels_element:
                gname = channel_group.tag
                if gname in ids_by_type:
                    for ch in channel_group:
                        cid = ch.get("id")
                        if cid:
                            ids_by_type[gname].add(cid)

        attr_group = {
            "x": "numericChannels",
            "y": "numericChannels",
            "z": "numericChannels",
            "time": "numericChannels",
            "color": "colorChannels",
            "shape": "shapeChannels",
        }

        marks_element = self.root_xml.find(".//marks")
        if marks_element is None:
            return True, ""

        for mark in marks_element:
            mapping = self.get_mark_types_from_names([mark.tag])
            channel_attributes, _ = (
                self.get_channel_attributes_from_xsd(mapping[0])
                if mapping
                else ([], "")
            )
            for attr_name in channel_attributes:
                if attr_name not in attr_group:
                    continue
                val = mark.get(attr_name)
                if not val or val in ("HANDLED_BY_MODE", "UNDESIRED", "UNDEFINED", "REQUIRED"):
                    continue
                expected_group = attr_group[attr_name]
                if val not in ids_by_type[expected_group]:
                    self.errors.append(
                        f"Channel id '{val}' used for '{attr_name}' does not exist in {expected_group}. Make sure the channel is not defined under 'undefinedChannels' if it is intended to be directly assigned to mark attribute."
                    )
                    logger().logp(
                        ERROR,
                        f"Channel id '{val}' used for '{attr_name}' does not exist in {expected_group}.",
                    )
                    return False
        return True

    def validate_color_palette_ids(self):
        defined_palette_ids = set()

        color_palettes_element = self.root_xml.find(".//colorPalettes")
        if color_palettes_element is not None:
            for color_palette in color_palettes_element:
                palette_id = color_palette.get("id")
                if palette_id:
                    defined_palette_ids.add(palette_id)

        cch_element = self.root_xml.find(".//colorChannels")
        if cch_element is not None:
            for channel in cch_element:
                channel_id = channel.get("colorPaletteId")
                if channel_id and channel_id != "UNDEFINED":
                    if channel_id not in defined_palette_ids:
                        logger().logp(
                            ERROR,
                            f"Color channel refers to the palette '{channel_id}' which is not defined in the color palettes.",
                        )
                        self.errors.append(
                            f"Color channel refers to the palette '{channel_id}' which is not defined in the color palettes."
                        )
                        return False
                    # logger().logp(INFO, f"Color channel '{channel_id}' is defined in the color palettes.")
        return True

    def validate_shape_palette_ids(self):
        defined_palette_ids = set()

        shape_palettes_element = self.root_xml.find(".//shapePalettes")
        if shape_palettes_element is not None:
            for shape_palette in shape_palettes_element:
                palette_id = shape_palette.get("id")
                if palette_id:
                    defined_palette_ids.add(palette_id)

        sch_element = self.root_xml.find(".//shapeChannels")
        if sch_element is not None:
            for channel in sch_element:
                channel_id = channel.get("shapePaletteId")
                if channel_id and channel_id != "UNDEFINED":
                    if channel_id not in defined_palette_ids:
                        logger().logp(
                            ERROR,
                            f"Shape channel refers to the palette '{channel_id}' which is not defined in the shape palettes.",
                        )
                        self.errors.append(
                            f"Shape channel refers to the palette '{channel_id}' which is not defined in the shape palettes."
                        )
                        return False
                    # logger().logp(INFO, f"Shape channel '{channel_id}' is defined in the shape palettes.")
        return True

    def get_mark_names_from_xml(self):
        """Extract mark names from XML root element."""
        names = []
        marks_element = self.root_xml.find('.//marks')
        if marks_element is not None:
            for child in marks_element:
                if child.tag:  
                    names.append(child.tag)
        return names

    def get_channel_attributes_from_xsd(self, mark_type_name):
        root = self.xsd_root
        ns = self.ns
        attributes = []
        mark_name = self.get_mark_name_from_type(mark_type_name) # name: unigrid, type: UniGridMark
        xml_declaration = f'<{mark_name}' # Useful only for intent classification
        base_mark_type = root.find(f".//xs:complexType[@name='Mark']", ns) # First we count the channels present in the base mark type
        for attr in base_mark_type.findall(".//xs:attribute", ns):
            attr_name = attr.get('name')
            attr_type = attr.get('type')
            attr_default = attr.get('default', '')
            xml_declaration += f' {attr_name}="{attr_default}"' 

            if attr_name and attr_type == 'UndesiredableInteger':
                attributes.append(attr_name)

        complex_type = root.find(f".//xs:complexType[@name='{mark_type_name}']", ns) # Then we check the specific mark type
        if complex_type is None:
            return attributes, xml_declaration + '/>'
        for attr in complex_type.findall(".//xs:attribute", ns):
            attr_name = attr.get('name')
            attr_type = attr.get('type')
            attr_default = attr.get('default', '')
            xml_declaration += f' {attr_name}="{attr_default}"'
            if attr_name and attr_type == 'UndesiredableInteger':
                attributes.append(attr_name)
        
        xml_declaration += '/>'
        return attributes, xml_declaration
    
    def check_fields_in_xml(self):
        try:
            channels_element = self.root_xml.find(".//channels")
            if channels_element is None:
                return True, self.errors

            for channel_group in channels_element:

                for channel in channel_group:
                    if not isinstance(channel.tag, str):  # skip lxml comment/PI nodes
                        continue
                    field_id = channel.get("fieldId")
                    data_id = channel.get("dataId")
                    label = channel.get("label")
                    if (
                        field_id is None or field_id == "UNDEFINED"
                    ) and label != "UNDEFINED":
                        message_error = f"[FIELD_DEFINITION] We encountered an error getting the field labeled '{channel.get('label')}'. Please ensure to specify the fieldId for this channel in the XML and that it corresponds to an existing field in your dataset. If the issue persists, consider re-uploading your dataset to refresh the field list."
                        logger().logp(ERROR, message_error)
                        self.errors.append(
                            message_error
                        )
                        return False, self.errors

                    if (data_id is None or data_id == "UNDEFINED") and label != "UNDEFINED":
                        message_error = f"[FIELD_DEFINITION] We encountered an error getting the field labeled '{channel.get('label')}'. Please ensure to specify the dataId for this channel in the XML and that it corresponds to an existing field in your dataset. If the issue persists, consider re-uploading your dataset to refresh the field list."
                        logger().logp(ERROR, message_error)
                        self.errors.append(
                            message_error
                        )
                        return False, self.errors

            is_valid = len(self.errors) == 0

            return is_valid, self.errors

        except etree.XMLSyntaxError as e:
            logger().logp(ERROR, f"XML parsing error: {e}")
            return False, []
        except Exception as e:
            logger().logp(ERROR, f"Unexpected error during field validation: {e}")
            return False, []
    
    def validate_with_xmlschema_lib(self):
        try:
            schema = xmlschema.XMLSchema(self.xsd_filepath)
            is_valid = schema.is_valid(self.xml_str)
            if not is_valid:
                errors = list(schema.iter_errors(self.xml_str))
                return False, [str(err) for err in errors]
            return True, []
        except Exception as e:
            return False, [f"Validation error: {str(e)}"]
    
    def validate_xml_string_with_xsd(self):
        """
        Validates an XML string against an XSD schema file.

        Parameters:
            - xml_string (str): The XML content as a string.
            - xsd_file_path (str): The file path to the XSD schema.

        Returns:
            - tuple: A tuple containing:
            - is_valid (bool): True if the XML is valid, False otherwise.
            - errors (list): A list of error messages if the XML is invalid.

        Exceptions:
            - Raises XMLSchemaParseError if there is an issue parsing the XSD schema.
            - Raises XMLSyntaxError if there is a syntax error in the XML string.
            - Raises FileNotFoundError if the XSD file is not found.
            - Catches and handles any unexpected exceptions.
        """
        try:
            errors = []
            fields_valid, field_errors = self.check_fields_in_xml()
            if len(
                field_errors
            )>0:  # The only case we don't want to proceed with the XSD validation is when a fieldId/dataId is UNDEFINED.
                return False, field_errors, ""
            is_valid = (
                self.validate_color_palette_ids()
                and self.validate_shape_palette_ids()
                and self.ensure_channel_attributed_is_not_undefined()
            )

            # Check each element in the XML against the XSD schema
            is_valid_xsd = False
            xsd_errors = []
            if is_valid:
                is_valid_xsd, xsd_errors = self.validate_with_xmlschema_lib()
            xml_content = self.llm_clean_response()
            if is_valid_xsd:
                logger().logp(
                    SUCCESS,
                    f"The XML string is valid according to '{self.xsd_filepath}' schema.",
                )
                return True, [], xml_content
            else:
                errors.extend(xsd_errors)
                errors.extend(self.errors)
                logger().logp(
                    ERROR,
                    f"The XML string is not valid according to '{self.xsd_filepath}' schema.",
                )
                for error_msg in errors:
                    logger().logp(ERROR, error_msg)
                return False, errors, xml_content

        except etree.XMLSyntaxError as e:
            logger().logp(ERROR, f"Error during the parsing of the XML or XSD schema: {e}")
            return False, [f"Parse error: {e}"], None
        except Exception as e:
            logger().logp(ERROR, f"Unexpected error happened: {e}")
            return False, [f"Unexpected error: {e}"], None


    def get_mark_types_from_names(self, mark_names):
        """Get mark types from mark names using XSD schema."""
        elements = self.xsd_root.findall(".//xs:complexType[@name='Marks']//xs:element", self.ns)
        mark_mapping = {
            e.get('name'): e.get('type')
            for e in elements
            if e.get('name') and e.get('type')
        }
        return [mark_mapping[name] for name in mark_names if name in mark_mapping]


    def get_mark_name_from_type(self, mark_type):
        """Get mark name from mark type using XSD schema."""
        elements = self.xsd_root.findall(".//xs:complexType[@name='Marks']//xs:element", self.ns)
        type_mapping = {
            e.get('type'): e.get('name')
            for e in elements
            if e.get('name') and e.get('type')
        }
        return type_mapping.get(mark_type)
    
    def count_mark_channels(self, mark_name):
        """Count channels required for a specific mark type."""
        if mark_name == 'Mark':
            return 7
        
        c = 0
        # Count channels in base mark (typed Mark)
        base_mark = self.xsd_root.find(".//xs:complexType[@name='Mark']", self.ns)
        if base_mark is not None:
            for attr in base_mark.findall(".//xs:attribute", self.ns):
                attr_type = attr.get('type')
                if attr_type == 'UndesiredableInteger':  # Only channels are typed as UndesiredableInteger
                    c += 1
                    
        # Count channels in the actual mark
        mark = self.xsd_root.find(f".//xs:complexType[@name='{mark_name}']", self.ns)
        if mark is not None:
            for attr in mark.findall(".//xs:attribute", self.ns):
                attr_type = attr.get('type')
                if attr_type == 'UndesiredableInteger': 
                    c += 1
        return c

    def count_existing_channels(self):
        """Count existing channels in XML."""
        return sum(
            len(list(group)) 
            for group in self.root_xml.findall('.//channels/*') 
            if group is not None
        )

    def count_channels_required(self):
        """Calculate total undefined channels required minus existing ones.

        The first mark gets its full channel slot count (all unassigned slots
        are available for ASP). Each additional mark adds at most 2 extra
        channels for variation — in practice, multi-mark specs share most
        channels (e.g. same X axis) and only differ on one or two.
        """
        marks_present = self.get_mark_names_from_xml()
        marks_types = self.get_mark_types_from_names(marks_present)
        if len(marks_types) == 0:
            total_channels_required = 7
        else:
            # First mark: full channel slot count
            first_type = marks_types[0]
            if first_type:
                total_channels_required = self.count_mark_channels(first_type)
            else:
                total_channels_required = 7
            # Additional marks: at most 2 extra channels each
            for mark_type in marks_types[1:]:
                total_channels_required += 2
        already_present_channels = self.count_existing_channels()
        return max(0, total_channels_required - already_present_channels)

    def ensure_minimum_channels(self):
        """Ensure minimum required channels exist in XML."""
        channels_elem = self.root_xml.find("channels")
        if channels_elem is None:
            return
        
        undefined_channels = channels_elem.find("undefinedChannels")
        if undefined_channels is None:
            undefined_channels = etree.SubElement(channels_elem, "undefinedChannels")
        
        all_channels = channels_elem.findall(".//*[@id]")
        existing_ids = {int(ch.get("id", 0)) for ch in all_channels if ch.get("id", "").isdigit()}
        next_id = max(existing_ids, default=0) + 1
        
        needed = min(self.count_channels_required(), 7)
        for i in range(needed):
            etree.SubElement(
                undefined_channels, "channel",
                id=str(next_id + i),
                label="UNDEFINED",
                dataId="UNDEFINED",
                fieldId="UNDEFINED",
                boundMin="UNDEFINED",
                boundMax="UNDEFINED",
                scaleType="UNDEFINED",
                category="UNDEFINED",
                discrete="UNDEFINED"
            )
        
    def get_mark_declaration(self):
        marks_elem = self.root_xml.find('.//marks')
        if marks_elem is None:
            return "" 
        return etree.tostring(marks_elem[0], encoding='unicode') 
    
    def replace_current_mark(self, new_mark_xml_str):
        """Replace the current mark in XML with a new one."""
        marks_elem = self.root_xml.find('.//marks')
        if marks_elem is None:
            return
        
        new_mark_elem = etree.fromstring(new_mark_xml_str.encode("utf-8") if isinstance(new_mark_xml_str, str) else new_mark_xml_str)
        if len(marks_elem) > 0:
            marks_elem.remove(marks_elem[0])
        marks_elem.append(new_mark_elem)
    
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

    def llm_clean_response(self):
        """
        Clean up the LLM response to extract valid XML content.
        """
        self.ensure_minimum_channels()
        return self.to_string()

    def to_string(self):
        """Convert XML tree to a pretty-printed string."""
        self.indent(self.root_xml)
        return etree.tostring(self.root_xml, encoding='unicode')
    
    def merge_mark_attributes(self, source_xml_str, target_xml_str):
        """Merge mark attributes from source XML into target XML."""
        src_el = etree.fromstring(source_xml_str.encode("utf-8") if isinstance(source_xml_str, str) else source_xml_str)
        targ_el = etree.fromstring(target_xml_str.encode("utf-8") if isinstance(target_xml_str, str) else target_xml_str)
        
        for attr_name, src_val in src_el.attrib.items():
            if attr_name in targ_el.attrib:
                targ_el.attrib[attr_name] = src_val

        attrs_serialized = " ".join(f'{k}="{v}"' for k, v in targ_el.attrib.items())
        return f"<{targ_el.tag} {attrs_serialized}/>"