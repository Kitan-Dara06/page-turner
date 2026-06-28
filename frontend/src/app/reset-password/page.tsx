"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import styles from "./page.module.css";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    // Supabase puts the access_token + refresh_token in the URL hash
    // after the user clicks the reset link in their email.
    // We need to call supabase.auth.onAuthStateChange to pick it up,
    // or parse the hash directly.
    const hash = window.location.hash;
    if (hash && hash.includes("access_token")) {
      // Let Supabase process the hash — this sets the session
      supabase.auth.onAuthStateChange((event, session) => {
        if (event === "PASSWORD_RECOVERY" || (session && hash.includes("type=recovery"))) {
          setReady(true);
        }
      });
      // Also parse manually in case the event already fired
      const params = new URLSearchParams(hash.replace("#", ""));
      if (params.get("type") === "recovery" && params.get("access_token")) {
        setReady(true);
      }
    } else {
      // No recovery token — already processed or invalid link
      setReady(true);
    }
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const { error } = await supabase.auth.updateUser({ password });
      if (error) {
        setError(error.message);
      } else {
        setDone(true);
        setTimeout(() => router.replace("/login"), 3000);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logo}>
          Page<span>turner</span>
        </div>

        {done ? (
          <div className={styles.successBox}>
            <div className={styles.successIcon}>✓</div>
            <h2>Password updated</h2>
            <p>Redirecting you to sign in...</p>
          </div>
        ) : ready ? (
          <>
            <h1 className={styles.title}>Choose a new password</h1>
            <p className={styles.sub}>
              Enter a new password for your account. Must be at least 6
              characters.
            </p>

            <form className={styles.form} onSubmit={handleSubmit} noValidate>
              <label className={styles.label} htmlFor="new-password">
                New password
              </label>
              <input
                id="new-password"
                className={styles.input}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Min. 6 characters"
                required
                autoComplete="new-password"
                autoFocus
              />

              {error && <p className={styles.error}>{error}</p>}

              <button
                type="submit"
                className={styles.submit}
                disabled={loading || password.length < 6}
              >
                {loading ? (
                  <span className="spinner" style={{ width: 14, height: 14 }} />
                ) : (
                  "Set new password"
                )}
              </button>
            </form>
          </>
        ) : (
          <div className={styles.loading}>
            <span className="spinner" style={{ width: 20, height: 20 }} />
            <p>Loading...</p>
          </div>
        )}
      </div>
    </div>
  );
}
