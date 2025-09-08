-- Maintain tsvector columns via triggers (portable across PG versions)

-- Recreate safely
CREATE OR REPLACE FUNCTION magazine_info_tsv_trigger() RETURNS trigger AS $$
BEGIN
  NEW.info_tsv := to_tsvector(
    'english',
    COALESCE(NEW.title,'') || ' ' ||
    COALESCE(NEW.author,'') || ' ' ||
    COALESCE(NEW.category,'')
  );
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS magazine_info_tsv_update ON magazine_info;
CREATE TRIGGER magazine_info_tsv_update
BEFORE INSERT OR UPDATE ON magazine_info
FOR EACH ROW
EXECUTE FUNCTION magazine_info_tsv_trigger();


CREATE OR REPLACE FUNCTION magazine_content_tsv_trigger() RETURNS trigger AS $$
BEGIN
  NEW.content_tsv := to_tsvector('english', COALESCE(NEW.content,''));
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS magazine_content_tsv_update ON magazine_content;
CREATE TRIGGER magazine_content_tsv_update
BEFORE INSERT OR UPDATE ON magazine_content
FOR EACH ROW
EXECUTE FUNCTION magazine_content_tsv_trigger();