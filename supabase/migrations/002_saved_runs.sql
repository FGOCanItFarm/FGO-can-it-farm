-- Saved community farming runs.
-- Clients submit via supabase.rpc('submit_run', {...}) — never direct INSERT.
-- Pruning rule: lower total_np_cost wins for the same quest+servants+np_levels key.

CREATE TABLE IF NOT EXISTS public.saved_runs (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quest_id               INTEGER NOT NULL,
    servant_collection_nos INTEGER[] NOT NULL,
    np_levels              SMALLINT[] NOT NULL,
    total_np_cost          SMALLINT NOT NULL,
    token_string           TEXT NOT NULL,
    wave_results           JSONB NOT NULL DEFAULT '{}',
    submitted_at           TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_run_key UNIQUE (quest_id, servant_collection_nos, np_levels)
);

ALTER TABLE public.saved_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read" ON public.saved_runs
    FOR SELECT TO anon USING (true);

CREATE INDEX saved_runs_quest_id_idx ON public.saved_runs (quest_id);
CREATE INDEX saved_runs_servants_idx ON public.saved_runs USING GIN (servant_collection_nos);
CREATE INDEX saved_runs_cost_idx     ON public.saved_runs (total_np_cost);

-- RPC called by browser clients. SECURITY DEFINER bypasses RLS so the
-- ON CONFLICT ... WHERE pruning clause can execute an UPDATE atomically.
CREATE OR REPLACE FUNCTION public.submit_run(
    p_quest_id               INTEGER,
    p_servant_collection_nos INTEGER[],
    p_np_levels              SMALLINT[],
    p_total_np_cost          SMALLINT,
    p_token_string           TEXT,
    p_wave_results           JSONB
) RETURNS void
  LANGUAGE sql
  SECURITY DEFINER
  SET search_path = public
AS $$
    INSERT INTO public.saved_runs (
        quest_id, servant_collection_nos, np_levels,
        total_np_cost, token_string, wave_results
    ) VALUES (
        p_quest_id, p_servant_collection_nos, p_np_levels,
        p_total_np_cost, p_token_string, p_wave_results
    )
    ON CONFLICT ON CONSTRAINT uq_run_key DO UPDATE
        SET token_string  = EXCLUDED.token_string,
            wave_results  = EXCLUDED.wave_results,
            total_np_cost = EXCLUDED.total_np_cost,
            submitted_at  = now()
        WHERE EXCLUDED.total_np_cost < saved_runs.total_np_cost;
$$;

GRANT EXECUTE ON FUNCTION public.submit_run TO anon;
