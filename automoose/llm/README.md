# llm/ — provider-agnostic model client (W7a)

Uniform `complete(messages, tools, model, ...)` that dispatches to Anthropic,
any OpenAI-compatible endpoint, or a local server (vLLM). The model name lives
in `config.env` and is recorded in run metadata — never hard-coded.
