"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { profile, feedback } from "@/lib/api";
import type { CalibrationData, TimelineEvent, WorkResponse } from "@/lib/types";
import BookCover from "@/components/BookCover";
import styles from "./page.module.css";

interface ProfileDimension {
  key: string;
  name: string;
  question: string;
  value: number;
  interpretation: string;
}

interface ReaderPhase {
  phase: string;
  confidence: number;
  description: string;
  genre?: string;
  velocity?: number;
}

const KEY_LABELS: Record<string, string> = {
  moral_grayness_and_angst: "Darkness & Angst",
  steamy_centrality_and_heat: "Explicit/Romance Heat",
  pacing_and_plot_momentum: "Plot Momentum vs. Slow Burn",
  world_building_and_lyrical_complexity: "World Complexity vs. Lyrical Focus",
  character_centrality: "Character-driven focus",
};

export default function ProfilePage() {
  const [dimensions, setDimensions] = useState<ProfileDimension[]>([]);
  const [phase, setPhase] = useState<ReaderPhase | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  
  // Calibration & Timeline additions
  const [calibration, setCalibration] = useState<CalibrationData | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [activeTab, setActiveTab] = useState<"dimensions" | "timeline">("dimensions");
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());

  useEffect(() => {
    profile
      .get()
      .then((data) => {
        if (data.message) setMessage(data.message);
        setDimensions(data.dimensions || []);
        setPhase(data.phase || null);
        if (data.calibration) setCalibration(data.calibration);
        setLoading(false);
      })
      .catch(() => setLoading(false));

    feedback
      .getTimeline()
      .then((data) => {
        setTimeline(data.timeline || []);
      })
      .catch(() => {});
  }, []);

  function barColor(value: number): string {
    if (value >= 0.7) return styles.barHigh;
    if (value <= 0.3) return styles.barLow;
    return styles.barMid;
  }

  const toggleExpand = (eventUuid: string) => {
    setExpandedEvents((prev) => {
      const next = new Set(prev);
      if (next.has(eventUuid)) {
        next.delete(eventUuid);
      } else {
        next.add(eventUuid);
      }
      return next;
    });
  };

  const getEventLabel = (type: string) => {
    switch (type) {
      case "logged_read":
        return "Devoured";
      case "reread":
        return "Reread";
      case "tbr_add":
        return "Saved to Cravings";
      case "not_interested":
        return "Passed";
      case "interested":
        return "Marked Interested";
      case "query":
        return "Searched";
      default:
        return "Interacted";
    }
  };

  const getEventBadgeClass = (type: string) => {
    switch (type) {
      case "logged_read":
      case "reread":
        return styles.badgeRead;
      case "tbr_add":
        return styles.badgeTbr;
      case "not_interested":
        return styles.badgePass;
      case "query":
        return styles.badgeQuery;
      default:
        return styles.badgeDefault;
    }
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.container}>
          <div className={styles.loading}>Loading your taste profile...</div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>Your Reading Profile</h1>
          <p className={styles.subtitle}>
            This is how PageTurner understands your taste. It shapes every
            recommendation. Strong signals (far from centre) influence results
            more than weak ones.
          </p>
        </div>

        {/* FR-CS-03: Calibration Indicator */}
        {calibration && !calibration.complete && (
          <div className={styles.calibrationBanner}>
            <div className={styles.calibrationIcon}>⚙️</div>
            <div className={styles.calibrationContent}>
              <div className={styles.calibrationTextHeader}>
                <h3>Calibration Phase Active</h3>
                <span>{calibration.total_interactions} / 20 meaningful interactions logged</span>
              </div>
              <p className={styles.calibrationDesc}>
                PageTurner is calibrating its recommendation engine to match your cravings. The training wheels come off once you reach 20 interactions or after your 30-day window.
              </p>
              <div className={styles.calibrationProgressBg}>
                <div
                  className={styles.calibrationProgressFill}
                  style={{ width: `${Math.min(100, (calibration.total_interactions / 20) * 100)}%` }}
                />
              </div>
              <div className={styles.calibrationMeta}>
                <span>{calibration.interactions_remaining} interactions remaining</span>
                <span>{calibration.days_remaining} days remaining</span>
              </div>
            </div>
          </div>
        )}

        {message && <div className={styles.emptyState}>{message}</div>}

        {phase && (
          <div
            className={`${styles.phaseBanner} ${styles[`phase_${phase.phase}`] || ""}`}
          >
            <span className={styles.phaseIcon}>
              {phase.phase === "genre_sprint"
                ? "📚"
                : phase.phase === "exploration"
                  ? "🧭"
                  : phase.phase === "comfort"
                    ? "🔄"
                    : phase.phase === "dormant"
                      ? "💤"
                      : "📖"}
            </span>
            <div>
              <p className={styles.phaseDesc}>{phase.description}</p>
              {phase.velocity != null && (
                <span className={styles.phaseMeta}>
                  {phase.velocity} books in 14 days
                </span>
              )}
            </div>
          </div>
        )}

        {/* Tab Selection */}
        <div className={styles.tabsHeader}>
          <button
            className={`${styles.tabBtn} ${activeTab === "dimensions" ? styles.activeTabBtn : ""}`}
            onClick={() => setActiveTab("dimensions")}
          >
            📊 Taste Dimensions
          </button>
          <button
            className={`${styles.tabBtn} ${activeTab === "timeline" ? styles.activeTabBtn : ""}`}
            onClick={() => setActiveTab("timeline")}
          >
            📜 Activity Timeline ({timeline.length})
          </button>
        </div>

        {/* Tab 1: Dimensions Grid */}
        {activeTab === "dimensions" && (
          <div className={styles.grid}>
            {dimensions.map((dim) => (
              <div key={dim.key} className={styles.card}>
                <div className={styles.cardHeader}>
                  <h3 className={styles.dimName}>{dim.name}</h3>
                  <span className={styles.dimValue}>{dim.value.toFixed(2)}</span>
                </div>
                <p className={styles.dimQuestion}>{dim.question}</p>

                <div className={styles.barTrack}>
                  <div
                    className={`${styles.barFill} ${barColor(dim.value)}`}
                    style={{ width: `${dim.value * 100}%` }}
                  />
                </div>

                <div className={styles.barLabels}>
                  <span>Low</span>
                  <span>High</span>
                </div>

                <p className={styles.interpretation}>{dim.interpretation}</p>
              </div>
            ))}
          </div>
        )}

        {/* Tab 2: Activity Timeline */}
        {activeTab === "timeline" && (
          <div className={styles.timelineContainer}>
            {timeline.length === 0 ? (
              <div className={styles.emptyTimeline}>
                No recorded interactions yet. Devour books, save cravings, or search vibes to build history!
              </div>
            ) : (
              <div className={styles.timelineList}>
                {timeline.map((event) => {
                  const isExpanded = expandedEvents.has(event.event_uuid);
                  const displayDate = new Date(event.event_timestamp).toLocaleString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  });

                  return (
                    <div key={event.event_uuid} className={styles.timelineItem}>
                      <div className={styles.timelineLeft}>
                        <span className={`${styles.eventBadge} ${getEventBadgeClass(event.event_type)}`}>
                          {getEventLabel(event.event_type)}
                        </span>
                        <span className={styles.eventTime}>{displayDate}</span>
                      </div>

                      <div className={styles.timelineContent}>
                        <div className={styles.timelineRow}>
                          <div className={styles.eventDescription}>
                            {event.event_type === "query" ? (
                              <span>
                                Searched for <span className={styles.queryHighlight}>"{event.query_text}"</span>
                              </span>
                            ) : event.work ? (
                              <span>
                                <strong>{event.work.title}</strong> by {event.work.author?.canonical_name || "Unknown"}
                              </span>
                            ) : (
                              <span>Generic event: {event.event_type}</span>
                            )}
                          </div>

                          {event.work && (
                            <div className={styles.coverThumbnail}>
                              <BookCover work={event.work} className={styles.thumbImage} />
                            </div>
                          )}
                        </div>

                        {event.tower1_snapshot && (
                          <div className={styles.debugActions}>
                            <button
                              className={styles.debugBtn}
                              onClick={() => toggleExpand(event.event_uuid)}
                            >
                              {isExpanded ? "Hide Engine State ▲" : "Explain/Debug Engine State ▼"}
                            </button>
                          </div>
                        )}

                        {/* Expandable snap debugger */}
                        {isExpanded && event.tower1_snapshot && (
                          <div className={styles.debugPanel}>
                            <div className={styles.debugTitle}>
                              🧠 Taste Profile snapshot at moment of interaction:
                            </div>
                            <div className={styles.debugGrid}>
                              {Object.entries(event.tower1_snapshot).map(([key, val]) => {
                                const numericVal = typeof val === "number" ? val : parseFloat(val as string);
                                if (isNaN(numericVal)) return null;

                                return (
                                  <div key={key} className={styles.debugRow}>
                                    <span className={styles.debugKey}>{KEY_LABELS[key] || key}:</span>
                                    <div className={styles.debugBarBg}>
                                      <div
                                        className={styles.debugBarFill}
                                        style={{ width: `${numericVal * 100}%` }}
                                      />
                                    </div>
                                    <span className={styles.debugValue}>{numericVal.toFixed(2)}</span>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
