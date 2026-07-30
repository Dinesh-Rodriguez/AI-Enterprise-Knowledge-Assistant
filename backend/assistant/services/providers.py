from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import requests
from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class LLMProvider(Protocol):
    def chat(self, messages: list[dict], model: str | None = None) -> str: ...


@dataclass
class LocalEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_normalize_embedding(_pseudo_embedding(text), settings.EMBEDDING_DIMENSIONS) for text in texts]


@dataclass
class LocalLLMProvider:
    def chat(self, messages: list[dict], model: str | None = None) -> str:
        query = next((msg["content"] for msg in reversed(messages) if msg["role"] == "user"), "")
        context_message = next((msg["content"] for msg in messages if msg["content"].startswith("Context:")), "")
        context = context_message.removeprefix("Context:").strip()
        raw_lines = []
        for line in context.splitlines():
            line = line.strip()
            if line and not line.startswith("[") and line not in raw_lines:
                raw_lines.append(line)
        sentences = []
        for line in raw_lines:
            for sentence in line.replace("\n", " ").split(". "):
                sentence = sentence.strip().rstrip(".")
                if len(sentence) > 24 and sentence not in sentences:
                    sentences.append(sentence)
        if not sentences:
            return "I could not find a concise answer in the indexed sources."
        if "summar" in query.lower():
            return "Summary:\n" + "\n".join(f"- {sentence}." for sentence in sentences[:8])
        query_lower = query.lower()
        if "purpose" in query_lower or "role" in query_lower:
            matches = [sentence for sentence in sentences if any(term in sentence.lower() for term in ("responsible", "helps organizations", "employee", "workplace"))]
            if matches:
                return " ".join(matches[:2]) + "."
        if "mean" in query_lower or "what is hr" in query_lower:
            matches = [sentence for sentence in sentences if "human resources" in sentence.lower()]
            if matches:
                return matches[0] + "."
        query_terms = {term for term in query.lower().split() if len(term) > 3}
        relevant = [sentence for sentence in sentences if query_terms.intersection(sentence.lower().split())]
        return (relevant or sentences)[:3][0] + "."


@dataclass
class OpenAIProvider:
    client: OpenAI | None = None

    def _client(self) -> OpenAI:
        if self.client is None:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return self.client

    def chat(self, messages: list[dict], model: str | None = None) -> str:
        response = self._client().responses.create(
            model=model or settings.DEFAULT_LLM_MODEL,
            input=[
                {
                    "role": message["role"],
                    "content": [{"type": "input_text", "text": message["content"]}],
                }
                for message in messages
            ],
        )
        return (response.output_text or "").strip()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self._client().embeddings.create(
            model=settings.DEFAULT_EMBEDDING_MODEL,
            input=texts,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        return [_normalize_embedding(item.embedding, settings.EMBEDDING_DIMENSIONS) for item in response.data]


@dataclass
class GeminiProvider:
    session: requests.Session | None = None

    def _session(self) -> requests.Session:
        if self.session is None:
            self.session = requests.Session()
        return self.session

    def chat(self, messages: list[dict], model: str | None = None) -> str:
        system_instruction = None
        prompt_messages = messages
        if messages and messages[0]["role"] == "system":
            system_instruction = messages[0]["content"]
            prompt_messages = messages[1:]

        payload = {
            "contents": [
                {
                    "parts": [{"text": _messages_to_prompt(prompt_messages)}],
                }
            ]
        }
        if system_instruction:
            payload["system_instruction"] = {
                "parts": [{"text": system_instruction}],
            }
        response = self._session().post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model or settings.GEMINI_LLM_MODEL}:generateContent",
            headers=_gemini_headers(),
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(part.get("text", "") for part in parts).strip()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            response = self._session().post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_EMBEDDING_MODEL}:embedContent",
                headers=_gemini_headers(),
                json={"content": {"parts": [{"text": text}]}, "taskType": "SEMANTIC_SIMILARITY"},
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            values = data["embedding"]["values"] if "embedding" in data else data["embeddings"][0]["values"]
            vectors.append(_normalize_embedding(values, settings.EMBEDDING_DIMENSIONS))
        return vectors


@dataclass
class OllamaProvider:
    session: requests.Session | None = None

    def _session(self) -> requests.Session:
        if self.session is None:
            self.session = requests.Session()
        return self.session

    def chat(self, messages: list[dict], model: str | None = None) -> str:
        response = self._session().post(
            f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
            json={
                "model": model or settings.OLLAMA_LLM_MODEL,
                "messages": messages,
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return (data.get("message", {}) or {}).get("content", "").strip()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self._session().post(
            f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embed",
            json={
                "model": settings.OLLAMA_EMBEDDING_MODEL,
                "input": texts,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return [_normalize_embedding(values, settings.EMBEDDING_DIMENSIONS) for values in data["embeddings"]]


def _normalize_embedding(values: list[float], dimensions: int) -> list[float]:
    values = [float(value) for value in values]
    if len(values) >= dimensions:
        return values[:dimensions]
    return values + [0.0] * (dimensions - len(values))


def _pseudo_embedding(text: str) -> list[float]:
    bucket = [0.0] * settings.EMBEDDING_DIMENSIONS
    for index, char in enumerate(text.lower()):
        bucket[index % settings.EMBEDDING_DIMENSIONS] += (ord(char) % 31) / 31.0
    return bucket


def _messages_to_prompt(messages: list[dict]) -> str:
    return "\n\n".join(f"{message['role'].upper()}: {message['content']}" for message in messages)


def _gemini_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.GEMINI_API_KEY,
    }


def get_embedding_provider() -> EmbeddingProvider:
    provider = settings.EMBEDDING_PROVIDER.lower()
    if provider == "openai" and settings.OPENAI_API_KEY:
        return OpenAIProvider()
    if provider == "gemini" and settings.GEMINI_API_KEY:
        return GeminiProvider()
    if provider == "ollama":
        return OllamaProvider()
    return LocalEmbeddingProvider()


def get_llm_provider() -> LLMProvider:
    provider = settings.LLM_PROVIDER.lower()
    if provider == "openai" and settings.OPENAI_API_KEY:
        return OpenAIProvider()
    if provider == "gemini" and settings.GEMINI_API_KEY:
        return GeminiProvider()
    if provider == "ollama":
        return OllamaProvider()
    return LocalLLMProvider()
