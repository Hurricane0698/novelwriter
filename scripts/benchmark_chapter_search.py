"""Compare projected chapter-search fetch sizes on a disposable SQLite corpus.

No batch size is promoted automatically. Timing, peak Python allocations,
result equality and cooperative cancellation latency are measured separately.
"""

import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import random
from statistics import median
import tempfile
import threading
from time import perf_counter
import tracemalloc
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Query, sessionmaker

from app.database import Base
from app.models import Chapter, Novel
from app.core.copilot import research_tools as tools
from app.core.copilot.sync_runtime import SyncExecutionChannel


async def cancellation_probe(factory, novel, batch):
    entered, resume = threading.Event(), threading.Event()
    channel = SyncExecutionChannel(max_workers=1)
    original_scan = tools._scan_chapter_matches
    original_yield = Query.yield_per
    first = True

    def scan(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            entered.set()
            if not resume.wait(10):
                raise TimeoutError("cancellation probe barrier")
        return original_scan(*args, **kwargs)

    def run():
        with factory() as db:
            return tools._find_from_chapters("cat", db, novel)

    try:
        with patch.object(tools, "_scan_chapter_matches", scan), patch.object(Query, "yield_per", lambda query, _: original_yield(query, batch)):
            task = asyncio.create_task(channel.run(run))
            async with asyncio.timeout(10):
                while not entered.is_set():
                    await asyncio.sleep(0.001)
            start = perf_counter()
            task.cancel()
            await asyncio.sleep(0)
            resume.set()
            try:
                await task
            except asyncio.CancelledError:
                pass
            elapsed = (perf_counter() - start) * 1000
            assert await channel.run(lambda: True)
            return elapsed
    finally:
        resume.set()
        channel._executor.shutdown(wait=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapters", type=int, default=400)
    parser.add_argument("--chars", type=int, default=20000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    batches = [1, 8, 32, 64]
    with tempfile.TemporaryDirectory(prefix="novwr-search-bench-") as directory:
        engine = create_engine(f"sqlite:///{directory}/corpus.db")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        text = ("cat " + "scatter " * (args.chars // 8))[:args.chars]
        with factory.begin() as db:
            db.add(Novel(id=1, title="Benchmark", file_path="unused", language="en", total_chapters=args.chapters))
            db.flush()
            db.bulk_insert_mappings(Chapter, [
                {"novel_id": 1, "chapter_number": index + 1, "content": text + " cat" * (index % 17)}
                for index in range(args.chapters)
            ])
        novel = SimpleNamespace(id=1, language="en")
        expected = None
        times = {batch: [] for batch in batches}
        original_yield = Query.yield_per

        def run(batch):
            with patch.object(Query, "yield_per", lambda query, _: original_yield(query, batch)), factory() as db:
                return tools._find_from_chapters("cat", db, novel)

        rng = random.Random(17)
        for _ in range(args.repeats):
            rng.shuffle(batches)
            for batch in batches:
                start = perf_counter()
                result = run(batch)
                times[batch].append((perf_counter() - start) * 1000)
                if expected is None:
                    expected = result
                assert result == expected
        rows = []
        for batch in sorted(batches):
            tracemalloc.start()
            assert run(batch) == expected
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            rows.append({
                "batch": batch, "median_ms": round(median(times[batch]), 2),
                "runs_ms": [round(value, 2) for value in times[batch]],
                "peak_python_mib": round(peak / 1024**2, 3),
                "cancel_at_first_scan_ms": round(asyncio.run(cancellation_probe(factory, novel, batch)), 3),
                "results_equal": True,
            })
        report = {"database": "SQLite", "chapters": args.chapters, "chars_per_chapter": args.chars,
                  "result_digest": sha256(repr(expected).encode()).hexdigest(), "measurements": rows,
                  "limits": "Python allocations exclude native driver buffers/RSS; cancellation is measured after first batch fetch, not while the database driver is blocked."}
        output = json.dumps(report, indent=2) + "\n"
        if args.output:
            args.output.write_text(output)
        print(output, end="")
        engine.dispose()


if __name__ == "__main__":
    main()
