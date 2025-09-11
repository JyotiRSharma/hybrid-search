-- Start import

-- Enable pgvector (safe to run multiple times)
CREATE EXTENSION IF NOT EXISTS vector;

-- 1) Main tables
CREATE TABLE IF NOT EXISTS magazine_info (
  id BIGSERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  author TEXT NOT NULL,
  publication_date DATE NOT NULL,
  category TEXT NOT NULL,
  info_tsv TSVECTOR
);

CREATE TABLE IF NOT EXISTS magazine_content (
  id BIGSERIAL PRIMARY KEY,
  magazine_id BIGINT NOT NULL REFERENCES magazine_info(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  embedding VECTOR(384),   -- can stay NULL for now; we’ll backfill later
  content_tsv TSVECTOR
);

CREATE OR REPLACE FUNCTION magazine_info_tsv_trigger() RETURNS trigger AS $$
BEGIN
  NEW.info_tsv := to_tsvector('english',
    COALESCE(NEW.title,'') || ' ' || COALESCE(NEW.author,'') || ' ' || COALESCE(NEW.category,''));
  RETURN NEW;
END$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS magazine_info_tsv_update ON magazine_info;
CREATE TRIGGER magazine_info_tsv_update
BEFORE INSERT OR UPDATE ON magazine_info
FOR EACH ROW EXECUTE FUNCTION magazine_info_tsv_trigger();

CREATE OR REPLACE FUNCTION magazine_content_tsv_trigger() RETURNS trigger AS $$
BEGIN
  NEW.content_tsv := to_tsvector('english', COALESCE(NEW.content,''));
  RETURN NEW;
END$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS magazine_content_tsv_update ON magazine_content;
CREATE TRIGGER magazine_content_tsv_update
BEFORE INSERT OR UPDATE ON magazine_content
FOR EACH ROW EXECUTE FUNCTION magazine_content_tsv_trigger();

-- 3) Indexes for speed
CREATE INDEX IF NOT EXISTS idx_mag_info_tsv    ON magazine_info    USING GIN (info_tsv);
CREATE INDEX IF NOT EXISTS idx_mag_content_tsv ON magazine_content USING GIN (content_tsv);
-- CREATE INDEX IF NOT EXISTS idx_mag_content_magazine_id ON magazine_content(magazine_id);

-- Insert data to magazine_info
-- Pick ONE of the to_date() formats below
INSERT INTO magazine_info (title, author, publication_date, category)
SELECT DISTINCT
  title,
  author,
  to_date(publication_date, 'DD/MM/YY')::date,  -- OR 'MM/DD/YY'
  category
FROM import_articles;

-- Add data into magazine_content
INSERT INTO magazine_content (magazine_id, content)
SELECT mi.id, ia.content
FROM import_articles ia
JOIN magazine_info mi
  ON mi.title = ia.title
 AND mi.author = ia.author
 AND mi.category = ia.category
 AND mi.publication_date = to_date(ia.publication_date, 'DD/MM/YY')::date; -- OR 'MM/DD/YY'
