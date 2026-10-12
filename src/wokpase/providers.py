from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from wokpase.config import AgentConfig, AppConfig


class AIRequestError(RuntimeError):
    """An AI provider request failed or returned an invalid response."""


def generate(config: AppConfig, agent: AgentConfig, prompt: str) -> str:
    key = config.api_key(agent.provider)
    if agent.provider == "gemini":
        return _generate_gemini(agent.model, key, prompt)
    if agent.provider == "groq":
        return _generate_groq(agent.model, key, prompt)
    raise AIRequestError(f"provider tidak didukung: {agent.provider}")


def _post_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise AIRequestError(f"provider membalas HTTP {error.code}: {detail}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise AIRequestError(f"permintaan AI gagal: {error}") from error
    if not isinstance(result, dict):
        raise AIRequestError("provider mengembalikan respons yang tidak valid")
    return result


def _generate_gemini(model: str, key: str, prompt: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(model, safe='')}:generateContent?"
        f"key={urllib.parse.quote(key, safe='')}"
    )
    result = _post_json(
        url,
        {"contents": [{"parts": [{"text": prompt}]}]},
        {},
    )
    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as error:
        raise AIRequestError("respons Gemini tidak berisi teks") from error


def _generate_groq(model: str, key: str, prompt: str) -> str:
    result = _post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        {"Authorization": f"Bearer {key}"},
    )
    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise AIRequestError("respons Groq tidak berisi teks") from error
