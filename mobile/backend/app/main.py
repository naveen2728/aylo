"""Stateless, internal-test relay for Ayloo Android command audio."""
from __future__ import annotations

import io
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

LOG = logging.getLogger("ayloo.mobile")
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_DURATION_MS = 30_000
MAX_REQUESTS_PER_MINUTE = 12
ALLOWED_AUDIO_TYPES = {"audio/mp4", "audio/m4a", "audio/mpeg", "audio/wav", "audio/x-wav", "application/octet-stream"}
ANSWER_ONLY_PROMPT = (
    "Return only the final content the user can directly paste. Never add explanations, labels, "
    "preambles, markdown fences, quotes, or follow-up questions."
)


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
    return result.strip('"').strip()


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
            completion = app.state.groq.chat.completions.create(
                model=app.state.settings.command_model,
                max_tokens=1024,
                messages=[{"role": "system", "content": ANSWER_ONLY_PROMPT}, {"role": "user", "content": transcript}],
            )
            result = clean_output(completion.choices[0].message.content)
            if not result:
                raise HTTPException(502, "The AI did not return a usable response. Please retry.")
            LOG.info("command completed", extra={"audio_bytes": len(payload)})
            return {"transcript": transcript, "result": result}
        except HTTPException:
            raise
        except Exception as exc:
            LOG.exception("Groq command failed: %s", type(exc).__name__)
            raise HTTPException(502, "The AI service is temporarily unavailable. Your recording can be retried.") from exc

    return app


app = create_app()
