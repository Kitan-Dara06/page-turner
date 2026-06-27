"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { notifications as notifApi, profile as profileApi } from "@/lib/api";
import TBRDrawer from "./TBRDrawer";
import ReleasePanel from "./ReleasePanel";
import styles from "./AppShell.module.css";

const PUBLIC_PATHS = ["/login"];
const NO_HEADER_PATHS = ["/login", "/onboarding"];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [releaseCount, setReleaseCount] = useState(0);
  const [tbrOpen, setTbrOpen] = useState(false);
  const [releasesOpen, setReleasesOpen] = useState(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement>(null);

  // Redirect to login if not public path and not authenticated
  useEffect(() => {
    if (loading) return;
    const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
    if (!user && !isPublic) router.replace("/login");
  }, [user, loading, pathname, router]);

  // Fetch release count & admin status
  useEffect(() => {
    if (!user) return;
    
    notifApi.getReleases()
      .then((r) => setReleaseCount(r.releases?.length ?? 0))
      .catch(() => {});

    profileApi.get()
      .then((data) => {
        setIsAdmin(!!data.is_admin);
      })
      .catch(() => {});
  }, [user]);

  // Close profile menu on outside click
  useEffect(() => {
    function handleOutsideClick(e: MouseEvent) {
      if (
        profileMenuOpen &&
        profileMenuRef.current &&
        !profileMenuRef.current.contains(e.target as Node)
      ) {
        setProfileMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [profileMenuOpen]);

  if (loading) {
    return (
      <div className={styles.authLoading}>
        <div className="spinner" style={{ width: 28, height: 28 }} />
      </div>
    );
  }

  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
  if (isPublic) return <>{children}</>;
  if (!user) return null;

  const showHeader = !NO_HEADER_PATHS.includes(pathname);
  const isHome = pathname === "/";
  const initials = user?.email?.slice(0, 2).toUpperCase() ?? "?";

  return (
    <div className={styles.shell}>
      <div className={styles.main}>
        {showHeader && (
          <header className={styles.header}>
            <div className={styles.leftSection}>
              {!isHome ? (
                <button
                  className={styles.backBtn}
                  onClick={() => router.push("/")}
                  aria-label="Back to Vibe Prompt"
                >
                  ← vibe prompt
                </button>
              ) : (
                <Link href="/" className={styles.logo}>
                  Pageturner
                </Link>
              )}
            </div>

            <div className={styles.navActions}>
              {/* Discover Link */}
              <Link
                href="/discover"
                className={styles.discoverBtn}
                aria-label="Discover Tropes"
              >
                <span>✨</span>
                <span>discover</span>
              </Link>

              {/* Archived Cravings (TBR Drawer Trigger) */}
              <button
                className={styles.cravingsBtn}
                onClick={() => setTbrOpen(true)}
                aria-label="Open Archived Cravings"
              >
                <span>🔖</span>
                <span>cravings</span>
              </button>

              {/* Releases Alert Trigger */}
              <button
                className={styles.bellBtn}
                onClick={() => setReleasesOpen(true)}
                aria-label={`Open New Releases (${releaseCount} new)`}
              >
                <span className={styles.bellWrap}>
                  <span>🔔</span>
                  {releaseCount > 0 && <span className={styles.dot} />}
                </span>
                <span>releases</span>
              </button>

              {/* Profile Avatar / Dropdown */}
              <div className={styles.avatarWrap} ref={profileMenuRef}>
                <button
                  className={styles.avatar}
                  onClick={() => setProfileMenuOpen((o) => !o)}
                  aria-label="Account Menu"
                  aria-expanded={profileMenuOpen}
                >
                  {initials}
                </button>
                {profileMenuOpen && (
                  <div className={styles.signOutMenu} role="menu">
                    <button
                      className={styles.menuItem}
                      onClick={() => {
                        setProfileMenuOpen(false);
                        router.push("/profile");
                      }}
                      role="menuitem"
                    >
                      profile settings
                    </button>
                    <button
                      className={styles.menuItem}
                      onClick={() => {
                        setProfileMenuOpen(false);
                        router.push("/discover");
                      }}
                      role="menuitem"
                    >
                      discover by trope
                    </button>
                    {isAdmin && (
                      <button
                        className={styles.menuItem}
                        onClick={() => {
                          setProfileMenuOpen(false);
                          router.push("/admin/orphans");
                        }}
                        role="menuitem"
                      >
                        🔧 admin queue
                      </button>
                    )}
                    <button
                      className={styles.signOutBtn}
                      onClick={() => {
                        setProfileMenuOpen(false);
                        signOut();
                      }}
                      role="menuitem"
                    >
                      sign out
                    </button>
                  </div>
                )}
              </div>
            </div>
          </header>
        )}

        <main className={styles.content} style={showHeader ? { paddingTop: 64 } : undefined}>
          {children}
        </main>
      </div>

      {/* Slide-out TBR Drawer */}
      <TBRDrawer isOpen={tbrOpen} onClose={() => setTbrOpen(false)} />

      {/* Slide-out Releases Panel */}
      {releasesOpen && (
        <ReleasePanel
          onClose={() => setReleasesOpen(false)}
          onDismissAll={() => {
            setReleaseCount(0);
            setReleasesOpen(false);
          }}
        />
      )}
    </div>
  );
}
