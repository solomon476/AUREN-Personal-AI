-- Migration: 006_chat_requests_fingerprint.sql
-- Description: Add immutable request_fingerprint column to chat_requests table to bind idempotency keys to request content

ALTER TABLE public.chat_requests ADD COLUMN IF NOT EXISTS request_fingerprint TEXT;

