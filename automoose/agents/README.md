# agents/ — explicit f1–f5 orchestrator (W7b)

Headless pipeline: prompt → Architect(f1) → InputWriter(f2) → Runner(f3)
→ Reviewer(f4) → Visualization(f5). Calls `llm/` for reasoning and the existing
FastAPI / MCP tools for actions, so the whole agentic loop runs on any configured
model (closed or open) without depending on a desktop MCP client.
