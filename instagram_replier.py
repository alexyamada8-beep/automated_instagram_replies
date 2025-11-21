# app.py
import os
from typing import Any, Dict
import time
from flask import Flask, request, jsonify, make_response
import httpx
from ollama import Client  # pip install ollama

VERIFY_TOKEN = "hello"
PAGE_ACCESS_TOKEN = 
OLLAMA_MODEL = "phi3:latest"
OLLAMA_HOST = "http://localhost:11434"
IG_BUSINESS_ID = 17841477753965493
SERVER_START_MS = int(time.time() * 1000)


if not PAGE_ACCESS_TOKEN:
    raise RuntimeError("PAGE_ACCESS_TOKEN env var is required")

app = Flask(__name__)
ollama_client = Client(host=OLLAMA_HOST)


@app.route("/webhook", methods=['GET'])
def webhook():
    # Facebook webhook verification (GET)
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if verify_token == VERIFY_TOKEN:
            return challenge, 200
        return "Verification token mismatch", 403

    # Facebook webhook event handling (POST)
    elif request.method == 'POST':
        data = request.get_json()
        print("Received webhook data:", data)  # Log payload for debugging

        # Handle your message/event here
        # e.g., process received messages or postbacks

        return "EVENT_RECEIVED", 200


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    data: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
    print("WEBHOOK DATA:", data)

    obj = data.get("object")
    if obj not in ("instagram", "page"):
        return jsonify({"status": "ignored", "reason": "unsupported_object"}), 200

    # --- CASE A: Messenger-style events: entry[].messaging[] ---
    for entry in data.get("entry", []):
        messaging_events = entry.get("messaging", [])
        for event in messaging_events:
            # Ignore events from before this server booted (timestamp in ms)
            event_ts_ms = event.get("timestamp")
            if isinstance(event_ts_ms, (int, float)) and event_ts_ms < SERVER_START_MS:
                print("Ignoring old messaging event:", event_ts_ms)
                continue

            sender = event.get("sender", {}) or {}
            sender_id = sender.get("id")
            message = event.get("message") or {}

            # 1) Ignore echoes (messages sent by your business)
            if message.get("is_echo"):
                print("Ignoring echo message from:", sender_id)
                continue

            # 2) Ignore anything sent by your own IG business ID
            if IG_BUSINESS_ID and sender_id == IG_BUSINESS_ID:
                print("Ignoring self-sent message from business account:", sender_id)
                continue

            text = message.get("text")
            if text and sender_id:
                reply_text = generate_ai_reply(text, sender_id)
                send_instagram_message(sender_id, reply_text)

    # --- CASE B: Instagram Platform 'messages' field: entry[].changes[] ---
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue

            value = change.get("value", {}) or {}
            msg = value.get("message", {}) or {}

            # Ignore old events (value.timestamp is seconds in IG webhook examples)
            raw_ts = value.get("timestamp")
            try:
                ts_sec = int(raw_ts)
                if ts_sec < SERVER_START_MS // 1000:
                    print("Ignoring old changes[] message:", ts_sec)
                    continue
            except (TypeError, ValueError):
                pass  # if no/invalid timestamp, fall through

            # Some IG webhooks may also include is_echo here; be safe:
            if msg.get("is_echo"):
                print("Ignoring echo message (changes[] branch)")
                continue

            sender = value.get("sender", {}) or {}
            sender_id = sender.get("id")
            text = msg.get("text")

            if IG_BUSINESS_ID and sender_id == IG_BUSINESS_ID:
                print("Ignoring self-sent message in changes[] branch:", sender_id)
                continue

            if sender_id and text:
                reply_text = generate_ai_reply(text, sender_id)
                send_instagram_message(sender_id, reply_text)

    return jsonify({"status": "ok"}), 200


# ---------- AI REPLY WITH OLLAMA ----------

def generate_ai_reply(user_text: str, sender_id: str) -> str:
    """
    Use a local Ollama model to generate a reply.
    """
    system_prompt = (
        "You are a helpful assistant for my Instagram account. "
        "Answer followers' questions clearly, concisely, and in a friendly tone."
    )

    response = ollama_client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"User ID: {sender_id}\nMessage: {user_text}",
            },
        ],
        stream=False,
    )

    return response["message"]["content"].strip()


# ---------- SEND MESSAGE BACK TO IG ----------

def send_instagram_message(recipient_igid: str, text: str) -> None:
    # Instagram Messaging API with Instagram Login
    url = f"https://graph.instagram.com/v23.0/{IG_BUSINESS_ID}/messages"

    headers = {
        "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "recipient": {"id": recipient_igid},   # sender.id from the webhook
        "message": {"text": text},
    }

    with httpx.Client(timeout=10) as client:
        resp = client.post(url, headers=headers, json=payload)
        print("SEND RESPONSE:", resp.status_code, resp.text)
        # You can comment this out if you don't want 400s to crash the webhook:
        resp.raise_for_status()


if __name__ == "__main__":
    # Flask dev server; ngrok will tunnel to this
    app.run(host="0.0.0.0", port=8000, debug=True)