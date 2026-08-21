# Solar Assistant Grafana dashboards

Import each JSON file using Grafana, Dashboards, New, Import:

- solar-production-central.json
- solar-health-central.json

At import time, select either verified InfluxDB datasource. The production
dashboard supports the common Home Assistant power measurements W and state
through its Power measurement variable.

The health dashboard expects a solar_assistant_health measurement. The supplied
Node-RED flow prepares this payload but deliberately leaves the final InfluxDB
writer unconnected until authentication and the retention policy are verified.

Do not treat an empty dashboard as evidence of zero production. First verify the
datasource, then SHOW MEASUREMENTS, and select the actual measurement name.
