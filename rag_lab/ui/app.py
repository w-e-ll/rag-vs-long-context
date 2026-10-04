"""No database/provider credentials or global content cache in the UI."""

import hashlib
import os
from uuid import uuid4

import httpx
import streamlit as st

st.set_page_config(page_title="RAG cost lab", page_icon=":material/science:", layout="wide")
st.caption("SUNDAY AI BUILDS / 03")
st.title("RAG is not automatically cheaper")
st.write("One reviewed document. Two ways to supply evidence. Measure the tradeoff.")
API = os.environ.get("API_URL", "http://localhost:8003")
token = st.sidebar.text_input("Access token", type="password", help="From .demo-credentials.json")
if not token:
    st.caption("Enter a tenant-scoped token to load documents and experiments.")
    st.stop()

fingerprint = hashlib.sha256(token.encode()).hexdigest()
if st.session_state.get("identity") != fingerprint:
    # Prevent data from the previous credential remaining in the same browser session.
    st.session_state.clear()
    st.session_state["identity"] = fingerprint


def call(method, path, **kwargs):
    with httpx.Client(
        base_url=API, timeout=60, trust_env=False, headers={"Authorization": "Bearer " + token}
    ) as client:
        response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        body = response.json()
        raise ValueError(
            f"{body.get('message', 'Request failed')} (request {body.get('request_id', 'unknown')})"
        )
    return response.json()


page = st.sidebar.radio("Workspace", ["Documents", "Experiment", "Monitoring"])
st.sidebar.caption("Tenant is resolved by the API. No client-supplied tenant ID.")
try:
    if page == "Documents":
        with st.container(border=True):
            st.subheader("Upload a PDF")
            uploaded = st.file_uploader("Document", type=["pdf"], max_upload_size=20)
            st.caption(
                "API upload streams encrypted frames. This Streamlit widget buffers up to 20 MB."
            )
            if uploaded and st.button("Upload and queue extraction", type="primary"):
                key = st.session_state.setdefault("upload_key", str(uuid4()))
                uploaded.seek(0)
                result = call(
                    "POST",
                    "/api/v1/documents",
                    content=uploaded,
                    headers={"Content-Type": "application/pdf", "Idempotency-Key": key},
                )
                st.session_state.pop("upload_key", None)
                st.success(f"Document {result['id']} - {result['status']}")
        documents = call("GET", "/api/v1/documents")
        if documents:
            selected = st.selectbox(
                "Document to inspect", documents, format_func=lambda d: f"{d['id']} / {d['status']}"
            )
            doc = call("GET", f"/api/v1/documents/{selected['id']}")
            st.write("Status:", doc["status"])
            st.button("Refresh document status")
            if doc.get("error_code"):
                st.error(doc["error_code"])
            if doc.get("parsed"):
                pages = doc["parsed"]["pages"]
                st.subheader("Inspect and correct extracted evidence")
                st.caption(f"Extraction version: {doc['parsed'].get('parser_version', 'pdf-v1')}")
                if doc["parsed"].get("parser_version") != "pdf-v5":
                    st.warning(
                        "This uses the old parser. Upload the PDF again to extract a new version."
                    )
                st.caption(
                    "Compare with the original PDF. Tables retain cells and image text is OCR'd "
                    "separately. Local vision descriptions are model-generated and need checking. "
                    "The reviewed text below is the evidence used by both experiment modes."
                )
                with st.form("review_" + doc["id"]):
                    for p in pages:
                        with st.expander(f"Page {p['number']} / {p['method']}"):
                            for warning in p["warnings"]:
                                st.warning(warning)
                            vision_label = p.get("vision_status", "disabled")
                            if vision_label == "completed":
                                vision_label = "response received — unverified"
                            st.caption(
                                "Vision: "
                                f"{vision_label} | "
                                f"Extraction: {p.get('extraction_ms', 0) / 1000:.1f}s | "
                                f"Vision: {p.get('vision_ms', 0) / 1000:.1f}s"
                            )
                            if p.get("ocr_confidence") is not None:
                                st.caption(
                                    f"Mean OCR word confidence: {p['ocr_confidence']:.1f}/100"
                                )
                            if p.get("vision_model"):
                                usage = (
                                    "model-reported tokens: "
                                    f"{p.get('vision_input_tokens', 0)} input / "
                                    f"{p.get('vision_output_tokens', 0)} output"
                                    if p.get("vision_status") == "completed"
                                    else "token usage unavailable; vision incomplete or not invoked"
                                )
                                st.caption(
                                    f"Local model: {p['vision_model']} | {usage}. "
                                    "Shared preprocessing; excluded from generation cost estimates."
                                )
                            for block in p.get("blocks", []):
                                if block["source"] == "local_vision":
                                    st.caption(
                                        "Unverified model suggestion. Check against the PDF "
                                        "before copying into reviewed text."
                                    )
                                st.caption(f"Extracted {block['kind']} / {block['source']}")
                                if block.get("rows"):
                                    st.dataframe(block["rows"], hide_index=True)
                                else:
                                    st.text(block["text"])
                            if p.get("blocks"):
                                st.caption(
                                    "Blocks above show original extraction. Correct the reviewed "
                                    "text below, including conflicting versions."
                                )
                            p["text"] = st.text_area(
                                "Reviewed page text",
                                p["text"],
                                height=220,
                                key=f"text_{doc['id']}_{p['number']}",
                            )
                            p["method"] = "manual"
                    strategy = st.selectbox("Chunking strategy", ["recursive", "parent_child"])
                    size = st.slider("Child chunk tokens", 100, 1000, 450, 50)
                    overlap = st.slider("Overlap tokens", 0, min(200, size - 1), min(60, size - 1))
                    parent_size = st.slider(
                        "Parent maximum tokens", max(500, size), 2400, 1400, 100
                    )
                    reviewed = st.checkbox(
                        "I checked the extracted text, tables and visual descriptions"
                    )
                    submitted = st.form_submit_button("Approve and build index")
                if submitted:
                    if not reviewed:
                        st.error("Review is required before indexing.")
                    else:
                        result = call(
                            "POST",
                            f"/api/v1/documents/{doc['id']}/review",
                            json={
                                "parsed": doc["parsed"],
                                "settings": {
                                    "strategy": strategy,
                                    "size": size,
                                    "overlap": overlap,
                                    "parent_size": parent_size,
                                },
                            },
                        )
                        st.success(f"Index task {result['id']} queued")
            with st.expander("Delete this document and its derived data"):
                confirmed = st.checkbox("Delete this document, chunks, jobs and saved answers")
                if st.button("Delete document", disabled=not confirmed):
                    call("DELETE", f"/api/v1/documents/{doc['id']}")
                    st.rerun()
    elif page == "Experiment":
        docs = [d for d in call("GET", "/api/v1/documents") if d["status"] == "ready"]
        if not docs:
            st.info("Upload, review and index a document first.")
        else:
            with st.form("experiment"):
                doc = st.selectbox("Indexed document", docs, format_func=lambda d: d["id"])
                question = st.text_area(
                    "Question", "What are the four core functions of the framework?"
                )
                expected = st.text_area("Expected facts, one per line (optional)", "")
                top_k = st.slider("Retrieved child chunks", 1, 12, 4)
                budget = st.slider("Maximum retrieved context tokens", 500, 12000, 4000, 500)
                projected = st.number_input(
                    "Questions sharing this index (projection)", 1, 1000000, 100
                )
                st.caption(
                    "Illustrative USD per million tokens. Set your own scenario; "
                    "these are not current quotes."
                )
                input_price = st.number_input("Input rate", min_value=0.0, value=0.40)
                output_price = st.number_input("Output rate", min_value=0.0, value=1.60)
                embed_price = st.number_input("Embedding rate", min_value=0.0, value=0.02)
                submitted = st.form_submit_button("Run paired experiment", type="primary")
            if submitted:
                run_id = st.session_state.setdefault("pending_run_id", str(uuid4()))
                result = call(
                    "POST",
                    f"/api/v1/documents/{doc['id']}/compare",
                    json={
                        "run_id": run_id,
                        "question": question,
                        "expected_facts": [f for f in expected.splitlines() if f.strip()],
                        "top_k": top_k,
                        "context_budget": budget,
                        "projected_questions": projected,
                        "prices": {
                            "input_per_million": str(input_price),
                            "output_per_million": str(output_price),
                            "embedding_per_million": str(embed_price),
                        },
                    },
                )
                st.session_state["run_id"] = result["id"]
                st.session_state.pop("pending_run_id", None)
            history = [j for j in call("GET", "/api/v1/jobs") if j["kind"] == "compare"]
            if history:
                choice = st.selectbox(
                    "Experiment history",
                    history,
                    format_func=lambda j: f"{j['id']} / {j['status']}",
                )
                st.button("Refresh experiment")
                if choice["status"] == "completed":
                    result = call("GET", f"/api/v1/runs/{choice['id']}")
                    st.caption(f"Provider: {result['provider']} / model: {result['llm_model']}")
                    with st.container(horizontal=True):
                        st.metric(
                            "First-question savings (estimate)",
                            f"${float(result['first_question_savings']):.6f}",
                            border=True,
                        )
                        st.metric(
                            "Projected savings (estimate)",
                            f"${float(result['projected_savings']):.6f}",
                            border=True,
                        )
                        st.metric(
                            "Questions until RAG is cheaper",
                            result["break_even_questions"] or "Never at these rates",
                            border=True,
                        )
                    st.dataframe(
                        [
                            {
                                "Mode": mode,
                                "Input tokens": result[mode]["usage"]["input_tokens"],
                                "Output tokens": result[mode]["usage"]["output_tokens"],
                                "Usage source": result[mode]["usage"]["source"],
                                "Generation ms": round(result[mode]["latency_ms"], 1),
                                "Fact coverage (heuristic)": result[mode]["fact_coverage"],
                                "Generation cost estimate USD": result[mode]["estimated_cost"],
                            }
                            for mode in ["long_context", "rag"]
                        ],
                        hide_index=True,
                    )
                    for col, mode in zip(st.columns(2), ["long_context", "rag"]):
                        with col:
                            st.subheader(mode.replace("_", " ").capitalize())
                            st.text(result[mode]["text"])
                            if result[mode].get("citation_check") == "quote_match_only":
                                st.caption(
                                    "Quotes matched supplied sources. Claim meaning and "
                                    "completeness still require review."
                                )
                            if result[mode].get("evidence_derivation") == "source_excerpt":
                                st.caption(
                                    "Source excerpt was selected by the application because "
                                    "the model did not return a quote."
                                )
                            claims = result[mode].get("evidence_claims", [])
                            if claims:
                                with st.expander("Supporting quotes"):
                                    for claim in claims:
                                        page = (
                                            result[mode]
                                            .get("citation_sources", {})
                                            .get(claim["source"])
                                        )
                                        location = (
                                            f"PDF page {page}"
                                            if page is not None
                                            else "source not supplied"
                                        )
                                        quote = claim["quote"] or "(No supporting quote supplied)"
                                        st.text(f"[{claim['source']}] ({location}) {quote}")
                            if result[mode].get("raw_model_output") is not None:
                                with st.expander("Original model response (JSON)"):
                                    st.text(result[mode]["raw_model_output"])
                            for warning in result[mode].get("citation_warnings", []):
                                st.warning(warning)
                            if result[mode].get("citation_check") == "abstention_unverified":
                                st.info(
                                    "Model reported insufficient evidence. No citation required; "
                                    "whether the refusal is justified still needs review."
                                )
                            elif result[mode].get("citation_check") == "source_membership_only":
                                st.caption(
                                    "Source identifiers checked; factual support is not verified."
                                )
                                sources = result[mode].get("citation_sources", {})
                                st.caption(
                                    "Available sources: "
                                    + "; ".join(
                                        f"[{key}] = PDF page {page}"
                                        for key, page in sources.items()
                                    )
                                )
                            if result[mode].get("citation_check") == "page_membership_only":
                                st.caption(
                                    "Citation check verifies supplied page numbers only; "
                                    "claim accuracy still requires review."
                                )
                    st.caption(
                        f"RAG retrieval + embedding: {result['retrieval_ms']:.1f} ms; "
                        f"RAG end-to-end: {result['rag_end_to_end_ms']:.1f} ms"
                    )
                    st.write("Evidence pages:", result["retrieved_pages"])
                    for note in result["limitations"]:
                        st.caption(note)
                    st.download_button(
                        "Download experiment JSON",
                        data=__import__("json").dumps(result, indent=2),
                        file_name="experiment.json",
                        mime="application/json",
                    )
                elif choice.get("error_code"):
                    st.error(choice["error_code"])
    else:
        st.subheader("Tenant operation history")
        st.button("Refresh monitoring")
        jobs = call("GET", "/api/v1/jobs")
        total = len(jobs)
        failures = sum(j["status"] in {"failed", "dead"} for j in jobs)
        with st.container(horizontal=True):
            st.metric("Jobs in view", total, border=True)
            st.metric("Failed / dead", failures, border=True)
            st.metric(
                "Failure rate in view",
                f"{100 * failures / total:.1f}%" if total else "N/A",
                border=True,
            )
        st.caption("Window: latest 100 jobs for your tenant, including queued/running jobs.")
        st.dataframe(jobs, hide_index=True)
        st.link_button("Open Grafana operations dashboard", "http://localhost:3003")
        st.caption("Grafana is an operator-only, cross-tenant aggregate view. No document content.")
except (httpx.HTTPError, ValueError) as exc:
    st.error(
        str(exc)
        if isinstance(exc, ValueError)
        else "API unavailable. Check service health and retry."
    )
