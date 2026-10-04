"""One synthetic request through the real vision adapter; no customer data or credentials."""

import json
import os
import time

import httpx
from PIL import Image, ImageDraw, ImageFont

from rag_lab.ingestion.vision import VisionOutputError, analyze


def main():
    model = os.environ.get("PDF_VISION_MODEL")
    if not model:
        print(json.dumps({"status": "vision_not_configured"}), flush=True)
        return 1
    with Image.new("RGB", (640, 240), "white") as image:
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=24)
        draw.rectangle((20, 40, 260, 180), outline="black", width=3)
        draw.rectangle((380, 40, 620, 180), outline="black", width=3)
        draw.text((50, 95), "INPUT", fill="black", font=font)
        draw.text((415, 95), "OUTPUT", fill="black", font=font)
        draw.line((265, 110, 370, 110), fill="black", width=3)
        draw.polygon(((370, 110), (350, 100), (350, 120)), fill="black")
        print(
            json.dumps(
                {"status": "started", "fixture": "synthetic_two_boxes", "timeout_seconds": 240}
            ),
            flush=True,
        )
        started = time.monotonic()
        report = {}
        try:
            blocks, _, _, _ = analyze(image, model, diagnostics=report.update)
            report["status"] = "response_received_unverified"
            # Limited fixture recall only, not diagram relationship accuracy.
            words = " ".join(b.text for b in blocks).casefold()
            report["fixture_labels_present"] = all(w in words for w in ("input", "output"))
        except httpx.TimeoutException:
            report["status"] = "request_timeout"
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            report["status"] = exc.code if isinstance(exc, VisionOutputError) else "request_failed"
        report["wall_seconds"] = round(time.monotonic() - started, 3)
        print(json.dumps(report), flush=True)
        return 0 if report["status"] == "response_received_unverified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
