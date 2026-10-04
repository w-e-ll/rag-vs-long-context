from rag_lab.core.citations import ABSTENTION, citation_warnings, is_abstention, source_text


def test_printed_folio_distinguished_without_rewriting_prose():
    assert source_text("Evidence\nPage 20\nSee Page 12 for details.") == (
        "Evidence\n\nSee Page 12 for details."
    )


def test_valid_membership_is_not_semantic_validation():
    assert citation_warnings("Unverified claim [S006]", {1, 2, 4, 6}) == []


def test_observed_hallucinated_page_is_flagged():
    warnings = citation_warnings("GOVERN (Source Page 3), MAP (Source Page 6)", {1, 2, 4, 6})
    assert any("outside supplied evidence: 3" in w for w in warnings)
    assert any("required" in w for w in warnings)


def test_missing_and_out_of_range_canonical_citations():
    assert citation_warnings("GOVERN, MAP, MEASURE, MANAGE", {6})
    assert any("outside" in w for w in citation_warnings("Claim [PDF page 20]", {6}))


def test_printed_number_cannot_be_used_as_source_identifier():
    assert citation_warnings("Risk tolerances [S009]", {9}) == []
    assert any("Unknown" in w for w in citation_warnings("Risk tolerances [S026]", {9}))
    assert any("Unknown" in w for w in citation_warnings("Risk tolerances [S9]", {9}))


def test_only_whole_answer_abstention_is_exempt():
    assert is_abstention(ABSTENTION)
    assert citation_warnings(ABSTENTION, {9}) == []
    assert not is_abstention(ABSTENTION + " The price is $20.")
    assert citation_warnings(ABSTENTION + " The price is $20.", {9})
    assert citation_warnings(ABSTENTION + " [S026]", {9})


def test_compound_citation_checks_source_without_endorsing_region():
    warnings = citation_warnings("MANAGE [S006, Figure region 3]", {6})
    assert any("Compound citations" in w for w in warnings)
    assert not any("No citation" in w for w in warnings)
    assert not any("Unknown" in w for w in warnings)
    assert any("Unknown" in w for w in citation_warnings("MAP [S026, Figure 5]", {6}))


def test_valid_citation_does_not_hide_extra_unverified_locations():
    assert citation_warnings("MANAGE [S006], Figure region 3", {6})
    assert any("outside" in w for w in citation_warnings("Source [S006], page [26]", {6}))
    assert citation_warnings("GOVERN [S006]; MANAGE [S006, Figure region 3]", {6})
