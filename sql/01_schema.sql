-- Main tables
CREATE TABLE
    IF NOT EXISTS magazine_info (
        id BIGSERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        author TEXT NOT NULL,
        publication_date DATE NOT NULL,
        category TEXT NOT NULL,
        -- Filled by trigger in 02_triggers.sql
        info_tsv TSVECTOR
    );

CREATE TABLE
    IF NOT EXISTS magazine_content (
        id BIGSERIAL PRIMARY KEY,
        magazine_id BIGINT NOT NULL REFERENCES magazine_info (id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        embedding VECTOR (384), -- vector embedding for semantic search
        -- Filled by trigger in 02_triggers.sql
        content_tsv TSVECTOR
    );
