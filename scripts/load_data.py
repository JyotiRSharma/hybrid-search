import asyncio, argparse, csv, json
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from sentence_transformers import SentenceTransformer

DEFAULT_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/magdb"

parser = argparse.ArgumentParser("Load one CSV (title,author,publication_date,category,content) into two tables.")
parser.add_argument("--db", dest="db_url", default=DEFAULT_DB_URL)
parser.add_argument("--articles_csv", required=True, help="Single CSV with title,author,publication_date,category,content")
parser.add_argument("--batch", type=int, default=256, help="Batch size for inserts/embeddings")
parser.add_argument("--limit_content", type=int, default=None, help="Optional cap on rows to load from CSV")
parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
args = parser.parse_args()

model = SentenceTransformer(args.model)

# ---------- helpers ----------
def normalize_date(s: Optional[str]) -> str:
    if not s:
        return "2024-01-01"
    for fmt in ("%Y-%m-%d", "%d/%m/%y", "%m/%d/%y", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return "2024-01-01"

def norm_key(k: str) -> str:
    return "".join(ch for ch in (k or "").lower() if ch.isalnum())

async def ensure_vector_extension(engine):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

# ---------- main loader for single CSV ----------
async def load_single_csv(engine, path: str, batch: int, limit: Optional[int] = None):
    print(f"Reading {path} and splitting into magazine_info + magazine_content …")

    # Pass 0: scan headers
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit("CSV has no header row.")
        fn = {norm_key(h): h for h in reader.fieldnames}
        title_k   = fn.get("title")
        author_k  = fn.get("author")
        date_k    = fn.get("publicationdate") or fn.get("publication_date")
        cat_k     = fn.get("category")
        content_k = fn.get("content") or fn.get("article") or fn.get("text") or fn.get("body")
        need = [title_k, author_k, date_k, cat_k, content_k]
        if any(v is None for v in need):
            raise SystemExit(f"CSV must have title, author, publication_date, category, content. Found: {reader.fieldnames}")

    # Pass 1: collect unique magazines (by composite key) and also keep a compact list of article rows
    unique_keys: Dict[Tuple[str,str,str,str], None] = {}
    # we’ll re-read the file for content; this pass is only to compute unique magazines cheaply
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        total = 0
        for r in reader:
            if limit is not None and total >= limit:
                break
            title = (r.get(title_k) or "").strip()
            author = (r.get(author_k) or "").strip()
            pub_date = normalize_date((r.get(date_k) or "").strip())
            category = (r.get(cat_k) or "general").strip()
            unique_keys[(title, author, pub_date, category)] = None
            total += 1

    unique_mags = [
        {"title": t, "author": a, "publication_date": d, "category": c}
        for (t,a,d,c) in unique_keys.keys()
    ]
    print(f"Found {len(unique_mags)} unique magazines across {total} rows.")

    # Insert only missing magazines (no schema change required)
    async with engine.begin() as conn:
        for i in range(0, len(unique_mags), batch):
            chunk = unique_mags[i:i+batch]
            await conn.execute(text("""
                WITH incoming AS (
                  SELECT DISTINCT title, author, publication_date, category
                  FROM jsonb_to_recordset((:j)::jsonb)
                    AS x(title text, author text, publication_date date, category text)
                ),
                missing AS (
                  SELECT i.*
                  FROM incoming i
                  LEFT JOIN magazine_info m
                    ON m.title = i.title
                   AND m.author = i.author
                   AND m.publication_date = i.publication_date
                   AND m.category = i.category
                  WHERE m.id IS NULL
                )
                INSERT INTO magazine_info(title,author,publication_date,category)
                SELECT title,author,publication_date,category FROM missing;
            """), {"j": json.dumps(chunk)})

    # Build mapping (title,author,date,category) -> magazine_info.id using a JSON join (handles big sets)
    mapping: Dict[Tuple[str,str,str,str], int] = {}
    async with engine.connect() as conn:
        for i in range(0, len(unique_mags), 5000):
            chunk = unique_mags[i:i+5000]
            rows = await conn.execute(text("""
                SELECT i.title, i.author, i.publication_date, i.category, m.id
                FROM jsonb_to_recordset((:j)::jsonb)
                  AS i(title text, author text, publication_date date, category text)
                JOIN magazine_info m
                  ON m.title = i.title
                 AND m.author = i.author
                 AND m.publication_date = i.publication_date
                 AND m.category = i.category
            """), {"j": json.dumps(chunk)})
            for t,a,d,c, mid in rows.fetchall():
                mapping[(t,a,d,c)] = mid

    if len(mapping) != len(unique_mags):
        raise SystemExit(f"Could not map all magazines ({len(mapping)} of {len(unique_mags)}).")

    # Pass 2: stream content, attach magazine_id, embed, insert in batches
    print("Embedding content and inserting into magazine_content …")
    inserted = 0
    skipped_empty = 0
    mids: List[int] = []
    texts: List[str] = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        async with engine.begin() as conn:
            processed = 0
            for r in reader:
                if limit is not None and processed >= limit:
                    break
                title = (r.get(title_k) or "").strip()
                author = (r.get(author_k) or "").strip()
                pub_date = normalize_date((r.get(date_k) or "").strip())
                category = (r.get(cat_k) or "general").strip()
                content = (r.get(content_k) or "").strip()
                processed += 1

                if not content:
                    skipped_empty += 1
                    continue

                mid = mapping.get((title,author,pub_date,category))
                if not mid:
                    continue  # very unlikely now

                mids.append(mid)
                texts.append(content[:2000])  # keep RAM reasonable

                if len(texts) >= batch:
                    vecs = model.encode(texts, normalize_embeddings=True)
                    payload = [
                        {"magazine_id": m, "content": t, "embedding": v.tolist()}
                        for m, t, v in zip(mids, texts, vecs)
                    ]
                    await conn.execute(text("""
                        INSERT INTO magazine_content (magazine_id, content, embedding)
                        SELECT * FROM jsonb_to_recordset((:j)::jsonb)
                          AS x(magazine_id bigint, content text, embedding vector(384))
                    """), {"j": json.dumps(payload)})
                    inserted += len(payload)
                    mids.clear(); texts.clear()

            if texts:
                vecs = model.encode(texts, normalize_embeddings=True)
                payload = [
                    {"magazine_id": m, "content": t, "embedding": v.tolist()}
                    for m, t, v in zip(mids, texts, vecs)
                ]
                await conn.execute(text("""
                    INSERT INTO magazine_content (magazine_id, content, embedding)
                    SELECT * FROM jsonb_to_recordset((:j)::jsonb)
                      AS x(magazine_id bigint, content text, embedding vector(384))
                """), {"j": json.dumps(payload)})
                inserted += len(payload)

    print(f"Inserted {inserted} content rows. Skipped empty content rows: {skipped_empty}.")

async def analyze(engine):
    print("Running ANALYZE …")
    async with engine.begin() as conn:
        await conn.execute(text("ANALYZE magazine_info"))
        await conn.execute(text("ANALYZE magazine_content"))
    print("ANALYZE done.")

async def main():
    engine = create_async_engine(args.db_url, pool_size=10, max_overflow=20)
    await ensure_vector_extension(engine)
    await load_single_csv(engine, args.articles_csv, args.batch, args.limit_content)
    await analyze(engine)

def main_cli():
    asyncio.run(main())

if __name__ == "__main__":
    main_cli()
