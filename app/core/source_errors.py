from __future__ import annotations


class SourceEncodingUnsupportedError(ValueError):
    """The source bytes cannot be decoded under the format's encoding contract."""


class MarkdownStructureInvalidError(ValueError):
    """The Markdown source does not satisfy the novel import hierarchy."""
