#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import requests


def main() -> int:
    p = argparse.ArgumentParser(description="Analyze screenshot with Gemini")
    p.add_argument("image", help="Path to image")
    p.add_argument("--token-file", default="/home/pi/token.key")
    p.add_argument("--model", default="gemini-2.5-flash")
    p.add_argument("--prompt", default="Read this screen exactly. Return: visible title, selected row text, footer text, and playback clues.")
    p.add_argument("--out-json", default="")
    args = p.parse_args()

    image_path = Path(args.image)
    token = Path(args.token_file).read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("token file is empty")
    data = base64.b64encode(image_path.read_bytes()).decode("ascii")

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": args.prompt},
                    {"inline_data": {"mime_type": "image/png", "data": data}},
                ],
            }
        ]
    }

    models = [
        args.model,
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.5-pro",
    ]
    body = None
    last_err = None
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={token}"
        resp = requests.post(url, json=payload, timeout=60)
        if resp.ok:
            body = resp.json()
            break
        last_err = f"{resp.status_code} {resp.text[:240]}"
    if body is None:
        raise RuntimeError(f"Gemini request failed: {last_err}")

    text = ""
    for cand in body.get("candidates", []):
        content = cand.get("content", {})
        for part in content.get("parts", []):
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text += part["text"] + "\n"

    print(text.strip() or json.dumps(body, indent=2))
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(body, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
