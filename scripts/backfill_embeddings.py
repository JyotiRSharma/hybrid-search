# scripts/backfill_psycopg.py
import argparse, json
import psycopg
from sentence_transformers import SentenceTransformer
import numpy as np

parser = argparse.ArgumentParser("Backfill embeddings into public.magazine_content")
parser.add_argument("--dsn",   default="postgresql://postgres:postgres@localhost:5432/postgres")
parser.add_argument("--batch", type=int, default=256)
parser.add_argument("--limit", type=int, default=100)
parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
args = parser.parse_args()

def main():
    # 1) load model (384-dim)
    model = SentenceTransformer(args.model)
    dim = model.encode(["check"], normalize_embeddings=True)[0].shape[-1]
    assert dim == 384, f"Model dim={dim}; table expects vector(384)"

    # 2) connect & say where we are
    with psycopg.connect(args.dsn) as conn:
        db, host, port = conn.execute(
            "SELECT current_database(), inet_server_addr(), inet_server_port()"
        ).fetchone()
        print(f"Connected to db={db} host={host} port={port}")

        # 3) how many rows need work?
        (pending,) = conn.execute(
            "SELECT COUNT(*) FROM public.magazine_content WHERE embedding IS NULL"
        ).fetchone()
        if args.limit is not None:
            pending = min(pending, args.limit)
        print(f"Rows pending: {pending}")
        if pending == 0:
            return

        processed, last_id = 0, 0
        while processed < pending:
            to_fetch = min(args.batch, pending - processed)

            # 4) fetch a batch
            rows = conn.execute("""
                SELECT id, content
                FROM public.magazine_content
                WHERE id > %s AND embedding IS NULL
                ORDER BY id
                LIMIT %s
            """, (last_id, to_fetch)).fetchall()
            if not rows:
                break

            ids   = [r[0] for r in rows]
            texts = [(r[1] or "")[:2000] for r in rows]  # keep it reasonable
            last_id = ids[-1]

            # 5) embed
            vecs = model.encode(texts, normalize_embeddings=True)
            payload = [{"id": int(i), "embedding": np.asarray(v, float).tolist()}
                       for i, v in zip(ids, vecs)]

            # 6) upsert via JSONB → pgvector
            conn.execute("""
                UPDATE public.magazine_content AS mc
                SET embedding = src.embedding
                FROM (
                  SELECT *
                  FROM jsonb_to_recordset(%s::jsonb)
                    AS x(id bigint, embedding vector(384))
                ) AS src
                WHERE mc.id = src.id
            """, (json.dumps(payload),))
            conn.commit()

            processed += len(ids)
            print(f"Embedded + updated: {processed}/{pending}")

        print("Backfill complete.")

if __name__ == "__main__":
    main()
    # read_first_ten()

# def read_first_ten():
#     print("hello")
#     with psycopg.connect(DSN) as conn:
#         with conn.cursor() as cur:
#             cur.execute("SELECT current_database(), current_schema()")
#             print(cur.fetchone())
#             cur.execute("SELECT id, magazine_id, LEFT(content, 80) FROM public.magazine_content LIMIT 10;")
#             rows = cur.fetchall()
#             print("hello2", rows)
#             for row in rows:
#                 print(row)
