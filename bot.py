import discord
import re
import os
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
# GOOGLE SHEETS SETUP
# =========================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credentials.json", scope
)
gs_client = gspread.authorize(creds)

sheet = gs_client.open_by_key(
    "19Ax_hj9exjwfM6NPyw9JBL2ad3qW1_LOkMHddJ6stlc"
).worksheet("Ergebnisse")

# =========================
# MEMORY (Spieler + Tageslimit)
# =========================
match_count = defaultdict(int)
last_reset = date.today()

# =========================
# SAFE PARSER
# =========================
pattern = re.compile(r"(.+?)\s+vs\s+(.+?)\s+(\d+)\s*:\s*(\d+)", re.IGNORECASE)


def reset_daily_counter_if_needed():
    global last_reset, match_count

    if date.today() != last_reset:
        match_count = defaultdict(int)
        last_reset = date.today()


def normalize_player(name: str):
    return name.strip().lower()


def remaining_matches(player: str):
    return MAX_MATCHES_PER_DAY - match_count[normalize_player(player)]


# =========================
# EVENTS
# =========================
@client.event
async def on_ready():
    print(f"✅ Bot ist online als {client.user}")


@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.name != CHANNEL_NAME:
        return

    reset_daily_counter_if_needed()

    match = pattern.match(message.content)

    if not match:
        await message.channel.send("❌ Format: Spieler A vs Spieler B 3:0")
        return

    p1_raw, p2_raw, s1, s2 = match.groups()

    # =========================
    # Mentions PRIORITÄT (wenn vorhanden)
    # =========================
    p1 = message.mentions[0].display_name if len(message.mentions) >= 1 else p1_raw
    p2 = message.mentions[1].display_name if len(message.mentions) >= 2 else p2_raw

    p1_key = normalize_player(p1)
    p2_key = normalize_player(p2)

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
    # SCORE LOGIC (kein Verwechseln mehr)
    # =========================
    s1, s2 = int(s1), int(s2)

    # Gewinner bestimmen (nur zur Info möglich)
    winner = p1 if s1 > s2 else p2 if s2 > s1 else "Unentschieden"

    # =========================
    # SPEICHERN
    # =========================
    sheet.append_row([
        p1,
        p2,
        s1,
        s2,
        winner
    ])

    # =========================
    # COUNTER UPDATE
    # =========================
    match_count[p1_key] += 1
    match_count[p2_key] += 1

    # =========================
    # REST SPIELE
    # =========================
    await message.channel.send(
        f"✅ Gespeichert: {p1} {s1}:{s2} {p2}\n"
        f"🎮 {p1} noch {remaining_matches(p1)} Spiele\n"
        f"🎮 {p2} noch {remaining_matches(p2)} Spiele"
    )


client.run(TOKEN)
