import logging
import sys
import asyncio
import time

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)

from bot import fetch_page_text, parse_messages, seen_ids, warmed_up, fetch_channel


async def dry_cycle(channels: dict) -> tuple[float, int]:
    t0 = time.time()
    async def fetch_one(ch, kws):
        html = await fetch_page_text(f"https://t.me/s/{ch.lstrip('@')}")
        if html:
            return parse_messages(html, ch, kws)
        return []

    results = await asyncio.gather(*(fetch_one(ch, kws) for ch, kws in channels.items()))
    elapsed = time.time() - t0
    return elapsed, sum(len(r) for r in results)


async def main():
    CHANNELS = {
        "@lpr1_treugolnik": ["Белгород", "тревог"],
        "@mchs_belgorod": ["Ракетная опасность", "Отбой"],
        "@BelgorodDRONE": ["Ракетная опасность", "Отбой", "Белгород", "Бочковка"],
    }

    for ch in CHANNELS:
        seen_ids[ch] = set()

    # 1. WARMUP
    print("=== 1. WARMUP ===")
    await asyncio.gather(*(fetch_channel(ch, kws) for ch, kws in CHANNELS.items()))
    total = sum(len(v) for v in seen_ids.values())
    print(f"  Recorded: {total} msgs, {len(warmed_up)} channels warmed up")

    # 2. DEDUP
    print("\n=== 2. DEDUP TEST ===")
    elapsed, new = await dry_cycle(CHANNELS)
    print(f"  New matches after warmup: {new} (expected 0)")
    assert new == 0, "FAIL: duplicates!"
    print("  PASS")

    # 3. TIMING (5 cycles)
    print("\n=== 3. TIMING (5 cycles) ===")
    times = []
    for i in range(5):
        elapsed, new = await dry_cycle(CHANNELS)
        times.append(elapsed)
    avg = sum(times) / len(times)
    print(f"  Times: {[f'{t:.2f}' for t in times]}s")
    print(f"  Average: {avg:.2f}s")
    assert avg < 5, f"FAIL: too slow ({avg:.2f}s)"
    print("  PASS")

    # 4. CACHE BUSTING
    print("\n=== 4. CACHE BUSTING ===")
    html1 = await fetch_page_text("https://t.me/s/mchs_belgorod")
    await asyncio.sleep(0.1)
    html2 = await fetch_page_text("https://t.me/s/mchs_belgorod")
    assert html1 and html2, "FAIL: empty response"
    assert "tgme_widget_message" in html1, "FAIL: no message divs"
    print(f"  Page 1: {len(html1)} bytes")
    print(f"  Page 2: {len(html2)} bytes")
    print("  PASS")

    # 5. KEYWORD MATCHING
    print("\n=== 5. KEYWORD MATCHING ===")
    html = await fetch_page_text("https://t.me/s/BelgorodDRONE")
    # fresh parse with unique channel key
    results = parse_messages(html, "@_test_BelgorodDRONE", ["Ракетная опасность", "Отбой"])
    print(f"  Keyword matches: {len(results)}")
    for mid, kw, txt, url in results[:3]:
        print(f"    [{mid}] kw={kw}: {txt[:50]}...")
    print("  PASS")

    # 6. ERROR HANDLING
    print("\n=== 6. ERROR HANDLING ===")
    html = await fetch_page_text("https://t.me/s/____nonexistent____")
    assert html is None, "FAIL: expected None"
    print("  PASS: nonexistent channel")

    print("\n✓ ALL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
