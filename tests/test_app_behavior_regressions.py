import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


solar = load("solar_behavior", "solar_sentinel/app.py")
try:
    energy = load("energy_behavior", "energy_troubleshooter/app.py")
except ModuleNotFoundError:
    energy = None


class SolarDiscoveryTests(unittest.TestCase):
    def test_accepts_physical_solar_sensor(self):
        state = {"entity_id": "sensor.pvs6_inverter_power", "attributes": {
            "friendly_name": "PVS6 Inverter Power", "device_class": "power"}}
        self.assertTrue(solar.is_solar(state))

    def test_rejects_automation_with_solar_word(self):
        state = {"entity_id": "automation.solar_frequency_alert", "attributes": {
            "friendly_name": "Solar frequency alert"}}
        self.assertFalse(solar.is_solar(state))

    def test_rejects_financial_derivative(self):
        state = {"entity_id": "sensor.pvs6_lifetime_power_cost", "attributes": {
            "friendly_name": "PVS6 Lifetime Power Cost"}}
        self.assertFalse(solar.is_solar(state))


@unittest.skipIf(energy is None, "aiohttp not installed")
class EnergyIngressTests(unittest.TestCase):
    def test_root_audit_route_is_registered(self):
        resources = [resource.canonical for resource in energy.app.router.resources()]
        self.assertIn("/api/audit", resources)


if __name__ == "__main__":
    unittest.main()
