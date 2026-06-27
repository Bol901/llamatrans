"""Translation client for an LM Studio (OpenAI-compatible) backend."""

from __future__ import annotations

import base64
import mimetypes
import requests
from typing import List


# Default remote endpoint: a local LM Studio server. Override in the UI.
DEFAULT_BASE_URL = "http://localhost:1234"
DEFAULT_MODEL = "hy-mt2-1.8b"
DEFAULT_OCR_MODEL = "glm-ocr"

# Hard cap on characters sent in a single request so the small model stays
# coherent. Long paragraphs get split on sentence boundaries.
MAX_CHARS = 1200


class TranslationError(Exception):
    pass


class Translator:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL,
                 ocr_model: str = DEFAULT_OCR_MODEL, ocr_base_url: str | None = None,
                 timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.ocr_model = ocr_model
        # OCR may live on a different endpoint (e.g. a separate local server)
        self.ocr_base_url = (ocr_base_url or base_url).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    # -- public API -----------------------------------------------------

    def list_models(self, base_url: str | None = None) -> List[str]:
        url = f"{(base_url or self.base_url).rstrip('/')}/v1/models"
        try:
            r = self._session.get(url, timeout=15)
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", [])]
        except requests.RequestException as e:
            raise TranslationError(f"无法连接到模型服务: {e}") from e

    def translate_block(self, text: str) -> str:
        """Translate one block, splitting it further if it is very long."""
        chunks = _split_long(text, MAX_CHARS)
        return "".join(self._translate_chunk(c) for c in chunks)

    def ocr_image(self, path: str) -> str:
        """Recognise text in an image via the vision OCR model."""
        with open(path, "rb") as f:
            data = f.read()
        b64 = base64.b64encode(data).decode("ascii")
        mime = mimetypes.guess_type(path)[0] or "image/png"
        prompt = (
            "Extract all text from this image and format it as clean Markdown.\n"
            "- Use Markdown structure: '#' headings, '-' or '1.' lists, "
            "**bold**, *italic*, and Markdown tables where appropriate.\n"
            "- Preserve the original reading order.\n"
            "- For superscripts such as citation or footnote numbers, use "
            "Unicode superscript characters (e.g. ¹ ² ³). "
            "Do NOT use LaTeX or $...$ math notation.\n"
            "- Output only the Markdown content. Do not wrap it in code fences "
            "and do not add any explanations or comments."
        )
        payload = {
            "model": self.ocr_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }],
            "temperature": 0.1,
            "stream": False,
        }
        url = f"{self.ocr_base_url}/v1/chat/completions"
        try:
            r = self._session.post(url, json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            raise TranslationError(f"OCR 请求失败: {e}") from e
        try:
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise TranslationError(f"无法解析 OCR 响应: {data}") from e
        return _strip_code_fence(content)

    # -- internals ------------------------------------------------------

    def _translate_chunk(self, text: str) -> str:
        prompt = (
            "Translate the following text into Simplified Chinese. "
            "Preserve the original meaning, tone and formatting. "
            "Output only the translation with no explanations or notes.\n\n"
            f"{text}"
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "stream": False,
        }
        url = f"{self.base_url}/v1/chat/completions"
        try:
            r = self._session.post(url, json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            raise TranslationError(f"翻译请求失败: {e}") from e

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise TranslationError(f"无法解析模型响应: {data}") from e


def _strip_code_fence(text: str) -> str:
    """Remove a wrapping ```markdown ... ``` fence if the model added one."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        # drop the opening fence line (``` or ```markdown)
        lines = lines[1:]
        # drop the closing fence line if present
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _split_long(text: str, max_chars: int) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    import re

    # split on sentence enders (keep the punctuation)
    sentences = re.split(r"(?<=[.!?。！？\n])\s+", text)
    chunks: List[str] = []
    cur = ""
    for s in sentences:
        if not s:
            continue
        if len(cur) + len(s) + 1 > max_chars and cur:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    # final hard guard for a single monster sentence
    final: List[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            final.append(c)
        else:
            final.extend(c[i:i + max_chars] for i in range(0, len(c), max_chars))
    return final
