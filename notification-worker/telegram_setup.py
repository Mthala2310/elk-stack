import sys
# pyrefly: ignore[missing-import]
from telegram_client import (
    telegram_api,
    send_telegram_message,
)


def show_chat_ids():
    data = telegram_api("getUpdates")
    updates = data.get("result", [])
    chats = {}

    for update in updates:
        event = (
            update.get("message")
            or update.get("channel_post")
            or update.get("my_chat_member")
        )
        if not event:
            continue
        chat = event.get("chat", {})
        chat_id = chat.get("id")
        if chat_id is not None:
            chats[chat_id] = chat.get(
                "type", "unknown"
            )

    if not chats:
        print(
            "Belum ada chat ditemukan. "
            "Kirim /start ke bot terlebih dahulu."
        )
        return

    for chat_id, chat_type in chats.items():
        print(
            f"Chat ID: {chat_id} "
            f"| Type: {chat_type}"
        )


def send_test():
    message = (
        "✅ ELK Monitoring Bot Connected!\n\n"
        "Telegram Notification Phase 9\n"
        "Status: CONNECTION TEST SUCCESS\n\n"
        "Belum ada incident nyata yang dikirim."
    )
    result = send_telegram_message(message)
    print("PASS: Pesan berhasil dikirim.")
    print("Message ID:", result.get("message_id"))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "Usage: python telegram_setup.py "
            "[chats|send-test]"
        )
        raise SystemExit(1)

    command = sys.argv[1]
    if command == "chats":
        show_chat_ids()
    elif command == "send-test":
        send_test()
    else:
        raise SystemExit(
            "Perintah tidak dikenal."
        )
