from app.core.generator import _trim_to_target_chars
from app.language_policy import (
    detect_language_from_text,
    LanguageDetectionAccumulator,
    get_language_policy,
)


def test_detect_language_from_text_supports_cjk_families():
    assert detect_language_from_text("Alice and Bob walked home.") == "en"
    assert detect_language_from_text("云澈看向远方。") == "zh"
    assert detect_language_from_text("勇者は城へ向かった。") == "ja"
    assert detect_language_from_text("민수는 집으로 돌아갔다.") == "ko"


def test_detect_language_from_text_ignores_sparse_kana_noise_in_chinese_text():
    noisy_chinese = (
        "云澈看向前方，周围的人都屏住了呼吸。"
        "他抬起手时，所有人都感到心口发紧。"
        "这段正文里混进了少量乱码假名ぃアご。"
    )

    assert detect_language_from_text(noisy_chinese) == "zh"


def test_detection_accumulator_ignores_sparse_kana_noise_in_chinese_text():
    texts = (
        "云澈看向前方，周围的人都屏住了呼吸。",
        "他抬起手时，所有人都感到心口发紧。",
        "这段正文里混进了少量乱码假名ぃアご。",
    )

    accumulator = LanguageDetectionAccumulator()
    for text in texts:
        accumulator.add_text(text)
    assert accumulator.detect_language() == "zh"


def test_zh_policy_normalizes_variant_characters_for_matching():
    policy = get_language_policy("zh")

    assert policy.normalize_for_matching("凤雪児") == policy.normalize_for_matching("凤雪儿")
    assert policy.normalize_token("凤雪児。") == "凤雪儿"


def test_ja_policy_does_not_rewrite_variant_characters_into_chinese_forms():
    policy = get_language_policy("ja")

    assert policy.normalize_for_matching("雪児") == "雪児"
    assert policy.normalize_token("雪児。") == "雪児"


def test_english_policy_trims_at_period_boundary():
    trimmed = get_language_policy("en").trim_to_sentence_boundary(
        "Alpha beta. Gamma delta. Omega",
        17,
    )

    assert trimmed == "Alpha beta."


def test_english_policy_treats_apostrophes_as_word_boundaries():
    policy = get_language_policy("en")
    straight = "Alice's lantern dimmed."
    curly = "Alice’s lantern dimmed."

    straight_start = straight.index("Alice")
    curly_start = curly.index("Alice")

    assert policy.match_has_word_boundaries(straight, straight_start, straight_start + len("Alice"))
    assert policy.match_has_word_boundaries(curly, curly_start, curly_start + len("Alice"))


def test_generator_trim_uses_language_policy_for_english():
    trimmed = _trim_to_target_chars(
        "Alpha beta. Gamma delta. Omega",
        17,
        language="en",
    )

    assert trimmed == "Alpha beta."


def test_forward_overshoot_keeps_straddling_sentence():
    policy = get_language_policy("zh")
    text = "第一句。第二句子在这里。第三句。"
    # target=8 lands inside the 2nd sentence; the next boundary (idx 12) is
    # within the overrun ceiling (8 + 6), so the straddling sentence is kept.
    trimmed = policy.trim_to_sentence_boundary(text, 8, max_overrun_chars=6)

    assert trimmed == "第一句。第二句子在这里。"


def test_default_trim_is_backward_only_without_overrun():
    policy = get_language_policy("zh")
    text = "第一句。第二句子在这里。第三句。"
    # No overrun budget -> historical behavior: cut back to the last boundary <= target.
    trimmed = policy.trim_to_sentence_boundary(text, 8)

    assert trimmed == "第一句。"


def test_forward_overshoot_falls_back_when_no_boundary_in_ceiling():
    policy = get_language_policy("zh")
    text = "第一句。第二句子在这里。第三句。"
    # ceiling (8 + 2 = 10) cannot reach the next boundary at idx 12 -> backward trim.
    trimmed = policy.trim_to_sentence_boundary(text, 8, max_overrun_chars=2)

    assert trimmed == "第一句。"


def test_generator_trim_allows_bounded_overrun_for_chinese():
    # 2nd sentence ends at idx 44; default trim-overrun ratio (1.15) makes the
    # ceiling for target=40 reach it, so the sentence straddling target is kept
    # whole instead of severed back to idx 39.
    text = "甲" * 38 + "。" + "乙" * 4 + "。" + "丙" * 10 + "。"
    overrun = _trim_to_target_chars(text, 40, language="zh")
    backward_only = get_language_policy("zh").trim_to_sentence_boundary(text, 40)

    assert overrun == "甲" * 38 + "。" + "乙" * 4 + "。"
    assert overrun.endswith("。")
    assert len(overrun) > len(backward_only)
