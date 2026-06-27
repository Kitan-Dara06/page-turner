"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AuthorCatalog, SeriesCatalog } from "@/lib/types";
import { authors as authorsApi } from "@/lib/api";
import styles from "./page.module.css";

function SeriesAccordion({ series }: { series: SeriesCatalog }) {
  const [open, setOpen] = useState(true);
  return (
    <div className={styles.seriesBlock}>
      <button
        className={styles.seriesToggle}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        id={`series-${series.series_uuid}`}
      >
        <span className={styles.seriesTitle}>
          {series.title}
          {series.is_complete && (
            <span className={styles.completeStar} title="Series complete">
              {" "}
              ⭐
            </span>
          )}
        </span>
        <span className={styles.seriesCount}>{series.works.length} works</span>
        <span className={styles.chevron}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className={styles.seriesWorks}>
          {series.works.map((work) => (
            <div key={work.work_uuid} className={styles.seriesWork}>
              <span className={styles.orderBadge}>
                {Number.isInteger(work.order)
                  ? work.order
                  : work.order.toFixed(1)}
              </span>
              <span className={styles.workTitle}>
                {work.is_read && (
                  <span className={styles.readTick} title="Read">
                    ✓{" "}
                  </span>
                )}
                {work.title}
              </span>
              {!work.is_core && (
                <span className={`badge badge-dim ${styles.nonCoreBadge}`}>
                  Side story
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AuthorPage() {
  const params = useParams();
  const personId = params?.personId as string;

  const [catalog, setCatalog] = useState<AuthorCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!personId) return;
    authorsApi
      .getCatalog(personId)
      .then((data) => {
        setCatalog(data);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.detail ?? "Author not found.");
        setLoading(false);
      });
  }, [personId]);

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.container}>
          <div className={`skeleton ${styles.skeletonName}`} />
          <div className={`skeleton ${styles.skeletonSection}`} />
          <div className={`skeleton ${styles.skeletonSection}`} />
        </div>
      </div>
    );
  }

  if (error || !catalog) {
    return (
      <div className={styles.page}>
        <div className={styles.container}>
          <div className="error-banner">{error ?? "Author not found."}</div>
          <Link href="/" className="btn btn-ghost" style={{ marginTop: 16 }}>
            ← Back
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* Author header */}
        <div className={styles.authorHeader}>
          <div className={styles.authorAvatar}>
            {catalog.canonical_name.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <h1 className={styles.authorName}>{catalog.canonical_name}</h1>
            {catalog.pen_names.length > 0 && (
              <p className={styles.penNames}>
                Also writes as{" "}
                {catalog.pen_names.map((pn, i) => (
                  <span key={pn.pen_name_uuid}>
                    <Link
                      href={`/authors/${catalog.person_uuid}?pen=${encodeURIComponent(pn.display_name)}`}
                      className={styles.penNamePill}
                    >
                      {pn.display_name}
                    </Link>
                    {i < catalog.pen_names.length - 1 ? ", " : ""}
                  </span>
                ))}
              </p>
            )}
          </div>
        </div>

        {/* Series */}
        {catalog.series.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>
              <span className={styles.sectionIcon}>◈</span> Series
            </h2>
            <div className={styles.seriesList}>
              {catalog.series.map((s) => (
                <SeriesAccordion key={s.series_uuid} series={s} />
              ))}
            </div>
          </section>
        )}

        {/* Standalones */}
        {catalog.standalones.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>
              <span className={styles.sectionIcon}>✦</span> Standalones
            </h2>
            <div className={styles.standaloneGrid}>
              {catalog.standalones.map((work) => (
                <div key={work.work_uuid} className={styles.standaloneCard}>
                  <span className={styles.standaloneTitle}>{work.title}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {catalog.series.length === 0 && catalog.standalones.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">📚</div>
            <h3>No catalog data yet</h3>
            <p>This author's works will appear here as the catalog grows.</p>
          </div>
        )}
      </div>
    </div>
  );
}
