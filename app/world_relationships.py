import re
import unicodedata

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af]")
_CJK_SUFFIXES = ("关系", "關係")


def canonicalize_relationship_label(label: str) -> str:
    normalized = unicodedata.normalize("NFKC", label or "").strip()
    normalized = re.sub(r"\s+", " ", normalized)
    canonical = normalized.lower()

    if _CJK_RE.search(canonical):
        for suffix in _CJK_SUFFIXES:
            if canonical.endswith(suffix) and len(canonical) > len(suffix):
                canonical = canonical[: -len(suffix)].rstrip()
                break

    return canonical or normalized.lower()
