"""Adaptive, structure-aware chunker — hierarchical parent/child chunks (§3.3)."""

from dataclasses import dataclass

from src.db.models import ChunkType
from src.ingestion.parsers.base import ParsedDocument, ParsedPage


@dataclass
class RawChunk:
    text: str
    chunk_index: int
    chunk_type: ChunkType
    page_number: int | None = None
    section_heading: str | None = None
    parent_index: int | None = None  # index of parent RawChunk; None = this IS a parent/leaf
    is_indexable: bool = True        # False = parent chunk, stored for context but NOT indexed in vector DB


def _token_count(text: str) -> int:
    """Rough token count (4 chars ≈ 1 token for English text)."""
    return max(1, len(text) // 4)


def _recursive_split(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Recursive character splitting: paragraphs → sentences → words."""
    if _token_count(text) <= max_tokens:
        return [text]

    # Try splitting on double newline (paragraphs)
    for sep in ["\n\n", "\n", ". ", " "]:
        parts = text.split(sep)
        if len(parts) > 1:
            chunks: list[str] = []
            buf = ""
            for part in parts:
                candidate = buf + (sep if buf else "") + part
                if _token_count(candidate) > max_tokens and buf:
                    chunks.append(buf.strip())
                    # overlap: keep last overlap_tokens worth of buf
                    words = buf.split()
                    overlap_words = words[-overlap_tokens:] if overlap_tokens else []
                    buf = " ".join(overlap_words) + (sep if overlap_words else "") + part
                else:
                    buf = candidate
            if buf.strip():
                chunks.append(buf.strip())
            return [c for c in chunks if c]

    # No good separator — hard split by word count
    words = text.split()
    chunks = []
    step = max(1, max_tokens - overlap_tokens)
    for i in range(0, len(words), step):
        chunk_words = words[i : i + max_tokens]
        chunks.append(" ".join(chunk_words))
    return [c for c in chunks if c]


def chunk_page(
    page: ParsedPage,
    page_idx: int,
    *,
    chunk_size: int = 512,
    overlap: int = 52,         # ~10% of 512
    parent_size: int = 1024,   # parent chunks for hierarchical retrieval
) -> list[RawChunk]:
    """Chunk a single page into (optional) parent + child chunks."""
    results: list[RawChunk] = []
    base_index = page_idx * 10000  # reserve space per page

    # Tables are their own chunks — never split mid-table
    for table_text in page.tables:
        results.append(
            RawChunk(
                text=table_text,
                chunk_index=base_index + len(results),
                chunk_type=ChunkType.table,
                page_number=page.page_number,
                section_heading=page.section_heading,
            )
        )

    # Figure descriptions — one chunk each
    for fig_text in page.figures:
        results.append(
            RawChunk(
                text=fig_text,
                chunk_index=base_index + len(results),
                chunk_type=ChunkType.figure_description,
                page_number=page.page_number,
                section_heading=page.section_heading,
            )
        )

    # Main prose text — hierarchical split: large parent → small children.
    # Parents are stored in Postgres for context lookup but NOT indexed in Qdrant
    # (is_indexable=False).  Only children are indexed.  If a parent produces only
    # one child (text already short enough), the parent itself is the leaf and IS
    # indexed (is_indexable=True, no children created).
    if page.text.strip():
        parents = _recursive_split(page.text, parent_size, overlap)
        for parent_text in parents:
            parent_idx = base_index + len(results)
            children = _recursive_split(parent_text, chunk_size, overlap)
            has_children = len(children) > 1

            parent_chunk = RawChunk(
                text=parent_text,
                chunk_index=parent_idx,
                chunk_type=ChunkType.prose,
                page_number=page.page_number,
                section_heading=page.section_heading,
                is_indexable=not has_children,  # leaf if no children
            )
            results.append(parent_chunk)

            if has_children:
                for child_text in children:
                    results.append(
                        RawChunk(
                            text=child_text,
                            chunk_index=base_index + len(results),
                            chunk_type=ChunkType.prose,
                            page_number=page.page_number,
                            section_heading=page.section_heading,
                            parent_index=parent_idx,
                            is_indexable=True,
                        )
                    )

    return results


def chunk_document(
    doc: ParsedDocument,
    file_type: str,
    *,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[RawChunk]:
    """Full document → flat list of RawChunks with parent links."""
    # Content-type defaults (§3.3 decision table)
    if file_type == "pptx":
        # Slides are natural units — each slide = one chunk, no further splitting
        chunks: list[RawChunk] = []
        for i, page in enumerate(doc.pages):
            chunks.append(
                RawChunk(
                    text=page.text,
                    chunk_index=i,
                    chunk_type=ChunkType.slide,
                    page_number=page.page_number,
                    section_heading=page.section_heading,
                )
            )
        return chunks

    _chunk_size = chunk_size or 512
    _overlap = overlap or 52

    all_chunks: list[RawChunk] = []
    for i, page in enumerate(doc.pages):
        page_chunks = chunk_page(page, i, chunk_size=_chunk_size, overlap=_overlap)
        all_chunks.extend(page_chunks)

    # Re-number chunk_index sequentially, keeping parent_index in sync.
    # chunk_page() uses page-based offsets (page_idx * 10000) so the old
    # values are unique within this call but not sequential from 0.
    old_to_new: dict[int, int] = {c.chunk_index: i for i, c in enumerate(all_chunks)}
    for i, chunk in enumerate(all_chunks):
        chunk.chunk_index = i
        if chunk.parent_index is not None:
            chunk.parent_index = old_to_new.get(chunk.parent_index)  # None if parent missing

    return all_chunks
