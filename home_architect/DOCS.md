# Home Architect

Home Architect is a local, text-first Home Assistant sidebar assistant. It connects to an Ollama server, retrieves task-relevant Home Assistant entity context, and answers solar, climate, and energy questions.

## Setup

Configure `ollama_url` with an Ollama endpoint reachable from this App container and select a model such as `qwen3:8b`. The default assumes a resolvable host named `ollama`; replace it with the hostname or IP exposed by your Ollama App. `localhost` normally will not reach a separate App.

Version 0.1.0 does not execute changes. Configuration and automation requests are stored as pending review issues with the assistant's proposal, validation steps, and rollback plan.
