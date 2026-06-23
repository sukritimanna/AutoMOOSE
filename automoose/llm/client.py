"""Provider-agnostic LLM client (W7a).

Uniform interface over Anthropic and OpenAI-compatible (vLLM / nersc-chat)
backends. Model identity, endpoint and key come from config.env, never
hard-coded. Token usage recorded on every call for the comparison table.
"""
from __future__ import annotations
import os, time
from dataclasses import dataclass
from typing import Iterator, List, Dict, Optional


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_s: float = 0.0


class LLMClient:
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None,
                 base_url: Optional[str] = None, api_key: Optional[str] = None,
                 max_tokens: int = 1500):
        self.provider = (provider or os.environ.get("LLM_PROVIDER", "anthropic")).lower()
        self.model = model or os.environ.get("LLM_MODEL", "claude-sonnet-4-5")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL") or None
        self.api_key = (api_key or os.environ.get("LLM_API_KEY")
                        or os.environ.get("ANTHROPIC_API_KEY", ""))
        self.max_tokens = int(os.environ.get("LLM_MAX_TOKENS", max_tokens))
        self.last_usage = Usage()
        self._client = None

    def _anthropic(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _openai(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key or "EMPTY")
        return self._client

    @staticmethod
    def _with_system(system: Optional[str], messages: List[Dict]) -> List[Dict]:
        if system:
            return [{"role": "system", "content": system}] + list(messages)
        return list(messages)

    def complete(self, system: Optional[str], messages: List[Dict],
                 max_tokens: Optional[int] = None) -> str:
        mt = max_tokens or self.max_tokens
        t0 = time.time()
        if self.provider == "anthropic":
            resp = self._anthropic().messages.create(
                model=self.model, max_tokens=mt, system=system or "", messages=messages)
            text = resp.content[0].text
            u = resp.usage
            self.last_usage = Usage(u.input_tokens, u.output_tokens,
                                    u.input_tokens + u.output_tokens, time.time() - t0)
        else:
            resp = self._openai().chat.completions.create(
                model=self.model, max_tokens=mt, messages=self._with_system(system, messages))
            text = resp.choices[0].message.content
            u = resp.usage
            self.last_usage = Usage(u.prompt_tokens, u.completion_tokens,
                                    u.total_tokens, time.time() - t0)
        return text

    def stream(self, system: Optional[str], messages: List[Dict],
               max_tokens: Optional[int] = None) -> Iterator[str]:
        mt = max_tokens or self.max_tokens
        t0 = time.time()
        if self.provider == "anthropic":
            with self._anthropic().messages.stream(
                    model=self.model, max_tokens=mt, system=system or "",
                    messages=messages) as s:
                for chunk in s.text_stream:
                    yield chunk
                u = s.get_final_message().usage
                self.last_usage = Usage(u.input_tokens, u.output_tokens,
                                        u.input_tokens + u.output_tokens, time.time() - t0)
        else:
            s = self._openai().chat.completions.create(
                model=self.model, max_tokens=mt, messages=self._with_system(system, messages),
                stream=True, stream_options={"include_usage": True})
            pt = ct = tt = 0
            for ev in s:
                if ev.choices and ev.choices[0].delta and ev.choices[0].delta.content:
                    yield ev.choices[0].delta.content
                if getattr(ev, "usage", None):
                    pt, ct, tt = (ev.usage.prompt_tokens, ev.usage.completion_tokens,
                                  ev.usage.total_tokens)
            self.last_usage = Usage(pt, ct, tt, time.time() - t0)


_default: Optional[LLMClient] = None


def get_client() -> LLMClient:
    global _default
    if _default is None:
        _default = LLMClient()
    return _default
