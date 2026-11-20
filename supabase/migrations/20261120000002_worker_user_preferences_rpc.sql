-- Migration: RPC for background worker to securely retrieve user extraction preferences

CREATE OR REPLACE FUNCTION public.get_user_extraction_preferences_rpc(
    p_user_id UUID,
    p_worker_id TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_prefs JSONB;
BEGIN
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user does not possess the auren_worker role'
            USING ERRCODE = '42501';
    END IF;

    SELECT preferences INTO v_prefs FROM public.profiles WHERE id = p_user_id;
    RETURN COALESCE(v_prefs, '{}'::jsonb);
END;
$$;

REVOKE ALL ON FUNCTION public.get_user_extraction_preferences_rpc(UUID, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_user_extraction_preferences_rpc(UUID, TEXT) TO auren_worker;
