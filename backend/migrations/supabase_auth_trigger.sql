-- ──────────────────────────────────────────────────────────────────────────
-- Supabase Auth → public.users sync trigger
--
-- Problem: Supabase creates rows in auth.users on signup.
--          Your public.users table has a FK to this UUID that never gets
--          populated automatically, causing FK violations on first request.
--
-- Solution: A Postgres trigger fires AFTER INSERT on auth.users and
--           inserts a minimal row into public.users. Idempotent.
--
-- Run this in: Supabase Dashboard → SQL Editor → New Query → Run
-- ──────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.users (user_uuid, created_at, calibration_complete)
  VALUES (
    NEW.id,
    NOW(),
    FALSE
  )
  ON CONFLICT (user_uuid) DO NOTHING;
  RETURN NEW;
END;
$$;

-- Drop old trigger if it exists (safe to re-run)
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_auth_user();

-- ──────────────────────────────────────────────────────────────────────────
-- Backfill: sync any existing auth.users that don't have a public.users row
-- (handles your current user who just signed up)
-- ──────────────────────────────────────────────────────────────────────────
INSERT INTO public.users (user_uuid, created_at, calibration_complete)
SELECT
  id          AS user_uuid,
  created_at,
  FALSE       AS calibration_complete
FROM auth.users
ON CONFLICT (user_uuid) DO NOTHING;
