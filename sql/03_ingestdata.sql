-- 1) Staging table
DROP TABLE IF EXISTS import_articles;
CREATE TABLE import_articles (
  title            text,
  author           text,
  publication_date text,
  category         text,
  content          text
);

-- 2) Server-side COPY (pure SQL)
COPY import_articles (title, author, publication_date, category, content)
FROM '/import/articles.csv'
WITH (FORMAT csv, HEADER true);
