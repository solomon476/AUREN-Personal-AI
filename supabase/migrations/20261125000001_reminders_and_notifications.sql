-- ============================================================================
-- AUREN Schema Migration: 20261125000001_reminders_and_notifications.sql
-- Description: Smart Reminders, Alarm System, In-App Notifications,
--              Web Push Subscriptions, Delivery Audit Logs, and Worker RPCs.
-- Security: Enforces strict RLS tenant isolation, cross-tenant entity validation,
--           least-privilege grants, and auren_worker-fenced SECURITY DEFINER RPCs.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Reminders Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    task_id UUID REFERENCES public.tasks(id) ON DELETE SET NULL,
    project_id UUID REFERENCES public.projects(id) ON DELETE SET NULL,
    goal_id UUID REFERENCES public.goals(id) ON DELETE SET NULL,
    title TEXT NOT NULL CHECK (char_length(trim(title)) > 0 AND char_length(title) <= 255),
    description TEXT,
    reminder_type TEXT NOT NULL DEFAULT 'general'
        CHECK (reminder_type IN (
            'general', 'task_before_due', 'task_due', 'task_overdue',
            'briefing', 'review', 'alarm', 'appointment', 'goal'
        )),
    trigger_at TIMESTAMPTZ NOT NULL,
    original_trigger_at TIMESTAMPTZ NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    recurrence_rule JSONB,
    recurrence_text TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'due', 'snoozed', 'completed', 'cancelled', 'missed')),
    priority TEXT NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('low', 'normal', 'high', 'alarm')),
    is_alarm BOOLEAN NOT NULL DEFAULT FALSE,
    sound_key TEXT,
    snoozed_until TIMESTAMPTZ,
    snooze_count INT NOT NULL DEFAULT 0 CHECK (snooze_count >= 0),
    last_triggered_at TIMESTAMPTZ,
    next_retry_at TIMESTAMPTZ,
    delivery_attempts INT NOT NULL DEFAULT 0 CHECK (delivery_attempts >= 0),
    max_delivery_attempts INT NOT NULL DEFAULT 5 CHECK (max_delivery_attempts BETWEEN 1 AND 20),
    escalation_count INT NOT NULL DEFAULT 0 CHECK (escalation_count >= 0),
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    source TEXT NOT NULL DEFAULT 'manual'
        CHECK (source IN ('manual', 'chat', 'task_sync', 'system_briefing')),
    dedupe_key TEXT,
    claimed_by TEXT,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_reminders_user_status_trigger
    ON public.reminders(user_id, status, trigger_at ASC);
CREATE INDEX IF NOT EXISTS idx_reminders_due_scan
    ON public.reminders(status, trigger_at ASC)
    WHERE status IN ('scheduled', 'snoozed');
CREATE INDEX IF NOT EXISTS idx_reminders_task_id
    ON public.reminders(task_id)
    WHERE task_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_reminders_active_dedupe
    ON public.reminders(user_id, dedupe_key)
    WHERE dedupe_key IS NOT NULL AND status IN ('scheduled', 'due', 'snoozed');

-- ----------------------------------------------------------------------------
-- 2. In-App Notifications Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    reminder_id UUID REFERENCES public.reminders(id) ON DELETE SET NULL,
    task_id UUID REFERENCES public.tasks(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    body TEXT,
    category TEXT NOT NULL DEFAULT 'reminder'
        CHECK (category IN ('reminder', 'alarm', 'task', 'system', 'briefing')),
    priority TEXT NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('low', 'normal', 'high', 'alarm')),
    is_alarm BOOLEAN NOT NULL DEFAULT FALSE,
    action_url TEXT NOT NULL DEFAULT '/reminders',
    delivery_channel TEXT NOT NULL DEFAULT 'in_app'
        CHECK (delivery_channel IN ('in_app', 'web_push', 'both')),
    status TEXT NOT NULL DEFAULT 'unread'
        CHECK (status IN ('unread', 'read', 'dismissed', 'acted', 'suppressed_quiet_hours')),
    occurrence_key TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    read_at TIMESTAMPTZ,
    acted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_user_occurrence
    ON public.notifications(user_id, occurrence_key);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
    ON public.notifications(user_id, status, triggered_at DESC);

-- ----------------------------------------------------------------------------
-- 3. Web Push Subscriptions Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.push_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth_secret TEXT NOT NULL,
    user_agent TEXT,
    device_label TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    failure_count INT NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
    last_error TEXT,
    last_success_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT uq_push_subscriptions_user_endpoint UNIQUE (user_id, endpoint)
);

CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_active
    ON public.push_subscriptions(user_id, is_active);

-- ----------------------------------------------------------------------------
-- 4. Notification Delivery Logs Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.notification_delivery_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    reminder_id UUID REFERENCES public.reminders(id) ON DELETE CASCADE,
    notification_id UUID REFERENCES public.notifications(id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES public.push_subscriptions(id) ON DELETE SET NULL,
    channel TEXT NOT NULL CHECK (channel IN ('in_app', 'web_push')),
    status TEXT NOT NULL CHECK (status IN (
        'pending', 'sent', 'retrying', 'failed',
        'expired_subscription', 'suppressed_quiet_hours', 'skipped_disabled'
    )),
    attempt_number INT NOT NULL DEFAULT 1,
    http_status INT,
    error_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_delivery_logs_reminder
    ON public.notification_delivery_logs(reminder_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_delivery_logs_user
    ON public.notification_delivery_logs(user_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- 5. Row Level Security Policies (Strict Tenant & Hierarchy Isolation)
-- ----------------------------------------------------------------------------
ALTER TABLE public.reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.push_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_delivery_logs ENABLE ROW LEVEL SECURITY;

-- Reminders RLS (also ensures linked task/project/goal belong to auth.uid())
DROP POLICY IF EXISTS "reminders_select_own" ON public.reminders;
DROP POLICY IF EXISTS "reminders_insert_own" ON public.reminders;
DROP POLICY IF EXISTS "reminders_update_own" ON public.reminders;
DROP POLICY IF EXISTS "reminders_delete_own" ON public.reminders;

CREATE POLICY "reminders_select_own" ON public.reminders
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "reminders_insert_own" ON public.reminders
    FOR INSERT WITH CHECK (
        user_id = auth.uid()
        AND (task_id IS NULL OR EXISTS (SELECT 1 FROM public.tasks t WHERE t.id = task_id AND t.user_id = auth.uid()))
        AND (project_id IS NULL OR EXISTS (SELECT 1 FROM public.projects p WHERE p.id = project_id AND p.user_id = auth.uid()))
        AND (goal_id IS NULL OR EXISTS (SELECT 1 FROM public.goals g WHERE g.id = goal_id AND g.user_id = auth.uid()))
    );

CREATE POLICY "reminders_update_own" ON public.reminders
    FOR UPDATE USING (user_id = auth.uid())
    WITH CHECK (
        user_id = auth.uid()
        AND (task_id IS NULL OR EXISTS (SELECT 1 FROM public.tasks t WHERE t.id = task_id AND t.user_id = auth.uid()))
        AND (project_id IS NULL OR EXISTS (SELECT 1 FROM public.projects p WHERE p.id = project_id AND p.user_id = auth.uid()))
        AND (goal_id IS NULL OR EXISTS (SELECT 1 FROM public.goals g WHERE g.id = goal_id AND g.user_id = auth.uid()))
    );

CREATE POLICY "reminders_delete_own" ON public.reminders
    FOR DELETE USING (user_id = auth.uid());

-- Notifications RLS
DROP POLICY IF EXISTS "notifications_select_own" ON public.notifications;
DROP POLICY IF EXISTS "notifications_insert_own" ON public.notifications;
DROP POLICY IF EXISTS "notifications_update_own" ON public.notifications;
DROP POLICY IF EXISTS "notifications_delete_own" ON public.notifications;

CREATE POLICY "notifications_select_own" ON public.notifications
    FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "notifications_insert_own" ON public.notifications
    FOR INSERT WITH CHECK (user_id = auth.uid());
CREATE POLICY "notifications_update_own" ON public.notifications
    FOR UPDATE USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY "notifications_delete_own" ON public.notifications
    FOR DELETE USING (user_id = auth.uid());

-- Push Subscriptions RLS
DROP POLICY IF EXISTS "push_subscriptions_select_own" ON public.push_subscriptions;
DROP POLICY IF EXISTS "push_subscriptions_insert_own" ON public.push_subscriptions;
DROP POLICY IF EXISTS "push_subscriptions_update_own" ON public.push_subscriptions;
DROP POLICY IF EXISTS "push_subscriptions_delete_own" ON public.push_subscriptions;

CREATE POLICY "push_subscriptions_select_own" ON public.push_subscriptions
    FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "push_subscriptions_insert_own" ON public.push_subscriptions
    FOR INSERT WITH CHECK (user_id = auth.uid());
CREATE POLICY "push_subscriptions_update_own" ON public.push_subscriptions
    FOR UPDATE USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY "push_subscriptions_delete_own" ON public.push_subscriptions
    FOR DELETE USING (user_id = auth.uid());

-- Delivery Logs RLS (Read + Insert by owner; immutable telemetry)
DROP POLICY IF EXISTS "delivery_logs_select_own" ON public.notification_delivery_logs;
DROP POLICY IF EXISTS "delivery_logs_insert_own" ON public.notification_delivery_logs;

CREATE POLICY "delivery_logs_select_own" ON public.notification_delivery_logs
    FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "delivery_logs_insert_own" ON public.notification_delivery_logs
    FOR INSERT WITH CHECK (user_id = auth.uid());

-- ----------------------------------------------------------------------------
-- 6. Least-Privilege Role Grants
-- ----------------------------------------------------------------------------
REVOKE ALL ON TABLE public.reminders FROM anon;
REVOKE ALL ON TABLE public.notifications FROM anon;
REVOKE ALL ON TABLE public.push_subscriptions FROM anon;
REVOKE ALL ON TABLE public.notification_delivery_logs FROM anon;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    public.reminders,
    public.notifications,
    public.push_subscriptions
TO authenticated;

GRANT SELECT, INSERT ON TABLE public.notification_delivery_logs TO authenticated;

-- ----------------------------------------------------------------------------
-- 7. Worker SECURITY DEFINER RPCs (Fenced to auren_worker role)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.claim_due_reminders_rpc(
    p_worker_id TEXT,
    p_batch_size INT DEFAULT 20,
    p_lease_seconds INT DEFAULT 120
)
RETURNS SETOF public.reminders
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
BEGIN
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER
            USING ERRCODE = '42501';
    END IF;

    IF p_worker_id IS NULL OR length(trim(p_worker_id)) = 0 THEN
        RAISE EXCEPTION 'Worker ID cannot be empty' USING ERRCODE = '22023';
    END IF;

    RETURN QUERY
    WITH candidate AS (
        SELECT r.id
        FROM public.reminders r
        WHERE (
            (r.status = 'scheduled' AND r.trigger_at <= clock_timestamp())
            OR (r.status = 'snoozed' AND COALESCE(r.snoozed_until, r.trigger_at) <= clock_timestamp())
            OR (r.status = 'due' AND r.next_retry_at IS NOT NULL AND r.next_retry_at <= clock_timestamp() AND r.delivery_attempts < r.max_delivery_attempts)
        )
        AND (r.lease_expires_at IS NULL OR r.lease_expires_at < clock_timestamp())
        ORDER BY r.trigger_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT GREATEST(1, LEAST(COALESCE(p_batch_size, 20), 100))
    )
    UPDATE public.reminders r
    SET claimed_by = trim(p_worker_id),
        lease_expires_at = clock_timestamp() + (GREATEST(10, LEAST(COALESCE(p_lease_seconds, 120), 600)) || ' seconds')::INTERVAL,
        updated_at = clock_timestamp()
    FROM candidate
    WHERE r.id = candidate.id
    RETURNING r.*;
END;
$$;

CREATE OR REPLACE FUNCTION public.get_user_push_subscriptions_rpc(
    p_user_id UUID
)
RETURNS SETOF public.push_subscriptions
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
BEGIN
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER
            USING ERRCODE = '42501';
    END IF;

    RETURN QUERY
    SELECT * FROM public.push_subscriptions
    WHERE user_id = p_user_id AND is_active = TRUE;
END;
$$;

CREATE OR REPLACE FUNCTION public.record_worker_notification_rpc(
    p_user_id UUID,
    p_reminder_id UUID,
    p_task_id UUID,
    p_title TEXT,
    p_body TEXT,
    p_category TEXT,
    p_priority TEXT,
    p_is_alarm BOOLEAN,
    p_action_url TEXT,
    p_delivery_channel TEXT,
    p_status TEXT,
    p_occurrence_key TEXT,
    p_metadata JSONB
)
RETURNS TABLE(notification_id UUID, inserted BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_notif_id UUID;
    v_inserted BOOLEAN := FALSE;
BEGIN
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER
            USING ERRCODE = '42501';
    END IF;

    INSERT INTO public.notifications (
        user_id, reminder_id, task_id, title, body, category, priority,
        is_alarm, action_url, delivery_channel, status, occurrence_key, metadata
    )
    VALUES (
        p_user_id, p_reminder_id, p_task_id, p_title, p_body, p_category, p_priority,
        p_is_alarm, p_action_url, p_delivery_channel, p_status, p_occurrence_key, COALESCE(p_metadata, '{}'::jsonb)
    )
    ON CONFLICT (user_id, occurrence_key) DO NOTHING
    RETURNING id INTO v_notif_id;

    IF v_notif_id IS NOT NULL THEN
        v_inserted := TRUE;
    ELSE
        SELECT id INTO v_notif_id FROM public.notifications
        WHERE user_id = p_user_id AND occurrence_key = p_occurrence_key;
    END IF;

    RETURN QUERY SELECT v_notif_id, v_inserted;
END;
$$;

CREATE OR REPLACE FUNCTION public.finalize_reminder_trigger_rpc(
    p_reminder_id UUID,
    p_new_status TEXT,
    p_next_trigger_at TIMESTAMPTZ,
    p_last_triggered_at TIMESTAMPTZ,
    p_delivery_attempts INT,
    p_next_retry_at TIMESTAMPTZ
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
BEGIN
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER
            USING ERRCODE = '42501';
    END IF;

    UPDATE public.reminders
    SET status = p_new_status,
        trigger_at = COALESCE(p_next_trigger_at, trigger_at),
        snoozed_until = CASE WHEN p_new_status = 'scheduled' THEN NULL ELSE snoozed_until END,
        last_triggered_at = COALESCE(p_last_triggered_at, last_triggered_at),
        delivery_attempts = p_delivery_attempts,
        next_retry_at = p_next_retry_at,
        claimed_by = NULL,
        lease_expires_at = NULL,
        updated_at = clock_timestamp()
    WHERE id = p_reminder_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.update_push_subscription_health_rpc(
    p_subscription_id UUID,
    p_is_active BOOLEAN,
    p_failure_count INT,
    p_last_error TEXT,
    p_last_success_at TIMESTAMPTZ
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
BEGIN
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER
            USING ERRCODE = '42501';
    END IF;

    UPDATE public.push_subscriptions
    SET is_active = p_is_active,
        failure_count = p_failure_count,
        last_error = p_last_error,
        last_success_at = COALESCE(p_last_success_at, last_success_at),
        updated_at = clock_timestamp()
    WHERE id = p_subscription_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.log_worker_delivery_rpc(
    p_user_id UUID,
    p_reminder_id UUID,
    p_notification_id UUID,
    p_subscription_id UUID,
    p_channel TEXT,
    p_status TEXT,
    p_attempt_number INT,
    p_http_status INT,
    p_error_detail TEXT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
BEGIN
    IF NOT public.is_authorized_worker_session() THEN
        RAISE EXCEPTION 'Unauthorized: session user (%) does not possess the auren_worker role', SESSION_USER
            USING ERRCODE = '42501';
    END IF;

    INSERT INTO public.notification_delivery_logs (
        user_id, reminder_id, notification_id, subscription_id,
        channel, status, attempt_number, http_status, error_detail
    )
    VALUES (
        p_user_id, p_reminder_id, p_notification_id, p_subscription_id,
        p_channel, p_status, p_attempt_number, p_http_status, p_error_detail
    );
END;
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'auren_worker') THEN
        REVOKE ALL ON FUNCTION public.claim_due_reminders_rpc(TEXT, INT, INT) FROM PUBLIC, anon, authenticated;
        REVOKE ALL ON FUNCTION public.get_user_push_subscriptions_rpc(UUID) FROM PUBLIC, anon, authenticated;
        REVOKE ALL ON FUNCTION public.record_worker_notification_rpc(UUID, UUID, UUID, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, TEXT, JSONB) FROM PUBLIC, anon, authenticated;
        REVOKE ALL ON FUNCTION public.finalize_reminder_trigger_rpc(UUID, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, INT, TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;
        REVOKE ALL ON FUNCTION public.update_push_subscription_health_rpc(UUID, BOOLEAN, INT, TEXT, TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;
        REVOKE ALL ON FUNCTION public.log_worker_delivery_rpc(UUID, UUID, UUID, UUID, TEXT, TEXT, INT, INT, TEXT) FROM PUBLIC, anon, authenticated;

        GRANT EXECUTE ON FUNCTION public.claim_due_reminders_rpc(TEXT, INT, INT) TO auren_worker;
        GRANT EXECUTE ON FUNCTION public.get_user_push_subscriptions_rpc(UUID) TO auren_worker;
        GRANT EXECUTE ON FUNCTION public.record_worker_notification_rpc(UUID, UUID, UUID, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, TEXT, JSONB) TO auren_worker;
        GRANT EXECUTE ON FUNCTION public.finalize_reminder_trigger_rpc(UUID, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, INT, TIMESTAMPTZ) TO auren_worker;
        GRANT EXECUTE ON FUNCTION public.update_push_subscription_health_rpc(UUID, BOOLEAN, INT, TEXT, TIMESTAMPTZ) TO auren_worker;
        GRANT EXECUTE ON FUNCTION public.log_worker_delivery_rpc(UUID, UUID, UUID, UUID, TEXT, TEXT, INT, INT, TEXT) TO auren_worker;
    END IF;
END
$$;
