import type { Metadata } from "next";
import FlashcardStack from "@/components/FlashcardStack";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Calibrate — PageTurner",
  description: "Swipe through a selection of books to seed your taste profile.",
};

export default function OnboardingPage() {
  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Calibrate your taste</h1>
        <p className={styles.subtitle}>
          Swipe through these books to seed your reading profile.
          Be honest — <em>not interested</em> is just as useful as <em>read it</em>.
          You can redo this any time from the Calibrate tab.
        </p>
      </div>
      <FlashcardStack />
    </div>
  );
}
