-- ─────────────────────────────────────────────
-- SERVANTS
-- ─────────────────────────────────────────────
CREATE TABLE public.servants (
    collection_no     INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    class_name        TEXT NOT NULL,
    rarity            SMALLINT NOT NULL,
    -- NP card type for filtering; null when the servant can choose at runtime
    np_card           TEXT,
    np_card_variable  BOOLEAN NOT NULL DEFAULT false,
    np_card_options   TEXT[],
    -- attackEnemyOne | attackEnemyAll | support
    attack_type       TEXT,
    is_enemy_only     BOOLEAN NOT NULL DEFAULT false,
    -- null | 'irreversible' | 'reversible'  (ascension-locked kit servants)
    form_transition   TEXT,
    -- arbitrary parser annotations consumed by the simulation engine
    parser_flags      JSONB,
    aa_data_hash      TEXT,
    data              JSONB NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.servants ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read" ON public.servants
    FOR SELECT TO anon USING (true);

CREATE INDEX servants_class_name_idx  ON public.servants (class_name);
CREATE INDEX servants_rarity_idx      ON public.servants (rarity);
CREATE INDEX servants_np_card_idx     ON public.servants (np_card);
CREATE INDEX servants_attack_type_idx ON public.servants (attack_type);


-- ─────────────────────────────────────────────
-- QUESTS
-- ─────────────────────────────────────────────
CREATE TABLE public.quests (
    id            INTEGER PRIMARY KEY,
    name          TEXT,
    war_id        INTEGER,
    war_name      TEXT,
    recommend_lv  TEXT,
    consume       SMALLINT,
    after_clear   TEXT,
    data          JSONB NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.quests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read" ON public.quests
    FOR SELECT TO anon USING (true);

CREATE INDEX quests_war_id_idx ON public.quests (war_id);


-- ─────────────────────────────────────────────
-- MYSTIC CODES
-- ─────────────────────────────────────────────
CREATE TABLE public.mystic_codes (
    id            INTEGER PRIMARY KEY,
    name          TEXT,
    aa_data_hash  TEXT,
    data          JSONB NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.mystic_codes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read" ON public.mystic_codes
    FOR SELECT TO anon USING (true);


-- ─────────────────────────────────────────────
-- METADATA
-- ─────────────────────────────────────────────
CREATE TABLE public.metadata (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.metadata ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read" ON public.metadata
    FOR SELECT TO anon USING (true);
