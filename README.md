# Scheditor Bot

Discord ↔ Trello MVP to help podcast hosts request edits and get status updates as Trello cards move across lists.

- `/request_edit` creates a Trello card in **Requests**, attaches a Drive/Dropbox link (or the uploaded Discord file), and stores who asked + where.
- When the card moves lists (e.g., **Requests → In-Progress → Complete**), the bot posts **in the same channel/thread** and @mentions the requester.
- When it reaches **Complete**, any Trello attachments/links on the card are posted too.
- A tiny SQLite DB (`bot.db`) maps `card_id ↔ user_id/channel_id`.

---

## Tech Stack

- **discord.py** (bot + slash command)
- **FastAPI** + **Uvicorn** (Trello webhook receiver)
- **Trello REST API**
- **SQLite** for minimal persistence

---

## Bring Your Own Bot & Keys (don’t use mine)

This project is **self-hosted**. Every user must create **their own** Discord bot and Trello credentials. Please **do not** ask for or reuse someone else’s tokens.

### What each user must do
1) **Create a Discord Application + Bot**
   - Discord Developer Portal → **New Application** → **Bot**.
   - **Turn OFF** “Require OAuth2 Code Grant”.
   - Invite with scopes: `bot`, `applications.commands`.
   - Permissions: at least **View Channels**, **Send Messages** (add **Attach Files** if needed).
   - Copy your **Bot Token** (keep it secret; no `Bot ` prefix in `.env`).

2) **Create Trello API credentials**
   - Get your **API key** and **token** from <https://trello.com/app-key>.
   - Use **your own** board and list IDs (Requests/In-Progress/Complete/Timed Out).
   - Register **your own** webhook pointing at **your** server/URL.

3) **Fill out your own `.env`**
   - Use `.env.example` as a template.
   - Never commit tokens; rotate if leaked.

> This repo is GPLv3, but **tokens/credentials are NOT shared**. You run and pay for your own hosting (local dev, EC2, etc.). The maintainer isn’t hosting a shared, multi-tenant bot.

---

## Quick Start (Local)

### Prereqs
- Python **3.11+**
- Discord Application with a **Bot** user
- Trello **API key** and **token**

### 1) Install
```bash
git clone https://github.com/<you>/scheditor-bot.git
cd scheditor-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install fastapi uvicorn[standard] discord.py python-dotenv requests
```

### 2) Configure environment
Create `.env` (see `.env.example` for a template):

```
DISCORD_TOKEN=your_discord_bot_token            # no quotes, no "Bot " prefix
TRELLO_KEY=your_trello_key
TRELLO_TOKEN=your_trello_token
TRELLO_BOARD_ID=xxxxxxxxxxxxxxxxxxxx

TRELLO_REQUESTS_LIST_ID=xxxxxxxxxxxxxxxx
TRELLO_INPROGRESS_LIST_ID=xxxxxxxxxxxxxx
TRELLO_COMPLETE_LIST_ID=xxxxxxxxxxxxxxxx
TRELLO_TIMEDOUT_LIST_ID=xxxxxxxxxxxxxxxx

PORT=8000
```

**Finding Trello IDs**
```bash
curl "https://api.trello.com/1/members/me/boards?key=$TRELLO_KEY&token=$TRELLO_TOKEN"
curl "https://api.trello.com/1/boards/<BOARD_ID>/lists?key=$TRELLO_KEY&token=$TRELLO_TOKEN"
```

### 3) Invite the bot
- Discord Developer Portal → **Applications** → your app → **Bot**  
  Turn **OFF** “Require OAuth2 Code Grant”  
- OAuth2 → **URL Generator** → Scopes: `bot`, `applications.commands`  
  Permissions: **View Channels**, **Send Messages** (and **Attach Files** if you want)
- Open the generated URL → select your server → **Authorize**.

### 4) Run
```bash
python main.py
# expect: "Uvicorn running on http://0.0.0.0:8000" and slash commands sync
```

### 5) Register Trello webhook (for local dev via ngrok)
```bash
ngrok http http://127.0.0.1:8000
CALLBACK="https://<your-ngrok>.ngrok-free.app/trello"
curl -X POST "https://api.trello.com/1/webhooks/?key=$TRELLO_KEY&token=$TRELLO_TOKEN"   -d "description=Scheditor board webhook"   -d "callbackURL=$CALLBACK"   -d "idModel=$TRELLO_BOARD_ID"
```

---

## Using It

In Discord:

```
/request_edit
  episode_title: "Home Viewing"
  drive_link: "https://drive.google.com/..."
  notes: "Noise reduction please"
  file: (optional upload)
```

- A card appears in Trello’s **Requests** list.
- Move the card between lists → the bot posts updates in the same channel/thread and mentions the requester.
- Move to **Complete** (with attachments on the card) → final links are posted.

---

## Deploy (very short)

For a friends-only setup, a tiny **EC2 + systemd + Nginx** works great:
1. Copy this repo to the instance, create `.env` (do **not** commit secrets).  
2. Run `python main.py` under a systemd service.  
3. Nginx reverse-proxies `/:8000`.  
4. Register the Trello webhook to `http(s)://<your-host>/trello`.

---

## Project Layout

```
.
├── main.py
├── .env.example
├── .gitignore
└── README.md
```

Local state: `bot.db` (SQLite) stores `card_id → user/channel/title`.

---

## Troubleshooting

- `Improper token has been passed` → wrong Discord token or you included `Bot ` prefix.
- Slash command missing → ensure `applications.commands` scope; or sync to a guild in code.
- Webhook disabled → ensure app is reachable and using the correct public URL; HEAD to `/trello` returns 200.

---

## License

This project is licensed under the **GNU General Public License v3.0**.  
See <https://www.gnu.org/licenses/gpl-3.0.en.html> for full terms.
