import os
from pathlib import Path
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def telegram_api(method: str, payload=None):
    # Ambil token bot dari environment
    token = os.getenv(
        "TELEGRAM_BOT_TOKEN", ""
    ).strip()
    if not token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN belum dikonfigurasi."
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/{method}"
    )

    try:
        # Gunakan GET untuk membaca updates,
        # POST untuk mengirim pesan.
        if method == "getUpdates":
            response = requests.get(
                url,
                timeout=(5, 15)
            )
        else:
            response = requests.post(
                url,
                json=payload,
                timeout=(5, 15)
            )
    except requests.RequestException as exc:
        # Hindari mencetak URL yang berisi token
        raise RuntimeError(
            f"Koneksi Telegram gagal: "
            f"{type(exc).__name__}"
        ) from None

    if response.status_code != 200:
        raise RuntimeError(
            f"Telegram HTTP {response.status_code}"
        )

    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(
            "Respons Telegram bukan JSON valid."
        )

    if not data.get("ok"):
        raise RuntimeError(
            f"Telegram API error: {data.get('description', 'Unknown error')}"
        )

    return data


def send_telegram_message(message: str) -> dict:
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        raise ValueError(
            "TELEGRAM_CHAT_ID belum dikonfigurasi."
        )

    payload = {
        "chat_id": chat_id,
        "text": message,
    }

    data = telegram_api("sendMessage", payload=payload)
    return data.get("result", {})
