# Home Architect

Home Architect is a local, text-first Home Assistant sidebar assistant. It connects to an Ollama server, retrieves task-relevant Home Assistant context, and answers solar, climate, and energy questions.

Version 0.2.0 joins the Home Assistant entity, device, area, and floor registries. Climate proposals prioritize real temperature and HVAC entities with known locations. A change proposal is not added to the review queue if it references an entity ID that does not exist in Home Assistant.

Version 0.2.1 requires a verified indoor temperature sensor for the upper, main, and lower floors before a three-floor mapping can enter the review queue. Equipment temperatures such as solar inverter, battery, CPU, GPU, and drive sensors are excluded. While viewing review issues, **Clear** now clears the review queue rather than chat history.

## Setup

Configure `ollama_url` with an Ollama endpoint reachable from this App container and select a model such as `qwen3:8b`. The default assumes a resolvable host named `ollama`; replace it with the hostname or IP exposed by your Ollama App. `localhost` normally will not reach a separate App.

Home Architect does not execute changes. Configuration and automation requests are stored as pending review issues with the assistant's proposal, validated entity list, registry status, validation steps, and rollback plan.
