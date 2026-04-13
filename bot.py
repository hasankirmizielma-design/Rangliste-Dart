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
# GOOGLE SHEETS SETUP (ENV VERSION)
# =========================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_json = os.getenv("GOOGLE_CREDENTIALS")

if not creds_json:
    raise Exception("❌ GOOGLE_CREDENTIALS ist nicht gesetzt!")

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
# MEMORY (Tageslimit)
# =========================
match_count = defaultdict(int)
last_reset = date.today()

# =========================
# ROBUSTER PARSER
# =========================
pattern = re.compile(
    r"(.+?)\s*(?:vs|gegen)\s*(.+?)\s*(\d+)\s*:\s*(\d+)",
    re.IGNORECASE
)

# =========================
# HELPER
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

    # Mentions haben Priorität
    if len(message.mentions) >= 2:
        p1 = message.mentions[0].display_name
        p2 = message.mentions[1].display_name
    else:
        p1 = p1_raw
        p2 = p2_raw

    s1 = int(s1)
    s2 = int(s2)

    p1_key = normalize(p1)
    p2_key = normalize(p2)

    # =========================
    # LIMIT CHECK
    # =========================
    if match_count[p1_key] >= MAX_MATCHES_PER_DAY:
        await message.channel.send(f"⚠️ {p1} hat heute keine Spiele mehr übrig.")
        return

    if match_count[p2_key] >= MAX_MATCHES_PER_DAY:
        await message.channel.send(f"⚠️ {p2} hat heute keine Spiele mehr übrig.")
        return

    # =========================
    # WINNER
    # =========================
    if s1 > s2:
        winner = p1
    elif s2 > s1:
        winner = p2
    else:
        winner = "Unentschieden"

    # =========================
    # SHEETS WRITE
    # =========================
    try:
        sheet.append_row([
            p1,
            p2,
            s1,
            s2,
            winner
        ])
    except Exception as e:
        print("❌ SHEETS ERROR:", e)
        await message.channel.send("❌ Fehler beim Google Sheets Eintrag!")
        return

    # =========================
    # COUNTER UPDATE
    # =========================
    match_count[p1_key] += 1
    match_count[p2_key] += 1

    # =========================
    # RESPONSE
    # =========================
    await message.channel.send(
        f"✅ Eingetragen: {p1} {s1}:{s2} {p2}\n"
        f"🎮 {p1} noch {remaining(p1)} Spiele\n"
        f"🎮 {p2} noch {remaining(p2)} Spiele"
    )


client.run(TOKEN)
