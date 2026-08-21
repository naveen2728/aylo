from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import Settings, create_app


class FakeTranscriptions:
    def __init__(self, text="write a friendly follow-up"):
        self.text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)


class FakeCompletions:
    def __init__(self, text="Just checking in — please let me know your thoughts."):
        self.text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.text))])


class FakeGroq:
    def __init__(self, transcript="write a friendly follow-up", result="Just checking in — please let me know your thoughts."):
        self.audio = SimpleNamespace(transcriptions=FakeTranscriptions(transcript))
        self.chat = SimpleNamespace(completions=FakeCompletions(result))


def client(fake=None, tokens=frozenset({"test-token"})):
    return TestClient(create_app(Settings("test-key", tokens), fake or FakeGroq()))


def post_command(test_client, token="test-token", data=b"m4a-bytes"):
    return test_client.post(
        "/v1/commands",
        headers={"Authorization": f"Bearer {token}"},
        files={"audio": ("command.m4a", data, "audio/mp4")},
        data={"duration_ms": "1000", "mode": "command"},
    )


def test_health_is_available():
    with client() as test_client:
        assert test_client.get("/health").json() == {"status": "ok"}


def test_command_transcribes_and_generates_paste_ready_response():
    fake = FakeGroq(result="```\nHello there\n```")
    with client(fake) as test_client:
        response = post_command(test_client)
    assert response.status_code == 200
    assert response.json() == {"transcript": "write a friendly follow-up", "result": "Hello there"}
    assert fake.audio.transcriptions.calls[0]["model"] == "whisper-large-v3-turbo"
    assert fake.chat.completions.calls[0]["messages"][1]["content"] == "write a friendly follow-up"


def test_dictate_returns_exact_transcript_without_calling_generation():
    fake = FakeGroq(transcript="This is exactly what I said.")
    with client(fake) as test_client:
        response = test_client.post(
            "/v1/commands", headers={"Authorization": "Bearer test-token"},
            files={"audio": ("dictation.m4a", b"m4a-bytes", "audio/mp4")},
            data={"duration_ms": "1000", "mode": "dictate"},
        )
    assert response.status_code == 200
    assert response.json() == {"transcript": "This is exactly what I said.", "result": "This is exactly what I said."}
    assert fake.chat.completions.calls == []


def test_command_rejects_missing_or_invalid_credentials():
    with client() as test_client:
        assert test_client.post("/v1/commands", files={"audio": ("x.m4a", b"a", "audio/mp4")}, data={"duration_ms": "1000", "mode": "command"}).status_code == 401
        assert post_command(test_client, "wrong-token").status_code == 403


def test_command_rejects_invalid_type_and_excessive_upload():
    with client() as test_client:
        bad_type = test_client.post(
            "/v1/commands", headers={"Authorization": "Bearer test-token"}, files={"audio": ("x.txt", b"hello", "text/plain")}
            , data={"duration_ms": "1000", "mode": "command"}
        )
        assert bad_type.status_code == 415
        assert post_command(test_client, data=b"x" * (10 * 1024 * 1024 + 1)).status_code == 413
        too_long = test_client.post(
            "/v1/commands", headers={"Authorization": "Bearer test-token"},
            files={"audio": ("x.m4a", b"x", "audio/mp4")}, data={"duration_ms": "30001", "mode": "command"},
        )
        assert too_long.status_code == 422


def test_command_returns_safe_error_when_provider_fails():
    fake = FakeGroq()
    fake.audio.transcriptions.create = lambda **_: (_ for _ in ()).throw(RuntimeError("provider detail"))
    with client(fake) as test_client:
        response = post_command(test_client)
    assert response.status_code == 502
    assert "provider detail" not in response.json()["detail"]


def test_rate_limit_blocks_thirteenth_command():
    with client() as test_client:
        for _ in range(12):
            assert post_command(test_client).status_code == 200
        assert post_command(test_client).status_code == 429
