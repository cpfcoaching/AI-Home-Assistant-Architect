import importlib.util, unittest
from pathlib import Path

try:
    spec=importlib.util.spec_from_file_location("energy",Path(__file__).parents[1]/"energy_troubleshooter"/"app.py")
    app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
except ModuleNotFoundError:
    app=None

@unittest.skipIf(app is None,"aiohttp not installed")
class EnergyTests(unittest.TestCase):
    def test_detects_kwh_usage_as_cost(self):
        prefs={"energy_sources":[{"type":"grid","stat_energy_from":"sensor.pvs6","entity_energy_from_cost":"sensor.smarthub_monthly_usage"}]}
        stats=[{"statistic_id":"smarthub:usage_hourly","statistics_unit_of_measurement":"kWh"}]
        titles=[x["title"] for x in app.analyze(prefs,stats,{})]
        self.assertIn("Grid import is not using SmartHub",titles)
        self.assertIn("Energy usage selected as cost",titles)
