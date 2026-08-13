import importlib.util, unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location("climate",Path(__file__).parents[1]/"climate_balancer"/"app.py")
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class ClimateTests(unittest.TestCase):
    def test_celsius_conversion(self):
        self.assertEqual(app.fahrenheit({"state":"20","attributes":{"unit_of_measurement":"°C"}}),68)
    def test_unavailable_temperature(self):
        self.assertIsNone(app.fahrenheit({"state":"unavailable","attributes":{}}))
