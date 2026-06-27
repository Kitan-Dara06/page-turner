"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { recommendations as recApi, feedback as feedbackApi, tbr as tbrApi } from "@/lib/api";
import type { TropeItem, WorkResponse, TBREntryResponse } from "@/lib/types";
import BookCover from "@/components/BookCover";
import styles from "./page.module.css";

export default function DiscoverPage() {
  const [tropes, setTropes] = useState<TropeItem[]>([]);
  const [loadingTropes, setLoadingTropes] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  
  const [selectedTrope, setSelectedTrope] = useState<TropeItem | null>(null);
  const [works, setWorks] = useState<WorkResponse[]>([]);
  const [loadingWorks, setLoadingWorks] = useState(false);

  // User status cache for button states
  const [tbrWorkUuids, setTbrWorkUuids] = useState<Set<string>>(new Set());
  const [finishedWorkUuids, setFinishedWorkUuids] = useState<Set<string>>(new Set());
  const [actioning, setActioning] = useState<Set<string>>(new Set());

  // Load tropes and user caches
  useEffect(() => {
    recApi.getTropes()
      .then((data) => {
        setTropes(data.tropes || []);
        setLoadingTropes(false);
      })
      .catch(() => setLoadingTropes(false));

    fetchUserStates();
  }, []);

  const fetchUserStates = async () => {
    try {
      const [tbrData, historyData] = await Promise.all([
        tbrApi.getList(),
        feedbackApi.getHistory()
      ]);
      setTbrWorkUuids(new Set(tbrData.map(e => e.work.work_uuid)));
      setFinishedWorkUuids(new Set(historyData.finished.map(e => e.work_uuid)));
    } catch {
      // best effort
    }
  };

  const handleSelectTrope = (trope: TropeItem) => {
    setSelectedTrope(trope);
    setLoadingWorks(true);
    recApi.getTropeDetails(trope.trope_uuid)
      .then((data) => {
        setWorks(data.works || []);
        setLoadingWorks(false);
      })
      .catch(() => setLoadingWorks(false));
  };

  const handleAddToTbr = async (work: WorkResponse) => {
    if (actioning.has(work.work_uuid)) return;
    setActioning(prev => new Set(prev).add(work.work_uuid));
    try {
      await tbrApi.add({ work_uuid: work.work_uuid });
      setTbrWorkUuids(prev => new Set(prev).add(work.work_uuid));
    } catch {
      alert("Failed to save to TBR.");
    } finally {
      setActioning(prev => {
        const next = new Set(prev);
        next.delete(work.work_uuid);
        return next;
      });
    }
  };

  const handleMarkRead = async (work: WorkResponse) => {
    if (actioning.has(work.work_uuid)) return;
    setActioning(prev => new Set(prev).add(work.work_uuid));
    try {
      const hasRead = finishedWorkUuids.has(work.work_uuid);
      let eventType: any = "logged_read";
      if (hasRead) {
        const confirmReread = window.confirm(`You've already read "${work.title}". Is this a reread?`);
        if (confirmReread) {
          eventType = "reread";
        }
      }

      await feedbackApi.submit({
        work_uuid: work.work_uuid,
        event_type: eventType,
        checkpoint_status: "finished"
      });
      
      setFinishedWorkUuids(prev => new Set(prev).add(work.work_uuid));
      // Remove from TBR cache if it was there
      if (tbrWorkUuids.has(work.work_uuid)) {
        setTbrWorkUuids(prev => {
          const next = new Set(prev);
          next.delete(work.work_uuid);
          return next;
        });
      }
    } catch {
      alert("Failed to log book as read.");
    } finally {
      setActioning(prev => {
        const next = new Set(prev);
        next.delete(work.work_uuid);
        return next;
      });
    }
  };

  const filteredTropes = tropes.filter(t => 
    t.canonical_name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className={styles.discoverContainer}>
      <header className={styles.header}>
        <h1 className={styles.pageTitle}>✨ Discover by Trope</h1>
        <p className={styles.pageSubtitle}>
          Browse the library of {tropes.length || "311"} canonical narrative devices and tropes.
        </p>
      </header>

      <div className={styles.layoutGrid}>
        {/* Left side: Tropes list */}
        <aside className={styles.sidebar}>
          <div className={styles.searchWrapper}>
            <input
              type="text"
              placeholder="Search tropes..."
              className={styles.searchInput}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            {searchTerm && (
              <button className={styles.clearSearch} onClick={() => setSearchTerm("")}>
                ✕
              </button>
            )}
          </div>

          <div className={styles.tropesScrollArea}>
            {loadingTropes ? (
              <div className={styles.loader}>Loading tropes...</div>
            ) : filteredTropes.length === 0 ? (
              <div className={styles.noTropes}>No tropes found matching "{searchTerm}"</div>
            ) : (
              <ul className={styles.tropesList} role="menu">
                {filteredTropes.map((t) => (
                  <li key={t.trope_uuid}>
                    <button
                      className={`${styles.tropeBtn} ${selectedTrope?.trope_uuid === t.trope_uuid ? styles.activeTropeBtn : ""}`}
                      onClick={() => handleSelectTrope(t)}
                    >
                      <span className={styles.tropeName}>{t.canonical_name}</span>
                      <span className={styles.tropeCount}>{t.book_count}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        {/* Right side: Books list */}
        <main className={styles.booksSection}>
          {selectedTrope ? (
            <div className={styles.booksWrap}>
              <div className={styles.tropeTitleHeader}>
                <h2 className={styles.tropeTitleName}>#{selectedTrope.canonical_name}</h2>
                <span className={styles.tropeTitleCount}>
                  Surfacing top {works.length} books matching this trope
                </span>
              </div>

              {loadingWorks ? (
                <div className={styles.worksLoaderWrap}>
                  <div className={styles.loadingPulse} />
                  <p className={styles.worksLoaderText}>Surfacing books...</p>
                </div>
              ) : works.length === 0 ? (
                <div className={styles.emptyWorks}>
                  No books associated with #{selectedTrope.canonical_name} in the system yet.
                </div>
              ) : (
                <div className={styles.booksGrid}>
                  {works.map((work) => {
                    const isSaved = tbrWorkUuids.has(work.work_uuid);
                    const isFinished = finishedWorkUuids.has(work.work_uuid);
                    
                    return (
                      <article key={work.work_uuid} className={styles.bookCard}>
                        <div className={styles.coverWrap}>
                          <BookCover work={work} className={styles.bookCover} />
                        </div>
                        <div className={styles.bookInfo}>
                          <h3 className={styles.bookTitle}>{work.title}</h3>
                          <p className={styles.bookAuthor}>
                            {work.author ? `by ${work.author.canonical_name}` : "Unknown author"}
                          </p>
                          {work.aggregate_rating && (
                            <div className={styles.rating}>
                              ★ {work.aggregate_rating.toFixed(1)}
                            </div>
                          )}
                          
                          <div className={styles.cardActions}>
                            {isFinished ? (
                              <button 
                                className={`${styles.actionBtn} ${styles.finishedBadge}`}
                                onClick={() => handleMarkRead(work)}
                                disabled={actioning.has(work.work_uuid)}
                                title="Reread?"
                              >
                                🖤 Devoured (Log Reread)
                              </button>
                            ) : (
                              <>
                                <button
                                  className={`${styles.actionBtn} ${isSaved ? styles.savedBtn : styles.saveBtn}`}
                                  onClick={() => !isSaved && handleAddToTbr(work)}
                                  disabled={isSaved || actioning.has(work.work_uuid)}
                                >
                                  {isSaved ? "Saved" : "Save to Cravings"}
                                </button>
                                <button
                                  className={`${styles.actionBtn} ${styles.readBtn}`}
                                  onClick={() => handleMarkRead(work)}
                                  disabled={actioning.has(work.work_uuid)}
                                >
                                  Devour
                                </button>
                              </>
                            )}
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </div>
          ) : (
            <div className={styles.discoverPlaceholder}>
              <div className={styles.placeholderIcon}>✨</div>
              <h3 className={styles.placeholderTitle}>Select a Trope</h3>
              <p className={styles.placeholderSubtitle}>
                Choose a narrative device from the sidebar to browse matching books in our index.
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
