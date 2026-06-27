"use client";

import { WorkResponse } from "@/lib/types";

// Generates a deterministic gradient from a book's uuid so every
// cover-less book gets a unique, repeatable color identity.
function gradientFromId(id: string) {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash << 5) - hash + id.charCodeAt(i);
    hash |= 0;
  }
  const h1 = Math.abs(hash % 360);
  const h2 = (h1 + 40) % 360;
  return `linear-gradient(135deg, hsl(${h1},35%,18%), hsl(${h2},30%,12%))`;
}

interface Props {
  work: WorkResponse;
  className?: string;
  style?: React.CSSProperties;
}

export default function BookCover({ work, className, style }: Props) {
  if (work.cover_url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={work.cover_url}
        alt={`Cover of ${work.title}`}
        className={className}
        style={{ objectFit: "cover", ...style }}
        onError={(e) => {
          // Fallback to gradient if image 404s
          const el = e.currentTarget as HTMLImageElement;
          el.style.display = "none";
          const parent = el.parentElement;
          if (parent) parent.style.background = gradientFromId(work.work_uuid);
        }}
      />
    );
  }

  return (
    <div
      className={className}
      style={{
        background: gradientFromId(work.work_uuid),
        display: "flex",
        alignItems: "flex-end",
        padding: "12px",
        ...style,
      }}
    >
      <span
        style={{
          fontFamily: "'Playfair Display', serif",
          fontSize: "0.8rem",
          fontStyle: "italic",
          color: "rgba(255,255,255,0.4)",
          lineClamp: 3,
          WebkitLineClamp: 3,
          display: "-webkit-box",
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}
      >
        {work.title}
      </span>
    </div>
  );
}
