"""Offline tests for VistaTube branding."""
import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/brand.py"
spec = importlib.util.spec_from_file_location("vistatube_brand", SCRIPT)
brand = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brand)

class BrandingTests(unittest.TestCase):
    def test_icon_valid(self):
        icon = ET.fromstring(brand.ICON)
        self.assertTrue(icon.tag.endswith("vector"))
        self.assertGreaterEqual(len(icon), 3)

    def test_palette(self):
        self.assertGreaterEqual(len(brand.COLORS), 20)
        for name, value in brand.COLORS.items():
            self.assertTrue(name.startswith("blue_md_theme_"))
            self.assertRegex(value, r"^#[0-9a-fA-F]{6}$")

    def test_app_identifier(self):
        self.assertEqual(brand.PACKAGE, "app.vistatube.mobile")

if __name__ == "__main__":
    unittest.main()
