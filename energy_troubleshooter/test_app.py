import unittest
import sys
import types


class DummyRouter:
    def add_get(self, *args, **kwargs):
        pass


fake_aiohttp = types.ModuleType("aiohttp")
fake_aiohttp.ClientSession = object
fake_aiohttp.WSMsgType = types.SimpleNamespace(TEXT="text")
fake_aiohttp.web = types.SimpleNamespace(
    Application=lambda: types.SimpleNamespace(router=DummyRouter()),
    json_response=lambda *args, **kwargs: None,
    Response=lambda *args, **kwargs: None,
    run_app=lambda *args, **kwargs: None,
)
sys.modules.setdefault("aiohttp", fake_aiohttp)

import app


class EnergyTroubleshooterTests(unittest.TestCase):
    def test_empty_nested_validation_slots_are_ignored(self):
        self.assertEqual(app.validation_issues({"energy_sources": [[], [], {}]}), [])

    def test_meaningful_validation_leaf_is_reported(self):
        issues = app.validation_issues({"energy_sources": [[], [{"error": "unit mismatch"}]]})
        self.assertEqual(len(issues), 1)
        self.assertIn("unit mismatch", issues[0]["message"])

    def test_matching_pvs_meter_family_passes_consistency_check(self):
        prefs = {"energy_sources": [{
            "type": "grid",
            "stat_energy_from": "sensor.power_meter_pvs6_kwh_to_home",
            "stat_energy_to": "sensor.power_meter_pvs6_kwh_to_grid",
        }]}
        findings, overview, issues = app.analyze(prefs, [], {"energy_sources": [[], []]})
        self.assertEqual(overview["import"]["family"], "PVS local meter")
        self.assertEqual(overview["export"]["family"], "PVS local meter")
        self.assertEqual(issues, [])
        self.assertEqual(findings[0]["severity"], "healthy")

    def test_mixed_meter_families_are_explained(self):
        prefs = {"energy_sources": [{
            "type": "grid",
            "stat_energy_from": "smarthub:hourly_usage",
            "stat_energy_to": "sensor.power_meter_pvs6_kwh_to_grid",
        }]}
        findings, _, _ = app.analyze(prefs, [], {})
        titles = [item["title"] for item in findings]
        self.assertIn("Import and export use different meter families", titles)


if __name__ == "__main__":
    unittest.main()
