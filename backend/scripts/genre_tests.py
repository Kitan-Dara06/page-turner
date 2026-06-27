#!/usr/bin/env python3
"""
Genre coverage test suite.
Results appended to result.txt after each test - safe to Ctrl+C.
Run: PYTHONPATH=$PWD .venv/bin/python scripts/genre_tests.py
"""

import json
import time
import urllib.error
import urllib.request

API = "http://localhost:8000/api/v1/recommend/"
OUT = "result.txt"

# Write header once
with open(OUT, "w") as f:
    f.write("# PageTurner Genre Test Results\n")
    f.write(f"# Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("# Run: PYTHONPATH=$PWD .venv/bin/python scripts/genre_tests.py\n\n")


def test(label, query, expected_type=None):
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        API, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
            elapsed = round(time.time() - t0, 2)
    except Exception as e:
        lines = f"\n## {label}\n**Query:** {query}\n**ERROR:** {e}\n"
        with open(OUT, "a") as f:
            f.write(lines + "\n" + "-" * 60 + "\n")
        print(f"  [{label}] ERROR: {e}")
        return

    n = len(data.get("results", []))
    qtype = data.get("query_rewritten", "?")[:80]
    moods = data.get("mood_tags_extracted", [])

    lines = [f"\n## {label}", f"**Query:** {query}", f"**Response:** {elapsed}s"]
    if expected_type:
        lines.append(f"**Expected:** {expected_type}")
    lines.append(f"**Results:** {n}")
    if moods:
        lines.append(f"**Moods:** {', '.join(moods)}")
    lines.append(f"**Rewritten:** {qtype}")

    for r in data.get("results", []):
        w = r.get("work", {})
        author = w.get("author", {}).get("canonical_name", "?")
        explanation = r.get("explanation", "")[:120]
        source = r.get("match_source", "?")
        title = w.get("title", "?")
        lines.append(f"\n  [{source}] {title} by {author}")
        lines.append(f"    {explanation}")

    if n == 0:
        lines.append("  (no results)")

    out = "\n".join(lines) + "\n" + "-" * 60 + "\n"
    with open(OUT, "a") as f:
        f.write(out)
    print(f"  [{label}] {n} results in {elapsed}s")


def run():
    print("Writing results to result.txt...")

    # ── 1. FANTASY ───────────────────────────────────────────
    test("Fantasy - Lookup", "books by Leigh Bardugo", "lookup")
    test("Fantasy - Lookup(2)", "The Lies of Locke Lamora series", "lookup")
    test("Fantasy - Discovery", "found family heist fantasy", "discovery")
    test("Fantasy - Discovery(2)", "chosen one epic destiny", "discovery")
    test("Fantasy - Discovery(3)", "dark academia magic school", "discovery")
    test("Fantasy - Similarity", "like Six of Crows but adult", "similarity")

    # ── 2. SCIENCE FICTION ───────────────────────────────────
    test("SciFi - Discovery", "hard sci-fi first contact", "discovery")
    test("SciFi - Discovery(2)", "cyberpunk dystopian future", "discovery")
    test("SciFi - Discovery(3)", "space opera political intrigue", "discovery")
    test("SciFi - Similarity", "like Project Hail Mary", "similarity")

    # ── 3. HISTORICAL FICTION ────────────────────────────────
    test("Historical - Discovery", "historical epic medieval", "discovery")
    test("Historical - Discovery(2)", "WWI from german perspective", "discovery")
    test("Historical - Similarity", "like All Quiet on the Western Front", "similarity")

    # ── 4. HORROR ────────────────────────────────────────────
    test("Horror - Lookup", "Stephen King", "lookup")
    test("Horror - Discovery", "cosmic horror existential dread", "discovery")
    test("Horror - Discovery(2)", "psychological horror haunted house", "discovery")
    test("Horror - Discovery(3)", "gothic folk horror", "discovery")
    test("Horror - Similarity", "more books like Mexican Gothic", "similarity")

    # ── 5. NARRATIVE NONFICTION ──────────────────────────────
    test("NonFic - Discovery", "memoir survival overcoming adversity", "discovery")
    test("NonFic - Discovery(2)", "investigative journalism true crime", "discovery")
    test("NonFic - Similarity", "like Educated", "similarity")

    # ── 6. NON-NARRATIVE NONFICTION ──────────────────────────
    test("NonFic(2) - Discovery", "stoic philosophy practical wisdom", "discovery")
    test("NonFic(2) - Discovery(2)", "history of human civilization", "discovery")
    test("NonFic(2) - Similarity", "like Sapiens", "similarity")

    # ── 7. THRILLER / MYSTERY ────────────────────────────────
    test(
        "Thriller - Discovery",
        "psychological thriller unreliable narrator",
        "discovery",
    )
    test("Thriller - Discovery(2)", "gothic mystery atmospheric mansion", "discovery")
    test("Thriller - Discovery(3)", "domestic thriller marriage secrets", "discovery")
    test("Thriller - Discovery(4)", "true crime investigative journalism", "discovery")

    # ── 8. EDGE CASES ────────────────────────────────────────
    test("Edge - Neutral", "just give me something good", "discovery")
    test("Edge - Contradictory", "cozy horror lighthearted", "discovery")

    print(f"\nDone. Results in {OUT}")


if __name__ == "__main__":
    run()
