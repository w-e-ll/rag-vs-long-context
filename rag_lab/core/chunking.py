"""LangChain splitters with stable page provenance and bounded parent expansion."""

import hashlib
from dataclasses import dataclass
from functools import lru_cache

import tiktoken
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_lab.core.citations import source_id, source_text
from rag_lab.core.models import ChunkSettings, ParsedDocument


@lru_cache
def encoding():
    return tiktoken.get_encoding("cl100k_base")


def tokens(text: str) -> int:
    """A consistent experimental tokenizer, not an Ollama billing tokenizer."""
    return len(encoding().encode(text, disallowed_special=()))


@dataclass
class Chunk:
    key: str
    page: int
    text: str
    parent_key: str
    parent_text: str


def splitter(size: int, overlap: int):
    return RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        length_function=tokens,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def chunk_document(parsed: ParsedDocument, config: ChunkSettings) -> list[Chunk]:
    """Page is the provenance boundary. Structured table text is reviewed before indexing."""
    result = []
    for page in parsed.pages:
        parents = splitter(config.parent_size, 0).split_documents(
            [Document(page_content=page.text, metadata={"page": page.number})]
        )
        for parent_no, parent in enumerate(parents):
            parent_key = f"p{page.number}-s{parent_no}"
            for child_no, text in enumerate(
                splitter(config.size, config.overlap).split_text(parent.page_content)
            ):
                digest = hashlib.sha256(text.encode()).hexdigest()[:16]
                result.append(
                    Chunk(
                        f"{parent_key}-c{child_no}-{digest}",
                        page.number,
                        text,
                        parent_key,
                        parent.page_content,
                    )
                )
    return result


def pack_context(chunks: list[Chunk], strategy: str, budget: int):
    """Deduplicate parents; never silently truncate a table, sentence or parent."""
    included, seen, selected = [], set(), []
    for chunk in chunks:
        key = chunk.parent_key if strategy == "parent_child" else chunk.key
        if key in seen:
            continue
        content = chunk.parent_text if strategy == "parent_child" else chunk.text
        item = f"[{source_id(chunk.page)}]\n{source_text(content)}\n[END SOURCE]"
        if tokens("\n\n".join(included + [item])) > budget:
            continue
        seen.add(key)
        included.append(item)
        selected.append(chunk)
    return "\n\n".join(included), selected
