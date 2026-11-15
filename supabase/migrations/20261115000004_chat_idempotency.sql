-- Migration: 004_chat_idempotency.sql
-- Description: Adds idempotency_key to messages table to prevent duplicate AI requests and message duplication on network retry

ALTER TABLE public.messages
ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

-- Enforce unique idempotency keys per user to guarantee deduplication on network retries
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_user_idempotency
ON public.messages (user_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

