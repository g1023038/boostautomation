import os
import requests

# Pinned deliberately -- do not switch to a floating alias like "claude-3-5-sonnet-latest".
# Generated test cases and scripts must be reproducible across runs.
MODEL = "claude-3-5-sonnet-20241022"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def call_llm(system_prompt, user_prompt, max_tokens=4096):
    r = requests.post(ANTHROPIC_URL, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }, json={
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    })
    r.raise_for_status()
    return r.json()["content"][0]["text"]
