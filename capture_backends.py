"""W7b capability-table capture: run one prompt through each backend, record usage."""
import time
from automoose.llm import LLMClient

PROMPT = "In one sentence, what is grain growth?"
SYSTEM = "You are an expert in MOOSE phase-field simulation and grain growth kinetics."

backends = [
    dict(name="Claude (closed)", provider="anthropic",
         model="claude-sonnet-4-5", base_url=None,
         api_key=None),  # uses ANTHROPIC_API_KEY from env
    dict(name="Qwen2.5-32B (open, Perlmutter)", provider="openai",
         model="Qwen/Qwen2.5-32B-Instruct", base_url="http://localhost:8000/v1",
         api_key=None),
]

rows = []
for b in backends:
    name = b.pop("name")
    try:
        c = LLMClient(**b)
        text = c.complete(system=SYSTEM, messages=[{"role": "user", "content": PROMPT}], max_tokens=120)
        u = c.last_usage
        rows.append((name, "OK", u.prompt_tokens, u.completion_tokens, u.total_tokens, round(u.latency_s, 2), text.strip()))
    except Exception as e:
        rows.append((name, f"FAIL: {type(e).__name__}", 0, 0, 0, 0, str(e)[:80]))

print("\n=== Backend capability capture ===")
print(f"{'Backend':<34} {'Status':<8} {'in':>5} {'out':>5} {'tot':>5} {'sec':>6}")
print("-" * 70)
for name, status, pin, pout, tot, sec, _ in rows:
    print(f"{name:<34} {status:<8} {pin:>5} {pout:>5} {tot:>5} {sec:>6}")
print()
for name, status, *_, text in rows:
    print(f"[{name}]\n  {text}\n")
