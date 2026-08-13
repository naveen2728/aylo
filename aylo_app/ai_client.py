import base64
import io
import re


MODEL = "llama-3.1-8b-instant"
CHAT_MODEL = "llama-3.3-70b-versatile"
# Groq retired the Llama 4 vision models in July 2026.  Qwen 3.6 is the
# current Groq model that accepts both screenshots and text.
VISION_MODEL = "qwen/qwen3.6-27b"
VISION_MODEL_FALLBACKS = (VISION_MODEL,)
MAX_VISION_IMAGE_BYTES = 3_500_000
ASSISTANT_PREAMBLES = (
    "sure",
    "sure thing",
    "certainly",
    "of course",
    "absolutely",
    "i can help with that",
    "i'd be happy to help",
    "here is the requested output",
    "here's the requested output",
    "here is the result",
    "here's the result",
    "here is the rewritten text",
    "here's the rewritten text",
    "here is the updated code",
    "here's the updated code",
)
ANSWER_ONLY_SYSTEM_PROMPT = (
    "Return only the final content the user can directly paste. "
    "Never add acknowledgements, offers to help, explanations, commentary, labels, preambles, "
    "follow-up questions, markdown fences, or surrounding quotes. "
    "Do not say phrases such as 'Sure', 'I can help with that', or 'Here is'. "
    "If the user asks for a message, return only the message. "
    "If the user asks for code, return only the code. "
    "If the user asks for a rewrite or translation, return only the rewritten or translated content."
)
CHAT_SYSTEM_PROMPT = (
    "You are Aylo AI, a concise desktop assistant. Start with the direct answer. "
    "Use one or two short paragraphs by default. Use a list only when it improves clarity, "
    "and prefix each list item with a plain hyphen and space. "
    "Do not use Markdown headings, bold markers, filler introductions, or repeat the user's request. "
    "Keep the tone and formatting consistent across replies. "
    "Ask a follow-up question only when required information is truly missing."
)


class GenerationError(RuntimeError):
    pass


def clean_generated_output(text):
    result = text.strip()
    if result.startswith("```"):
        lines = result.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            result = "\n".join(lines[1:-1]).strip()
    lines = result.splitlines()
    while len(lines) > 1 and _is_assistant_preamble(lines[0]):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    result = "\n".join(lines).strip()
    if len(result) >= 2 and result[0] == result[-1] == '"' and "\n" not in result:
        result = result[1:-1].strip()
    return result


def clean_chat_output(text):
    result = clean_generated_output(strip_reasoning_output(text))
    lines = []
    for line in result.splitlines():
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith(("* ", "- ", "+ ")):
            lines.append(f"{indent}• {stripped[2:]}")
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def strip_reasoning_output(text):
    """Remove reasoning-model scratch work before anything reaches the UI."""
    result = text or ""
    result = re.sub(r"<think>.*?</think>\s*", "", result, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r"<analysis>.*?</analysis>\s*", "", result, flags=re.IGNORECASE | re.DOTALL)
    # Never expose an incomplete raw reasoning block if a provider truncates it.
    open_tags = [position for tag in ("<think>", "<analysis>") if (position := result.lower().find(tag)) >= 0]
    if open_tags:
        result = result[: min(open_tags)]
    return result.strip()


def _is_assistant_preamble(line):
    normalized = line.strip().lower().rstrip(".!:")
    return normalized in ASSISTANT_PREAMBLES


def friendly_generation_error(exc):
    message = str(exc).lower()
    status_code = getattr(exc, "status_code", None)
    if status_code in (401, 403) or "invalid api key" in message or "authentication" in message:
        return "Groq API key is invalid. Update it from the context menu."
    if status_code == 413 or "request too large" in message or "requested" in message and "tokens" in message:
        return "The AI request is too large. Copy less text and try again."
    if status_code == 429 or "rate limit" in message or "rate_limit" in message:
        return "Groq limit reached. Try again shortly."
    if status_code == 404 or "model_not_found" in message or "model" in message and "not found" in message:
        return "The selected Groq model is unavailable for this API key. Check Groq model permissions or try another key."
    if "connection" in message or "timed out" in message or "timeout" in message:
        return "Could not connect to Groq. Check your internet connection."
    return "AI request failed. Try again."


def connect(api_key=None):
    from groq import Groq

    client = Groq(api_key=api_key) if api_key else Groq()
    client.chat.completions.create(
        model=MODEL,
        max_tokens=1,
        messages=[{"role": "user", "content": "hi"}],
    )
    return client


def cleanup(client, text, prompt, log_error):
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "system",
                    "content": "Fix errors as instructed. NEVER rewrite or change meaning. Return ONLY corrected text.",
                },
                {"role": "user", "content": f"{prompt}\n\nText: {text}"},
            ],
        )
        result = response.choices[0].message.content.strip()
        return result if len(result) <= len(text) * 1.5 else text
    except Exception as exc:
        log_error("Cleanup failed", exc)
        return text


def generate(client, prompt, log_error):
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=2048,
            messages=[
                {
                    "role": "system",
                    "content": ANSWER_ONLY_SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
        )
        return clean_generated_output(response.choices[0].message.content)
    except Exception as exc:
        log_error("Generation failed", exc)
        raise GenerationError(friendly_generation_error(exc)) from exc


def chat(client, messages, log_error):
    try:
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            max_tokens=2048,
            messages=[{"role": "system", "content": CHAT_SYSTEM_PROMPT}] + messages,
        )
        return clean_chat_output(response.choices[0].message.content)
    except Exception as exc:
        log_error("Chat failed", exc)
        raise GenerationError(friendly_generation_error(exc)) from exc


def _image_data_url(path):
    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGB")
        max_side = 1600
        if max(image.size) > max_side:
            image.thumbnail((max_side, max_side))

        quality = 85
        while quality >= 45:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality, optimize=True)
            data = buffer.getvalue()
            if len(data) <= MAX_VISION_IMAGE_BYTES:
                encoded = base64.b64encode(data).decode("ascii")
                return f"data:image/jpeg;base64,{encoded}"
            quality -= 10

    raise GenerationError("Screenshot is too large to send. Try capturing a smaller screen area later.")


def read_screen(client, question, screenshot_path, log_error):
    try:
        image_url = _image_data_url(screenshot_path)
        prompt = (
            f"{question}\n\n"
            "Answer the user's question using only what is visibly supported by the screenshot. "
            "Return only the final answer—never show analysis, reasoning, <think> tags, or drafting notes. "
            "Do not speculate about hidden context or narrate how you inspected the image. "
            "If it shows an error or app UI, briefly explain what is happening and the most useful next step. "
            "Keep the answer concise: one short paragraph or at most four simple bullet points."
        )
        last_error = None
        for model in VISION_MODEL_FALLBACKS:
            try:
                response = client.chat.completions.create(
                    model=model,
                    max_completion_tokens=700,
                    reasoning_format="hidden",
                    reasoning_effort="none",
                    temperature=0.3,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ],
                        }
                    ],
                )
                break
            except Exception as exc:
                last_error = exc
                message = str(exc).lower()
                status_code = getattr(exc, "status_code", None)
                if status_code != 404 and "model_not_found" not in message and "model" not in message:
                    raise
                log_error(f"Screen vision model unavailable: {model}", exc)
        else:
            raise last_error
        result = clean_chat_output(response.choices[0].message.content)
        if not result:
            raise GenerationError("The screen reader did not return a final answer. Please try again.")
        return result
    except GenerationError:
        raise
    except Exception as exc:
        log_error("Screen vision failed", exc)
        raise GenerationError(friendly_generation_error(exc)) from exc
