-- Migration: 005_chat_requests_idempotency.sql
-- Description: State table tracking chat request lifecycle for strict idempotency, deduplication, and recovery

CREATE TABLE IF NOT EXISTS public.chat_requests (
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('processing', 'completed', 'failed', 'interrupted')),
    user_message_id UUID NOT NULL REFERENCES public.messages(id) ON DELETE CASCADE,
    assistant_message_id UUID REFERENCES public.messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    PRIMARY KEY (user_id, idempotency_key)
);

-- Automatic timestamp management
DROP TRIGGER IF EXISTS set_chat_requests_updated_at ON public.chat_requests;
CREATE TRIGGER set_chat_requests_updated_at
    BEFORE UPDATE ON public.chat_requests
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- Enable and force Row Level Security
ALTER TABLE public.chat_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_requests FORCE ROW LEVEL SECURITY;

CREATE POLICY "chat_requests_all_own" ON public.chat_requests
    FOR ALL TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Performance and lookup index
CREATE INDEX IF NOT EXISTS idx_chat_requests_user_status ON public.chat_requests(user_id, status);
