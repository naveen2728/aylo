class SpeechError(RuntimeError):
    pass


def speak_text(text):
    message = (text or "").strip()
    if not message:
        return
    try:
        try:
            import pythoncom

            pythoncom.CoInitialize()
        except Exception:
            pass

        import win32com.client

        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Speak(message)
    except Exception as exc:
        raise SpeechError("Could not speak the AI response.") from exc
