from dataclasses import dataclass
from typing import Iterable

from pgvector.django import CosineDistance

from assistant.models import DocumentChunk
from assistant.services.providers import get_llm_provider
from assistant.services.providers import get_embedding_provider


@dataclass
class RetrievalHit:
    chunk_id: int
    document_id: int
    content: str
    document_title: str
    page_number: int
    score: float
    citation: str


def retrieve_relevant_chunks(workspace, query: str, limit: int = 5) -> list[RetrievalHit]:
    query_embedding = get_embedding_provider().embed_texts([query])[0]
    hits: list[RetrievalHit] = []

    queryset = (
        DocumentChunk.objects.filter(document__workspace=workspace, embedding__isnull=False)
        .select_related("document")
        .annotate(distance=CosineDistance("embedding", query_embedding))
        .order_by("distance")
    )

    for chunk in queryset[:limit]:
        distance = float(chunk.distance or 0.0)
        hits.append(
            RetrievalHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                content=chunk.content[:900],
                document_title=chunk.document.title,
                page_number=chunk.page_number,
                score=1.0 - distance,
                citation=chunk.citation_label or f"{chunk.document.title} page {chunk.page_number}",
            )
        )

    return hits


def compose_answer(query: str, hits: Iterable[RetrievalHit]) -> dict:
    hits = list(hits)
    if not hits:
        return {
            "answer": "I could not find a strong match in the indexed documents yet.",
            "citations": [],
        }

    system_prompt = (
        "You are an enterprise knowledge assistant. Answer only from the provided context. "
        "If the context is insufficient, say so clearly."
    )
    context_blocks = []
    citations = []
    for index, hit in enumerate(hits, start=1):
        context_blocks.append(f"[{index}] {hit.citation}\n{hit.content.strip()[:900]}")
        citations.append(
            {
                "chunk_id": hit.chunk_id,
                "document_id": hit.document_id,
                "label": hit.citation,
                "document_title": hit.document_title,
                "page_number": hit.page_number,
                "score": hit.score,
            }
        )
    llm = get_llm_provider()
    answer = llm.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": "Context:\n" + "\n\n".join(context_blocks)},
            {"role": "user", "content": query},
        ]
    )
    return {"answer": answer, "citations": citations}
