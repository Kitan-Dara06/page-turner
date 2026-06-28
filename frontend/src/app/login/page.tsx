"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import styles from "./page.module.css";

type Mode = "login" | "signup" | "forgot";

export default function LoginPage() {
  const { signIn, signUp, resetPassword } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  function friendlyError(raw: string | null): string | null {
    if (!raw) return null;
    const r = raw.toLowerCase();
    if (
      r.includes("invalid login credentials") ||
      r.includes("invalid credentials")
    ) {
      // Supabase deliberately doesn't distinguish wrong email vs wrong password
      // to prevent user enumeration. But we can separate from "email not confirmed".
      return "Wrong email or password. Double-check both, or sign up if you don't have an account yet.";
    }
    if (r.includes("email not confirmed")) {
      return "Your email hasn't been confirmed yet. Check your inbox for the confirmation link. Didn't get it? Try signing up again to resend.";
    }
    if (r.includes("user already registered") || r.includes("already exists"))
      return "An account with this email already exists. Try signing in instead.";
    if (r.includes("password should be") || r.includes("password must be"))
      return "Password must be at least 6 characters.";
    if (r.includes("forbidden") || r.includes("not authorized"))
      return "Access denied. Try logging in again.";
    return raw;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "forgot") {
        const { error } = await resetPassword(email);
        if (error) {
          setError(friendlyError(error));
        } else {
          setSuccess(true);
        }
      } else if (mode === "login") {
        const { error } = await signIn(email, password);
        if (error) {
          setError(friendlyError(error));
        } else {
          router.replace("/");
        }
      } else {
        const { error } = await signUp(email, password);
        if (error) {
          setError(friendlyError(error));
        } else {
          // If email confirmation is disabled, signUp auto-logs in → redirect
          // Otherwise show the "check your email" success state
          setSuccess(true);
        }
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.page}>
      {/* ── Left: Brand panel ─────────────────────────── */}
      <div className={styles.brand}>
        <div className={styles.brandLogo}>
          Page<span>turner</span>
        </div>
        <div className={styles.brandSub}>reading intelligence</div>

        <p className={styles.brandCopy}>
          Not just what to read — <em>why</em> it fits you, right now. Your
          taste evolves. So do your recommendations.
        </p>

        <div className={styles.brandFeatures}>
          {[
            {
              icon: "◈",
              title: "Taste-matched",
              desc: "Every rec explained in one line pulled from your reading history.",
            },
            {
              icon: "⏱",
              title: "Checkpoint loop",
              desc: "Quick updates before each session keep your profile sharp.",
            },
            {
              icon: "🕐",
              title: "Time-aware",
              desc: "Mon morning isn't Fri night — temporal patterns shape what surfaces.",
            },
          ].map((f) => (
            <div key={f.title} className={styles.brandFeature}>
              <div className={styles.featureIcon}>{f.icon}</div>
              <div className={styles.featureText}>
                <strong>{f.title}</strong>
                {f.desc}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Right: Auth form ───────────────────────────── */}
      <div className={styles.formPanel}>
        <div className={styles.card}>
          <h1 className={styles.cardTitle}>
            {mode === "forgot"
              ? "Reset your password"
              : mode === "login"
                ? "Welcome back"
                : "Create account"}
          </h1>
          <p className={styles.cardSub}>
            {mode === "forgot"
              ? "Enter your email and we'll send you a reset link."
              : mode === "login"
                ? "Sign in to your reading intelligence dashboard."
                : "Start building your taste profile."}
          </p>

          {/* Mode tabs — hidden in forgot mode */}
          {mode !== "forgot" && (
            <div className={styles.tabs}>
              <button
                type="button"
                className={mode === "login" ? styles.tabActive : styles.tab}
                onClick={() => {
                  setMode("login");
                  setError(null);
                }}
              >
                Sign in
              </button>
              <button
                type="button"
                className={mode === "signup" ? styles.tabActive : styles.tab}
                onClick={() => {
                  setMode("signup");
                  setError(null);
                }}
              >
                Create account
              </button>
            </div>
          )}

          {success ? (
            <div className={styles.successBox}>
              <div className={styles.successIcon}>✓</div>
              {mode === "forgot" ? (
                <p>
                  Check your email! We've sent a password reset link. The link
                  expires in 1 hour.
                </p>
              ) : (
                <p>
                  Account created! Check your email to confirm, then sign in.
                </p>
              )}
            </div>
          ) : (
            <form className={styles.form} onSubmit={handleSubmit} noValidate>
              <label className={styles.label} htmlFor="email">
                Email
              </label>
              <input
                id="email"
                className={styles.input}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                autoComplete="email"
              />

              {mode !== "forgot" && (
                <>
                  <label className={styles.label} htmlFor="password">
                    Password
                  </label>
                  <input
                    id="password"
                    className={styles.input}
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={
                      mode === "signup" ? "Min. 6 characters" : "••••••••"
                    }
                    required
                    autoComplete={
                      mode === "login" ? "current-password" : "new-password"
                    }
                  />
                </>
              )}

              {error && <p className={styles.error}>{error}</p>}

              <button
                id="auth-submit"
                type="submit"
                className={styles.submit}
                disabled={loading || !email || (mode !== "forgot" && !password)}
              >
                {loading ? (
                  <span className="spinner" style={{ width: 14, height: 14 }} />
                ) : mode === "forgot" ? (
                  "Send reset link"
                ) : mode === "login" ? (
                  "Sign in"
                ) : (
                  "Create account"
                )}
              </button>

              {/* Forgot password link — only on login */}
              {mode === "login" && (
                <button
                  type="button"
                  className={styles.forgotLink}
                  onClick={() => {
                    setMode("forgot");
                    setError(null);
                    setPassword("");
                  }}
                >
                  Forgot your password?
                </button>
              )}
            </form>
          )}

          {mode !== "forgot" && (
            <p className={styles.hint}>
              {mode === "login" ? "No account yet?" : "Already have one?"}{" "}
              <button
                type="button"
                className={styles.switchMode}
                onClick={() => {
                  setMode(mode === "login" ? "signup" : "login");
                  setError(null);
                }}
              >
                {mode === "login" ? "Sign up" : "Sign in"}
              </button>
            </p>
          )}

          {/* Back link when in forgot mode */}
          {mode === "forgot" && !success && (
            <p className={styles.hint}>
              <button
                type="button"
                className={styles.switchMode}
                onClick={() => {
                  setMode("login");
                  setError(null);
                }}
              >
                ← Back to sign in
              </button>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
