# scripts/backfill_embeddings.py
import argparse, json, os, time, math
import psycopg
import numpy as np

# torch is optional: we try to accelerate if on host with MPS/CUDA
try:
    import torch
    TORCH_OK = True
except Exception:
    TORCH_OK = False

from sentence_transformers import SentenceTransformer

parser = argparse.ArgumentParser("Backfill embeddings into public.magazine_content (pgvector)")

parser.add_argument("--dsn", default=os.getenv("DB_DSN", "postgresql://postgres:postgres@db:5432/postgres"))
parser.add_argument("--only-null", action="store_true", help="Only process rows with embedding IS NULL")
parser.add_argument("--limit", type=int, default=None, help="Cap total rows to process")

# Streaming/throughput knobs (safe defaults for M1 Air)
parser.add_argument("--fetch-batch",  type=int, default=256, help="How many rows to fetch from DB each iteration")
parser.add_argument("--encode-batch", type=int, default=64,  help="Batch size for model.encode (keep small on M1)")
parser.add_argument("--cooldown",     type=float, default=0.15, help="Seconds to sleep between iterations")

# Sharding knobs (parallel workers)
parser.add_argument("--workers", type=int, default=1, help="Total workers for modulo sharding")
parser.add_argument("--me",      type=int, default=0, help="This worker id in [0..workers-1]")

# Index management
parser.add_argument("--postindex", action="store_true", help="Create vector/fulltext indexes + ANALYZE at end")
parser.add_argument("--drop-vector-index-first", action="store_true", help="Drop vector index before upsert to speed writes")

# Model
parser.add_argument("--model", default=os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
args = parser.parse_args()

INDEX_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

-- Vector ANN index (cosine for MiniLM)
CREATE INDEX IF NOT EXISTS idx_mag_content_embedding_ivf
  ON public.magazine_content USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 200);

-- Full-text (if not created elsewhere)
CREATE INDEX IF NOT EXISTS idx_mag_info_tsv
  ON public.magazine_info USING GIN (info_tsv);
CREATE INDEX IF NOT EXISTS idx_mag_content_tsv
  ON public.magazine_content USING GIN (content_tsv);

ANALYZE public.magazine_content;
ANALYZE public.magazine_info;
"""

DROP_VEC_INDEX_SQL = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname='public' AND indexname='idx_mag_content_embedding_ivf'
  ) THEN
    EXECUTE 'DROP INDEX public.idx_mag_content_embedding_ivf';
  END IF;
END$$;
"""

def device_string():
    """Pick the best device without cooking the laptop."""
    if not TORCH_OK:
        return "cpu"
    # Inside Docker you typically won't have MPS/CUDA; prefer CPU there
    in_docker = os.path.exists("/.dockerenv")
    if not in_docker and torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"

def load_model(name: str, device: str):
    model = SentenceTransformer(name, device=device)
    # Lower threads on CPU to keep temps sane (helps macOS + Docker)
    if device == "cpu" and TORCH_OK:
        try:
            torch.set_num_threads(max(1, os.cpu_count() // 2))
        except Exception:
            pass
    return model

def count_pending(conn: psycopg.Connection) -> int:
    cond = "embedding IS NULL" if args.only_null else "TRUE"
    shard_sql = " AND mod(id, %s) = %s" if args.workers > 1 else ""
    sql = f"SELECT COUNT(*) FROM public.magazine_content WHERE {cond}{shard_sql}"

    with conn.cursor() as cur:
        if args.workers > 1:
            cur.execute(sql, (args.workers, args.me))
        else:
            cur.execute(sql)
        (n,) = cur.fetchone()
        return int(n)


def fetch_batch(conn: psycopg.Connection, last_id: int, fetch_batch: int):
    cond = "embedding IS NULL" if args.only_null else "TRUE"
    shard_sql = " AND mod(id, %s) = %s" if args.workers > 1 else ""
    sql = f"""
        SELECT id, content
        FROM public.magazine_content
        WHERE id > %s AND {cond}{shard_sql}
        ORDER BY id
        LIMIT %s
    """
    with conn.cursor() as cur:
        if args.workers > 1:
            cur.execute(sql, (last_id, args.workers, args.me, fetch_batch))
        else:
            cur.execute(sql, (last_id, fetch_batch))
        return cur.fetchall()

def upsert_embeddings(conn: psycopg.Connection, payload_json: str):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE public.magazine_content AS mc
            SET embedding = src.embedding
            FROM (
              SELECT *
              FROM jsonb_to_recordset(%s::jsonb)
                AS x(id bigint, embedding vector(384))
            ) AS src
            WHERE mc.id = src.id
        """, (payload_json,))
    conn.commit()

def run_postindex(conn: psycopg.Connection):
    with conn.cursor() as cur:
        cur.execute(INDEX_SQL)
    conn.commit()
    print("Indexes created/refreshed + ANALYZE done.")

def maybe_drop_vector_index(conn: psycopg.Connection):
    with conn.cursor() as cur:
        cur.execute(DROP_VEC_INDEX_SQL)
    conn.commit()
    print("Dropped existing vector index (if any).")

def main():
    dev = device_string()
    print(f"Device: {dev}  |  DSN: {args.dsn}  |  workers={args.workers} me={args.me}")

    model = load_model(args.model, dev)
    dim = model.encode(["check"], normalize_embeddings=True, batch_size=1)[0].shape[-1]
    assert dim == 384, f"Model dim={dim}; table expects vector(384)"

    with psycopg.connect(args.dsn) as conn:
        # Confirm connection target (helps avoid "wrong DB" surprises)
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), inet_server_addr(), inet_server_port()")
            db, host, port = cur.fetchone()
            print(f"Connected to db={db} host={host} port={port}")

        # Optional: drop ANN index first for faster writes
        if args.drop_vector_index_first:
            maybe_drop_vector_index(conn)

        pending_total = count_pending(conn)
        pending = pending_total if args.limit is None else min(pending_total, args.limit)
        print(f"Rows pending for this worker: {pending} (total found={pending_total})")
        if pending == 0:
            if args.postindex:
                run_postindex(conn)
            return

        processed, last_id = 0, 0
        while processed < pending:
            todo = min(args.fetch_batch, pending - processed)
            rows = fetch_batch(conn, last_id, todo)
            if not rows:
                break

            ids = [int(r[0]) for r in rows]
            texts = [((r[1] or "")[:2000]) for r in rows]
            last_id = ids[-1]

            # Encode in micro-batches to keep temps/memory low
            vecs_all = []
            for i in range(0, len(texts), args.encode_batch):
                chunk = texts[i:i+args.encode_batch]
                vecs = model.encode(
                    chunk,
                    normalize_embeddings=True,
                    batch_size=min(len(chunk), args.encode_batch),
                    convert_to_numpy=True
                ).astype(np.float32)
                vecs_all.append(vecs)
                # micro-cooldown between encode chunks
                if args.cooldown > 0:
                    time.sleep(args.cooldown * 0.35)
            vecs_all = np.vstack(vecs_all)

            # Build JSON payload (id, embedding) pairs
            payload = [{"id": i, "embedding": v.tolist()} for i, v in zip(ids, vecs_all)]
            upsert_embeddings(conn, json.dumps(payload))

            processed += len(ids)
            print(f"Embedded + updated: {processed}/{pending} (last_id={last_id})")

            # friendly cooldown between DB iterations
            if args.cooldown > 0:
                time.sleep(args.cooldown)

        print("Backfill complete.")
        if args.postindex:
            run_postindex(conn)

if __name__ == "__main__":
    main()
