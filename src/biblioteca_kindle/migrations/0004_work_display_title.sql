ALTER TABLE works ADD COLUMN display_title TEXT
    CHECK (display_title IS NULL OR length(trim(display_title)) > 0);
