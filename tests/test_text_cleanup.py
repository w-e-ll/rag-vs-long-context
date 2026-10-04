from rag_lab.ingestion.layout import table_text
from rag_lab.ingestion.text_cleanup import repair_wraps


def test_wraps_require_corroboration_to_remove_hyphen():
    source = "Risks are docu-\nmented in context-\nspecific reports."
    assert repair_wraps(source, "documented") == (
        "Risks are documented in context-specific reports."
    )
    assert repair_wraps("unknown-\nfragment") == "unknown-fragment"


def test_never_guess_numeric_ids_or_acronyms():
    source = "MAP Iota: product Al policy. 12-\n34\n• unchanged"
    assert repair_wraps(source) == source


def test_normalizes_only_known_ocr_label_confusions():
    assert repair_wraps("Al Model\nMAP I: Context") == "AI Model\nMAP 1: Context"
    assert repair_wraps("Al policy\nMAP Iota") == "Al policy\nMAP Iota"


def test_table_cleanup_preserves_raw_cells_and_boundaries():
    rows = [["MAP I", "docu-\nmented"], ["Next", "documented context-\nspecific"]]
    assert table_text(rows) == "MAP I | documented\nNext | documented context-specific"
    assert rows[0][1] == "docu-\nmented"
