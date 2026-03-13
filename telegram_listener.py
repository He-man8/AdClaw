"""
Telegram Reply Listener
------------------------
Polls for replies from the user and acts on them:
  "approved" → activates all staged ads in upload_log.json
  "skip"     → defers, does nothing
  "status"   → sends current ad health summary
  "check my ads" → triggers a full orchestrator run

Run this as a background process alongside the main agent:
  python3 telegram_listener.py
"""

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID     = os.environ["TELEGRAM_CHAT_ID"]
UPLOAD_LOG  = Path("upload_log.json")
OFFSET_FILE = Path(".telegram_offset")   # tracks last processed update


def send(text: str) -> None:
    payload = json.dumps({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


def get_updates(offset: int) -> list[dict]:
    url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
        f"?timeout=30&offset={offset}"
    )
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=35) as resp:
        data = json.loads(resp.read())
    return data.get("result", [])


def load_offset() -> int:
    if OFFSET_FILE.exists():
        return int(OFFSET_FILE.read_text().strip())
    return 0


def save_offset(offset: int) -> None:
    OFFSET_FILE.write_text(str(offset))


def activate_staged_ads() -> str:
    if not UPLOAD_LOG.exists():
        return "No upload log found. Run the agent first."

    log = json.loads(UPLOAD_LOG.read_text())
    staged = [r for r in log if r.get("status") == "PAUSED" and not r.get("dry_run", True) is False]
    mock   = [r for r in log if r.get("dry_run", True)]

    if mock:
        # dry run mode — simulate activation
        activated = []
        for r in log:
            if r.get("status") == "PAUSED":
                r["status"] = "ACTIVE"
                r["activated_at"] = datetime.now(timezone.utc).isoformat()
                activated.append(r["ad_id"])

        UPLOAD_LOG.write_text(json.dumps(log, indent=2))
        names = "\n".join(f"  ✅ {r['headline']}" for r in log if r.get("status") == "ACTIVE")
        return (
            f"✅ *{len(activated)} ads activated* (dry run mode)\n\n"
            f"{names}\n\n"
            f"_Connect Meta credentials to publish live._"
        )
    else:
        # live mode — call social-flow for each ad
        activated = []
        for r in log:
            if r.get("status") == "PAUSED":
                ad_id = r.get("ad_id")
                if ad_id:
                    subprocess.run(
                        ["social", "marketing", "ad", "update",
                         "--ad-id", ad_id, "--status", "ACTIVE"],
                        check=True,
                    )
                    r["status"] = "ACTIVE"
                    activated.append(ad_id)

        UPLOAD_LOG.write_text(json.dumps(log, indent=2))
        return f"✅ *{len(activated)} ads set to ACTIVE* in Meta Ads Manager."


def run_full_audit() -> None:
    send("🔄 Running full ads audit... (this takes ~40 seconds)")
    subprocess.Popen(
        ["python3", "orchestrator.py"],
        cwd="/Users/aiteam1/Code/openclaw",
    )


def handle_message(text: str) -> None:
    text = text.strip().lower()

    if text in ("approved", "approve"):
        send("⏳ Activating staged ads...")
        result = activate_staged_ads()
        send(result)

    elif text == "skip":
        send("⏭ Deferred. Staged ads remain PAUSED. I'll remind you tomorrow.")

    elif text in ("check my ads", "status", "how are my ads doing",
                  "any dying ads?", "morning brief", "ads report"):
        run_full_audit()

    elif text == "help":
        send(
            "*Available commands:*\n\n"
            "• *approved* — activate all staged ads\n"
            "• *skip* — defer, keep ads paused\n"
            "• *check my ads* — run full audit now\n"
            "• *status* — same as above\n"
            "• *help* — show this message"
        )
    else:
        send(
            f'Didn\'t recognise "{text}"\n\n'
            "Reply *approved*, *skip*, *check my ads*, or *help*."
        )


def main() -> None:
    print(f"[WallE] Listening for replies on chat {CHAT_ID}...")
    send("🤖 *WallE is online.* Reply *help* to see available commands.")
    offset = load_offset()

    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                save_offset(offset)

                msg = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text    = msg.get("text", "")

                # only respond to messages from your own chat
                if chat_id != CHAT_ID:
                    continue

                print(f"[{datetime.now(timezone.utc).strftime('%H:%M')}] Received: {text}")
                handle_message(text)

        except KeyboardInterrupt:
            print("\n[WallE] Stopped.")
            break
        except Exception as e:
            print(f"[WallE] Error: {e}")


if __name__ == "__main__":
    main()
