"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { notifications } from "@/lib/api";
import ReleasePanel from "./ReleasePanel";
import styles from "./Nav.module.css";

const links = [
  { href: "/",           label: "Discover",  icon: "✦" },
  { href: "/tbr",        label: "TBR",       icon: "🔖" },
  { href: "/profile",    label: "Profile",   icon: "◈" },
];

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const [releaseCount, setReleaseCount] = useState(0);
  const [panelOpen, setPanelOpen] = useState(false);

  // Fetch release count once on mount
  useEffect(() => {
    notifications.getReleases()
      .then((data) => setReleaseCount(data.count ?? 0))
      .catch(() => {});
  }, []);

  async function handleSignOut() {
    await signOut();
    router.replace("/login");
  }

  function handleDismissAll() {
    setReleaseCount(0);
    setPanelOpen(false);
  }

  return (
    <>
      <nav className={styles.nav}>
        <div className={`container ${styles.inner}`}>
          <Link href="/" className={styles.logo}>Tome</Link>

          <ul className={styles.links}>
            {links.map((l) => (
              <li key={l.href}>
                <Link
                  href={l.href}
                  className={`${styles.link} ${pathname === l.href ? styles.active : ""}`}
                >
                  <span className={styles.icon}>{l.icon}</span>
                  <span className={styles.label}>{l.label}</span>
                </Link>
              </li>
            ))}
          </ul>

          <div className={styles.right}>
            {/* Release alert bell */}
            <button
              className={styles.bellBtn}
              onClick={() => setPanelOpen(true)}
              aria-label="Author release alerts"
              title="New releases from authors you've read"
            >
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              {releaseCount > 0 && (
                <span className={styles.dot}>{releaseCount > 9 ? "9+" : releaseCount}</span>
              )}
            </button>

            {/* User avatar / sign out */}
            {user && (
              <button
                className={styles.avatar}
                onClick={handleSignOut}
                title={`Signed in as ${user.email} — click to sign out`}
                aria-label="Sign out"
              >
                {user.email?.[0]?.toUpperCase() ?? "U"}
              </button>
            )}
          </div>
        </div>
      </nav>

      {panelOpen && (
        <ReleasePanel
          onClose={() => setPanelOpen(false)}
          onDismissAll={handleDismissAll}
        />
      )}
    </>
  );
}
