# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import unittest

from viz_file_utils.utils.viz_spec_validator import XMLSpecProcessor

DUMMY_XML = """
<visuSpecAI name="UserFile">
</visuSpecAI>
"""

class TestXMLSpecProcessor(unittest.TestCase):
    def test_get_mark_names_from_xml(self):
        xml_content = """<visuSpecAI name="UserFile">
  <coordinates>UNDEFINED</coordinates>
  <colorPalettes/>
  <shapePalettes/>
  <channels>
    <undefinedChannels/>
    <numericChannels/>
    <colorChannels/>
    <shapeChannels/>
  </channels>
  <marks>
    <unigrid id="1" name="heatmap" x="HANDLED_BY_MODE" y="HANDLED_BY_MODE" z="HANDLED_BY_MODE" color="HANDLED_BY_MODE" time="HANDLED_BY_MODE" resolution="UNDEFINED" interpolation="UNDEFINED" radius="UNDEFINED" influence="UNDEFINED"/>
  </marks>
  <space xSpatialScaling="UNDEFINED" ySpatialScaling="UNDEFINED" zSpatialScaling="UNDEFINED" sizeSpatialScaling="UNDEFINED"/>
</visuSpecAI>"""
        self.processor = XMLSpecProcessor(xml_content)
        mark_names = self.processor.get_mark_names_from_xml()
        self.assertIn("unigrid", mark_names)

        xml_content = """<visuSpecAI name="UserFile">
  <coordinates>UNDEFINED</coordinates>
  <colorPalettes/>
  <shapePalettes/>
  <channels>
    <undefinedChannels/>
    <numericChannels/>
    <colorChannels/>
    <shapeChannels/>
  </channels>
  <marks>
    <unigrid id="1" name="heatmap" x="HANDLED_BY_MODE" y="HANDLED_BY_MODE" z="HANDLED_BY_MODE" color="HANDLED_BY_MODE" time="HANDLED_BY_MODE" resolution="UNDEFINED" interpolation="UNDEFINED" radius="UNDEFINED" influence="UNDEFINED"/>
    <point id="1" name="pointcloud" x="HANDLED_BY_MODE" y="HANDLED_BY_MODE" z="HANDLED_BY_MODE" color="HANDLED_BY_MODE" time="HANDLED_BY_MODE" size="HANDLED_BY_MODE" shape="HANDLED_BY_MODE" />
  </marks>
  <space xSpatialScaling="UNDEFINED" ySpatialScaling="UNDEFINED" zSpatialScaling="UNDEFINED" sizeSpatialScaling="UNDEFINED"/>
</visuSpecAI>"""

        self.processor = XMLSpecProcessor(xml_content)
        mark_names = self.processor.get_mark_names_from_xml()
        self.assertEqual(set(mark_names), set(["unigrid", "point"]))

    def test_get_channel_attributes_from_xsd(self):
        self.processor = XMLSpecProcessor(DUMMY_XML)
        attrs, _ = self.processor.get_channel_attributes_from_xsd("UniGridMark")
        self.assertEqual(set(attrs), set(["x", "y", "z", "color", "time"]))
        attrs, _ = self.processor.get_channel_attributes_from_xsd("Mark")
        self.assertEqual(set(attrs), set(["x", "y", "z", "color", "time"]))
        attrs, _ = self.processor.get_channel_attributes_from_xsd("PointMark")
        self.assertEqual(set(attrs), set(["x", "y", "z", "color", "time", "shape", "size"]))
        attrs, _ = self.processor.get_channel_attributes_from_xsd("InexistingMark")
        self.assertEqual(set(attrs), set(["x", "y", "z", "color", "time"]))

    def test_get_mark_types_from_names(self):
        self.processor = XMLSpecProcessor(DUMMY_XML)
        mark_types = self.processor.get_mark_types_from_names(["unigrid", "point"])
        self.assertEqual(mark_types, ["UniGridMark", "PointMark"])
        mark_types = self.processor.get_mark_types_from_names(["unigrid"])
        self.assertEqual(mark_types, ["UniGridMark"])
        mark_types = self.processor.get_mark_types_from_names(["inexisting"])
        self.assertEqual(mark_types, [])
        mark_types = self.processor.get_mark_types_from_names([None])
        self.assertEqual(mark_types, [])
    
    def test_count_mark_channels(self):
        self.processor = XMLSpecProcessor(DUMMY_XML)
        count = self.processor.count_mark_channels("UniGridMark")
        self.assertEqual(count, 5)
        count = self.processor.count_mark_channels("Mark")
        self.assertEqual(count, 7)
        count = self.processor.count_mark_channels("PointMark")
        self.assertEqual(count, 7)
        count = self.processor.count_mark_channels("InexistingMark")
        self.assertEqual(count, 5)

    def test_count_existing_channels(self):
        xml_content = """<visuSpecAI name="UserFile">
  <coordinates>UNDEFINED</coordinates>
  <colorPalettes/>
  <shapePalettes/>
  <channels>
    <undefinedChannels>
        <channel id="1" label="Age" dataId="1" fieldId="1" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED"/>
        <channel id="2" label="MonthlyIncome" dataId="1" fieldId="19" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED"/>
        <channel id="3" label="MaritalStatus" dataId="1" fieldId="18" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED"/>
    </undefinedChannels>
    <numericChannels/>
    <colorChannels/>
    <shapeChannels/>
  </channels>
  <marks>
  </marks>
  <space xSpatialScaling="UNDEFINED" ySpatialScaling="UNDEFINED" zSpatialScaling="UNDEFINED" sizeSpatialScaling="UNDEFINED"/>
</visuSpecAI>"""
        self.processor = XMLSpecProcessor(xml_content)
        count = self.processor.count_existing_channels()
        self.assertEqual(count, 3)

        xml_content = """<visuSpecAI name="UserFile">
  <coordinates>UNDEFINED</coordinates>
  <colorPalettes/>
  <shapePalettes/>
  <channels>
    <undefinedChannels/>
    <numericChannels/>
    <colorChannels/>
    <shapeChannels/>
  </channels>
  <marks>
  </marks>
  <space xSpatialScaling="UNDEFINED" ySpatialScaling="UNDEFINED" zSpatialScaling="UNDEFINED" sizeSpatialScaling="UNDEFINED"/>
</visuSpecAI>"""
        self.processor = XMLSpecProcessor(xml_content)
        count = self.processor.count_existing_channels()
        self.assertEqual(count, 0)

        xml_content = """<visuSpecAI name="UserFile">
  <coordinates>UNDEFINED</coordinates>
  <colorPalettes/>
  <shapePalettes/>
  <channels>
    <undefinedChannels>
        <channel id="1" label="Age" dataId="1" fieldId="1" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED"/>
    </undefinedChannels>
    <numericChannels>
        <numericChannel id="1" label="Age" dataId="1" fieldId="1" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED"/>
    </numericChannels>
    <colorChannels>
        <colorChannel id="1" label="Age" dataId="1" fieldId="1" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED" colorPaletteId="UNDEFINED"/>
    </colorChannels>
    <shapeChannels>
        <shapeChannel id="1" label="Age" dataId="1" fieldId="1" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED" shapePaletteId="UNDEFINED"/>
    </shapeChannels>
  </channels>
  <marks>
  </marks>
  <space xSpatialScaling="UNDEFINED" ySpatialScaling="UNDEFINED" zSpatialScaling="UNDEFINED" sizeSpatialScaling="UNDEFINED"/>
</visuSpecAI>"""
        self.processor = XMLSpecProcessor(xml_content)
        count = self.processor.count_existing_channels()
        self.assertEqual(count, 4)

    def test_count_channels_required(self):
        xml_content = """<visuSpecAI name="UserFile">
  <coordinates>UNDEFINED</coordinates>
  <colorPalettes/>
  <shapePalettes/>
  <channels>
    <undefinedChannels>
        <channel id="1" label="Age" dataId="1" fieldId="1" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED"/>
        <channel id="2" label="MonthlyIncome" dataId="1" fieldId="19" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED"/>
        <channel id="3" label="MaritalStatus" dataId="1" fieldId="18" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED"/>
    </undefinedChannels>
    <numericChannels/>
    <colorChannels/>
    <shapeChannels/>
  </channels>
  <marks>
  </marks>
  <space xSpatialScaling="UNDEFINED" ySpatialScaling="UNDEFINED" zSpatialScaling="UNDEFINED" sizeSpatialScaling="UNDEFINED"/>
</visuSpecAI>"""
        self.processor = XMLSpecProcessor(xml_content)
        count = self.processor.count_channels_required()
        self.assertEqual(count, 4)

        xml_content = """<visuSpecAI name="UserFile">
  <coordinates>UNDEFINED</coordinates>
  <colorPalettes/>
  <shapePalettes/>
  <channels>
    <undefinedChannels/>
    <numericChannels/>
    <colorChannels/>
    <shapeChannels/>
  </channels>
  <marks>
    <unigrid id="1" name="heatmap" x="HANDLED_BY_MODE" y="HANDLED_BY_MODE" z="HANDLED_BY_MODE" color="HANDLED_BY_MODE" time="HANDLED_BY_MODE" resolution="UNDEFINED" interpolation="UNDEFINED" radius="UNDEFINED" influence="UNDEFINED"/>
    <point id="1" name="pointcloud" x="HANDLED_BY_MODE" y="HANDLED_BY_MODE" z="HANDLED_BY_MODE" color="HANDLED_BY_MODE" time="HANDLED_BY_MODE" size="HANDLED_BY_MODE" shape="HANDLED_BY_MODE" />
  </marks>
  <space xSpatialScaling="UNDEFINED" ySpatialScaling="UNDEFINED" zSpatialScaling="UNDEFINED" sizeSpatialScaling="UNDEFINED"/>
</visuSpecAI>"""
        self.processor = XMLSpecProcessor(xml_content)
        count = self.processor.count_channels_required()
        # unigrid (5 channels) + point (+2 for additional mark) - 0 existing = 7
        self.assertEqual(count, 7)

        xml_content = """<visuSpecAI name="UserFile">
  <coordinates>UNDEFINED</coordinates>
  <colorPalettes/>
  <shapePalettes/>
  <channels>
    <undefinedChannels>
        <channel id="1" label="Age" dataId="1" fieldId="1" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED"/>
    </undefinedChannels>
    <numericChannels>
        <numericChannel id="1" label="Age" dataId="1" fieldId="1" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED"/>
    </numericChannels>
    <colorChannels>
        <colorChannel id="1" label="Age" dataId="1" fieldId="1" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED" colorPaletteId="UNDEFINED"/>
    </colorChannels>
    <shapeChannels>
        <shapeChannel id="1" label="Age" dataId="1" fieldId="1" boundMin="UNDEFINED" boundMax="UNDEFINED" scaleType="UNDEFINED" categories="UNDEFINED" discrete="UNDEFINED" shapePaletteId="UNDEFINED"/>
    </shapeChannels>
  </channels>
  <marks>
    <point id="1" name="pointcloud" x="HANDLED_BY_MODE" y="HANDLED_BY_MODE" z="HANDLED_BY_MODE" color="HANDLED_BY_MODE" time="HANDLED_BY_MODE" size="HANDLED_BY_MODE" shape="HANDLED_BY_MODE" />
  </marks>
  <space xSpatialScaling="UNDEFINED" ySpatialScaling="UNDEFINED" zSpatialScaling="UNDEFINED" sizeSpatialScaling="UNDEFINED"/>
</visuSpecAI>"""
        self.processor = XMLSpecProcessor(xml_content)
        count = self.processor.count_channels_required()
        self.assertEqual(count, 3)

if __name__ == "__main__":
    unittest.main()

# python -m unittest discover -s backend/ai_service/tests