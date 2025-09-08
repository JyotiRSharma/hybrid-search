-- Full-text (keyword) indexes
CREATE INDEX IF NOT EXISTS idx_mag_info_tsv ON magazine_info USING GIN (info_tsv);

CREATE INDEX IF NOT EXISTS idx_mag_content_tsv ON magazine_content USING GIN (content_tsv);

-- Vector ANN index (pgvector)
-- IVFFLAT is a good baseline; tune `lists` as data grows.
CREATE INDEX IF NOT EXISTS idx_mag_content_embedding_ivf ON magazine_content USING ivfflat (embedding vector_cosine_ops)
WITH
    (lists = 200);

-- Optional (if your pgvector build supports it and RAM allows):
-- CREATE INDEX IF NOT EXISTS idx_mag_content_embedding_hnsw ON magazine_content USING hnsw (embedding vector_cosine_ops);

-- Helpful join/filter index
CREATE INDEX IF NOT EXISTS idx_mag_content_magazine_id ON magazine_content (magazine_id);
