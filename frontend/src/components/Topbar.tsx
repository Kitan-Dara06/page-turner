"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import { profile as profileApi } from "@/lib/api";
import styles from "./Topbar.module.css";

function daysLabel(phase: any): string {
  // Shows "calibrating" or "X days in" based on phase confidence
  if (!phase || phase.confidence < 0.3) return "calibrating";
  const conf = Math.round(phase.confidence * 100);
  return `${conf}% calibrated`;
}

export default function Topbar() {
  const { user, signOut } = useAuth();
  const [phase, setPhase]   = useState<any>(null);
  const [open, setOpen]     = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    profileApi.get()
      .then((p) => setPhase(p.phase))
      .catch(() => {});
  }, []);

  // Close menu on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const initials = user?.email?.slice(0, 2).toUpperCase() ?? "?";

  return (
    <header className={styles.topbar}>
      {/* Search */}
      <div className={styles.search}>
        <span className={styles.searchIcon}>⌕</span>
        <input
          className={styles.searchInput}
          type="search"
          placeholder="Search books, authors, vibes..."
          aria-label="Search"
        />
      </div>

      {/* Calibration pill */}
      <div className={styles.calibPill}>
        ◈ {daysLabel(phase)}
      </div>

      {/* Avatar + sign-out */}
      <div className={styles.avatarWrap} ref={ref}>
        <button
          className={styles.avatar}
          onClick={() => setOpen((o) => !o)}
          aria-label="Account menu"
          aria-expanded={open}
        >
          {initials}
        </button>
        {open && (
          <div className={styles.signOutMenu} role="menu">
            <button
              className={styles.signOutBtn}
              onClick={() => { setOpen(false); signOut(); }}
              role="menuitem"
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
