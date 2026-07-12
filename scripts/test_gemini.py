#!/usr/bin/env python3
"""
Standalone Gemini key validation script.

Loads GEMINI_API_KEY from .env and sends a single JSON-formatted
probe to the free-tier v1beta endpoint. Exits 0 on success, 1 on failure.
"""

import os
import sys
import json

# ensure project root is importable so pydantic-settings picks up .env
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
PROBE = 'Return a JSON object with {"status": "ok"}'


def main() -> int:
    from src.config import settings

    key = settings.gemini_api_key
    if not key:
        print("✗ GEMINI_API_KEY is empty in .env")
        return 1

    if not key.startswith("AIza") and not key.startswith("AQ."):
        print("✗ GEMINI_API_KEY does not start with 'AIza' or 'AQ.' — likely invalid")
        return 1

    print(f"  key prefix: {key[:8]}...")
    print(f"  endpoint:   {ENDPOINT}")

    payload = {
        "contents": [{"role": "user", "parts": [{"text": PROBE}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1,
            "maxOutputTokens": 200,
        },
    }

    try:
        resp = httpx.post(
            ENDPOINT,
            params={"key": key},
            json=payload,
            timeout=15,
        )
    except httpx.TimeoutException:
        print("✗ Request timed out after 15s")
        return 1
    except httpx.RequestError as e:
        print(f"✗ Network error: {e}")
        return 1

    print(f"  HTTP {resp.status_code}")

    if resp.status_code == 200:
        try:
            data = resp.json()
            candidate = data["candidates"][0]
            text = candidate["content"]["parts"][0]["text"]
            finish = candidate.get("finishReason", "unknown")
            print(f"  finishReason: {finish}")
            print(f"  content:      {text[:200]}")
            # validate it's parseable JSON
            parsed = json.loads(text.strip())
            if parsed.get("status") == "ok":
                print("✓ Gemini key is valid and returned expected JSON")
                return 0
            else:
                print(f"✗ Unexpected JSON content: {parsed}")
                return 1
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            print(f"✗ Failed to parse response: {e}")
            print(f"  raw snippet: {resp.text[:300]}")
            return 1
    elif resp.status_code == 400:
        body = resp.text[:500]
        if "API_KEY_INVALID" in body:
            print("✗ Gemini says: API_KEY_INVALID — the key is dead, generate a new one")
        else:
            print(f"✗ HTTP 400 — likely payload issue. Body:\n{body}")
        return 1
    elif resp.status_code == 429:
        print("✗ HTTP 429 — quota exhausted. Wait or use a different key")
        return 1
    else:
        print(f"✗ Unexpected status. Body:\n{resp.text[:500]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
