import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("app", Path(__file__).parents[1] / "solar_sentinel" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class HealthTests(unittest.TestCase):
    def test_unavailable_is_critical(self):
        score, symptoms = app.assess(
            {"state": "unavailable", "attributes": {}},
            {"stale_after_minutes": 30, "low_production_threshold_w": 100},
        )
        self.assertEqual(score, 20)
        self.assertEqual(symptoms, ["Telemetry unavailable"])

    def test_nominal_energy_sensor(self):
        score, symptoms = app.assess(
            {"state": "42", "attributes": {"device_class": "energy", "unit_of_measurement": "kWh"}},
            {"stale_after_minutes": 30, "low_production_threshold_w": 100},
        )
        self.assertEqual(score, 100)
        self.assertEqual(symptoms, [])
