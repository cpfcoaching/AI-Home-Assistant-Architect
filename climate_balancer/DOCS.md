# Whole-Home Climate Balancer

This read-only MVP models the Kevin V299 as three thermal levels: lower recreation floor, main living floor, and upper bedroom floor.

Configure comma-separated temperature entity IDs for each level. The dashboard reports averages, upper-floor comfort targets, imbalance, HVAC/fan inventory, and circulation recommendations.

Version 0.1.2 accepts both numeric temperature sensors and `climate.*` thermostat entities. For thermostats, the dashboard reads the `current_temperature` attribute.

Version 0.1.0 never changes thermostat settings and never starts fans.
