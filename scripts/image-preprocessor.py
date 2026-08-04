#!/usr/bin/env python3
"""
image-preprocessor — AgentOS pipeline stage for vision.

Detects image_url content in chat messages, calls OpenAI GPT-4o to describe
the image, and replaces the image with a text description so the downstream
LLM (deepseek-v4-flash, which has no vision) can understand what's in the image.

Usage:
  # As a pipe: read a chat completion body from stdin, write modified body to stdout
  cat body.json | python3 image-preprocessor.py

  # As a library:
  from image_preprocessor import preprocess_messages
  messages = [{"role": "user", "content": [{"type": "image_url", ...}]}]
  modified = preprocess_messages(messages)
"""

import json
import logging
import os
import subprocess
import sys
import urllib.request
import base64

logger = logging.getLogger("image-preprocessor")

# OpenAI API config
_OPENAI_MODEL = "gpt-4o"
_OPENAI_API_KEY = None  # resolved on first use


def _get_api_key() -> str:
    global _OPENAI_API_KEY
    if _OPENAI_API_KEY is not None:
        return _OPENAI_API_KEY
    # Try: keychain → env
    try:
        key = subprocess.check_output(
            ["security", "find-generic-password", "-s", "openai-api-key", "-w"],
            stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip()
        if key:
            _OPENAI_API_KEY = key
            return key
    except Exception:
        pass
    env_key = os.environ.get("OPENAI_API_KEY", "")
    if env_key:
        _OPENAI_API_KEY = env_key
        return env_key
    raise RuntimeError("No OpenAI API key found (keychain openai-api-key or OPENAI_API_KEY env)")


def _has_image_content(content) -> bool:
    """Check if a message content contains image_url parts."""
    if isinstance(content, str):
        return False
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                return True
    return False


def _describe_image(image_url: str, context: str = "") -> str:
    """Call OpenAI GPT-4o to describe an image. Returns a text description."""
    key = _get_api_key()
    system_prompt = (
        "You are an image description assistant. Describe the image in detail "
        "so that someone who cannot see it can understand its contents. "
        "Focus on: what is shown, the composition, colors, text, people/objects, "
        "and any notable details. Be concise but complete (2-5 sentences)."
    )
    user_content = [{"type": "image_url", "image_url": {"url": image_url}}]
    if context:
        user_content.insert(0, {"type": "text", "text": context})

    payload = json.dumps({
        "model": _OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "max_tokens": 500,
    }).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
        description = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        return description.strip() if description else "[Image description failed]"
    except Exception as e:
        logger.error(f"OpenAI vision call failed: {e}")
        return f"[Image description error: {e}]"


def preprocess_messages(messages: list, context: str = "") -> list:
    """Process a list of messages, replacing image_url content with text descriptions.

    Args:
        messages: List of message dicts (OpenAI chat format)
        context: Optional context text to prepend to each image description request

    Returns:
        Modified messages with images replaced by text descriptions
    """
    modified = []
    for msg in messages:
        content = msg.get("content", "")
        if not _has_image_content(content):
            modified.append(msg)
            continue

        # Extract text parts and image URLs
        text_parts = []
        image_urls = []
        for part in content if isinstance(content, list) else [content]:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
                elif part.get("type") == "image_url":
                    image_urls.append(part["image_url"]["url"])

        combined_text = " ".join(text_parts) if text_parts else ""

        # Describe each image
        descriptions = []
        for i, url in enumerate(image_urls):
            prefix = f"Image {i+1}/{len(image_urls)}: "
            desc = prefix + _describe_image(url, context=combined_text)
            descriptions.append(desc)

        # Build the replacement text message
        new_text = ""
        if text_parts:
            new_text += "\n".join(text_parts) + "\n\n"
        new_text += "---\n[This message contained images. The following descriptions were generated by a vision model:]\n"
        new_text += "\n\n".join(descriptions)
        new_text += "\n---"

        modified.append({
            "role": msg.get("role", "user"),
            "content": new_text
        })

    return modified


def preprocess_body(body: dict) -> dict:
    """Process a full chat completion request body, modifying messages in place.

    Returns the modified body (same dict reference, mutated).
    """
    messages = body.get("messages", [])
    if not messages:
        return body

    # Check if any message has image content
    has_image = any(_has_image_content(m.get("content", "")) for m in messages)
    if not has_image:
        return body

    context = body.get("user_msg", "")
    body["messages"] = preprocess_messages(messages, context=context)
    logger.info(f"image-preprocessor: replaced {sum(1 for m in body['messages'] if '---' in str(m.get('content','')))} messages with image descriptions")
    return body


def main():
    """CLI entry point: read JSON body from stdin, write modified body to stdout."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    try:
        body = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        sys.exit(1)

    modified = preprocess_body(body)
    json.dump(modified, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()