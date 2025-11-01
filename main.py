import os, sqlite3, threading, asyncio, requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
import uvicorn

import discord
from discord import app_commands

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

TRELLO_KEY = os.getenv("TRELLO_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
BOARD_ID = os.getenv("TRELLO_BOARD_ID")

REQUESTS_LIST_ID   = os.getenv("TRELLO_REQUESTS_LIST_ID")
INPROGRESS_LIST_ID = os.getenv("TRELLO_INPROGRESS_LIST_ID")
COMPLETE_LIST_ID   = os.getenv("TRELLO_COMPLETE_LIST_ID")
TIMEDOUT_LIST_ID   = os.getenv("TRELLO_TIMEDOUT_LIST_ID")

TRELLO_BASE = "https://api.trello.com/1"

# tiny persistence for card<->user mapping
conn = sqlite3.connect("bot.db", check_same_thread=False)
conn.execute("""
CREATE TABLE IF NOT EXISTS requests (
  card_id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  channel_id INTEGER,
  episode_title TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# Discord bot (slash command for intake)
intents = discord.Intents.default()
client = discord.Client(
    intents=intents,
    allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False)
)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    try:
        synced = await tree.sync()
        print(f"Slash commands synced: {len(synced)}")
    except Exception as e:
        print("Slash command sync failed:", e)

def trello_create_card(list_id: str, name: str, desc: str):
    r = requests.post(f"{TRELLO_BASE}/cards",
                      params={"key":TRELLO_KEY, "token":TRELLO_TOKEN,
                              "idList":list_id, "name":name, "desc":desc})
    r.raise_for_status()
    return r.json()

def trello_attach(card_id: str, url: str, name: str):
    r = requests.post(f"{TRELLO_BASE}/cards/{card_id}/attachments",
                      params={"key":TRELLO_KEY, "token":TRELLO_TOKEN,
                              "url":url, "name":name})
    r.raise_for_status()
    return r.json()

def trello_attachments(card_id: str):
    r = requests.get(f"{TRELLO_BASE}/cards/{card_id}/attachments",
                     params={"key":TRELLO_KEY, "token":TRELLO_TOKEN})
    r.raise_for_status()
    return r.json()

@tree.command(name="request_edit", description="Request a podcast edit")
@app_commands.describe(
    episode_title="Episode title",
    drive_link="Link to your files (Google Drive/Dropbox/OneDrive)",
    notes="Anything the editor should know",
    file="Optional attachment (Discord will host)"
)
async def request_edit(interaction: discord.Interaction,
                       episode_title: str,
                       drive_link: str | None = None,
                       notes: str | None = None,
                       file: discord.Attachment | None = None):
    await interaction.response.defer(ephemeral=True, thinking=True)

    desc = (
        f"**Requested by:** {interaction.user} (ID: {interaction.user.id})\n"
        f"**Origin:** Discord\n"
    )
    if notes:
        desc += f"\n**Notes:** {notes}"

    card = trello_create_card(REQUESTS_LIST_ID, episode_title, desc)

    # attach link or file URL (Discord CDN) to the card
    if drive_link:
        trello_attach(card["id"], drive_link, "Source files")

    if file:
        # Discord attachment URLs are accessible via link; good enough for MVP.
        trello_attach(card["id"], file.url, file.filename)

    # store mapping for later notifications
    conn.execute(
        "INSERT OR REPLACE INTO requests(card_id, user_id, channel_id, episode_title) VALUES(?,?,?,?)",
        (card["id"], interaction.user.id, interaction.channel_id, episode_title)
    )
    conn.commit()

    await interaction.followup.send(
        f"✅ Request created for **{episode_title}**.\n"
        f"I’ll tag you as the card moves (Requests → In-Progress → Complete).",
        ephemeral=True
    )

# FastAPI server to receive Trello webhooks
app = FastAPI()

@app.get("/")
def healthcheck():
    return {"ok": True}

# Trello verifies webhooks with a HEAD request; return 200.
@app.head("/trello")
def trello_head():
    return Response(status_code=200)

@app.post("/trello")
async def trello_webhook(req: Request):
    body = await req.json()
    action = body.get("action", {})
    atype  = action.get("type")
    data   = action.get("data", {})
    card   = data.get("card", {}) or {}
    card_id = card.get("id")

    if atype == "updateCard":
        list_before = data.get("listBefore")
        list_after  = data.get("listAfter")

        if list_before and list_after and card_id:
            row = conn.execute(
                "SELECT user_id, channel_id, episode_title FROM requests WHERE card_id = ?",
                (card_id,)
            ).fetchone()

            if row:
                user_id, channel_id, title = row

                # Pre-compute any final links here (we're in FastAPI's thread)
                final_links = None
                if list_after["id"] == COMPLETE_LIST_ID:
                    try:
                        atts = trello_attachments(card_id)
                        urls = [a["url"] for a in atts if a.get("url")]
                        if urls:
                            final_links = "\n".join(urls)
                    except Exception as e:
                        print("Attachment fetch failed:", e)

                # Build the message text
                text = f"🔔 **{title or card.get('name','Episode')}** moved from **{list_before['name']}** → **{list_after['name']}**."
                if final_links:
                    text += f"\n📦 Final files/links:\n{final_links}"

                # Post on the bot's loop (do NOT await discord.py in this thread)
                asyncio.run_coroutine_threadsafe(
                    post_update_to_channel(
                        channel_id=int(channel_id),
                        user_id=int(user_id),
                        content=text
                    ),
                    client.loop
                )

    return {"received": True}

async def post_update_to_channel(channel_id: int, user_id: int, content: str):
    # Grab the channel or thread
    ch = client.get_channel(int(channel_id)) or await client.fetch_channel(int(channel_id))

    # Build a safe, user-only mention
    mention = f"<@{int(user_id)}>"

    await ch.send(
        f"{mention} {content}",
        allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=int(user_id))], roles=False, everyone=False)
    )

def run_api():
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

async def run_bot():
    await tree.sync()
    await client.start(DISCORD_TOKEN)

if __name__ == "__main__":
    import threading, asyncio
    threading.Thread(target=run_api, daemon=True).start()
    asyncio.run(client.start(DISCORD_TOKEN))
