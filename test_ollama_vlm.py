#!/usr/bin/env python3
"""Minimal OpenAI-compatible VLM test for the local Ollama server.

Examples:
  python test_ollama_vlm.py
  python test_ollama_vlm.py --model qwen2.5vl:32b
  python test_ollama_vlm.py --endpoint http://localhost:11435/v1 --model llava:7b
"""

import argparse
import json
import time
import urllib.error
import urllib.request

# 1x1 red PNG, enough to verify OpenAI image_url handling.
RED_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1Pe"
    "AAAADUlEQVR42mP8z8BQDwAFgwJ/lrWf9wAAAABJRU5ErkJggg=="
)

def request_json(url, payload, timeout):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, time.time() - started, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, time.time() - started, body
    except Exception as exc:
        return "EXCEPTION", time.time() - started, repr(exc)


def parse_response(body):
    try:
        data = json.loads(body)
    except Exception:
        return {"raw": body[:1000]}

    if "error" in data:
        return {"error": data["error"]}

    msg = data.get("choices", [{}])[0].get("message", {})
    return {
        "content": msg.get("content"),
        "reasoning": msg.get("reasoning"),
        "finish_reason": data.get("choices", [{}])[0].get("finish_reason"),
        "usage": data.get("usage"),
    }


def test_text(endpoint, model, timeout):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply exactly: OK"}],
        "temperature": 0,
        "max_tokens": 32,
    }
    return request_json(f"{endpoint}/chat/completions", payload, timeout)


def test_image(endpoint, model, timeout):
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "What color is this image? Reply with one word.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64," + RED_PNG_BASE64,
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 64,
    }
    return request_json(f"{endpoint}/chat/completions", payload, timeout)


def get_models(endpoint, timeout):
    url = endpoint.rstrip("/").rsplit("/", 1)[0] + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"error": repr(exc), "url": url}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://localhost:11435/v1")
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Model to test. Can be repeated. Defaults to installed candidates.",
    )
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    endpoint = args.endpoint.rstrip("/")
    models = args.models or ["qwen2.5vl:32b", "qwen3.5:27b", "llava:7b"]

    print(f"Endpoint: {endpoint}")
    print("\nInstalled models / API tags:")
    print(json.dumps(get_models(endpoint, 5), ensure_ascii=False, indent=2)[:4000])

    for model in models:
        print(f"\n===== MODEL: {model} =====")

        status, elapsed, body = test_text(endpoint, model, args.timeout)
        print(f"\n[TEXT] status={status} elapsed={elapsed:.2f}s")
        print(json.dumps(parse_response(body), ensure_ascii=False, indent=2)[:2000])

        status, elapsed, body = test_image(endpoint, model, args.timeout)
        print(f"\n[IMAGE_URL] status={status} elapsed={elapsed:.2f}s")
        print(json.dumps(parse_response(body), ensure_ascii=False, indent=2)[:2000])


if __name__ == "__main__":
    main()
