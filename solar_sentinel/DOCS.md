# Solar Assistant

Solar Assistant discovers panel-level inverter power entities and assigns conservative health scores based on availability, telemetry freshness, daylight, and performance relative to peer inverters.

## Health model

- Production is evaluated only while the sun is above the configured minimum elevation.
- Each inverter is compared with the median output of the inverter fleet.
- A low peer ratio must persist for the configured duration before it becomes a degraded or critical finding.
- The fixed watt threshold is used only as a fallback when too few peer inverters are available.
- Ollama explains deterministic findings; it does not decide whether equipment is unhealthy.
- Static diagnostics, IP addresses, lifetime counters, and placeholder n/a entities are excluded from panel-health alerts.
- Binary state sensors are not treated as changing power telemetry. Fleet-wide stale or unavailable measurements are grouped as one gateway/integration incident.

## Boundaries

- Read-only. It cannot control equipment or edit automations.
- Peer groups currently include all discovered inverter power sensors; roof-orientation groups and weather-normalized seasonal baselines remain future work.
- Warranty evidence follows longer-term baseline validation.

## Installation

Add this repository in **Settings → Apps → Install app → Repositories**, install Solar Assistant, start it, and enable **Show in sidebar**.

The app uses Home Assistant's internal Supervisor API. It does not require a long-lived access token.
