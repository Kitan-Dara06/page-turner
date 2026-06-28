"use client";

import { useState } from "react";
import type { Metadata } from "next";
import SeedInput from "@/components/SeedInput";
import FlashcardStack from "@/components/FlashcardStack";
import styles from "./page.module.css";

export default function OnboardingPage() {
  const [phase, setPhase] = useState<"seed" | "flashcards">("seed");

  return (
    <div className={styles.page}>
      {phase === "seed" ? (
        <>
          <div className={styles.header}>
            <h1 className={styles.title}>Welcome to PageTurner</h1>
            <p className={styles.subtitle}>
              Tell us about books you love so we can calibrate your taste
              profile from day one — no cold start.
            </p>
          </div>
          <SeedInput onComplete={() => setPhase("flashcards")} />
        </>
      ) : (
        <>
          <div className={styles.header}>
            <h1 className={styles.title}>Calibrate your taste</h1>
            <p className={styles.subtitle}>
              Swipe through these books to seed your reading profile. Be honest
              — <em>not interested</em> is just as useful as <em>read it</em>.
              You can redo this any time from the Calibrate tab.
            </p>
          </div>
          <FlashcardStack />
        </>
      )}
    </div>
  );
}
