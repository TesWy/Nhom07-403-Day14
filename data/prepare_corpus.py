from __future__ import annotations

import json
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
from statistics import median
from typing import Any

import chromadb


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
DATA_ROOT = REPO_ROOT / "data"
LEGACY_ROOT = DATA_ROOT / "legacy"
CHUNKS_ROOT = DATA_ROOT / "chunks"
CORPUS_PATH = DATA_ROOT / "corpus.jsonl"
MANIFEST_PATH = DATA_ROOT / "corpus_manifest.json"
CHUNK_AUDIT_PATH = DATA_ROOT / "chunk_audit.json"
DOCUMENTS_ROOT = REPO_ROOT / "documents"
DOCUMENTS_MANIFEST_PATH = DOCUMENTS_ROOT / "manifest.json"


@dataclass(frozen=True)
class LegacyCopyPlan:
    day: str
    docs_path: Path
    chroma_path: Path
    extra_files: tuple[Path, ...] = ()


@dataclass(frozen=True)
class LegacyCollection:
    name: str
    day: str
    collection: str
    chroma_path: Path
    embedding_dimension: int


ACTIVE_PLAN = LegacyCopyPlan(
    day="day08",
    docs_path=WORKSPACE_ROOT / "Day_08_RAG" / "lab" / "data" / "docs",
    chroma_path=WORKSPACE_ROOT / "Day_08_RAG" / "lab" / "chroma_db",
)

EXPORT_SOURCES = (
    LegacyCollection(
        name="day08_rag_lab",
        day="day08",
        collection="rag_lab",
        chroma_path=ACTIVE_PLAN.chroma_path,
        embedding_dimension=1536,
    ),
)


def ensure_within_repo(path: Path) -> None:
    if not path.resolve().is_relative_to(REPO_ROOT):
        raise ValueError(f"Refusing to modify path outside repo: {path}")


def reset_dir(path: Path) -> None:
    ensure_within_repo(path)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def compact_dict(data: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, value in data.items():
        if value in (None, "", [], {}):
            continue
        compacted[key] = value
    return compacted


def copy_legacy_assets() -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    reset_dir(LEGACY_ROOT)

    target_root = LEGACY_ROOT / ACTIVE_PLAN.day
    reset_dir(target_root)

    docs_target = target_root / "docs"
    chroma_target = target_root / "chroma_db"

    shutil.copytree(ACTIVE_PLAN.docs_path, docs_target)
    shutil.copytree(ACTIVE_PLAN.chroma_path, chroma_target)

    copied_files = [
        str(docs_target.relative_to(REPO_ROOT)),
        str(chroma_target.relative_to(REPO_ROOT)),
    ]

    for extra_file in ACTIVE_PLAN.extra_files:
        destination = target_root / extra_file.name
        shutil.copy2(extra_file, destination)
        copied_files.append(str(destination.relative_to(REPO_ROOT)))

    summaries.append(
        {
            "day": ACTIVE_PLAN.day,
            "copied": copied_files,
        }
    )

    return summaries


def build_documents_directory() -> dict[str, Any]:
    reset_dir(DOCUMENTS_ROOT)

    copied_docs: list[dict[str, Any]] = []
    collisions: list[dict[str, Any]] = []

    for doc_path in sorted(ACTIVE_PLAN.docs_path.glob("*.txt")):
        content = doc_path.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        destination = DOCUMENTS_ROOT / doc_path.name
        shutil.copy2(doc_path, destination)
        copied_docs.append(
            {
                "filename": doc_path.name,
                "chosen_from_day": ACTIVE_PLAN.day,
                "source_days": [ACTIVE_PLAN.day],
                "sha256": digest,
                "path": str(destination.relative_to(REPO_ROOT)),
            }
        )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents_root": str(DOCUMENTS_ROOT),
        "files": copied_docs,
        "collisions": collisions,
    }
    DOCUMENTS_MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def chroma_ref_for(source: LegacyCollection) -> dict[str, Any]:
    return {
        "db_path": str((LEGACY_ROOT / source.day / "chroma_db").relative_to(REPO_ROOT)),
        "collection": source.collection,
        "legacy_day": source.day,
        "embedding_dimension": source.embedding_dimension,
    }


def load_collection(source: LegacyCollection) -> list[dict[str, Any]]:
    client = chromadb.PersistentClient(path=str(source.chroma_path))
    collection = client.get_collection(source.collection)
    payload = collection.get(include=["documents", "metadatas"])

    rows: list[dict[str, Any]] = []
    ids = list(payload.get("ids") or [])
    documents = list(payload.get("documents") or [])
    metadatas = list(payload.get("metadatas") or [])

    for index, chunk_id in enumerate(ids):
        document = documents[index] or ""
        metadata = dict(metadatas[index] or {})
        source_label = metadata.get("source") or metadata.get("doc_id") or source.name

        cleaned_metadata = {k: v for k, v in metadata.items() if k != "chroma:document"}

        rows.append(
            {
                "chunk_id": chunk_id,
                "source": source_label,
                "text": document,
                "context": document,
                "chroma_ref": chroma_ref_for(source),
                "metadata": compact_dict(
                    {
                        **cleaned_metadata,
                        "legacy_day": source.day,
                        "legacy_collection": source.collection,
                        "legacy_export": source.name,
                        "embedding_dimension": source.embedding_dimension,
                        "text_char_count": len(document),
                        "context_preview": document[:200],
                    }
                ),
            }
        )

    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_within_repo(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def merge_corpus(all_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    merged: list[dict[str, Any]] = []
    by_chunk_id: dict[str, dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    collisions: list[dict[str, Any]] = []

    for row in all_rows:
        chunk_id = row["chunk_id"]
        current = by_chunk_id.get(chunk_id)

        if current is None:
            by_chunk_id[chunk_id] = row
            merged.append(row)
            continue

        if current["text"] == row["text"]:
            duplicates.append(
                {
                    "chunk_id": chunk_id,
                    "kept_from": current["metadata"]["legacy_export"],
                    "dropped_from": row["metadata"]["legacy_export"],
                }
            )
            continue

        reassigned_id = f"{row['metadata']['legacy_export']}__{chunk_id}"
        row["metadata"]["original_chunk_id"] = chunk_id
        row["metadata"]["chunk_id_collision"] = True
        row["chunk_id"] = reassigned_id
        by_chunk_id[reassigned_id] = row
        merged.append(row)
        collisions.append(
            {
                "chunk_id": chunk_id,
                "reassigned_id": reassigned_id,
                "kept_from": current["metadata"]["legacy_export"],
                "reassigned_from": row["metadata"]["legacy_export"],
            }
        )

    return merged, duplicates, collisions


def summarize_lengths(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "count": 0,
            "min_chars": 0,
            "median_chars": 0,
            "avg_chars": 0,
            "max_chars": 0,
        }

    lengths = [len(row["text"]) for row in rows]
    return {
        "count": len(rows),
        "min_chars": min(lengths),
        "median_chars": int(median(lengths)),
        "avg_chars": round(sum(lengths) / len(lengths), 2),
        "max_chars": max(lengths),
    }


def build_chunk_audit(
    source_exports: list[dict[str, Any]],
    corpus_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    per_export: dict[str, Any] = {}
    for export in source_exports:
        rows = export["rows"]
        per_export[export["name"]] = {
            **summarize_lengths(rows),
            "collection": export["collection"],
            "legacy_day": export["day"],
            "sample_longest_chunks": [
                {
                    "chunk_id": row["chunk_id"],
                    "text_char_count": len(row["text"]),
                    "source": row["source"],
                    "section": row["metadata"].get("section"),
                }
                for row in sorted(rows, key=lambda item: len(item["text"]), reverse=True)[:5]
            ],
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": summarize_lengths(corpus_rows),
        "largest_chunks_in_corpus": [
            {
                "chunk_id": row["chunk_id"],
                "text_char_count": len(row["text"]),
                "legacy_export": row["metadata"].get("legacy_export"),
                "source": row["source"],
                "section": row["metadata"].get("section"),
            }
            for row in sorted(corpus_rows, key=lambda item: len(item["text"]), reverse=True)[:10]
        ],
        "per_export": per_export,
        "notes": [
            "Chunk size numbers above are measured on text only.",
            "The old Day 08 chunking config targeted CHUNK_SIZE=400 tokens and CHUNK_OVERLAP=80 tokens, implemented as ~1600 char chunks with ~320 char overlap.",
            "This audit now uses a single active legacy source to avoid duplicate chunks across days.",
            "Large JSONL lines previously came mostly from embedding arrays, not from oversized chunk text.",
        ],
    }


def build_manifest(
    copied_assets: list[dict[str, Any]],
    source_exports: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
    collisions: list[dict[str, Any]],
    corpus_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    dimension_counter = Counter(str(row["metadata"].get("embedding_dimension", 0)) for row in corpus_rows)
    chunk_counter = Counter(row["metadata"].get("legacy_day", "unknown") for row in corpus_rows)
    empty_sources = [source["name"] for source in source_exports if source["rows_exported"] == 0]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "copied_assets": copied_assets,
        "exports": source_exports,
        "summary": {
            "storage_mode": "text_and_metadata_with_chroma_refs",
            "raw_exported_chunks": sum(source["rows_exported"] for source in source_exports),
            "unique_chunks_in_corpus": len(corpus_rows),
            "duplicates_removed": len(duplicates),
            "chunk_id_collisions_reassigned": len(collisions),
            "chunks_by_legacy_day": dict(chunk_counter),
            "embedding_dimensions_in_corpus": dict(dimension_counter),
            "collections_with_no_rows": empty_sources,
            "meets_strict_50_chunk_target": len(corpus_rows) >= 50,
            "notes": [
                "Embedding vectors are not embedded inside corpus.jsonl; use chroma_ref to retrieve from copied ChromaDB snapshots.",
                "Only one legacy source is kept active to avoid duplicate docs and duplicate chunks across days.",
            ],
        },
        "duplicates": duplicates,
        "collisions": collisions,
    }


def main() -> None:
    documents_manifest = build_documents_directory()
    copied_assets = copy_legacy_assets()
    reset_dir(CHUNKS_ROOT)

    all_rows: list[dict[str, Any]] = []
    source_exports: list[dict[str, Any]] = []

    for source in EXPORT_SOURCES:
        rows = load_collection(source)
        write_jsonl(CHUNKS_ROOT / f"{source.name}.jsonl", rows)
        all_rows.extend(rows)

        source_exports.append(
            {
                "name": source.name,
                "day": source.day,
                "collection": source.collection,
                "chroma_path": str(source.chroma_path),
                "copied_chroma_path": chroma_ref_for(source)["db_path"],
                "rows_exported": len(rows),
                "embedding_dimensions": [source.embedding_dimension] if rows else [],
                "rows": rows,
            }
        )

    corpus_rows, duplicates, collisions = merge_corpus(all_rows)
    write_jsonl(CORPUS_PATH, corpus_rows)
    chunk_audit = build_chunk_audit(source_exports, corpus_rows)
    CHUNK_AUDIT_PATH.write_text(
        json.dumps(chunk_audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest_exports = [
        {
            key: value
            for key, value in export.items()
            if key != "rows"
        }
        for export in source_exports
    ]

    manifest = build_manifest(
        copied_assets=copied_assets,
        source_exports=manifest_exports,
        duplicates=duplicates,
        collisions=collisions,
        corpus_rows=corpus_rows,
    )
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Copied legacy assets into: {LEGACY_ROOT}")
    print(f"Built documents directory: {DOCUMENTS_ROOT}")
    print(f"Exported raw chunk snapshots into: {CHUNKS_ROOT}")
    print(f"Wrote unified corpus: {CORPUS_PATH}")
    print(f"Wrote manifest: {MANIFEST_PATH}")
    print(f"Wrote chunk audit: {CHUNK_AUDIT_PATH}")
    print(f"Documents available: {len(documents_manifest['files'])}")
    print(f"Unique chunks ready for SDG: {len(corpus_rows)}")


if __name__ == "__main__":
    main()
