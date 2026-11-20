-- Migration: Add cryptographic integrity signature column to journal_entries
-- Supports RFC 8785 canonical JSON and HMAC-SHA256 integrity verification.

ALTER TABLE public.journal_entries
ADD COLUMN IF NOT EXISTS integrity_signature TEXT;

COMMENT ON COLUMN public.journal_entries.integrity_signature IS
'RFC 8785 canonical JSON HMAC-SHA256 integrity signature for tamper detection.';
