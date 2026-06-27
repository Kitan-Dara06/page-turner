"use client";

import Link from "next/link";
import { TBRMatch } from "@/lib/types";
import BookCover from "./BookCover";
import styles from "./TBRStrip.module.css";

interface Props {
  matches: TBRMatch[];
}

/**
 * Displays mood-matched TBR books as a horizontal strip above the main
 * recommendation grid. Only rendered when the API returns tbr_matches.length > 0.
 *
 * These are books you've already saved that happen to match the current query mood —
 * "now's the moment to read it" surfacing rather than discovery.
 */
export default function TBRStrip({ matches }: Props) {
  if (!matches || matches.length === 0) return null;

  return (
    <section className={styles.strip} aria-label="Your TBR — right for this mood">
      <div className={styles.header}>
        <span className={styles.icon}>🔖</span>
        <h2 className={styles.title}>From your TBR</h2>
        <span className={styles.subtitle}>Saved books that match this mood</span>
      </div>

      <div className={styles.scroll}>
        {matches.map((match) => (
          <article key={match.work_uuid} className={styles.card}>
            {/* Minimal cover — no full WorkResponse available, use placeholder */}
            <div className={styles.coverWrap}>
              {match.cover_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={match.cover_url}
                  alt={match.title}
                  className={styles.cover}
                />
              ) : (
                <div className={styles.coverPlaceholder}>
                  <span>{match.title[0]}</span>
                </div>
              )}
            </div>

            <div className={styles.info}>
              <p className={styles.bookTitle}>{match.title}</p>
              <p className={styles.author}>{match.author_name}</p>
              <p className={styles.explanation}>{match.explanation}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
