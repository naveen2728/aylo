import os
import webbrowser


MARKETING_URL = ""
CHECKOUT_URL = ""
SUPPORT_URL = ""


PLANS = [
    {
        "name": "Starter",
        "price": "$0",
        "cadence": "forever",
        "summary": "Local dictation for personal use.",
        "features": [
            "Offline English speech-to-text",
            "Floating dictation orb",
            "Clipboard paste workflow",
            "Basic microphone settings",
        ],
    },
    {
        "name": "Plus",
        "price": "$9",
        "cadence": "per month",
        "summary": "AI cleanup, rewrites, and voice commands for daily work.",
        "features": [
            "AI cleanup for emails, docs, chats, and prompts",
            "Voice commands for selected or copied text",
            "Clipboard rewrite presets and custom instructions",
            "Recent result history",
            "Priority updates",
        ],
    },
    {
        "name": "Team",
        "price": "$19",
        "cadence": "per user / month",
        "summary": "Shared billing and commercial use for small teams.",
        "features": [
            "Everything in Plus",
            "Shared configuration guidance",
            "Central billing",
            "Priority support",
            "Deployment guidance",
        ],
    },
]


def checkout_url():
    return os.environ.get("AYLO_CHECKOUT_URL", CHECKOUT_URL)


def marketing_url():
    return os.environ.get("AYLO_MARKETING_URL", MARKETING_URL)


def open_checkout():
    url = checkout_url().strip()
    if not url:
        return False
    return webbrowser.open(url)
