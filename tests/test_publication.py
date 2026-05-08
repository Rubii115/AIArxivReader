from arxiv_reader.publication import publication_query


def test_publication_query_prefers_arxiv_id():
    assert publication_query("arXiv:2401.01234 Foo") == "id:2401.01234"


def test_publication_query_extracts_bibtex_title_author_and_doi():
    query = publication_query(
        """
        @inproceedings{demo,
          title={A Useful Paper About Retrieval},
          author={Ada Lovelace and Alan Turing},
          doi={10.1145/1234567.8901234}
        }
        """
    )
    assert 'ti:"A Useful Paper About Retrieval"' in query
    assert 'all:"10.1145/1234567.8901234"' in query
    assert 'au:"Ada Lovelace"' in query


def test_publication_query_splits_plain_title_author_citation():
    query = publication_query("Ultraviolet Completion of the Big Bang in Quadratic Gravity, Ruolin Liu")

    assert 'all:"Ultraviolet Completion of the Big Bang in Quadratic Gravity"' in query
    assert 'au:"Ruolin Liu"' not in query
    assert "Quadratic Gravity, Ruolin Liu" not in query
