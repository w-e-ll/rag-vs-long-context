from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_login_gate_renders_without_network():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "rag_lab/ui/app.py").run()
    assert not app.exception
    assert "RAG is not automatically cheaper" in app.title[0].value


def test_authenticated_document_screen(monkeypatch):
    import httpx

    monkeypatch.setattr(
        httpx.Client, "request", lambda *args, **kwargs: httpx.Response(200, json=[])
    )
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "rag_lab/ui/app.py").run()
    app.text_input[0].set_value("a" * 40).run()
    assert not app.exception
    assert any(x.value == "Upload a PDF" for x in app.subheader)


def test_review_shows_table_provenance_and_vision_state(monkeypatch):
    import httpx

    document = {
        "id": "example",
        "status": "review",
        "error_code": None,
        "parsed": {
            "parser_version": "pdf-v2",
            "pages": [
                {
                    "number": 1,
                    "method": "hybrid",
                    "warnings": [],
                    "text": "Categories | Subcategories",
                    "vision_status": "failed",
                    "ocr_confidence": 81,
                    "blocks": [
                        {
                            "kind": "table",
                            "source": "pdf_geometry",
                            "rows": [["Categories", "Subcategories"], ["GOVERN", "GOVERN 1.1"]],
                        }
                    ],
                }
            ],
        },
    }
    monkeypatch.setattr(
        httpx.Client,
        "request",
        lambda self, method, path, **kwargs: httpx.Response(
            200,
            json=[{"id": "example", "status": "review"}]
            if path == "/api/v1/documents"
            else document,
        ),
    )
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "rag_lab/ui/app.py").run()
    app.text_input[0].set_value("a" * 40).run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert any("Vision: failed" in item.value for item in app.caption)
    assert any("pdf_geometry" in item.value for item in app.caption)
    app.run()
    assert not app.exception
    assert any(x.value == "Upload a PDF" for x in app.subheader)
