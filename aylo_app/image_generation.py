import os
import re
import time
import urllib.parse
import urllib.request

from .config import appdata_dir, load_image_api_key


IMAGE_REQUEST_RE = re.compile(
    r"\b(generate|create|make|draw)\b.*\b(image|picture|photo|poster|wallpaper|art|logo)\b"
    r"|\b(image|picture|photo|poster|wallpaper|art|logo)\b.*\b(of|for)\b",
    re.IGNORECASE,
)


class ImageGenerationError(RuntimeError):
    pass


def is_image_generation_request(text):
    return bool(IMAGE_REQUEST_RE.search(text or ""))


def image_prompt_from_request(text):
    prompt = (text or "").strip()
    prompt = re.sub(r"^\s*(please\s+)?(generate|create|make|draw)\s+(me\s+)?(an?\s+)?", "", prompt, flags=re.IGNORECASE)
    prompt = re.sub(r"^\s*(image|picture|photo)\s+(of|for)\s+", "", prompt, flags=re.IGNORECASE)
    return prompt.strip(" .") or "a clean modern illustration"


def generate_image(prompt):
    key = load_image_api_key()
    if not key:
        raise ImageGenerationError(
            "Image generation needs a Pollinations API key. Right-click the orb and choose Update Image API Key."
        )
    directory = os.path.join(appdata_dir(), "generated-images")
    os.makedirs(directory, exist_ok=True)
    filename = f"image-{int(time.time())}.jpg"
    path = os.path.join(directory, filename)
    encoded = urllib.parse.quote(prompt)
    query = urllib.parse.urlencode({"width": "1024", "height": "1024", "nologo": "true", "key": key})
    url = f"https://gen.pollinations.ai/image/{encoded}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Aylo/1.1"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
    except Exception as exc:
        raise ImageGenerationError("I could not generate the image. Check your internet connection and try again.") from exc
    if len(data) < 1024:
        raise ImageGenerationError("The image service returned an empty image. Try a more specific prompt.")
    with open(path, "wb") as handle:
        handle.write(data)
    return path
