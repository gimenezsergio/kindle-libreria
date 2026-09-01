ALTER TABLE cover_candidates ADD COLUMN external_key TEXT;
ALTER TABLE cover_candidates ADD COLUMN search_round INTEGER NOT NULL DEFAULT 1;
CREATE UNIQUE INDEX idx_cover_candidates_external_key ON cover_candidates(work_id, external_key) WHERE external_key IS NOT NULL;
