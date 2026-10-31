"""Provider-agnostic text completion for the judge.

JUDGE_PROVIDER: groq (default), openai or anthropic. For any OpenAI-compatible endpoint use
openai with JUDGE_BASE_URL and JUDGE_KEY_ENV (name of the env var holding that key).
"""
import os

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.environ.get("JUDGE_PROVIDER", "groq")
EFFORT = os.environ.get("JUDGE_EFFORT", "low") or None
_clients = {}


class RateLimited(Exception):
    def __init__(self, message, wait=None):
        super().__init__(message)
        self.wait = wait


class LLMError(Exception):
    pass


def _client(name, factory):
    if name not in _clients:
        _clients[name] = factory()
    return _clients[name]


def _wait(e):
    try:
        return float(e.response.headers.get("retry-after"))
    except (AttributeError, TypeError, ValueError):
        return None


def _groq(prompt, model):
    from groq import APIError, Groq, RateLimitError

    client = _client("groq", lambda: Groq(api_key=os.environ.get("GROQ_API_KEY")))
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            extra_body={"reasoning_effort": EFFORT} if EFFORT else None,
        )
        return (r.choices[0].message.content or "").strip()
    except RateLimitError as e:
        raise RateLimited(str(e), _wait(e)) from e
    except APIError as e:
        raise LLMError(str(e)) from e


def _openai(prompt, model):
    from openai import APIError, BadRequestError, OpenAI, RateLimitError

    def make():
        key_env = os.environ.get("JUDGE_KEY_ENV", "OPENAI_API_KEY")
        return OpenAI(base_url=os.environ.get("JUDGE_BASE_URL") or None, api_key=os.environ[key_env])

    client = _client("openai", make)
    kwargs = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    try:
        try:
            r = client.chat.completions.create(temperature=0, **kwargs)
        except BadRequestError as e:
            if "temperature" not in str(e).lower():
                raise
            r = client.chat.completions.create(**kwargs)
        return (r.choices[0].message.content or "").strip()
    except RateLimitError as e:
        raise RateLimited(str(e), _wait(e)) from e
    except APIError as e:
        raise LLMError(str(e)) from e


def _anthropic(prompt, model):
    import anthropic

    client = _client("anthropic", anthropic.Anthropic)
    kwargs = {"model": model, "max_tokens": 1000, "messages": [{"role": "user", "content": prompt}]}
    try:
        try:
            msg = client.messages.create(temperature=0, **kwargs)
        except (TypeError, anthropic.BadRequestError):
            msg = client.messages.create(**kwargs)
        return "".join(b.text for b in msg.content if b.type == "text").strip()
    except anthropic.RateLimitError as e:
        raise RateLimited(str(e), _wait(e)) from e
    except anthropic.APIError as e:
        raise LLMError(str(e)) from e


def complete(prompt, model):
    """Send one prompt and return the reply text. Raises RateLimited or LLMError on API failure."""
    providers = {"groq": _groq, "openai": _openai, "anthropic": _anthropic}
    if PROVIDER not in providers:
        raise RuntimeError(f"unknown JUDGE_PROVIDER: {PROVIDER}")
    return providers[PROVIDER](prompt, model)
