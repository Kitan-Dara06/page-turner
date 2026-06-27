"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { profile as profileApi } from "@/lib/api";
import type { ProfilePhase } from "@/lib/api";
import ReleasePanel from "./ReleasePanel";
import styles from "./Sidebar.module.css";

const NAV_MAIN = [
  { href: "/",           label: "For you",  icon: "✦" },
  { href: "/tbr",        label: "TBR",      icon: "🔖" },
  { href: "/profile",    label: "Profile",  icon: "◈" },
  { href: "/authors",    label: "Authors",  icon: "✒" },
];

const NAV_DISCOVER = [
  { href: "/releases",   label: "Releases", icon: "🔔", bell: true },
];

function timeContext(): string {
  const h = new Date().getHours();
  const day = ["sunday","monday","tuesday","wednesday","thursday","friday","saturday"][new Date().getDay()];
  if (h >= 5  && h < 12) return `${day} morning`;
  if (h >= 12 && h < 17) return `${day} afternoon`;
  if (h >= 17 && h < 21) return `${day} evening`;
  return `${day} night`;
}

function phaseToMood(phase: ProfilePhase | null): string {
  if (!phase) return "still calibrating";
  const map: Record<string, string> = {
    genre_sprint: "genre sprinting ⚡",
    exploration:  "exploring ◎",
    comfort:      "comfort mode ♻",
    dormant:      "dormant 🌙",
    active:       "reading actively",
  };
  return map[phase.phase] ?? phase.description ?? phase.phase;
}

interface Props {
  releaseCount: number;
}

export default function Sidebar({ releaseCount }: Props) {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  const [phase, setPhase]         = useState<ProfilePhase | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);

  useEffect(() => {
    profileApi.get()
      .then((p) => setPhase(p.phase))
      .catch(() => {});
  }, []);

  return (
    <>
      <aside className={styles.sidebar}>
        {/* Logo */}
        <div className={styles.logo}>
          <div className={styles.logoText}>Pageturner</div>
          <div className={styles.logoSub}>reading intelligence</div>
        </div>

        {/* Nav */}
        <nav className={styles.nav} aria-label="Main navigation">
          {NAV_MAIN.map(({ href, label, icon }) => (
            <Link
              key={href}
              href={href}
              className={`${styles.navItem} ${pathname === href ? styles.active : ""}`}
            >
              <span className={styles.navIcon}>{icon}</span>
              {label}
            </Link>
          ))}

          <div className={styles.section}>Discover</div>

          {NAV_DISCOVER.map(({ href, label, icon, bell }) => (
            bell ? (
              <button
                key={href}
                className={`${styles.navItem} ${panelOpen ? styles.active : ""}`}
                onClick={() => setPanelOpen(true)}
                aria-label={`${label}${releaseCount > 0 ? ` (${releaseCount} new)` : ""}`}
              >
                <span className={styles.navIcon}>
                  <span className={styles.bellWrap}>
                    {icon}
                    {releaseCount > 0 && <span className={styles.dot} />}
                  </span>
                </span>
                {label}
              </button>
            ) : (
              <Link
                key={href}
                href={href}
                className={`${styles.navItem} ${pathname === href ? styles.active : ""}`}
              >
                <span className={styles.navIcon}>{icon}</span>
                {label}
              </Link>
            )
          ))}
        </nav>

        {/* Mood bar */}
        <div className={styles.moodBar}>
          <div className={styles.moodLabel}>your taste right now</div>
          <div className={styles.moodChips}>
            <span className={styles.moodChip}>
              <span className={styles.moodChipIcon}>◈</span>
              {phaseToMood(phase)}
            </span>
            <span className={styles.moodChip}>
              <span className={styles.moodChipIcon}>🕐</span>
              {timeContext()}
            </span>
          </div>
        </div>
      </aside>

      {/* Release slide-in panel */}
      {panelOpen && (
        <ReleasePanel
          onClose={() => setPanelOpen(false)}
          onDismissAll={() => setPanelOpen(false)}
        />
      )}
    </>
  );
}
