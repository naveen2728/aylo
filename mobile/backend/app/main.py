"""Stateless, internal-test relay for Ayloo Android command audio."""
from __future__ import annotations

import io
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

LOG = logging.getLogger("ayloo.mobile")
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_DURATION_MS = 30_000
MAX_TEXT_CHARS = 20_000
MAX_REQUESTS_PER_MINUTE = 12
ALLOWED_AUDIO_TYPES = {"audio/mp4", "audio/m4a", "audio/mpeg", "audio/wav", "audio/x-wav", "application/octet-stream"}
ANSWER_ONLY_PROMPT = (
    "Create a polished, complete answer that the user can paste immediately. Return only the requested content; "
    "never discuss how you produced it, repeat the request, or add a preamble, closing note, quotation marks, "
    "or follow-up question. Match the structure to the task: use concise paragraphs for prose, ordinary numbered "
    "lists for steps or multiple requirements, and short plain-text section titles only when they materially improve "
    "readability. Put a blank line between distinct sections. Keep important details from the request, remove repetition, "
    "and make wording natural and specific. If the user asks for a prompt, return a refined ready-to-use prompt. "
    "Use plain text only: no Markdown, asterisks, backticks, heading markers, tables, or other formatting syntax."
)
TEXT_ACTION_INSTRUCTIONS = {
    "improve": "Improve clarity, flow, and wording while preserving the meaning and approximate length.",
    "grammar": "Fix grammar, spelling, punctuation, and capitalization without changing the meaning or tone.",
    "shorten": "Make the text substantially shorter while preserving every essential point.",
    "summarize": "Summarize the essential information clearly and concisely.",
    "professional": "Rewrite the text in a polished, professional, natural tone.",
    "reply": "Write a useful, natural reply to the supplied message. Return only the reply.",
}


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    tester_tokens: frozenset[str]
    transcription_model: str = "whisper-large-v3-turbo"
    command_model: str = "openai/gpt-oss-20b"

    @classmethod
    def from_environment(cls) -> "Settings":
        key = os.getenv("GROQ_API_KEY", "").strip()
        tokens = frozenset(value.strip() for value in os.getenv("AYLOO_TESTER_TOKENS", "").split(",") if value.strip())
        if not key or not tokens:
            raise RuntimeError("GROQ_API_KEY and AYLOO_TESTER_TOKENS must be configured.")
        return cls(key, tokens, os.getenv("AYLOO_TRANSCRIPTION_MODEL", "whisper-large-v3-turbo"), os.getenv("AYLOO_COMMAND_MODEL", "openai/gpt-oss-20b"))


class RateLimiter:
    def __init__(self, limit: int = MAX_REQUESTS_PER_MINUTE):
        self.limit = limit
        self.calls: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, subject: str) -> bool:
        now = time.monotonic()
        calls = self.calls[subject]
        while calls and now - calls[0] >= 60:
            calls.popleft()
        if len(calls) >= self.limit:
            return False
        calls.append(now)
        return True


def clean_output(text: str) -> str:
    result = (text or "").strip()
    if result.startswith("```") and result.endswith("```"):
        result = "\n".join(result.splitlines()[1:-1]).strip()
    # Android input fields receive plain text, so Markdown markers otherwise
    # appear as visible punctuation (for example, *Hero section* in WhatsApp).
    result = result.replace("*", "").replace("`", "").replace("__", "")
    lines = [line.lstrip("# ") if line.lstrip().startswith("#") else line for line in result.splitlines()]
    return "\n".join(lines).strip('"').strip()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def authorize(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    request: Request = None,
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Internal tester authorization is required.")
    token = authorization.removeprefix("Bearer ").strip()
    if token not in settings.tester_tokens:
        raise HTTPException(403, "This build is not authorized for the Ayloo prototype.")
    if not request.app.state.limiter.allow(token):
        raise HTTPException(429, "Command limit reached. Please wait a minute and retry.")
    return token


def create_app(settings: Settings | None = None, groq_client=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings or Settings.from_environment()
        if groq_client is None:
            from groq import Groq
            app.state.groq = Groq(api_key=app.state.settings.groq_api_key)
        else:
            app.state.groq = groq_client
        app.state.limiter = RateLimiter()
        yield

    app = FastAPI(title="Ayloo Mobile Relay", docs_url=None, redoc_url=None, lifespan=lifespan)
    origins = [origin for origin in os.getenv("AYLOO_ALLOWED_ORIGINS", "").split(",") if origin]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["POST", "GET"], allow_headers=["Authorization", "Content-Type"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/v1/commands")
    async def command(
        audio: UploadFile = File(...),
        duration_ms: int = Form(...),
        mode: Literal["dictate", "command"] = Form(...),
        _tester: str = Depends(authorize),
    ):
        if not 250 <= duration_ms <= MAX_AUDIO_DURATION_MS:
            raise HTTPException(422, "Audio must be between 0.25 and 30 seconds.")
        if audio.content_type not in ALLOWED_AUDIO_TYPES:
            raise HTTPException(415, "Upload an M4A, MP3, or WAV recording.")
        payload = await audio.read(MAX_AUDIO_BYTES + 1)
        if not payload or len(payload) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Audio must be between 1 byte and 10 MB.")
        try:
            transcript_response = app.state.groq.audio.transcriptions.create(
                file=(audio.filename or "command.m4a", io.BytesIO(payload)),
                model=app.state.settings.transcription_model,
                response_format="json",
                language="en",
            )
            transcript = (getattr(transcript_response, "text", "") or "").strip()
            if not transcript:
                raise HTTPException(422, "No speech was recognized. Please speak for a little longer.")
            if mode == "dictate":
                LOG.info("dictation completed", extra={"audio_bytes": len(payload), "duration_ms": duration_ms})
                return {"transcript": transcript, "result": transcript}
            completion = app.state.groq.chat.completions.create(
                model=app.state.settings.command_model,
                max_tokens=1024,
                messages=[{"role": "system", "content": ANSWER_ONLY_PROMPT}, {"role": "user", "content": transcript}],
            )
            result = clean_output(completion.choices[0].message.content)
            if not result:
                raise HTTPException(502, "The AI did not return a usable response. Please retry.")
            LOG.info("command completed", extra={"audio_bytes": len(payload), "duration_ms": duration_ms})
            return {"transcript": transcript, "result": result}
        except HTTPException:
            raise
        except Exception as exc:
            # Provider exception strings can contain request metadata; log only the class.
            LOG.error("Groq command failed", extra={"error_type": type(exc).__name__})
            raise HTTPException(502, "The AI service is temporarily unavailable. Your recording can be retried.") from exc

    @app.post("/v1/text-actions")
    async def text_action(
        text: str = Form(...),
        action: Literal["improve", "grammar", "shorten", "summarize", "professional", "reply"] = Form(...),
        _tester: str = Depends(authorize),
    ):
        source = text.strip()
        if not source:
            raise HTTPException(422, "Select some text first.")
        if len(source) > MAX_TEXT_CHARS:
            raise HTTPException(413, "Selected text must be 20,000 characters or fewer.")
        try:
            completion = app.state.groq.chat.completions.create(
                model=app.state.settings.command_model,
                max_tokens=2048,
                messages=[
                    {"role": "system", "content": ANSWER_ONLY_PROMPT},
                    {
                        "role": "user",
                        "content": f"{TEXT_ACTION_INSTRUCTIONS[action]}\n\nText to transform:\n{source}",
                    },
                ],
            )
            result = clean_output(completion.choices[0].message.content)
            if not result:
                raise HTTPException(502, "The AI did not return usable text. Please retry.")
            # Deliberately log only metadata. Selected text and generated output are never logged.
            LOG.info("text action completed", extra={"action": action, "input_chars": len(source)})
            return {"result": result}
        except HTTPException:
            raise
        except Exception as exc:
            LOG.error("Groq text action failed", extra={"error_type": type(exc).__name__})
            raise HTTPException(502, "The AI service is temporarily unavailable. Please retry.") from exc

    return app


app = create_app()
