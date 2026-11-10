"""Chat model construction and model-call robustness.

Providers (config/models.yaml `provider`):
  openai  - ChatOpenAI on Chat Completions (seed, system_fingerprint)
  vertex  - ChatGoogleGenerativeAI with vertexai=True and a service-account key per Google Cloud project.
            The project comes from the DEEPRCA_GCP_PROJECT environment variable (one project per run) and its
            key from ~/.config/deeprca/<project>.json (outside git). Confirmed against langchain-google-genai 4.4.2:
            fields vertexai, project, location, credentials, seed, temperature, thinking_config, max_output_tokens.

Gemini 3 models are run at their default temperature: at temperature 0 their tool calls often come back as
MALFORMED_FUNCTION_CALL (measured, see WORKLOG), and Google's guide advises against lowering it. Determinism is
held by the fixed seed, a fixed thinking level and schema-validated outputs instead.
"""
from __future__ import annotations

import os
from pathlib import Path

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

CRED_DIR = Path(os.path.expanduser("~/.config/deeprca"))


def current_project() -> str | None:
    return os.environ.get("DEEPRCA_GCP_PROJECT") or (os.environ.get("GCP_PROJECTS", "").split(",")[0] or None)


def make_llm(mcfg: dict):
    if mcfg.get("provider", "openai") == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=mcfg["request_id"], temperature=mcfg["temperature"], seed=mcfg["seed"],
                          max_tokens=mcfg["max_output_tokens"], use_responses_api=False, max_retries=8, timeout=180)
    import google.auth
    from langchain_google_genai import ChatGoogleGenerativeAI

    project = current_project()
    if not project:
        raise RuntimeError("set DEEPRCA_GCP_PROJECT (or GCP_PROJECTS in .env) to the Google Cloud project to bill")
    # either a service-account key or a user login file (gcloud application-default credentials) per project;
    # the project to bill is always passed explicitly
    cred, _ = google.auth.load_credentials_from_file(
        str(CRED_DIR / f"{project}.json"), scopes=["https://www.googleapis.com/auth/cloud-platform"],
        quota_project_id=project)
    kw = {}
    if mcfg.get("temperature") is not None:
        kw["temperature"] = mcfg["temperature"]
    if mcfg.get("thinking_level"):
        kw["thinking_config"] = {"thinking_level": mcfg["thinking_level"]}
    return ChatGoogleGenerativeAI(model=mcfg["request_id"], vertexai=True, project=project,
                                  location=mcfg.get("location", "global"), credentials=cred, seed=mcfg["seed"],
                                  max_output_tokens=mcfg["max_output_tokens"], max_retries=10, timeout=300, **kw)


def _malformed(resp) -> bool:
    msgs = getattr(resp, "result", None) or ([resp] if isinstance(resp, AIMessage) else [])
    for m in msgs:
        if isinstance(m, AIMessage):
            fr = str((m.response_metadata or {}).get("finish_reason", ""))
            if "MALFORMED_FUNCTION_CALL" in fr and not m.tool_calls:
                return True
    return False


class MalformedCallRetry(AgentMiddleware):
    """Re-ask the model when it returns a malformed function call (a provider-side failure, not an answer).
    Counts retries on the run state so they appear in the result."""

    def __init__(self, st=None, max_retries: int = 3):
        super().__init__()
        self.st = st
        self.max_retries = max_retries

    def _count(self):
        if self.st is not None:
            with self.st.lock:
                self.st.malformed_retries = getattr(self.st, "malformed_retries", 0) + 1

    def wrap_model_call(self, request, handler):
        resp = handler(request)
        for _ in range(self.max_retries):
            if not _malformed(resp):
                break
            self._count()
            resp = handler(request)
        return resp

    async def awrap_model_call(self, request, handler):
        resp = await handler(request)
        for _ in range(self.max_retries):
            if not _malformed(resp):
                break
            self._count()
            resp = await handler(request)
        return resp
