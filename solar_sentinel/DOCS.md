# Solar Sentinel

Solar Sentinel discovers solar-related Home Assistant entities and assigns conservative health scores based on availability, telemetry freshness, and a configured low-production threshold.

## Version 0.1.0 boundaries

- Read-only. It cannot control equipment or edit automations.
- Threshold findings do not yet account for sunrise, weather, or seasonal baselines.
- Warranty evidence and Ollama analysis follow baseline validation.

## Installation

Add this repository in **Settings → Apps → Install app → Repositories**, install Solar Sentinel, start it, and enable **Show in sidebar**.

The app uses Home Assistant's internal Supervisor API. It does not require a long-lived access token.
