from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from pathlib import Path
from statistics import mean, median
from time import perf_counter

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import get_settings  # noqa: E402
from app.content_formats import PLAIN_TEXT_CONTENT_FORMAT  # noqa: E402
from app.core.bootstrap_text_fallback import (  # noqa: E402
    TEXT_FALLBACK_WINDOW_SIZE,
    TEXT_FALLBACK_WINDOW_STEP,
    build_refinement_inputs_from_text_candidates,
    count_text_fallback_windows,
    extract_text_candidate_counts,
    extract_rust_zh_sorted_candidates,
    resolve_text_fallback_shortlist_limit,
    resolve_text_fallback_window_threshold,
)
from app.core.indexing.builder import ChapterText, load_common_words  # noqa: E402
from app.core.ingest.parser_service import parse_source_file  # noqa: E402
from app.core.indexing.state_proto_rust_text import summarize_rust_zh_windows  # noqa: E402
from app.core.process_metrics import get_process_peak_rss_kib, get_process_rss_kib  # noqa: E402
from app.language_policy import (  # noqa: E402
    get_language_policy,
    resolve_text_processing_language,
)

DEFAULT_STAGES = ("parse", "candidate_count", "window_summary", "text_fallback")


class _RssSampler:
    def __init__(self, *, interval_ms: int):
        self._interval_seconds = max(int(interval_ms or 0), 1) / 1000
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.max_rss_kib = get_process_rss_kib()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> int | None:
        self._stop_event.set()
        self._thread.join()
        current_rss = get_process_rss_kib()
        if current_rss is not None:
            self.max_rss_kib = (
                current_rss
                if self.max_rss_kib is None
                else max(self.max_rss_kib, current_rss)
            )
        return self.max_rss_kib

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            current_rss = get_process_rss_kib()
            if current_rss is None:
                continue
            self.max_rss_kib = (
                current_rss
                if self.max_rss_kib is None
                else max(self.max_rss_kib, current_rss)
            )


def _format_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "No bootstrap refinement profile rows generated."

    headers = [
        "file",
        "stage",
        "repeats",
        "duration_ms_avg",
        "duration_ms_p50",
        "duration_ms_max",
        "rss_delta_kib_avg",
        "rss_delta_kib_max",
        "peak_rss_delta_kib_avg",
        "peak_rss_delta_kib_max",
        "details",
    ]
    widths = {
        header: max(len(header), *[len(str(row.get(header, ""))) for row in rows])
        for header in headers
    }
    lines = [
        " ".join(header.ljust(widths[header]) for header in headers),
        " ".join("-" * widths[header] for header in headers),
    ]
    for row in rows:
        lines.append(
            " ".join(
                str(row.get(header, "")).ljust(widths[header]) for header in headers
            )
        )
    return "\n".join(lines)


def _iter_real_file_paths(
    *, files: list[str], input_dir: str | None, glob_pattern: str
) -> list[Path]:
    resolved_paths: list[Path] = []
    for raw_path in files:
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Benchmark input file not found: {raw_path}")
        resolved_paths.append(path)

    if input_dir:
        root = Path(input_dir).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(
                f"Benchmark input directory not found: {input_dir}"
            )
        resolved_paths.extend(
            sorted(path.resolve() for path in root.glob(glob_pattern) if path.is_file())
        )

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in resolved_paths:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return deduped


def _delta_kib(after: int | None, before: int | None) -> int | None:
    if after is None or before is None:
        return None
    return after - before


def _load_parsed_chapters(
    file_path: Path,
    *,
    requested_language: str | None,
) -> dict[str, object]:
    parsed = parse_source_file(
        str(file_path),
        content_format=PLAIN_TEXT_CONTENT_FORMAT,
        requested_language=requested_language,
    )
    chapters = [
        ChapterText(chapter_id=index, text=chapter.content)
        for index, chapter in enumerate(parsed.chapters, start=1)
        if (chapter.content or "").strip()
    ]
    chapter_chars = sum(len(chapter.text or "") for chapter in chapters)
    return {
        "resolved_language": parsed.resolved_language,
        "chapters": chapters,
        "chapter_count": len(chapters),
        "chapter_chars": chapter_chars,
    }


def _measure_stage(
    stage: str,
    *,
    sample_interval_ms: int,
    workload,
) -> dict[str, object]:
    rss_before_kib = get_process_rss_kib()
    process_peak_before_kib = get_process_peak_rss_kib()
    sampler = _RssSampler(interval_ms=sample_interval_ms)
    started_at = perf_counter()
    sampler.start()
    try:
        payload = workload()
    finally:
        peak_rss_kib = sampler.stop()
    duration_ms = round((perf_counter() - started_at) * 1000, 1)
    rss_after_kib = get_process_rss_kib()
    process_peak_after_kib = get_process_peak_rss_kib()
    return {
        "stage": stage,
        "duration_ms": duration_ms,
        "rss_before_kib": rss_before_kib,
        "rss_after_kib": rss_after_kib,
        "rss_delta_kib": _delta_kib(rss_after_kib, rss_before_kib),
        "peak_rss_kib": peak_rss_kib,
        "peak_rss_delta_kib": _delta_kib(peak_rss_kib, rss_before_kib),
        "process_peak_before_kib": process_peak_before_kib,
        "process_peak_after_kib": process_peak_after_kib,
        "process_peak_delta_kib": _delta_kib(
            process_peak_after_kib,
            process_peak_before_kib,
        ),
        **payload,
    }


def run_stage_once(
    *,
    file_path: Path,
    stage: str,
    requested_language: str | None,
    limit: int,
    sample_interval_ms: int,
) -> dict[str, object]:
    if stage not in DEFAULT_STAGES:
        raise ValueError(f"Unsupported stage: {stage}")

    file_path = file_path.expanduser().resolve()
    settings = get_settings()

    if stage == "parse":

        def workload() -> dict[str, object]:
            parsed = _load_parsed_chapters(
                file_path,
                requested_language=requested_language,
            )
            return {
                "resolved_language": parsed["resolved_language"],
                "chapter_count": parsed["chapter_count"],
                "chapter_chars": parsed["chapter_chars"],
            }

        measured = _measure_stage(
            stage,
            sample_interval_ms=sample_interval_ms,
            workload=workload,
        )
        return {
            "file": file_path.name,
            **measured,
        }

    prepared = _load_parsed_chapters(file_path, requested_language=requested_language)
    chapters = prepared["chapters"]
    resolved_language = prepared["resolved_language"]
    chapter_count = prepared["chapter_count"]
    chapter_chars = prepared["chapter_chars"]
    normalized_language = resolve_text_processing_language(resolved_language)
    policy = get_language_policy(normalized_language)
    shortlist_limit = resolve_text_fallback_shortlist_limit(limit)

    if stage == "candidate_count":
        common_words = load_common_words(
            normalized_language,
            common_words_dir=settings.bootstrap_common_words_dir,
        )

        def workload() -> dict[str, object]:
            if policy.base_language == "zh":
                sorted_candidates = extract_rust_zh_sorted_candidates(
                    chapters,
                    common_words=common_words,
                    limit=shortlist_limit,
                )
                sorted_candidates = sorted_candidates or []
                return {
                    "resolved_language": resolved_language,
                    "chapter_count": chapter_count,
                    "chapter_chars": chapter_chars,
                    "candidate_count": len(sorted_candidates),
                    "shortlisted_count": min(len(sorted_candidates), shortlist_limit),
                }

            _, candidate_counts = extract_text_candidate_counts(
                chapters,
                novel_language=resolved_language,
                common_words_dir=settings.bootstrap_common_words_dir,
            )
            return {
                "resolved_language": resolved_language,
                "chapter_count": chapter_count,
                "chapter_chars": chapter_chars,
                "candidate_count": len(candidate_counts),
                "shortlisted_count": min(len(candidate_counts), shortlist_limit),
            }

        measured = _measure_stage(
            stage,
            sample_interval_ms=sample_interval_ms,
            workload=workload,
        )
        return {"file": file_path.name, **measured}

    if stage == "window_summary":
        if policy.base_language != "zh":
            return {
                "file": file_path.name,
                "stage": stage,
                "resolved_language": resolved_language,
                "chapter_count": chapter_count,
                "chapter_chars": chapter_chars,
                "skipped": True,
                "skip_reason": "window_summary_only_supported_for_zh",
            }

        common_words = load_common_words(
            normalized_language,
            common_words_dir=settings.bootstrap_common_words_dir,
        )
        sorted_candidates = (
            extract_rust_zh_sorted_candidates(
                chapters,
                common_words=common_words,
                limit=shortlist_limit,
            )
            or []
        )
        shortlisted_candidates = [
            candidate for candidate, _ in sorted_candidates[:shortlist_limit]
        ]
        total_windows = count_text_fallback_windows(chapters)
        threshold = resolve_text_fallback_window_threshold(total_windows)

        def workload() -> dict[str, object]:
            summary = summarize_rust_zh_windows(
                chapters=chapters,
                shortlisted_candidates=shortlisted_candidates,
                window_size=TEXT_FALLBACK_WINDOW_SIZE,
                window_step=TEXT_FALLBACK_WINDOW_STEP,
                threshold=threshold,
            )
            if summary is None:
                raise RuntimeError("Rust zh window summary helper is unavailable")
            return {
                "resolved_language": resolved_language,
                "chapter_count": chapter_count,
                "chapter_chars": chapter_chars,
                "shortlisted_count": len(shortlisted_candidates),
                "total_windows": total_windows,
                "threshold": threshold,
                "importance_count": len(summary.importance),
                "pair_count": len(summary.cooccurrence_pairs),
            }

        measured = _measure_stage(
            stage,
            sample_interval_ms=sample_interval_ms,
            workload=workload,
        )
        return {"file": file_path.name, **measured}

    def workload() -> dict[str, object]:
        importance, pairs = build_refinement_inputs_from_text_candidates(
            chapters,
            novel_language=resolved_language,
            common_words_dir=settings.bootstrap_common_words_dir,
            limit=limit,
        )
        total_windows = count_text_fallback_windows(chapters)
        return {
            "resolved_language": resolved_language,
            "chapter_count": chapter_count,
            "chapter_chars": chapter_chars,
            "total_windows": total_windows,
            "threshold": resolve_text_fallback_window_threshold(total_windows),
            "shortlist_limit": shortlist_limit,
            "importance_count": len(importance),
            "pair_count": len(pairs),
        }

    measured = _measure_stage(
        stage,
        sample_interval_ms=sample_interval_ms,
        workload=workload,
    )
    return {"file": file_path.name, **measured}


def _worker_command(
    *,
    file_path: Path,
    stage: str,
    requested_language: str | None,
    limit: int,
    sample_interval_ms: int,
) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--file",
        str(file_path),
        "--stage",
        stage,
        "--limit",
        str(limit),
        "--sample-interval-ms",
        str(sample_interval_ms),
    ]
    if requested_language:
        command.extend(["--requested-language", requested_language])
    return command


def _run_worker_subprocess(
    *,
    file_path: Path,
    stage: str,
    requested_language: str | None,
    limit: int,
    sample_interval_ms: int,
) -> dict[str, object]:
    command = _worker_command(
        file_path=file_path,
        stage=stage,
        requested_language=requested_language,
        limit=limit,
        sample_interval_ms=sample_interval_ms,
    )
    completed = subprocess.run(
        command,
        cwd=str(ROOT_DIR),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def _summarize_series(values: list[int | float]) -> dict[str, float]:
    return {
        "avg": round(mean(values), 1),
        "p50": round(median(values), 1),
        "max": round(max(values), 1),
    }


def _detail_string(row: dict[str, object]) -> str:
    if row.get("skipped"):
        return f"skipped={row.get('skip_reason')}"

    details: list[str] = []
    if row.get("resolved_language"):
        details.append(f"lang={row['resolved_language']}")
    if row.get("chapter_count") is not None:
        details.append(f"chapters={row['chapter_count']}")
    if row.get("chapter_chars") is not None:
        details.append(f"chars={row['chapter_chars']}")
    if row.get("candidate_count") is not None:
        details.append(f"candidates={row['candidate_count']}")
    if row.get("shortlisted_count") is not None:
        details.append(f"shortlisted={row['shortlisted_count']}")
    if row.get("shortlist_limit") is not None:
        details.append(f"shortlist_limit={row['shortlist_limit']}")
    if row.get("total_windows") is not None:
        details.append(f"windows={row['total_windows']}")
    if row.get("threshold") is not None:
        details.append(f"threshold={row['threshold']}")
    if row.get("importance_count") is not None:
        details.append(f"importance={row['importance_count']}")
    if row.get("pair_count") is not None:
        details.append(f"pairs={row['pair_count']}")
    return " ".join(details)


def aggregate_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault((str(row["file"]), str(row["stage"])), []).append(row)

    aggregated_rows: list[dict[str, object]] = []
    for (file_name, stage), group in sorted(grouped.items()):
        first = group[0]
        if first.get("skipped"):
            aggregated_rows.append(
                {
                    "file": file_name,
                    "stage": stage,
                    "repeats": len(group),
                    "duration_ms_avg": "",
                    "duration_ms_p50": "",
                    "duration_ms_max": "",
                    "rss_delta_kib_avg": "",
                    "rss_delta_kib_max": "",
                    "peak_rss_delta_kib_avg": "",
                    "peak_rss_delta_kib_max": "",
                    "details": _detail_string(first),
                    "skipped": True,
                    "skip_reason": first.get("skip_reason"),
                }
            )
            continue

        duration_series = _summarize_series(
            [
                float(row["duration_ms"])
                for row in group
                if row.get("duration_ms") is not None
            ]
        )
        rss_delta_values = [
            int(row["rss_delta_kib"])
            for row in group
            if row.get("rss_delta_kib") is not None
        ]
        peak_delta_values = [
            int(row["peak_rss_delta_kib"])
            for row in group
            if row.get("peak_rss_delta_kib") is not None
        ]
        aggregated_rows.append(
            {
                "file": file_name,
                "stage": stage,
                "repeats": len(group),
                "duration_ms_avg": duration_series["avg"],
                "duration_ms_p50": duration_series["p50"],
                "duration_ms_max": duration_series["max"],
                "rss_delta_kib_avg": (
                    _summarize_series(rss_delta_values)["avg"]
                    if rss_delta_values
                    else ""
                ),
                "rss_delta_kib_max": (
                    _summarize_series(rss_delta_values)["max"]
                    if rss_delta_values
                    else ""
                ),
                "peak_rss_delta_kib_avg": (
                    _summarize_series(peak_delta_values)["avg"]
                    if peak_delta_values
                    else ""
                ),
                "peak_rss_delta_kib_max": (
                    _summarize_series(peak_delta_values)["max"]
                    if peak_delta_values
                    else ""
                ),
                "details": _detail_string(first),
                "resolved_language": first.get("resolved_language"),
                "chapter_count": first.get("chapter_count"),
                "chapter_chars": first.get("chapter_chars"),
                "candidate_count": first.get("candidate_count"),
                "shortlisted_count": first.get("shortlisted_count"),
                "shortlist_limit": first.get("shortlist_limit"),
                "total_windows": first.get("total_windows"),
                "threshold": first.get("threshold"),
                "importance_count": first.get("importance_count"),
                "pair_count": first.get("pair_count"),
            }
        )
    return aggregated_rows


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices={"table", "json"}, default="table")
    parser.add_argument("--files", nargs="*", default=[])
    parser.add_argument("--input-dir")
    parser.add_argument("--glob", default="*.txt")
    parser.add_argument("--requested-language")
    parser.add_argument(
        "--limit", type=int, default=get_settings().bootstrap_max_candidates
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--sample-interval-ms", type=int, default=5)
    parser.add_argument("--stages", nargs="*", default=list(DEFAULT_STAGES))

    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--file")
    parser.add_argument("--stage", choices=DEFAULT_STAGES)
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.worker:
        if not args.file or not args.stage:
            raise SystemExit("--worker requires --file and --stage")
        row = run_stage_once(
            file_path=Path(args.file),
            stage=args.stage,
            requested_language=args.requested_language,
            limit=int(args.limit),
            sample_interval_ms=int(args.sample_interval_ms),
        )
        print(json.dumps(row, ensure_ascii=False))
        return 0

    if not args.stages:
        raise SystemExit("At least one stage is required")

    for stage in args.stages:
        if stage not in DEFAULT_STAGES:
            raise SystemExit(f"Unsupported stage: {stage}")

    rows: list[dict[str, object]] = []
    file_paths = _iter_real_file_paths(
        files=args.files,
        input_dir=args.input_dir,
        glob_pattern=args.glob,
    )
    for path in file_paths:
        for stage in args.stages:
            for repeat_index in range(max(int(args.repeat), 1)):
                row = _run_worker_subprocess(
                    file_path=path,
                    stage=stage,
                    requested_language=args.requested_language,
                    limit=int(args.limit),
                    sample_interval_ms=int(args.sample_interval_ms),
                )
                row["repeat"] = repeat_index + 1
                rows.append(row)

    aggregated_rows = aggregate_rows(rows)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "rows": rows,
                    "aggregated_rows": aggregated_rows,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(_format_table(aggregated_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
