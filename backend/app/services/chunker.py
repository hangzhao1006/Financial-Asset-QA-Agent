"""Structure-aware Markdown chunker."""
from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass, field

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_enc.encode(text))


@dataclass
class Chunk:
    text: str
    doc_id: str = ""
    title: str = ""
    section: str = ""
    source_urls: list[str] = field(default_factory=list)
    chunk_index: int = 0
    token_count: int = 0

    def to_metadata(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "section": self.section,
            "source_urls": ",".join(self.source_urls),
            "chunk_index": self.chunk_index,
            "token_count": self.token_count,
        }


def chunk_markdown(
    text: str,
    doc_id: str = "",
    title: str = "",
    source_urls: list[str] | None = None,
    max_tokens: int = 700,
    overlap_tokens: int = 100,
) -> list[Chunk]:
    """Split markdown by headings, then merge paragraphs into chunks."""
    source_urls = source_urls or []
    sections = _split_by_headings(text)
    chunks: list[Chunk] = []
    idx = 0

    for section_title, section_text in sections:
        paragraphs = [p.strip() for p in section_text.split("\n\n") if p.strip()]
        buffer = ""
        for para in paragraphs:
            if _count_tokens(para) > max_tokens:
                if buffer.strip():
                    chunks.append(_make_chunk(buffer, doc_id, title, section_title, source_urls, idx))
                    idx += 1
                    buffer = ""
                for piece in _split_long_text(para, max_tokens, overlap_tokens):
                    chunks.append(_make_chunk(piece, doc_id, title, section_title, source_urls, idx))
                    idx += 1
                continue

            candidate = (buffer + "\n\n" + para).strip() if buffer else para
            if _count_tokens(candidate) > max_tokens and buffer:
                chunks.append(_make_chunk(buffer, doc_id, title, section_title, source_urls, idx))
                idx += 1
                # Overlap: keep tail of previous buffer
                overlap_text = _get_tail(buffer, overlap_tokens)
                buffer = (overlap_text + "\n\n" + para).strip()
            else:
                buffer = candidate

        if buffer.strip():
            chunks.append(_make_chunk(buffer, doc_id, title, section_title, source_urls, idx))
            idx += 1

    if not chunks:
        chunks.append(_make_chunk(text[:3000], doc_id, title, "", source_urls, 0))

    return chunks


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """Split markdown text by H1/H2/H3 headings."""
    pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))

    if not matches:
        return [("", text)]

    sections = []
    for i, m in enumerate(matches):
        heading_text = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((heading_text, body))

    # Text before first heading
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.insert(0, ("", preamble))

    return sections


def _make_chunk(text: str, doc_id: str, title: str, section: str, urls: list[str], idx: int) -> Chunk:
    tc = _count_tokens(text)
    return Chunk(
        text=text,
        doc_id=doc_id or hashlib.md5(title.encode()).hexdigest()[:12],
        title=title,
        section=section,
        source_urls=urls,
        chunk_index=idx,
        token_count=tc,
    )


def _get_tail(text: str, max_tokens: int) -> str:
    """Get the last ~max_tokens tokens of text."""
    tokens = _enc.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _enc.decode(tokens[-max_tokens:])


def _split_long_text(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Split a single over-sized paragraph by token windows."""
    tokens = _enc.encode(text)
    if len(tokens) <= max_tokens:
        return [text]

    step = max(1, max_tokens - max(0, overlap_tokens))
    pieces = []
    for start in range(0, len(tokens), step):
        window = tokens[start:start + max_tokens]
        if not window:
            break
        pieces.append(_enc.decode(window).strip())
        if start + max_tokens >= len(tokens):
            break
    return [p for p in pieces if p]
