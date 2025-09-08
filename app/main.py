from fastapi import FastAPI, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from .db import get_session
from .embedding import embed_text
from .config import settings

app = FastAPI(title="Hybrid Search API", version="0.1.0")

class SearchRequest(BaseModel):
    query: str = Field(..., description="User query (keywords)")
    top_k: int = Field(20, ge=1, le=200)
    kw_weight: float = Field(settings.KW_WEIGHT, ge=0, le=1)
    vec_weight: float = Field(settings.VEC_WEIGHT, ge=0, le=1)

@app.post("/search")
async def search(req: SearchRequest, session: AsyncSession = Depends(get_session)):
    # 1) embed query for vector search
    qvec = embed_text(req.query)

    # 2) SQL: hybrid search (kw via ts_rank; vec via cosine; fuse)
    sql = text(
        """
        WITH kw AS (
          SELECT mc.id AS content_id,
                 /* weight content higher than title/author if desired */
                 ts_rank(mi.info_tsv, plainto_tsquery('english', :q)) * 0.3 +
                 ts_rank(mc.content_tsv, plainto_tsquery('english', :q)) * 0.7 AS kw_score
          FROM magazine_content mc
          JOIN magazine_info mi ON mi.id = mc.magazine_id
          WHERE mi.info_tsv @@ plainto_tsquery('english', :q)
             OR mc.content_tsv @@ plainto_tsquery('english', :q)
        ),
        vec AS (
          SELECT mc.id AS content_id,
                 1 - (mc.embedding <-> :qvec) AS vec_score
          FROM magazine_content mc
          ORDER BY mc.embedding <-> :qvec
          LIMIT :vec_k
        ),
        combined AS (
          SELECT COALESCE(kw.content_id, vec.content_id) AS content_id,
                 COALESCE(kw.kw_score, 0) AS kw_score,
                 COALESCE(vec.vec_score, 0) AS vec_score
          FROM kw FULL JOIN vec USING (content_id)
        )
        SELECT c.content_id,
               ( :kw_w * kw_score + :vec_w * vec_score ) AS hybrid_score,
               mi.id AS magazine_id,
               mi.title,
               mi.author,
               mi.category,
               mc.content
        FROM combined c
        JOIN magazine_content mc ON mc.id = c.content_id
        JOIN magazine_info mi ON mi.id = mc.magazine_id
        ORDER BY hybrid_score DESC
        LIMIT :limit;
        """
    )

    params = {
        "q": req.query,
        "qvec": qvec,
        "vec_k": req.top_k * 5,  # pull more from ANN to give fusion room
        "kw_w": req.kw_weight,
        "vec_w": req.vec_weight,
        "limit": req.top_k,
    }

    result = await session.execute(sql, params)
    rows = result.mappings().all()

    return {
        "query": req.query,
        "top_k": req.top_k,
        "results": [
            {
                "content_id": r["content_id"],
                "score": float(r["hybrid_score"]),
                "magazine": {
                    "id": r["magazine_id"],
                    "title": r["title"],
                    "author": r["author"],
                    "category": r["category"],
                },
                "snippet": r["content"][:240]
            }
            for r in rows
        ]
    }
