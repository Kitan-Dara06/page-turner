"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import styles from "./page.module.css";

type Mode = "login" | "signup";

export default function LoginPage() {
  const { signIn, signUp } = useAuth();
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
    if (r.includes("invalid login credentials") || r.includes("invalid credentials"))
      return "Wrong email or password — or your account hasn't been confirmed yet. Check your inbox, or sign up again.";
    if (r.includes("email not confirmed"))
      return "Email not confirmed. Check your inbox for a confirmation link, or ask your admin to confirm you manually.";
    if (r.includes("user already registered"))
      return "An account with this email already exists. Try signing in instead.";
    if (r.includes("password should be"))
      return "Password must be at least 6 characters.";
    return raw;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "login") {
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
          Not just what to read — <em>why</em> it fits you, right now.
          Your taste evolves. So do your recommendations.
        </p>

        <div className={styles.brandFeatures}>
          {[
            { icon: "◈", title: "Taste-matched",  desc: "Every rec explained in one line pulled from your reading history." },
            { icon: "⏱", title: "Checkpoint loop", desc: "Quick updates before each session keep your profile sharp." },
            { icon: "🕐", title: "Time-aware",     desc: "Mon morning isn't Fri night — temporal patterns shape what surfaces." },
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
            {mode === "login" ? "Welcome back" : "Create account"}
          </h1>
          <p className={styles.cardSub}>
            {mode === "login"
              ? "Sign in to your reading intelligence dashboard."
              : "Start building your taste profile."}
          </p>

          {/* Mode tabs */}
          <div className={styles.tabs}>
            <button
              type="button"
              className={mode === "login" ? styles.tabActive : styles.tab}
              onClick={() => { setMode("login"); setError(null); }}
            >
              Sign in
            </button>
            <button
              type="button"
              className={mode === "signup" ? styles.tabActive : styles.tab}
              onClick={() => { setMode("signup"); setError(null); }}
            >
              Create account
            </button>
          </div>

          {success ? (
            <div className={styles.successBox}>
              <div className={styles.successIcon}>✓</div>
              <p>Account created! Check your email to confirm, then sign in.</p>
            </div>
          ) : (
            <form className={styles.form} onSubmit={handleSubmit} noValidate>
              <label className={styles.label} htmlFor="email">Email</label>
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

              <label className={styles.label} htmlFor="password">Password</label>
              <input
                id="password"
                className={styles.input}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === "signup" ? "Min. 6 characters" : "••••••••"}
                required
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />

              {error && <p className={styles.error}>{error}</p>}

              <button
                id="auth-submit"
                type="submit"
                className={styles.submit}
                disabled={loading || !email || !password}
              >
                {loading
                  ? <span className="spinner" style={{ width: 14, height: 14 }} />
                  : mode === "login" ? "Sign in" : "Create account"
                }
              </button>
            </form>
          )}

          <p className={styles.hint}>
            {mode === "login" ? "No account yet?" : "Already have one?"}{" "}
            <button
              type="button"
              className={styles.switchMode}
              onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(null); }}
            >
              {mode === "login" ? "Sign up" : "Sign in"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
