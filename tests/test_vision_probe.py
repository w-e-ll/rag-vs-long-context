import json

import httpx

from rag_lab.core.models import EvidenceBlock
from rag_lab.ingestion import vision_probe
from rag_lab.ingestion.vision import performance_summary


def test_performance_metadata_excludes_content_and_invalid_numbers():
    result = performance_summary(
        {
            "response": "PRIVATE TEXT",
            "context": [123],
            "load_duration": 2e9,
            "prompt_eval_duration": -1,
            "eval_duration": 4e9,
            "eval_count": 20,
            "total_duration": float("nan"),
            "prompt_eval_count": True,
        }
    )
    assert result == {
        "load_seconds": 2,
        "eval_seconds": 4,
        "eval_count": 20,
        "output_tokens_per_second": 5,
    }


def test_synthetic_probe_prints_metadata_only(monkeypatch, capsys):
    monkeypatch.setenv("PDF_VISION_MODEL", "local-model")

    def analyze(image, model, *, diagnostics):
        assert image.size == (640, 240)
        diagnostics({"load_seconds": 2})
        return (
            [
                EvidenceBlock(
                    kind="visual_description",
                    source="local_vision",
                    text="INPUT OUTPUT PRIVATE RESPONSE",
                )
            ],
            [],
            10,
            5,
        )

    monkeypatch.setattr(vision_probe, "analyze", analyze)
    assert vision_probe.main() == 0
    output = capsys.readouterr().out
    assert "PRIVATE" not in output
    report = json.loads(output.splitlines()[-1])
    assert report["fixture_labels_present"] is True
    assert report["load_seconds"] == 2


def test_probe_timeout_has_no_exception_details(monkeypatch, capsys):
    monkeypatch.setenv("PDF_VISION_MODEL", "local-model")

    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("PRIVATE URL")

    monkeypatch.setattr(vision_probe, "analyze", timeout)
    assert vision_probe.main() == 1
    output = capsys.readouterr().out
    assert "PRIVATE" not in output
    assert json.loads(output.splitlines()[-1])["status"] == "request_timeout"


def test_probe_reports_safe_model_output_codes(monkeypatch, capsys):
    monkeypatch.setenv("PDF_VISION_MODEL", "local-model")

    def invalid(*args, **kwargs):
        raise vision_probe.VisionOutputError("invalid_schema")

    monkeypatch.setattr(vision_probe, "analyze", invalid)
    assert vision_probe.main() == 1
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["status"] == "invalid_schema"
