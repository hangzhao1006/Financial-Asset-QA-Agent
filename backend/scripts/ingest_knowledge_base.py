"""Ingest Markdown knowledge base files into ChromaDB vector store."""
from __future__ import annotations

import os
import sys
import glob
import asyncio
import logging
import re

# Ensure project root is on path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from backend.app.services.chunker import chunk_markdown
from backend.app.services.embedding import embed_texts
from backend.app.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = os.environ.get(
    "KNOWLEDGE_DIR",
    os.path.join(_PROJECT_ROOT, "knowledge_base"),
)


async def ingest():
    import chromadb

    settings = get_settings()
    chroma_dir = settings.chroma_persist_dir
    collection_name = "financial_knowledge"

    logger.info("ChromaDB dir: %s", chroma_dir)
    os.makedirs(chroma_dir, exist_ok=True)

    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    md_files = sorted(glob.glob(os.path.join(KNOWLEDGE_DIR, "**", "*.md"), recursive=True))
    if not md_files:
        logger.warning("No markdown files found in %s", KNOWLEDGE_DIR)
        return

    total_chunks = 0
    for filepath in md_files:
        rel_path = os.path.relpath(filepath, KNOWLEDGE_DIR)
        filename = os.path.basename(filepath)
        title = filename.rsplit(".", 1)[0]
        logger.info("Processing %s ...", filename)

        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()

        source_urls = _extract_source_urls(text)
        chunks = chunk_markdown(text, doc_id=rel_path, title=title, source_urls=source_urls, max_tokens=400, overlap_tokens=50)
        logger.info("  -> %d chunks", len(chunks))

        if not chunks:
            continue

        # Batch embed all chunk texts
        chunk_texts = [c.text for c in chunks]
        try:
            embeddings = await embed_texts(chunk_texts)
        except Exception as exc:
            logger.error("  Embedding failed for %s: %s", filename, exc)
            continue

        ids = []
        documents = []
        metadatas = []
        for i, chunk in enumerate(chunks):
            ids.append(f"{rel_path}_{i}")
            documents.append(chunk.text)
            metadatas.append({
                "source_file": rel_path,
                "title": chunk.title,
                "section": chunk.section,
                "chunk_index": i,
                "token_count": chunk.token_count,
                "source_urls": ",".join(chunk.source_urls),
            })

        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        total_chunks += len(ids)
        logger.info("  Done: %d chunks upserted", len(ids))

    logger.info("Ingestion complete: %d total chunks from %d files", total_chunks, len(md_files))
    logger.info("ChromaDB persisted to %s", chroma_dir)


def _extract_source_urls(text: str) -> list[str]:
    urls = []
    for match in re.finditer(r"https?://[^\s)>\"]+", text):
        url = match.group(0).rstrip(".,;")
        if url not in urls:
            urls.append(url)
    return urls[:10]


if __name__ == "__main__":
    asyncio.run(ingest())
