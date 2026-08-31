CREATE TABLE works (
    id TEXT PRIMARY KEY,
    preferred_title TEXT NOT NULL,
    merge_status TEXT NOT NULL DEFAULT 'normal'
        CHECK (merge_status IN ('normal', 'provisional', 'review')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE editions (
    id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL REFERENCES works(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    subtitle TEXT,
    language TEXT,
    publication_date TEXT,
    publisher TEXT,
    format_hint TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE INDEX editions_work_idx ON editions(work_id);

CREATE TABLE contributors (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE INDEX contributors_normalized_name_idx
    ON contributors(normalized_name);

CREATE TABLE edition_contributors (
    edition_id TEXT NOT NULL REFERENCES editions(id) ON DELETE CASCADE,
    contributor_id TEXT NOT NULL REFERENCES contributors(id) ON DELETE RESTRICT,
    role TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (edition_id, contributor_id, role)
) STRICT;

CREATE TABLE device_snapshots (
    id TEXT PRIMARY KEY,
    device_key TEXT NOT NULL,
    mount_point TEXT NOT NULL,
    mount_read_only INTEGER NOT NULL CHECK (mount_read_only IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    summary_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(summary_json)),
    warning_count INTEGER NOT NULL DEFAULT 0 CHECK (warning_count >= 0)
) STRICT;

CREATE INDEX device_snapshots_device_time_idx
    ON device_snapshots(device_key, started_at DESC);

CREATE TABLE source_observations (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES device_snapshots(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_relative_path TEXT NOT NULL,
    file_size INTEGER NOT NULL CHECK (file_size >= 0),
    file_modified_at TEXT,
    file_hash TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    parser_name TEXT,
    parser_version TEXT,
    parse_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (parse_status IN ('pending', 'parsed', 'warning', 'failed', 'ignored')),
    warning_json TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(warning_json)),
    UNIQUE (snapshot_id, source_relative_path)
) STRICT;

CREATE INDEX source_observations_hash_idx
    ON source_observations(file_hash, parser_name, parser_version);

CREATE TABLE kindle_deliveries (
    id TEXT PRIMARY KEY,
    edition_id TEXT NOT NULL REFERENCES editions(id) ON DELETE RESTRICT,
    source_observation_id TEXT REFERENCES source_observations(id) ON DELETE SET NULL,
    kindle_content_id TEXT,
    content_type TEXT,
    document_format TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sidecar_relative_path TEXT,
    file_size INTEGER NOT NULL CHECK (file_size >= 0),
    file_modified_at TEXT,
    content_hash TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    presence TEXT NOT NULL DEFAULT 'present'
        CHECK (presence IN ('present', 'absent', 'unknown')),
    UNIQUE (content_type, kindle_content_id)
) STRICT;

CREATE INDEX kindle_deliveries_edition_idx ON kindle_deliveries(edition_id);
CREATE INDEX kindle_deliveries_presence_idx ON kindle_deliveries(presence);

CREATE TABLE external_identifiers (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL
        CHECK (entity_type IN ('work', 'edition', 'kindle_delivery')),
    entity_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    value TEXT NOT NULL,
    source_observation_id TEXT REFERENCES source_observations(id) ON DELETE SET NULL,
    confidence TEXT NOT NULL
        CHECK (confidence IN ('exact', 'high', 'medium', 'low')),
    is_preferred INTEGER NOT NULL DEFAULT 0 CHECK (is_preferred IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (namespace, value, entity_type, entity_id)
) STRICT;

CREATE INDEX external_identifiers_entity_idx
    ON external_identifiers(entity_type, entity_id);

CREATE TABLE title_aliases (
    id TEXT PRIMARY KEY,
    edition_id TEXT REFERENCES editions(id) ON DELETE CASCADE,
    original_title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    source_observation_id TEXT REFERENCES source_observations(id) ON DELETE SET NULL,
    confidence TEXT NOT NULL
        CHECK (confidence IN ('exact', 'high', 'medium', 'low')),
    resolution_status TEXT NOT NULL DEFAULT 'resolved'
        CHECK (resolution_status IN ('resolved', 'provisional', 'conflict')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE INDEX title_aliases_normalized_idx ON title_aliases(normalized_title);

CREATE TABLE reading_states (
    id TEXT PRIMARY KEY,
    kindle_delivery_id TEXT NOT NULL
        REFERENCES kindle_deliveries(id) ON DELETE CASCADE,
    source_observation_id TEXT NOT NULL
        REFERENCES source_observations(id) ON DELETE RESTRICT,
    observed_at TEXT NOT NULL,
    last_position_native TEXT NOT NULL,
    last_position_type TEXT NOT NULL,
    last_position_at TEXT,
    furthest_position_native TEXT,
    furthest_position_type TEXT,
    furthest_position_at TEXT,
    progress_fraction REAL CHECK (
        progress_fraction IS NULL OR
        (progress_fraction >= 0.0 AND progress_fraction <= 1.0)
    ),
    progress_method TEXT,
    reading_time_ms INTEGER CHECK (reading_time_ms IS NULL OR reading_time_ms >= 0),
    words_read INTEGER CHECK (words_read IS NULL OR words_read >= 0),
    UNIQUE (kindle_delivery_id, source_observation_id)
) STRICT;

CREATE INDEX reading_states_delivery_time_idx
    ON reading_states(kindle_delivery_id, observed_at DESC);

CREATE TABLE annotations (
    id TEXT PRIMARY KEY,
    edition_id TEXT NOT NULL REFERENCES editions(id) ON DELETE RESTRICT,
    kind TEXT NOT NULL
        CHECK (kind IN ('highlight', 'note', 'bookmark', 'other')),
    text TEXT,
    note_text TEXT,
    start_position_native TEXT,
    end_position_native TEXT,
    position_type TEXT,
    native_created_at TEXT,
    native_modified_at TEXT,
    status TEXT NOT NULL DEFAULT 'unknown'
        CHECK (status IN ('active', 'historical', 'deleted', 'unknown')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE INDEX annotations_edition_kind_idx ON annotations(edition_id, kind);

CREATE TABLE annotation_occurrences (
    id TEXT PRIMARY KEY,
    annotation_id TEXT NOT NULL REFERENCES annotations(id) ON DELETE CASCADE,
    source_observation_id TEXT NOT NULL
        REFERENCES source_observations(id) ON DELETE RESTRICT,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('clippings', 'krds', 'han', 'other')),
    source_record_key TEXT NOT NULL,
    original_heading TEXT,
    original_position TEXT,
    original_date TEXT,
    raw_payload_ref TEXT,
    observed_at TEXT NOT NULL,
    UNIQUE (source_kind, source_record_key)
) STRICT;

CREATE INDEX annotation_occurrences_annotation_idx
    ON annotation_occurrences(annotation_id);

CREATE TABLE collections (
    id TEXT PRIMARY KEY,
    parent_id TEXT REFERENCES collections(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (parent_id, name)
) STRICT;

CREATE TABLE work_collections (
    work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    display_order INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    PRIMARY KEY (work_id, collection_id)
) STRICT;

CREATE TABLE personal_notes (
    id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL
        CHECK (target_type IN ('work', 'edition', 'annotation', 'work_relation')),
    target_id TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE INDEX personal_notes_target_idx ON personal_notes(target_type, target_id);

CREATE TABLE work_relations (
    id TEXT PRIMARY KEY,
    source_work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    target_work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    label TEXT,
    explanation TEXT,
    is_symmetric INTEGER NOT NULL DEFAULT 0 CHECK (is_symmetric IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (source_work_id <> target_work_id),
    UNIQUE (source_work_id, target_work_id, relation_type)
) STRICT;

CREATE INDEX work_relations_target_idx ON work_relations(target_work_id);

