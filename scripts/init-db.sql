-- Dev bootstrap for dating app (idempotent-friendly)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Placeholder schema marker; Alembic will own real migrations later.
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO schema_meta (key, value)
VALUES ('bootstrap', 'docker-init')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
