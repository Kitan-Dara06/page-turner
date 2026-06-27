"use client";

import { useEffect, useState } from "react";
import styles from "./page.module.css";

interface OrphanItem {
  tag_text: string;
  source: string;
  frequency_count: number;
  first_seen: string | null;
  last_seen: string | null;
}

interface TropeOption {
  canonical_name: string;
  trope_uuid: string;
}

import { getAuthToken } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getAuthToken();
  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options?.headers ?? {}),
    },
  }).then((r) => r.json());
}

export default function AdminOrphansPage() {
  const [orphans, setOrphans] = useState<OrphanItem[]>([]);
  const [tropes, setTropes] = useState<TropeOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [minFreq, setMinFreq] = useState(3);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [mappingTag, setMappingTag] = useState<string | null>(null);
  const [selectedTrope, setSelectedTrope] = useState<string>("");

  async function load() {
    setLoading(true);
    const [o, t] = await Promise.all([
      apiFetch<{ orphans: OrphanItem[] }>(`/api/admin/orphans?min_frequency=${minFreq}`),
      apiFetch<{ tropes: TropeOption[] }>("/api/admin/tropes"),
    ]);
    setOrphans(o.orphans);
    setTropes(t.tropes);
    setLoading(false);
  }

  useEffect(() => { load(); }, [minFreq]);

  async function promote(tagText: string) {
    setActionLoading(tagText);
    await apiFetch(`/api/admin/orphans/${encodeURIComponent(tagText)}/promote`, { method: "POST" });
    setActionLoading(null);
    load();
  }

  async function mapOrphan(tagText: string) {
    if (!selectedTrope) return;
    setActionLoading(tagText);
    await apiFetch(`/api/admin/orphans/${encodeURIComponent(tagText)}/map`, {
      method: "POST",
      body: JSON.stringify({ trope_uuid: selectedTrope }),
    });
    setActionLoading(null);
    setMappingTag(null);
    setSelectedTrope("");
    load();
  }

  async function dismiss(tagText: string) {
    setActionLoading(tagText);
    await apiFetch(`/api/admin/orphans/${encodeURIComponent(tagText)}/dismiss`, { method: "POST" });
    setActionLoading(null);
    load();
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <h1 className={styles.title}>Orphan Queue Review</h1>
        <p className={styles.subtitle}>
          Tags the LLM identifies as relevant but don&apos;t match canonical tropes.
          High-frequency orphans are candidates to become new trope nodes.
        </p>

        <div className={styles.controls}>
          <label>
            Min frequency:{" "}
            <select value={minFreq} onChange={(e) => setMinFreq(Number(e.target.value))}>
              {[1, 2, 3, 5, 10, 20].map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </label>
          <span className={styles.count}>{orphans.length} orphans</span>
        </div>

        {loading ? (
          <div className={styles.loading}>Loading...</div>
        ) : orphans.length === 0 ? (
          <div className={styles.empty}>No orphans above threshold. Try lowering min frequency.</div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Tag</th>
                <th>Frequency</th>
                <th>First Seen</th>
                <th>Last Seen</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {orphans.map((o) => (
                <tr key={o.tag_text}>
                  <td className={styles.tagCell}>{o.tag_text}</td>
                  <td className={styles.numCell}>{o.frequency_count}</td>
                  <td className={styles.dateCell}>{o.first_seen?.slice(0, 10) ?? "-"}</td>
                  <td className={styles.dateCell}>{o.last_seen?.slice(0, 10) ?? "-"}</td>
                  <td className={styles.actionsCell}>
                    {mappingTag === o.tag_text ? (
                      <span className={styles.mapRow}>
                        <select
                          value={selectedTrope}
                          onChange={(e) => setSelectedTrope(e.target.value)}
                        >
                          <option value="">Select trope...</option>
                          {tropes.map((t) => (
                            <option key={t.trope_uuid} value={t.trope_uuid}>
                              {t.canonical_name}
                            </option>
                          ))}
                        </select>
                        <button
                          className={styles.actionBtn}
                          onClick={() => mapOrphan(o.tag_text)}
                          disabled={actionLoading === o.tag_text || !selectedTrope}
                        >
                          ✓
                        </button>
                        <button className={styles.actionBtn} onClick={() => setMappingTag(null)}>
                          ✕
                        </button>
                      </span>
                    ) : (
                      <span className={styles.actionRow}>
                        <button
                          className={`${styles.actionBtn} ${styles.promoteBtn}`}
                          onClick={() => promote(o.tag_text)}
                          disabled={actionLoading === o.tag_text}
                        >
                          {actionLoading === o.tag_text ? "..." : "Promote"}
                        </button>
                        <button
                          className={`${styles.actionBtn} ${styles.mapBtn}`}
                          onClick={() => { setMappingTag(o.tag_text); setSelectedTrope(""); }}
                          disabled={actionLoading === o.tag_text}
                        >
                          Map
                        </button>
                        <button
                          className={`${styles.actionBtn} ${styles.dismissBtn}`}
                          onClick={() => dismiss(o.tag_text)}
                          disabled={actionLoading === o.tag_text}
                        >
                          Dismiss
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
