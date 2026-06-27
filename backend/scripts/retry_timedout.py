#!/usr/bin/env python3
"""Re-run only the tests that timed out."""

import json
import time
import urllib.request

API = "http://localhost:8000/api/v1/recommend/"

QUERIES = [
    ("Fantasy - Discovery(2)", "chosen one epic destiny"),
    ("Fantasy - Discovery(3)", "dark academia magic school"),
    ("SciFi - Discovery(3)", "space opera political intrigue"),
    ("Historical - Discovery", "historical epic medieval"),
    ("Historical - Discovery(2)", "WWI from german perspective"),
    ("Historical - Similarity", "like All Quiet on the Western Front"),
    ("Horror - Discovery", "cosmic horror existential dread"),
    ("Horror - Discovery(2)", "psychological horror haunted house"),
    ("Horror - Similarity", "more books like Mexican Gothic"),
    ("NonFic - Discovery", "memoir survival overcoming adversity"),
    ("NonFic - Discovery(2)", "investigative journalism true crime"),
    ("NonFic - Similarity", "like Educated"),
    ("NonFic(2) - Discovery", "stoic philosophy practical wisdom"),
    ("NonFic(2) - Discovery(2)", "history of human civilization"),
    ("NonFic(2) - Similarity", "like Sapiens"),
    ("Thriller - Discovery(4)", "true crime investigative journalism"),
    ("Edge - Contradictory", "cozy horror lighthearted"),
]

with open("result_retry.txt", "w") as f:
    f.write("# Retry of timed-out tests\n\n")

    for label, query in QUERIES:
        payload = json.dumps({"query": query}).encode()
        req = urllib.request.Request(
            API,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                elapsed = round(time.time() - t0, 2)
            n = len(data.get("results", []))
            moods = data.get("mood_tags_extracted", [])
            f.write(
                f"\n## {label}\n**Query:** {query}\n**Time:** {elapsed}s\n**Results:** {n}\n"
            )
            if moods:
                f.write(f"**Moods:** {', '.join(moods)}\n")
            for r in data.get("results", []):
                w = r.get("work", {})
                author = w.get("author", {}).get("canonical_name", "?")
                title = w.get("title", "?")
                expl = r.get("explanation", "")[:100]
                f.write(f"  {title} by {author}\n    {expl}\n")
            print(f"  [{label}] {n} results in {elapsed}s")
        except Exception as e:
            f.write(f"\n## {label}\n**Query:** {query}\n**ERROR:** {e}\n")
            print(f"  [{label}] ERROR: {e}")

print("\nWritten to result_retry.txt")
