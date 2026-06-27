import type { Metadata } from "next";
import TBRList from "@/components/TBRList";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "TBR — PageTurner",
  description: "Your To Be Read list, priority-sorted by your taste profile.",
};

export default function TBRPage() {
  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>To Be Read</h1>
            <p className={styles.subtitle}>
              Sorted by how well each book still fits your current taste profile.
              Priority decays over time — books you keep skipping move down.
            </p>
          </div>
        </div>
        <TBRList />
      </div>
    </div>
  );
}
