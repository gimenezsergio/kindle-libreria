CREATE TABLE IF NOT EXISTS philosophical_inquiries (
    id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    chapter_or_section TEXT,
    dilemma_question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sparring' CHECK (status IN ('draft', 'sparring', 'ready_to_write', 'completed')),
    
    -- Andamiaje síntesis generado por el tutor
    outline_thesis TEXT,
    outline_objection TEXT,
    outline_counterargument TEXT,
    
    -- El texto propio de cierre (300 a 600 palabras)
    final_text TEXT,
    word_count INTEGER DEFAULT 0 CHECK (word_count >= 0),
    
    -- Para reflexiones fechadas que revisan una postura anterior
    parent_inquiry_id TEXT REFERENCES philosophical_inquiries(id) ON DELETE SET NULL,
    
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
) STRICT;

CREATE INDEX IF NOT EXISTS philosophical_inquiries_work_idx
    ON philosophical_inquiries(work_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS inquiry_annotations (
    inquiry_id TEXT NOT NULL REFERENCES philosophical_inquiries(id) ON DELETE CASCADE,
    annotation_id TEXT NOT NULL REFERENCES annotations(id) ON DELETE CASCADE,
    display_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (inquiry_id, annotation_id)
) STRICT;

CREATE TABLE IF NOT EXISTS inquiry_messages (
    id TEXT PRIMARY KEY,
    inquiry_id TEXT NOT NULL REFERENCES philosophical_inquiries(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    role TEXT NOT NULL CHECK (role IN ('user', 'tutor')),
    content TEXT NOT NULL CHECK (length(trim(content)) > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (inquiry_id, sequence)
) STRICT;

CREATE INDEX IF NOT EXISTS inquiry_messages_inquiry_seq_idx
    ON inquiry_messages(inquiry_id, sequence);

CREATE TABLE IF NOT EXISTS inquiry_tags (
    inquiry_id TEXT NOT NULL REFERENCES philosophical_inquiries(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (inquiry_id, tag)
) STRICT;

CREATE INDEX IF NOT EXISTS inquiry_tags_tag_idx
    ON inquiry_tags(tag);

CREATE TABLE IF NOT EXISTS annotation_contexts (
    annotation_id TEXT PRIMARY KEY REFERENCES annotations(id) ON DELETE CASCADE,
    chapter_title TEXT,
    surrounding_before TEXT,
    surrounding_after TEXT,
    extracted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;
