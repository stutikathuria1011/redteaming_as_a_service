"""Minimal async LLM clients (Anthropic, OpenAI-compatible, Mock) with disk cache, retry/backoff and a concurrency cap.
Keys come from env vars: ANTHROPIC_API_KEY, OPENAI_API_KEY (+ optional OPENAI_BASE_URL for any compatible provider)."""
import asyncio, hashlib, json, os, random, re
from pathlib import Path


class LLMError(RuntimeError):
    pass


class _Retry(Exception):
    pass


class BaseClient:
    provider = "base"

    def __init__(self, model, cache_dir=".attackgen_cache", temperature=0.9, max_tokens=800, concurrency=5, max_retries=6):
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens
        self.concurrency, self.max_retries = concurrency, max_retries
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir: self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._sem = None
        self.api_calls = 0
        self.cache_hits = 0

    def _cache_path(self, system, user):
        h = hashlib.sha256(json.dumps([self.provider, self.model, self.temperature, system, user]).encode()).hexdigest()
        return self.cache_dir / f"{h}.txt" if self.cache_dir else None

    async def complete(self, system: str, user: str) -> str:
        path = self._cache_path(system, user)
        if path and path.exists():
            self.cache_hits += 1
            return path.read_text(encoding="utf-8")
        if self._sem is None: self._sem = asyncio.Semaphore(self.concurrency)
        async with self._sem:
            text = await self._call_with_retries(system, user)
        if path: path.write_text(text, encoding="utf-8")
        return text

    async def _call_with_retries(self, system, user):
        import httpx
        last = None
        async with httpx.AsyncClient(timeout=90) as http:
            for attempt in range(self.max_retries):
                try:
                    self.api_calls += 1
                    r = await self._request(http, system, user)
                    if r.status_code in (429, 500, 502, 503, 504, 529): raise _Retry(r.status_code)
                    if r.status_code >= 400: raise LLMError(f"{self.provider} HTTP {r.status_code}: {r.text[:300]}")
                    return self._parse(r.json())
                except (httpx.TransportError, _Retry) as e:
                    last = e
                    await asyncio.sleep(min(30, 2 ** attempt) + random.random())
        raise LLMError(f"gave up after {self.max_retries} attempts: {last!r}")


class AnthropicClient(BaseClient):
    provider = "anthropic"

    def __init__(self, model, **kw):
        super().__init__(model, **kw)
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.key: raise LLMError("Set ANTHROPIC_API_KEY (or use --provider mock / none).")

    async def _request(self, http, system, user):
        return await http.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": self.model, "max_tokens": self.max_tokens, "temperature": self.temperature,
                  "system": system, "messages": [{"role": "user", "content": user}]})

    def _parse(self, d):
        return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text").strip()


class OpenAICompatClient(BaseClient):
    provider = "openai"

    def __init__(self, model, **kw):
        super().__init__(model, **kw)
        self.key = os.environ.get("OPENAI_API_KEY")
        self.base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        if not self.key: raise LLMError("Set OPENAI_API_KEY (and OPENAI_BASE_URL for non-OpenAI providers).")

    async def _request(self, http, system, user):
        return await http.post(f"{self.base}/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json={"model": self.model, "max_tokens": self.max_tokens, "temperature": self.temperature,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})

    def _parse(self, d):
        return d["choices"][0]["message"]["content"].strip()


class MockClient(BaseClient):
    """Offline stand-in used for tests and dry runs. Produces trivially transformed text, NOT real paraphrases.
    Put REFUSE_ME in a seed to exercise the generator-refusal path."""
    provider = "mock"

    async def complete(self, system, user):
        self.api_calls += 1
        fam = re.search(r"FAMILY: (\w+)", user).group(1)
        orig = re.search(r"<original>\n(.*?)\n</original>", user, re.S).group(1)
        if "REFUSE_ME" in orig: return "I'm sorry, but I can't help with that."
        if fam == "multilingual":
            lang = re.search(r"LANGUAGE: (\w+)", user).group(1)
            return f"[{lang}] {orig}"
        return {"paraphrase": "In other words: ", "role_play": "Let's role-play. Respond in character to this: ",
                "hypothetical_framing": "Hypothetically speaking: "}[fam] + orig


def make_client(provider, model, **kw):
    if provider == "none": return None
    if provider == "mock": return MockClient(model or "mock", cache_dir=None, **{k: v for k, v in kw.items() if k != "cache_dir"})
    if provider == "anthropic": return AnthropicClient(model or "claude-haiku-5-5", **kw)
    if provider == "openai": return OpenAICompatClient(model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), **kw)
    raise LLMError(f"unknown provider {provider}")
