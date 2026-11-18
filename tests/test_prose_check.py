# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Unit tests for the prose-quality post-check module."""

from types import SimpleNamespace

import pytest

from app.core.prose_check import prose_check_continuation


def _make_continuations(*texts: str) -> list[SimpleNamespace]:
    """Create mock continuation objects with a .content attribute."""
    return [SimpleNamespace(content=t) for t in texts]


# ---- repeated_ngram --------------------------------------------------------


class TestRepeatedNgram:
    def test_no_warnings_for_clean_text(self) -> None:
        conts = _make_continuations("这是一段正常的文本，没有任何重复短语。")
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        ngram_warnings = [w for w in warnings if w.code == "repeated_ngram"]
        assert ngram_warnings == []

    def test_flags_cjk_repeated_trigram(self) -> None:
        phrase = "今天天气" * 4  # 4 repetitions of a 4-gram
        conts = _make_continuations(phrase)
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        ngram_warnings = [w for w in warnings if w.code == "repeated_ngram"]
        assert len(ngram_warnings) == 1
        assert ngram_warnings[0].version == 1
        assert ngram_warnings[0].message_params["count"] == 4

    def test_flags_whitespace_repeated_ngram(self) -> None:
        phrase = " ".join(["the quick brown"] * 4)  # 4 repetitions of a 3-gram
        conts = _make_continuations(phrase)
        warnings = prose_check_continuation(continuations=conts, novel_language="en")
        ngram_warnings = [w for w in warnings if w.code == "repeated_ngram"]
        assert len(ngram_warnings) == 1
        assert ngram_warnings[0].message_params["phrase"] == "the quick brown"

    def test_does_not_cross_cjk_sentence_boundaries(self) -> None:
        text = "甲乙。甲乙。甲乙。甲乙。"
        conts = _make_continuations(text)
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        ngram_warnings = [w for w in warnings if w.code == "repeated_ngram"]
        assert ngram_warnings == []

    def test_normalizes_whitespace_tokens_before_counting(self) -> None:
        text = "the quick brown, the quick brown. the quick brown!"
        conts = _make_continuations(text)
        warnings = prose_check_continuation(continuations=conts, novel_language="en")
        ngram_warnings = [w for w in warnings if w.code == "repeated_ngram"]
        assert len(ngram_warnings) == 1
        assert ngram_warnings[0].message_params["phrase"] == "the quick brown"
        assert ngram_warnings[0].message_params["count"] == 3

    def test_no_warning_below_threshold(self) -> None:
        text = "the quick brown fox jumped the quick brown"  # only 2 repetitions
        conts = _make_continuations(text)
        warnings = prose_check_continuation(continuations=conts, novel_language="en")
        ngram_warnings = [w for w in warnings if w.code == "repeated_ngram"]
        assert ngram_warnings == []

    @pytest.mark.parametrize(
        ("language", "phrase"),
        [
            ("ja", "あいうえお"),
            ("ko", "가나다라마"),
        ],
    )
    def test_flags_ja_ko_repeated_ngram_in_cjk_branch(self, language: str, phrase: str) -> None:
        conts = _make_continuations(phrase * 4)
        warnings = prose_check_continuation(continuations=conts, novel_language=language)
        ngram_warnings = [w for w in warnings if w.code == "repeated_ngram"]
        assert len(ngram_warnings) == 1
        assert ngram_warnings[0].message_params["phrase"] == phrase
        assert ngram_warnings[0].message_params["count"] == 4


# ---- long_paragraph --------------------------------------------------------


class TestLongParagraph:
    def test_no_warning_for_normal_paragraph(self) -> None:
        conts = _make_continuations("这是一个正常长度的段落。\n\n另一个段落。")
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        para_warnings = [w for w in warnings if w.code == "long_paragraph"]
        assert para_warnings == []

    def test_flags_very_long_cjk_paragraph(self) -> None:
        # Create a paragraph with >600 CJK chars
        long_para = "这是一个测试字段" * 80  # 640 chars
        conts = _make_continuations(long_para)
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        para_warnings = [w for w in warnings if w.code == "long_paragraph"]
        assert len(para_warnings) == 1
        assert para_warnings[0].version == 1
        assert para_warnings[0].evidence is not None
        assert len(para_warnings[0].evidence) <= 100  # truncated
        assert para_warnings[0].message_params["unit"] == "cjk_chars"

    def test_flags_very_long_english_paragraph(self) -> None:
        # Create a paragraph with >250 words
        long_para = " ".join(["word"] * 260)
        conts = _make_continuations(long_para)
        warnings = prose_check_continuation(continuations=conts, novel_language="en")
        para_warnings = [w for w in warnings if w.code == "long_paragraph"]
        assert len(para_warnings) == 1
        assert para_warnings[0].message_params["unit"] == "words"
        assert "words" in para_warnings[0].message

    @pytest.mark.parametrize(
        ("language", "chunk"),
        [
            ("ja", "あいうえお"),
            ("ko", "가나다라마"),
        ],
    )
    def test_flags_ja_ko_long_paragraphs_in_cjk_branch(self, language: str, chunk: str) -> None:
        conts = _make_continuations(chunk * 130)
        warnings = prose_check_continuation(continuations=conts, novel_language=language)
        para_warnings = [w for w in warnings if w.code == "long_paragraph"]
        assert len(para_warnings) == 1
        assert para_warnings[0].message_params["unit"] == "cjk_chars"


# ---- abnormal_sentence_length -----------------------------------------------


class TestAbnormalSentenceLength:
    def test_no_warning_for_normal_sentences(self) -> None:
        conts = _make_continuations("这是一句话。那是另一句。")
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        sent_warnings = [w for w in warnings if w.code == "abnormal_sentence_length"]
        assert sent_warnings == []

    def test_flags_long_cjk_sentence(self) -> None:
        # >200 CJK chars in one sentence
        long_sentence = "这" * 210 + "。"
        conts = _make_continuations(long_sentence)
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        sent_warnings = [w for w in warnings if w.code == "abnormal_sentence_length"]
        assert len(sent_warnings) >= 1

    def test_flags_long_english_sentence(self) -> None:
        # >60 words in one sentence
        long_sentence = " ".join(["word"] * 65) + "."
        conts = _make_continuations(long_sentence)
        warnings = prose_check_continuation(continuations=conts, novel_language="en")
        sent_warnings = [w for w in warnings if w.code == "abnormal_sentence_length"]
        assert len(sent_warnings) >= 1

    @pytest.mark.parametrize(
        ("language", "sentence"),
        [
            ("ja", "あ" * 210 + "。"),
            ("ko", "가" * 210 + "."),
        ],
    )
    def test_flags_ja_ko_long_sentences_in_cjk_branch(self, language: str, sentence: str) -> None:
        conts = _make_continuations(sentence)
        warnings = prose_check_continuation(continuations=conts, novel_language=language)
        sent_warnings = [w for w in warnings if w.code == "abnormal_sentence_length"]
        assert len(sent_warnings) >= 1


# ---- summary_tone -----------------------------------------------------------


class TestSummaryTone:
    def test_no_warning_for_clean_prose(self) -> None:
        conts = _make_continuations("他走在雨中，抬头看天。")
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        tone_warnings = [w for w in warnings if w.code == "summary_tone"]
        assert tone_warnings == []

    def test_flags_cjk_summary_phrase(self) -> None:
        conts = _make_continuations("他做了很多事情。总之，这一天结束了。")
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        tone_warnings = [w for w in warnings if w.code == "summary_tone"]
        assert len(tone_warnings) == 1
        assert "总之" in (tone_warnings[0].evidence or "")

    def test_flags_english_summary_phrase(self) -> None:
        conts = _make_continuations("He did many things. In summary, the day was over.")
        warnings = prose_check_continuation(continuations=conts, novel_language="en")
        tone_warnings = [w for w in warnings if w.code == "summary_tone"]
        assert len(tone_warnings) == 1

    def test_multiple_summary_phrases(self) -> None:
        conts = _make_continuations("总之，他走了。综上所述，一切结束了。")
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        tone_warnings = [w for w in warnings if w.code == "summary_tone"]
        assert len(tone_warnings) == 2

    @pytest.mark.parametrize(
        ("language", "text", "phrase"),
        [
            ("ja", "彼は黙って立っていた。要するに、答えは出ていた。", "要するに"),
            ("ko", "그는 한동안 침묵했다. 요컨대, 이미 답은 나와 있었다.", "요컨대"),
        ],
    )
    def test_flags_japanese_and_korean_summary_markers(
        self,
        language: str,
        text: str,
        phrase: str,
    ) -> None:
        conts = _make_continuations(text)
        warnings = prose_check_continuation(continuations=conts, novel_language=language)
        tone_warnings = [w for w in warnings if w.code == "summary_tone"]
        assert len(tone_warnings) == 1
        assert tone_warnings[0].message_params["phrase"] == phrase


# ---- edge/integration -------------------------------------------------------


class TestEdgeCases:
    def test_empty_text_produces_no_warnings(self) -> None:
        conts = _make_continuations("")
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        assert warnings == []

    def test_whitespace_only_produces_no_warnings(self) -> None:
        conts = _make_continuations("   \n\n   ")
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        assert warnings == []

    def test_multiple_continuations_get_correct_versions(self) -> None:
        text1 = "总之，这件事结束了。"
        text2 = "综上所述，没什么好说的。"
        conts = _make_continuations(text1, text2)
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        versions = {w.version for w in warnings}
        assert 1 in versions
        assert 2 in versions

    def test_sorted_output(self) -> None:
        # Create text that triggers multiple rule types
        text = "总之" + "这是一个测试字段" * 80 + "。"
        conts = _make_continuations(text)
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        assert len(warnings) >= 2  # at least summary_tone + long_paragraph
        # Verify sorted by (version, code)
        keys = [(w.version, w.code) for w in warnings]
        assert keys == sorted(keys)

    def test_warning_schema_fields(self) -> None:
        conts = _make_continuations("总之，一切都很好。")
        warnings = prose_check_continuation(continuations=conts, novel_language="zh")
        assert len(warnings) >= 1
        w = warnings[0]
        assert w.code == "summary_tone"
        assert w.message_key.startswith("continuation.prosecheck.warning.")
        assert isinstance(w.message_params, dict)
        assert w.version == 1

    def test_none_language_uses_both_families(self) -> None:
        conts = _make_continuations("总之，这件事结束了。In summary, it's done.")
        warnings = prose_check_continuation(continuations=conts, novel_language=None)
        tone_warnings = [w for w in warnings if w.code == "summary_tone"]
        # Should detect both CJK and English summary phrases
        assert len(tone_warnings) >= 2
