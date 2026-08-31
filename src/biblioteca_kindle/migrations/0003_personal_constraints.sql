CREATE UNIQUE INDEX collections_root_name_unique
    ON collections(name)
    WHERE parent_id IS NULL;
