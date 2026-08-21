# Solar Assistant Node-RED flow

Import solar_assistant_monitoring.json using Node-RED, menu, Import, Clipboard.

After import, open Persistent notification and select the existing Home
Assistant server. Deploy, trigger Poll every 5 minutes once, and inspect Central
monitoring payload.

The flow calls the internal app endpoint:

    http://7fb12d67-solar-sentinel:8099/api/status

It sends persistent notifications only for degraded and critical findings,
suppresses identical alerts for six hours, and emits a normalized health payload
through To verified InfluxDB writer.

Do not connect that output to an InfluxDB node until the database, credentials,
and retention policy have passed their connection tests.
