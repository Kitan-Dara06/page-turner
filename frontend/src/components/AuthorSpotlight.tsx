"use client";

import Link from "next/link";
import { tbr } from "@/lib/api";
import { AuthorSpotlight as AuthorSpotlightType } from "@/lib/types";
import styles from "./AuthorSpotlight.module.css";
import { useState } from "react";

interface Props {
  spotlight: AuthorSpotlightType;
}

export default function AuthorSpotlight({ spotlight }: Props) {
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());

  async function handleSave(work_uuid: string) {
    if (!work_uuid || savedIds.has(work_uuid)) return;
    try {
      await tbr.add({ work_uuid });
      setSavedIds((prev) => new Set(prev).add(work_uuid));
    } catch {
      /* soft fail */
    }
  }

  if (!spotlight.books.length) return null;

  return (
    <aside
      className={styles.spotlight}
      aria-label={`More by ${spotlight.author_name}`}
    >
      <div className={styles.header}>
        <span className={styles.eyebrow}>More by</span>
        {spotlight.person_uuid ? (
          <Link
            href={`/authors/${spotlight.person_uuid}`}
            className={styles.authorName}
          >
            {spotlight.author_name}
          </Link>
        ) : (
          <span className={styles.authorName}>{spotlight.author_name}</span>
        )}
        {spotlight.pen_names.length > 0 && (
          <p className={styles.penNames}>
            Also writes as: {spotlight.pen_names.join(", ")}
          </p>
        )}
      </div>

      <div className={styles.books}>
        {spotlight.books.map((book) => (
          <div key={book.work_uuid || book.title} className={styles.bookItem}>
            {book.cover_url && (
              <img
                src={book.cover_url}
                alt={book.title}
                className={styles.cover}
                loading="lazy"
              />
            )}
            <div className={styles.bookMeta}>
              <span className={styles.bookTitle}>{book.title}</span>
              {book.series_label && (
                <span className={styles.seriesLabel}>{book.series_label}</span>
              )}
              {book.publication_year && (
                <span className={styles.year}>{book.publication_year}</span>
              )}
              {book.work_uuid && (
                <button
                  className={`btn btn-ghost btn-sm ${styles.saveBtn}`}
                  onClick={() => handleSave(book.work_uuid)}
                  disabled={savedIds.has(book.work_uuid)}
                >
                  {savedIds.has(book.work_uuid) ? "✓ Saved" : "🔖 TBR"}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
