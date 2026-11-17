-- =============================================================================
-- Migration 021: Omnisearch Support & Cross-Entity Record Links
-- Phase 3C.5: Reflective Intelligence & Omnisearch
-- =============================================================================
-- Introduces:
--   1. record_links — user-isolated cross-entity relationship graph with RLS.
--   2. Full-text search indexes on tasks, projects, goals (pg_trgm trigrams).
--   3. Composite indexes on conversations and messages for search efficiency.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Enable pg_trgm extension (safe no-op if already present)
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------------
-- 2. record_links table — tenant-isolated cross-entity relationship store
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS record_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_type     TEXT NOT NULL
                        CHECK (source_type IN ('conversation','message','memory','task','project','goal')),
    source_id       UUID NOT NULL,
    target_type     TEXT NOT NULL
                        CHECK (target_type IN ('conversation','message','memory','task','project','goal')),
    target_id       UUID NOT NULL,
    relationship_type TEXT NOT NULL DEFAULT 'related'
                        CHECK (relationship_type IN ('related','supports','contradicts','supersedes','derived_from','referenced_in')),
    confidence      NUMERIC(4,3) NOT NULL DEFAULT 1.000
                        CHECK (confidence >= 0 AND confidence <= 1),
    is_inferred     BOOLEAN NOT NULL DEFAULT FALSE,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Prevent duplicate links between the same pair in the same direction
    CONSTRAINT record_links_unique_pair UNIQUE (user_id, source_type, source_id, target_type, target_id, relationship_type)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_record_links_user     ON record_links (user_id);
CREATE INDEX IF NOT EXISTS idx_record_links_source   ON record_links (user_id, source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_record_links_target   ON record_links (user_id, target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_record_links_inferred ON record_links (user_id, is_inferred);

-- updated_at trigger
CREATE OR REPLACE FUNCTION set_record_links_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_record_links_updated_at ON record_links;
CREATE TRIGGER trg_record_links_updated_at
    BEFORE UPDATE ON record_links
    FOR EACH ROW EXECUTE FUNCTION set_record_links_updated_at();

-- ---------------------------------------------------------------------------
-- 3. Row-Level Security on record_links
-- ---------------------------------------------------------------------------
ALTER TABLE record_links ENABLE ROW LEVEL SECURITY;

-- Drop any old policies first (idempotent)
DROP POLICY IF EXISTS record_links_select ON record_links;
DROP POLICY IF EXISTS record_links_insert ON record_links;
DROP POLICY IF EXISTS record_links_update ON record_links;
DROP POLICY IF EXISTS record_links_delete ON record_links;

CREATE POLICY record_links_select ON record_links
    FOR SELECT TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY record_links_insert ON record_links
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid());

CREATE POLICY record_links_update ON record_links
    FOR UPDATE TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY record_links_delete ON record_links
    FOR DELETE TO authenticated
    USING (user_id = auth.uid());

-- Revoke anon access
REVOKE ALL ON record_links FROM anon;

-- ---------------------------------------------------------------------------
-- 4. Full-text / trigram search indexes on productivity tables
-- ---------------------------------------------------------------------------

-- tasks
CREATE INDEX IF NOT EXISTS idx_tasks_title_trgm
    ON tasks USING gin (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_tasks_description_trgm
    ON tasks USING gin (description gin_trgm_ops)
    WHERE description IS NOT NULL;

-- projects
CREATE INDEX IF NOT EXISTS idx_projects_name_trgm
    ON projects USING gin (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_projects_description_trgm
    ON projects USING gin (description gin_trgm_ops)
    WHERE description IS NOT NULL;

-- goals
CREATE INDEX IF NOT EXISTS idx_goals_title_trgm
    ON goals USING gin (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_goals_description_trgm
    ON goals USING gin (description gin_trgm_ops)
    WHERE description IS NOT NULL;

-- conversations (title search)
CREATE INDEX IF NOT EXISTS idx_conversations_title_trgm
    ON conversations USING gin (title gin_trgm_ops)
    WHERE title IS NOT NULL;

-- messages (content full-text search)
CREATE INDEX IF NOT EXISTS idx_messages_content_trgm
    ON messages USING gin (content gin_trgm_ops)
    WHERE content IS NOT NULL;

-- memories (content full-text search) — backup to vector retrieval
CREATE INDEX IF NOT EXISTS idx_memories_content_trgm
    ON memories USING gin (content gin_trgm_ops)
    WHERE lifecycle_status IN ('active', 'superseded');

-- ---------------------------------------------------------------------------
-- 5. Comments
-- ---------------------------------------------------------------------------
COMMENT ON TABLE record_links IS
    'Phase 3C.5: Tenant-isolated cross-entity relationship graph for Reflective Intelligence. '
    'Rows are strictly owned by user_id via RLS. is_inferred=TRUE marks AI-suggested links '
    'that have not been confirmed by the user.';

