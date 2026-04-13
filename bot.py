import discord
import re
import os
import json
from collections import defaultdict
from datetime import date

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("TOKEN")

CHANNEL_NAME = "bullseye-rangliste-ergebnisse"
MAX_MATCHES_PER_DAY = 5

# =========================
# DISCORD SETUP
# =========================
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# =========================
# GOOGLE SHEETS SETUP (ENV)
# =========================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_json = os.getenv("GOOGLE_CREDENTIALS")

if not creds_json:
    raise Exception("❌ GOOGLE_CREDENTIALS fehlt in Environment Variables!")

creds_dict = json.loads(creds_json)

creds = ServiceAccountCredentials.from_json_keyfile_dict(
    creds_dict,
    scope
)

gs_client = gspread.authorize(creds)

sheet = gs_client.open_by_key(
    "19Ax_hj9exjwfM6NPyw9JBL2ad3qW1_LOkMHddJ6stlc"
).worksheet("Ergebnisse")

# =========================
# MEMORY (Daily Counter)
# =========================
match_count = defaultdict(int)
last_reset = date.today()

# =========================
# PARSER
# =========================
pattern = re.compile(
    r"(.+?)\s*(?:vs|gegen)\s*(.+?)\s*(\d+)\s*:\s*(\d+)",
    re.IGNORECASE
)

# =========================
# HELPERS
# =========================
def reset_daily_counter_if_needed():
    global match_count, last_reset

    if date.today() != last_reset:
        match_count = defaultdict(int)
        last_reset = date.today()


def normalize(name: str):
    return name.strip().lower()


def remaining(player: str):
    return MAX_MATCHES_PER_DAY - match_count[normalize(player)]


# =========================
# BOT EVENTS
# =========================
@client.event
async def on_ready():
    print(f"✅ Bot online als {client.user}")


@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.name != CHANNEL_NAME:
        return

    reset_daily_counter_if_needed()

    content = message.content
    print("📩 INPUT:", content)

    match = pattern.search(content)
    print("🔎 MATCH:", bool(match))

    if not match:
        await message.channel.send("❌ Format: Spieler A vs Spieler B 3:0")
        return

    p1_raw, p2_raw, s1, s2 = match.groups()

    s1 = int(s1)
    s2 = int(s2)

    # =========================
    # Mentions override names (optional)
    # =========================
    if len(message.mentions) >= 2:
        p1_raw = message.mentions[0].display_name
        p2_raw = message.mentions[1].display_name

    # =========================
    # 🎯 ABSOLUTE SCORE LOGIC (NO MORE SWITCHING)
    # =========================
    if s1 > s2:
        winner_name = p1_raw.strip()
        loser_name = p2_raw.strip()
        winner_score = s1
        loser_score = s2

    elif s2 > s1:
        winner_name = p2_raw.strip()
        loser_name = p1_raw.strip()
        winner_score = s2
        loser_score = s1

    else:
        winner_name = "Unentschieden"
        loser_name = ""
        winner_score = s1
        loser_score = s2

    # =========================
    # LIMIT CHECK (pro Spieler)
    # =========================
    if winner_name != "Unentschieden":
        if match_count[normalize(winner_name)] >= MAX_MATCHES_PER_DAY:
            await message.channel.send(f"⚠️ {winner_name} hat heute keine Spiele mehr übrig.")
            return

        if match_count[normalize(loser_name)] >= MAX_MATCHES_PER_DAY:
            await message.channel.send(f"⚠️ {loser_name} hat heute keine Spiele mehr übrig.")
            return

    # =========================
    # GOOGLE SHEETS WRITE
    # =========================
    try:
        sheet.append_row([
            winner_name,
            loser_name,
            winner_score,
            loser_score
        ])
    except Exception as e:
        print("❌ SHEETS ERROR:", e)
        await message.channel.send("❌ Fehler beim Eintragen in Google Sheets!")
        return

    # =========================
    # COUNTER UPDATE
    # =========================
    if winner_name != "Unentschieden":
        match_count[normalize(winner_name)] += 1
        match_count[normalize(loser_name)] += 1

    # =========================
    # RESPONSE
    # =========================
    if winner_name == "Unentschieden":
        await message.channel.send(
            f"🤝 Unentschieden {winner_score}:{loser_score}"
        )
    else:
        await message.channel.send(
            f"✅ Sieger: {winner_name} ({winner_score}:{loser_score})\n"
            f"🎮 {winner_name} noch {remaining(winner_name)} Spiele\n"
            f"🎮 {loser_name} noch {remaining(loser_name)} Spiele"
        )


client.run(TOKEN)
