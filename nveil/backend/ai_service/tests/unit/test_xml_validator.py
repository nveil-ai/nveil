# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import unittest

from viz_file_utils.utils.viz_spec_validator import XMLSpecProcessor


class TestFormatLLMResponse(unittest.TestCase):
    def test_basic_trimming(self):
        self.assertEqual(XMLSpecProcessor.format_llm_response("   <root></root>   "), "<root></root>")

    def test_remove_code_block_markers(self):
        self.assertEqual(XMLSpecProcessor.format_llm_response("```xml\n<root></root>\n```"), "<root></root>")

    def test_remove_xml_declaration(self):
        self.assertEqual(XMLSpecProcessor.format_llm_response('<?xml version="1.0" encoding="UTF-8"?><root></root>'), "<root></root>")

    def test_remove_all(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response("  ```xml\n<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<data>1</data>\n```  "),
            "<data>1</data>"
        )

    def test_no_changes_needed(self):
        self.assertEqual(XMLSpecProcessor.format_llm_response("<foo>bar</foo>"), "<foo>bar</foo>")

    def test_only_code_block_markers(self):
        self.assertEqual(XMLSpecProcessor.format_llm_response("```xml\nfoo\n```"), "foo")

    def test_only_xml_declaration_and_whitespace(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response("   <?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<bar/>   "),
            "<bar/>"
        )

    def test_multiple_code_block_markers(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response("```xml\n```xml\n<root/>\n```\n```"),
            "<root/>"
        )

    def test_empty_input(self):
        self.assertEqual(XMLSpecProcessor.format_llm_response(""), "")

    def test_only_whitespace(self):
        self.assertEqual(XMLSpecProcessor.format_llm_response("   "), "")

    def test_code_block_with_different_case(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response("```XML\n<root/>\n```"),
            "<root/>"
        )

    def test_xml_declaration_with_spaces(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response('<?xml   version="1.0" encoding="UTF-8"?>\n<root/>'),
            '<root/>'
        )

    def test_text_outside_xml_tags(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response("Some text before <root>data</root> some text after"),
            "<root>data</root>"
        )

    def test_multiple_xml_elements(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response("<foo>1</foo><bar>2</bar>"),
            "<foo>1</foo><bar>2</bar>"
        )

    def test_no_xml_tags(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response("Just some text, no xml here."),
            "Just some text, no xml here."
        )

    def test_nested_xml(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response("```xml\n<root><child>val</child></root>\n```"),
            "<root><child>val</child></root>"
        )

    def test_xml_with_attributes(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response('<root attr="1">val</root>'),
            '<root attr="1">val</root>'
        )

    def test_xml_with_newlines_and_spaces(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response("   \n<root>\n  <child>val</child>\n</root>\n   "),
            "<root>\n  <child>val</child>\n</root>"
        )

    def test_xml_with_comment(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response("<!-- comment --><root/>"),
            "<!-- comment --><root/>"
        )

    def test_xml_with_processing_instruction(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response("<?processing instruction?><root/>"),
            "<root/>"
        )

    def test_xml_with_multiple_roots(self):
        self.assertEqual(
            XMLSpecProcessor.format_llm_response("<a/><b/>"),
            "<a/><b/>"
        )


class TestValidateMarkChannelIds(unittest.TestCase):
    def build_spec(self, channels_fragment, marks_fragment):
        return f"""
<visuSpecAI name="UserFile">
  <coordinates>UNDEFINED</coordinates>
  <colorPalettes/>
  <shapePalettes/>
  <channels>
    {channels_fragment}
  </channels>
  <marks>
    {marks_fragment}
  </marks>
  <space xSpatialScaling="UNDEFINED" ySpatialScaling="UNDEFINED" zSpatialScaling="UNDEFINED" sizeSpatialScaling="UNDEFINED"/>
</visuSpecAI>
""".strip()

    def test_valid_channel_id(self):
        xml = self.build_spec(
            '<numericChannels><channel id="A"/></numericChannels>',
            '<unigrid x="A"/>'
        )
        self.assertTrue(XMLSpecProcessor(xml).ensure_channel_attributed_is_not_undefined())

    def test_invalid_channel_id(self):
        xml = self.build_spec(
            '<numericChannels><channel id="A"/></numericChannels>',
            '<unigrid x="B"/>'
        )
        self.assertFalse(XMLSpecProcessor(xml).ensure_channel_attributed_is_not_undefined())

    def test_channel_id_is_HANDLED_BY_MODE(self):
        xml = self.build_spec(
            '<numericChannels><channel id="A"/></numericChannels>',
            '<unigrid x="HANDLED_BY_MODE"/>'
        )
        self.assertTrue(XMLSpecProcessor(xml).ensure_channel_attributed_is_not_undefined())

    def test_channel_id_is_UNDESIRED(self):
        xml = self.build_spec(
            '<numericChannels><channel id="A"/></numericChannels>',
            '<unigrid x="UNDESIRED"/>'
        )
        self.assertTrue(XMLSpecProcessor(xml).ensure_channel_attributed_is_not_undefined())

    def test_channel_id_is_REQUIRED(self):
        xml = self.build_spec(
            '<numericChannels><channel id="A"/></numericChannels>',
            '<unigrid x="REQUIRED"/>'
        )
        self.assertTrue(XMLSpecProcessor(xml).ensure_channel_attributed_is_not_undefined())

    def test_no_channels_element(self):
        # channels fragment empty -> method should still return True
        xml = self.build_spec(
            '',
            '<unigrid x="HANDLED_BY_MODE"/>'
        )
        self.assertTrue(XMLSpecProcessor(xml).ensure_channel_attributed_is_not_undefined())

    def test_no_marks_element(self):
        xml = """
<visuSpecAI name="UserFile">
  <channels>
    <numericChannels><channel id="A"/></numericChannels>
  </channels>
  <marks/>
</visuSpecAI>
"""
        self.assertTrue(XMLSpecProcessor(xml).ensure_channel_attributed_is_not_undefined())

    def test_multiple_channel_groups_and_marks(self):
        xml = self.build_spec(
            '<numericChannels><channel id="A"/><channel id="B"/></numericChannels>',
            '<unigrid x="A"/><point y="A"/>'
        )
        self.assertTrue(XMLSpecProcessor(xml).ensure_channel_attributed_is_not_undefined())

    def test_missing_channel_attribute(self):
        # x refers to "A " (space) which is not in channel ids {"A"}
        xml = self.build_spec(
            '<numericChannels><channel id="A"/></numericChannels>',
            '<unigrid x="A "/>'
        )
        self.assertFalse(XMLSpecProcessor(xml).ensure_channel_attributed_is_not_undefined())


class TestValidateColorPaletteIds(unittest.TestCase):
    def build_spec(self, palettes_fragment, channels_fragment):
        return f"""
<visuSpecAI name="UserFile">
  <colorPalettes>
    {palettes_fragment}
  </colorPalettes>
  <colorChannels>
    {channels_fragment}
  </colorChannels>
</visuSpecAI>
""".strip()

    def test_valid_palette_and_channel(self):
        xml = self.build_spec('<colorPalette id="1"/><colorPalette id="2"/>',
                              '<colorChannel colorPaletteId="1"/><colorChannel colorPaletteId="2"/>')
        self.assertTrue(XMLSpecProcessor(xml).validate_color_palette_ids())

    def test_channel_id_not_in_palette(self):
        xml = self.build_spec('<colorPalette id="1"/>',
                              '<colorChannel colorPaletteId="1"/><colorChannel colorPaletteId="2"/>')
        self.assertFalse(XMLSpecProcessor(xml).validate_color_palette_ids())

    def test_channel_id_is_UNDEFINED(self):
        xml = self.build_spec('<colorPalette id="1"/>',
                              '<colorChannel colorPaletteId="1"/><colorChannel colorPaletteId="UNDEFINED"/>')
        self.assertTrue(XMLSpecProcessor(xml).validate_color_palette_ids())

    def test_no_color_palettes(self):
        xml = """
<visuSpecAI name="UserFile">
  <colorChannels>
    <colorChannel colorPaletteId="1"/>
  </colorChannels>
</visuSpecAI>
""".strip()
        self.assertFalse(XMLSpecProcessor(xml).validate_color_palette_ids())

    def test_no_color_channels(self):
        xml = """
<visuSpecAI name="UserFile">
  <colorPalettes>
    <colorPalette id="1"/>
  </colorPalettes>
</visuSpecAI>
""".strip()
        self.assertTrue(XMLSpecProcessor(xml).validate_color_palette_ids())

    def test_empty_palettes_and_channels(self):
        xml = """
<visuSpecAI name="UserFile">
  <colorPalettes/>
  <colorChannels/>
</visuSpecAI>
""".strip()
        self.assertTrue(XMLSpecProcessor(xml).validate_color_palette_ids())

    def test_channel_without_id(self):
        xml = self.build_spec('<colorPalette id="1"/>', '<colorChannel/>')
        self.assertTrue(XMLSpecProcessor(xml).validate_color_palette_ids())


if __name__ == "__main__":
    unittest.main()