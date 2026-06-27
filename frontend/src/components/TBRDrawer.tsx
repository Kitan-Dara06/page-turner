"use client";

import { useEffect, useState, useRef } from "react";
import { TBREntryResponse, WorkResponse } from "@/lib/types";
import { tbr as tbrApi, feedback as feedbackApi } from "@/lib/api";
import styles from "./TBRDrawer.module.css";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

type Tab = "cravings" | "history";

export default function TBRDrawer({ isOpen, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("cravings");
  const [entries, setEntries] = useState<TBREntryResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [dropping, setDropping] = useState<Set<string>>(new Set());

  const [historyData, setHistoryData] = useState<{
    reading: WorkResponse[];
    finished: WorkResponse[];
  }>({ reading: [], finished: [] });
  const [historyLoading, setHistoryLoading] = useState(false);
  const [actioningWork, setActioningWork] = useState<Set<string>>(new Set());

  const drawerRef = useRef<HTMLDivElement>(null);

  // Fetch active TBR cravings
  const fetchCravings = () => {
    setLoading(true);
    tbrApi
      .getList()
      .then((data) => {
        setEntries(data);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  };

  // Fetch history (reading & finished)
  const fetchHistory = () => {
    setHistoryLoading(true);
    feedbackApi
      .getHistory()
      .then((data) => {
        setHistoryData(data);
        setHistoryLoading(false);
      })
      .catch(() => {
        setHistoryLoading(false);
      });
  };

  // Load entries when drawer is opened
  useEffect(() => {
    if (isOpen) {
      fetchCravings();
      fetchHistory();
    }
  }, [isOpen]);

  // Handle outside click to close
  useEffect(() => {
    function handleOutsideClick(e: MouseEvent) {
      if (
        isOpen &&
        drawerRef.current &&
        !drawerRef.current.contains(e.target as Node)
      ) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [isOpen, onClose]);

  // Actions for Cravings:
  // 1. Remove from TBR
  async function handleRemove(entry: TBREntryResponse, e: React.MouseEvent) {
    e.stopPropagation();
    if (dropping.has(entry.tbr_uuid)) return;
    setDropping((prev) => new Set(prev).add(entry.tbr_uuid));
    try {
      await tbrApi.drop(entry.tbr_uuid);
      setEntries((prev) => prev.filter((e) => e.tbr_uuid !== entry.tbr_uuid));
    } catch {
      // silent best effort
    } finally {
      setDropping((prev) => {
        const next = new Set(prev);
        next.delete(entry.tbr_uuid);
        return next;
      });
    }
  }

  // 2. Mark as Started (still reading)
  async function handleStartReading(
    entry: TBREntryResponse,
    e: React.MouseEvent,
  ) {
    e.stopPropagation();
    if (actioningWork.has(entry.work.work_uuid)) return;
    setActioningWork((prev) => new Set(prev).add(entry.work.work_uuid));
    try {
      // Post event as "still_reading"
      await feedbackApi.submit({
        work_uuid: entry.work.work_uuid,
        event_type: "checkpoint_update",
        checkpoint_status: "still_reading",
      });
      // Remove from TBR cravings
      await tbrApi.drop(entry.tbr_uuid);
      // Remove from UI state
      setEntries((prev) => prev.filter((e) => e.tbr_uuid !== entry.tbr_uuid));
    } catch {
      // silent best effort
    } finally {
      setActioningWork((prev) => {
        const next = new Set(prev);
        next.delete(entry.work.work_uuid);
        return next;
      });
    }
  }

  // 3. Mark as Finished (logged read)
  async function handleMarkRead(entry: TBREntryResponse, e: React.MouseEvent) {
    e.stopPropagation();
    if (actioningWork.has(entry.work.work_uuid)) return;
    setActioningWork((prev) => new Set(prev).add(entry.work.work_uuid));
    try {
      const hasRead = historyData?.finished?.some((b) => b.work_uuid === entry.work.work_uuid);
      let eventType: any = "logged_read";
      if (hasRead) {
        const confirmReread = window.confirm(`You've already read "${entry.work.title}". Is this a reread?`);
        if (confirmReread) {
          eventType = "reread";
        }
      }

      // Post event
      await feedbackApi.submit({
        work_uuid: entry.work.work_uuid,
        event_type: eventType,
        checkpoint_status: "finished",
      });
      // Remove from TBR cravings
      await tbrApi.drop(entry.tbr_uuid);
      // Remove from UI state
      setEntries((prev) => prev.filter((e) => e.tbr_uuid !== entry.tbr_uuid));
      fetchHistory();
    } catch {
      // silent best effort
    } finally {
      setActioningWork((prev) => {
        const next = new Set(prev);
        next.delete(entry.work.work_uuid);
        return next;
      });
    }
  }

  // Action for History Reading -> Finished
  async function handleFinishReading(workUuid: string, e: React.MouseEvent) {
    e.stopPropagation();
    if (actioningWork.has(workUuid)) return;
    setActioningWork((prev) => new Set(prev).add(workUuid));
    try {
      const workTitle = historyData?.reading?.find((b) => b.work_uuid === workUuid)?.title || "this book";
      const hasRead = historyData?.finished?.some((b) => b.work_uuid === workUuid);
      let eventType: any = "logged_read";
      if (hasRead) {
        const confirmReread = window.confirm(`You've already read "${workTitle}". Is this a reread?`);
        if (confirmReread) {
          eventType = "reread";
        }
      }

      await feedbackApi.submit({
        work_uuid: workUuid,
        event_type: eventType,
        checkpoint_status: "finished",
      });
      // Refresh history list
      fetchHistory();
    } catch {
      // silent best effort
    } finally {
      setActioningWork((prev) => {
        const next = new Set(prev);
        next.delete(workUuid);
        return next;
      });
    }
  }

  // Group cravings entries by add_query_text
  const groups: Record<string, TBREntryResponse[]> = {};
  entries.forEach((entry) => {
    const rawMood = entry.add_query_text?.trim();
    const mood = rawMood || "general cravings";
    if (!groups[mood]) {
      groups[mood] = [];
    }
    groups[mood].push(entry);
  });

  return (
    <>
      {/* Backdrop overlay */}
      <div
        className={`${styles.backdrop} ${isOpen ? styles.backdropOpen : ""}`}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <div
        ref={drawerRef}
        className={`${styles.drawer} ${isOpen ? styles.drawerOpen : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label="Cravings & Library"
      >
        <div className={styles.header}>
          <h2 className={styles.title}>Cravings & Library</h2>
          <button
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Close drawer"
          >
            ✕
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className={styles.tabsHeader}>
          <button
            className={`${styles.tabBtn} ${activeTab === "cravings" ? styles.tabBtnActive : ""}`}
            onClick={() => setActiveTab("cravings")}
          >
            Cravings
          </button>
          <button
            className={`${styles.tabBtn} ${activeTab === "history" ? styles.tabBtnActive : ""}`}
            onClick={() => setActiveTab("history")}
          >
            Library
          </button>
        </div>

        <div className={styles.body}>
          {activeTab === "cravings" ? (
            loading ? (
              <div className={styles.loadingState}>
                <span className="spinner" style={{ width: 24, height: 24 }} />
                <p>Summoning cravings...</p>
              </div>
            ) : entries.length === 0 ? (
              <div className={styles.emptyState}>
                <div className={styles.emptyIcon}>🔖</div>
                <p className={styles.emptyTitle}>No cravings archived yet.</p>
                <p className={styles.emptySubtitle}>
                  Save books while browsing recommendations to collect them
                  here.
                </p>
              </div>
            ) : (
              <div className={styles.groupsList}>
                {Object.entries(groups).map(([mood, items]) => (
                  <div key={mood} className={styles.groupSection}>
                    <h3 className={styles.groupTitle}>
                      {mood === "general cravings"
                        ? "uncategorized cravings"
                        : `Added when you wanted: "${mood}"`}
                    </h3>
                    <div className={styles.groupItems}>
                      {items.map((entry) => (
                        <div key={entry.tbr_uuid} className={styles.itemRow}>
                          {entry.work.cover_url ? (
                            <img
                              src={entry.work.cover_url}
                              alt={entry.work.title}
                              className={styles.cover}
                            />
                          ) : (
                            <div className={styles.coverPlaceholder}>📖</div>
                          )}
                          <div className={styles.meta}>
                            <h4 className={styles.bookTitle}>
                              {entry.work.title}
                            </h4>
                            <p className={styles.bookAuthor}>
                              {entry.work.author?.canonical_name ?? "Unknown"}
                            </p>
                            <div className={styles.scoreRow}>
                              <span className={styles.scorePill}>
                                ★{" "}
                                {entry.work.aggregate_rating?.toFixed(1) ||
                                  "N/A"}
                              </span>
                              {entry.priority_score < 0.4 && (
                                <span className={styles.decayWarning}>
                                  fading
                                </span>
                              )}
                            </div>
                            <div className={styles.actionsRow}>
                              <button
                                className={styles.actionBtn}
                                onClick={(e) => handleStartReading(entry, e)}
                                disabled={actioningWork.has(
                                  entry.work.work_uuid,
                                )}
                                title="Start reading (In the trenches)"
                              >
                                📖 Started
                              </button>
                              <button
                                className={styles.actionBtn}
                                onClick={(e) => handleMarkRead(entry, e)}
                                disabled={actioningWork.has(
                                  entry.work.work_uuid,
                                )}
                                title="Mark as read (Devoured)"
                              >
                                🖤 Devoured
                              </button>
                              <button
                                className={styles.removeBtnInline}
                                onClick={(e) => handleRemove(entry, e)}
                                disabled={dropping.has(entry.tbr_uuid)}
                                title="Remove"
                              >
                                ✕
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : historyLoading ? (
            <div className={styles.loadingState}>
              <span className="spinner" style={{ width: 24, height: 24 }} />
              <p>Retrieving your library...</p>
            </div>
          ) : historyData.reading.length === 0 &&
            historyData.finished.length === 0 ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}>📚</div>
              <p className={styles.emptyTitle}>Your library is empty.</p>
              <p className={styles.emptySubtitle}>
                Mark books as Devoured or Started in your cravings list to build
                your library.
              </p>
            </div>
          ) : (
            <div className={styles.groupsList}>
              {/* 1. In progress / still reading section */}
              {historyData.reading.length > 0 && (
                <div className={styles.groupSection}>
                  <h3 className={styles.groupTitle}>📖 In the Trenches</h3>
                  <div className={styles.groupItems}>
                    {historyData.reading.map((book) => (
                      <div key={book.work_uuid} className={styles.itemRow}>
                        {book.cover_url ? (
                          <img
                            src={book.cover_url}
                            alt={book.title}
                            className={styles.cover}
                          />
                        ) : (
                          <div className={styles.coverPlaceholder}>📖</div>
                        )}
                        <div className={styles.meta}>
                          <h4 className={styles.bookTitle}>{book.title}</h4>
                          <p className={styles.bookAuthor}>
                            {book.author?.canonical_name ?? "Unknown"}
                          </p>
                          <div className={styles.scoreRow}>
                            <span className={styles.scorePill}>
                              ★ {book.aggregate_rating?.toFixed(1) || "N/A"}
                            </span>
                          </div>
                          <div className={styles.actionsRow}>
                            <button
                              className={`${styles.actionBtn} ${styles.finishBtn}`}
                              onClick={(e) =>
                                handleFinishReading(book.work_uuid, e)
                              }
                              disabled={actioningWork.has(book.work_uuid)}
                              title="Mark as finished"
                            >
                              🖤 Devoured
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 2. Finished / Devoured section */}
              {historyData.finished.length > 0 && (
                <div className={styles.groupSection}>
                  <h3 className={styles.groupTitle}>🖤 Devoured</h3>
                  <div className={styles.groupItems}>
                    {historyData.finished.map((book) => (
                      <div key={book.work_uuid} className={styles.itemRow}>
                        {book.cover_url ? (
                          <img
                            src={book.cover_url}
                            alt={book.title}
                            className={styles.cover}
                          />
                        ) : (
                          <div className={styles.coverPlaceholder}>📖</div>
                        )}
                        <div className={styles.meta}>
                          <h4 className={styles.bookTitle}>{book.title}</h4>
                          <p className={styles.bookAuthor}>
                            {book.author?.canonical_name ?? "Unknown"}
                          </p>
                          <div className={styles.scoreRow}>
                            <span className={styles.scorePill}>
                              ★ {book.aggregate_rating?.toFixed(1) || "N/A"}
                            </span>
                            <span className={styles.finishedBadge}>
                              completed
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
