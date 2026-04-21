# Chunk Status

## Current source of truth

- The current chunk/corpus snapshot is built from **Day 08 only**.
- We intentionally dropped Day 09 and Day 10 chunk exports from the committed dataset because the documents overlap heavily and would create duplicate chunks across days.
- The active export is `data/chunks/day08_rag_lab.jsonl`, and the merged corpus is `data/corpus.jsonl`.

## What is committed

- `documents/`: the 5 canonical text documents used for this version.
- `data/corpus.jsonl`: merged chunk dataset for SDG and retrieval-eval mapping.
- `data/corpus_manifest.json`: summary of source, counts, and storage mode.
- `data/chunk_audit.json`: audit of chunk lengths and largest chunks.
- `data/prepare_corpus.py`: script to rebuild the dataset snapshot locally.

## What is not committed

- `data/legacy/**/chroma_db/` is intentionally ignored in git.
- ChromaDB is large/binary and should be copied locally, not stored in the repo.

## Chunk count

- Current corpus size: `29` chunks.
- This is enough to proceed with the current benchmark version.
- It is below the earlier stretch target of `50+` chunks, so if broader coverage is needed later, the next safe step is re-chunking from `documents/` rather than mixing duplicate day snapshots back in.

## ID integrity

- `chunk_id` values in `data/corpus.jsonl` come directly from the Day 08 Chroma collection `rag_lab`.
- Reverse lookup by `chunk_id` against the matching ChromaDB snapshot returns the same chunk text.
- This means `ground_truth_chunk_ids` can safely reuse these IDs for Hit Rate / MRR evaluation.

## Regeneration

Run:

```bash
python data/prepare_corpus.py
```

This rebuilds:

- `documents/`
- `data/chunks/day08_rag_lab.jsonl`
- `data/corpus.jsonl`
- `data/corpus_manifest.json`
- `data/chunk_audit.json`

## Notes for teammates

- If you only need SDG / golden-set generation, `data/corpus.jsonl` is enough.
- If you need live retrieval from ChromaDB, you must have the local Day 08 Chroma snapshot present at the expected path from `data/prepare_corpus.py`, or copy it back into `data/legacy/day08/chroma_db/` locally.
