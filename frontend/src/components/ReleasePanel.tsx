"use client";

import { useEffect, useState } from "react";
import { notifications } from "@/lib/api";
import type { ReleaseItem } from "@/lib/types";
import styles from "./ReleasePanel.module.css";

interface Props {
  onClose: () => void;
  onDismissAll: () => void;
}

export default function ReleasePanel({ onClose, onDismissAll }: Props) {
  const [releases, setReleases] = useState<ReleaseItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    notifications.getReleases().then((data) => {
      setReleases(data.releases);
      setLoading(false);
    });
  }, []);

  async function handleDismiss(eventUuid: string) {
    await notifications.dismissRelease(eventUuid);
    setReleases((prev) => prev.filter((r) => r.event_uuid !== eventUuid));
  }

  async function handleDismissAll() {
    await Promise.all(releases.map((r) => notifications.dismissRelease(r.event_uuid)));
    setReleases([]);
    onDismissAll();
  }

  return (
    <>
      <div className={styles.backdrop} onClick={onClose} />
      <aside className={styles.panel} aria-label="Author release alerts">
        <div className={styles.header}>
          <h2 className={styles.title}>New releases</h2>
          <div className={styles.headerActions}>
            {releases.length > 0 && (
              <button className={styles.clearAll} onClick={handleDismissAll}>
                Clear all
              </button>
            )}
            <button className={styles.close} onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
        </div>

        <div className={styles.body}>
          {loading && (
            <div className={styles.empty}>
              <div className="spinner" style={{ width: 20, height: 20 }} />
            </div>
          )}
          {!loading && releases.length === 0 && (
            <div className={styles.empty}>
              <span className={styles.emptyIcon}>🔔</span>
              <p>No new releases from your tracked authors.</p>
            </div>
          )}
          {releases.map((r) => (
            <div key={r.event_uuid} className={styles.item}>
              <div className={styles.itemBody}>
                <p className={styles.itemTitle}>{r.title}</p>
                <p className={styles.itemAuthor}>{r.author_name}</p>
                {r.publication_date && (
                  <p className={styles.itemDate}>{r.publication_date}</p>
                )}
              </div>
              <button
                className={styles.dismiss}
                onClick={() => handleDismiss(r.event_uuid)}
                aria-label={`Dismiss ${r.title}`}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      </aside>
    </>
  );
}
