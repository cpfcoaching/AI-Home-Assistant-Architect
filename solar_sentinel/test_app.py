import unittest
from datetime import datetime, timedelta, timezone

import app


def power_state(entity_id, value, unit="W"):
    return {
        "entity_id": entity_id,
        "state": str(value),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "attributes": {
            "friendly_name": "Inverter " + entity_id.rsplit("_", 1)[-1],
            "device_class": "power",
            "unit_of_measurement": unit,
        },
    }


class SolarHealthTests(unittest.TestCase):
    def setUp(self):
        app.breaches.clear()
        self.cfg = app.options()
        self.now = datetime.now(timezone.utc)

    def test_power_unit_conversion(self):
        self.assertEqual(app.watts_for(power_state("sensor.inverter_1", 1.25, "kW")), 1250)

    def test_ipv4_is_not_mistaken_for_pv(self):
        state = {
            "entity_id": "sensor.system_monitor_ipv4_address_lo",
            "state": "127.0.0.1",
            "attributes": {"friendly_name": "System Monitor IPv4 address lo"},
        }
        self.assertFalse(app.is_solar(state))

    def test_placeholder_inverter_is_not_a_panel(self):
        state = power_state("sensor.inverter_n_a_power", "unavailable", "kW")
        self.assertFalse(app.is_inverter_power(state))

    def test_real_unavailable_inverter_remains_monitored(self):
        state = power_state("sensor.inverter_e001_power", "unavailable", "kW")
        self.assertTrue(app.is_inverter_power(state))

    def test_binary_inverter_state_is_not_power_telemetry(self):
        state = power_state("binary_sensor.inverter_e001_state", "on", "W")
        self.assertFalse(app.is_inverter_power(state))

    def test_fleet_staleness_becomes_one_incident(self):
        assets = [{"entity_id": "sensor.inverter_%d_power" % i} for i in range(4)]
        findings = [
            {"entity_id": item["entity_id"], "severity": "degraded", "symptoms": ["Telemetry stale for 60 minutes"]}
            for item in assets
        ]
        incidents = app.grouped_incidents(assets, findings)
        self.assertEqual(len(incidents), 1)
        self.assertIn("one communications incident", incidents[0]["action"])

    def test_low_output_is_not_penalized_at_night(self):
        score, symptoms, ratio, _, _ = app.assess(
            power_state("sensor.inverter_1", 0), self.cfg,
            {"daylight": False, "solar_elevation": -20}, 200, self.now
        )
        self.assertEqual(score, 100)
        self.assertEqual(symptoms, [])
        self.assertIsNone(ratio)

    def test_peer_anomaly_starts_as_observation(self):
        score, symptoms, ratio, _, _ = app.assess(
            power_state("sensor.inverter_1", 100), self.cfg,
            {"daylight": True, "solar_elevation": 40}, 200, self.now
        )
        self.assertEqual(score, 90)
        self.assertEqual(ratio, 0.5)
        self.assertIn("under observation", symptoms[0])

    def test_persistent_severe_peer_anomaly_is_critical(self):
        state = power_state("sensor.inverter_1", 80)
        app.breaches[state["entity_id"]] = self.now - timedelta(minutes=31)
        score, symptoms, ratio, _, _ = app.assess(
            state, self.cfg, {"daylight": True, "solar_elevation": 40}, 200, self.now
        )
        self.assertLess(score, 40)
        self.assertEqual(ratio, 0.4)
        self.assertIn("31 minutes", symptoms[0])


if __name__ == "__main__":
    unittest.main()
