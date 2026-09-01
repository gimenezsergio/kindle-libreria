CREATE TABLE ai_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    prompt TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    is_archived INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_ai_profiles_name_active ON ai_profiles(name COLLATE NOCASE) WHERE is_archived = 0;
CREATE UNIQUE INDEX idx_ai_profiles_one_default ON ai_profiles(is_default) WHERE is_default = 1;

INSERT INTO ai_profiles(id, name, description, prompt, is_default)
VALUES ('companion', 'Compañero de lectura',
        'Una perspectiva abierta para explorar la lectura sin imponer conclusiones.',
        'Conversá como un compañero de lectura curioso y riguroso. Ayudá a formular preguntas, contrastar interpretaciones y descubrir relaciones. Presentá las ideas como hipótesis conversables, distinguí hechos de interpretaciones y no inventes contenido de los libros.', 1);
