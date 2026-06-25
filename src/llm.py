"""Thin OpenAI wrapper shared by ingest / enrich / brief.

Keeps the API surface tiny: read the key from the environment, send one
system+user chat, and defensively parse JSON out of the response.
"""
from __future__ import annotations

import json
import os
import re


def have_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def get_client():
    from openai import OpenAI  # lazy import so non-LLM code paths need no SDK
    if not have_key():
        raise RuntimeError("OPENAI_API_KEY not set — copy .env.example to .env and add your key")
    return OpenAI()


def chat(system: str, user: str, model: str, temperature: float = 0) -> str:
    resp = get_client().chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content


def strip_fences(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def loads_array(content: str) -> list:
    data = json.loads(strip_fences(content))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):  # tolerate {"reviews": [...]} style wrapping
        for value in data.values():
            if isinstance(value, list):
                return value
        return [data]
    raise ValueError("expected a JSON array")


def loads_object(content: str) -> dict:
    data = json.loads(strip_fences(content))
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data
