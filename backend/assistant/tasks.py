from celery import shared_task

from assistant.models import Document, DocumentChunk
from assistant.services.chunking import chunk_text
from assistant.services.providers import get_embedding_provider
from assistant.services.extraction import extract_text_from_upload


@shared_task
def index_document_task(document_id: int) -> None:
    document = Document.objects.select_related("workspace").get(id=document_id)
    try:
        text, pages = extract_text_from_upload(document.file.path)
        document.extracted_text = text
        document.status = Document.Status.INDEXING
        document.progress = 10
        document.save(update_fields=["extracted_text", "status", "progress"])

        DocumentChunk.objects.filter(document=document).delete()
        chunks = []
        if pages:
            for page in pages:
                chunks.append(
                    {
                        "page_number": page["page_number"],
                        "content": page["text"],
                        "citation_label": f"{document.title} page {page['page_number']}",
                    }
                )
        else:
            for idx, chunk in enumerate(chunk_text(text), start=1):
                chunks.append(
                    {
                        "page_number": 1,
                        "content": chunk,
                        "citation_label": f"{document.title} section {idx}",
                    }
                )

        embeddings = get_embedding_provider().embed_texts([item["content"] for item in chunks]) if chunks else []
        for index, item in enumerate(chunks):
            vector = embeddings[index] if index < len(embeddings) else []
            document.progress = min(90, 10 + int((index + 1) / max(len(chunks), 1) * 80))
            document.save(update_fields=["progress"])
            DocumentChunk.objects.create(
                document=document,
                page_number=item["page_number"],
                chunk_index=index + 1,
                content=item["content"],
                citation_label=item["citation_label"],
                embedding=vector,
            )
        document.status = Document.Status.READY
        document.progress = 100
        document.save(update_fields=["status", "progress"])
    except Exception:
        document.status = Document.Status.FAILED
        document.error_message = "Indexing failed."
        document.save(update_fields=["status"])
        raise
