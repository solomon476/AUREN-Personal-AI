-- Migration: 20261121000002_connections_and_journeys.sql
-- Description: Trusted Connections, Voluntary Location Sharing, and Offline-Capable GPS Journeys

-- 1. Trusted Connections Table
CREATE TABLE IF NOT EXISTS public.connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    connected_user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
    invite_code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    avatar_initials TEXT NOT NULL DEFAULT 'TC',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined', 'revoked')),
    location_sharing_active BOOLEAN NOT NULL DEFAULT FALSE,
    location_sharing_expires_at TIMESTAMPTZ,
    last_latitude DOUBLE PRECISION,
    last_longitude DOUBLE PRECISION,
    last_location_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_connections_user_id ON public.connections(user_id);
CREATE INDEX IF NOT EXISTS idx_connections_connected_user ON public.connections(connected_user_id);
CREATE INDEX IF NOT EXISTS idx_connections_invite_code ON public.connections(invite_code);
CREATE INDEX IF NOT EXISTS idx_connections_status ON public.connections(status);

-- 2. GPS Journeys Table
CREATE TABLE IF NOT EXISTS public.journeys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('recording', 'paused', 'completed', 'cancelled')),
    distance_meters DOUBLE PRECISION NOT NULL DEFAULT 0,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    avg_speed_kmh DOUBLE PRECISION DEFAULT 0,
    is_offline_recorded BOOLEAN NOT NULL DEFAULT FALSE,
    is_team_assignment BOOLEAN NOT NULL DEFAULT FALSE,
    assignment_site TEXT,
    assignment_purpose TEXT,
    assignment_notes TEXT,
    check_in_time TIMESTAMPTZ,
    check_in_coords TEXT,
    points JSONB NOT NULL DEFAULT '[]'::jsonb,
    idempotency_key TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_journeys_user_id ON public.journeys(user_id);
CREATE INDEX IF NOT EXISTS idx_journeys_status ON public.journeys(status);
CREATE INDEX IF NOT EXISTS idx_journeys_created_at ON public.journeys(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_journeys_idempotency ON public.journeys(idempotency_key);

-- 3. Row Level Security Policies
ALTER TABLE public.connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.journeys ENABLE ROW LEVEL SECURITY;

-- Connections RLS: User can see connections where they are creator or recipient
CREATE POLICY "Users can view connections they belong to"
    ON public.connections
    FOR SELECT
    USING (auth.uid() = user_id OR auth.uid() = connected_user_id);

CREATE POLICY "Users can create connection invites"
    ON public.connections
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update connections they belong to"
    ON public.connections
    FOR UPDATE
    USING (auth.uid() = user_id OR auth.uid() = connected_user_id);

CREATE POLICY "Users can delete connections they created"
    ON public.connections
    FOR DELETE
    USING (auth.uid() = user_id);

-- Journeys RLS: Strictly private to owner
CREATE POLICY "Users can view own journeys"
    ON public.journeys
    FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can create own journeys"
    ON public.journeys
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own journeys"
    ON public.journeys
    FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own journeys"
    ON public.journeys
    FOR DELETE
    USING (auth.uid() = user_id);

