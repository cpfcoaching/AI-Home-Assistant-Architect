# Solar Sentinel

Solar Sentinel discovers solar-related Home Assistant entities and assigns conservative health scores based on availability, telemetry freshness, daylight, and performance relative to peer inverters.

## Health model

- Production is evaluated only while the sun is above the configured minimum elevation.
- Each inverter is compared with the median output of the inverter fleet.
- A low peer ratio must persist for the configured duration before it becomes a degraded or critical finding.
- The fixed watt threshold is used only as a fallback when too few peer inverters are available.
- Ollama explains deterministic findings; it does not decide whether equipment is unhealthy.

## Boundaries

- Read-only. It cannot control equipment or edit automations.
- Peer groups currently include all discovered inverter power sensors; roof-orientation groups and weather-normalized seasonal baselines remain future work.
- Warranty evidence follows longer-term baseline validation.

## Installation

Add this repository in **Settings → Apps → Install app → Repositories**, install Solar Sentinel, start it, and enable **Show in sidebar**.

The app uses Home Assistant's internal Supervisor API. It does not require a long-lived access token.
