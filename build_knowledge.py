# -*- coding: utf-8 -*-
"""NeuroKey — Bilim indeksini qurish.

Manba: permanent_memory (16 093 yozuv) + starter umumiy faktlar.
Wikipedia keyin build_wikipedia_index.py orqali qo'shiladi.

Ishga tushirish:  python build_knowledge.py
"""
import time

import knowledge_index as kb

# Starter faktlar (EN asosiy — model EN/RU da eng yaxshi ishlaydi).
# Bu Wikipedia o'rniga vaqtinchalik. build_wikipedia_index.py bilan
# haqiqiy Wikipedia qo'shiladi (kechasi).
STARTER_FACTS = [
    ("Recursion is when a function calls itself, solving a smaller "
     "subproblem each time until a base case.", "en:cs"),
    ("Python is a high-level programming language created by Guido van "
     "Rossum in 1991.", "en:cs"),
    ("FAISS (Facebook AI Similarity Search) is a library for fast "
     "vector similarity search.", "en:ai"),
    ("An embedding turns text into a numeric vector so semantic "
     "similarity can be measured.", "en:ai"),
    ("Global Workspace Theory (Baars, 1988) says consciousness is "
     "information winning a competition to a central broadcast stage.", "en:consciousness"),
    ("Butlin et al. (2023) 'Consciousness in AI' lists 14 indicator "
     "properties derived from the science of consciousness.", "en:consciousness"),
    ("Tashkent is the capital of Uzbekistan and the largest city in "
     "Central Asia.", "en:geo"),
    ("Paris is the capital of France, known for the Eiffel Tower.", "en:geo"),
    ("Cosine similarity is the cosine of the angle between two vectors: "
     "1 means identical, 0 means unrelated.", "en:math"),
    ("Quantum physics studies matter and energy at the smallest atomic "
     "and subatomic scales.", "en:physics"),
]


def gather_memory_chunks(limit=20000):
    """permanent_memory dan suhbat va faktlarni bo'lak sifatida oladi."""
    chunks = []
    try:
        import permanent_memory as pm
        with pm._db() as conn:
            rows = conn.execute(
                "SELECT content, role FROM conversations "
                "WHERE length(content) > 15 ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            for r in rows:
                txt = (r["content"] or "").strip()
                if txt and not txt.lower().startswith(("so'nggi", "последн")):
                    chunks.append((txt, "memory:conv"))
            # Bilimlar jadvali
            try:
                krows = conn.execute(
                    "SELECT topic, content FROM knowledge").fetchall()
                for r in krows:
                    chunks.append((f"{r['topic']}: {r['content']}", "memory:knowledge"))
            except Exception:
                pass
    except Exception as e:
        print("  [!] permanent_memory xato:", str(e)[:80])
    return chunks


def main():
    print("=" * 60)
    print("  NEUROKEY — BILIM INDEKSI QURISH")
    print("=" * 60)

    t0 = time.time()
    print("\n[1] Starter faktlar (toza bilim — suhbat shovqini QO'SHILMAYDI).")
    print("    Suhbatlar permanent_memory da qoladi. Haqiqiy hajm uchun:")
    print("    python build_wikipedia_index.py --simple")

    all_chunks = list(STARTER_FACTS)
    print(f"\n[2] {len(all_chunks)} fakt indekslanmoqda (GPU)...")
    total = kb.build(all_chunks, append=False)

    dt = time.time() - t0
    print(f"\n[3] TUGADI: {total} bo'lak, {dt:.1f}s")
    print(f"    stats: {kb.get_stats()}")

    # Tez tekshiruv
    print("\n[4] Qidiruv sinovi:")
    for q in ["rekursiya nima", "ong nazariyasi", "Toshkent qayerda"]:
        ts = time.time()
        hits = kb.search(q, k=2)
        ms = (time.time() - ts) * 1000
        print(f"    '{q}' -> {len(hits)} natija, {ms:.0f}ms")
        for h in hits[:1]:
            print(f"        [{h['score']}] {h['text'][:60]}")


if __name__ == "__main__":
    main()
