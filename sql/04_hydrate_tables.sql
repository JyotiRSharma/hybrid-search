-- Start import

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
