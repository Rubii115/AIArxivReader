from arxiv_reader.tex import clean_tex


def test_clean_tex_keeps_section_text_and_removes_comments():
    cleaned = clean_tex(
        r"""
        \section{Method}
        We propose a thing. % this is a comment
        See \cite{demo}.
        """
    )
    assert "## Method" in cleaned
    assert "We propose a thing." in cleaned
    assert "comment" not in cleaned
    assert "cite" not in cleaned
