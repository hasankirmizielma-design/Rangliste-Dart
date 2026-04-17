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
LOG_CHANNEL_ID = 1492394175906320605

MAX_MATCHES_PER_DAY = 5

# 🔐 ADMIN ROLE IDS
ADMIN_ROLE_IDS = [1463106884595880031]

# =========================
# DISCORD SETUP
# =========================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)

# =========================
# GOOGLE SHEETS
# =========================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_json = os.getenv("GOOGLE_CREDENTIALS")
if not creds_json:
    raise Exception("❌ GOOGLE_CREDENTIALS fehlt!")

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
# MEMORY
# =========================
match_count = defaultdict(int)
last_reset = date.today()

# =========================
# REGEX
# =========================
pattern = re.compile(
    r"(.+?)\s*(?:vs|gegen)\s*(.+?)\s*(\d+)\s*:\s*(\d+)",
    re.IGNORECASE
)

# =========================
# HELPERS
# =========================
def reset_daily():
    global match_count, last_reset
    if date.today() != last_reset:
        match_count = defaultdict(int)
        last_reset = date.today()


def normalize(name):
    return name.strip().lower()


def remaining(player):
    return MAX_MATCHES_PER_DAY - match_count[normalize(player)]


def is_admin(member):
    return any(role.id in ADMIN_ROLE_IDS for role in member.roles)


def resolve_names(message, raw_text):
    text = raw_text

    for m in message.mentions:
        text = text.replace(f"<@{m.id}>", m.display_name)
        text = text.replace(f"<@!{m.id}>", m.display_name)

    match = pattern.search(text)
    if not match:
        return None

    return match.groups()

# =========================
# BOT READY
# =========================
@client.event
async def on_ready():
    print(f"✅ Online als {client.user}")

# =========================
# MESSAGE HANDLER
# =========================
@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.name != CHANNEL_NAME:
        return

    reset_daily()

    content = message.content
    print("📩 INPUT:", content)

    # =========================
    # !add COMMAND
    # =========================
    if content.startswith("!add"):

        if not is_admin(message.author):
            await message.channel.send("⛔ Nur Admins dürfen das.")
            return

        parts = content.split()

        if message.mentions:
            player = message.mentions[0].display_name
        else:
            player = parts[1] if len(parts) > 1 else None

        if not player:
            await message.channel.send("❌ Nutzung: !add Spieler +1 oder -1")
            return

        change = int(parts[2]) if len(parts) > 2 else 1

        match_count[normalize(player)] += change

        if match_count[normalize(player)] < 0:
            match_count[normalize(player)] = 0

        await message.channel.send(
            f"🔧 {player}: Änderung {change}\n"
            f"🎮 Restspiele: {remaining(player)}"
        )
        return

    # =========================
    # MATCH PARSE
    # =========================
    result = resolve_names(message, content)

    if not result:
        await message.channel.send("❌ Format: Spieler A vs Spieler B 3:0")
        return

    p1, p2, s1, s2 = result
    s1 = int(s1)
    s2 = int(s2)

    # =========================
    # WIN LOGIC
    # =========================
    if s1 > s2:
        winner, loser = p1, p2
        w_score, l_score = s1, s2
    elif s2 > s1:
        winner, loser = p2, p1
        w_score, l_score = s2, s1
    else:
        winner = "Unentschieden"
        loser = ""
        w_score = s1
        l_score = s2

    # =========================
    # LIMIT CHECK
    # =========================
    if winner != "Unentschieden":
        if match_count[normalize(winner)] >= MAX_MATCHES_PER_DAY:
            await message.channel.send(f"⚠️ {winner} hat keine Spiele mehr übrig.")
            return

        if match_count[normalize(loser)] >= MAX_MATCHES_PER_DAY:
            await message.channel.send(f"⚠️ {loser} hat keine Spiele mehr übrig.")
            return

    # =========================
    # GOOGLE SHEETS
    # =========================
    sheet.append_row([
        winner,
        loser,
        w_score,
        l_score,
        p1,
        p2
    ])

    # =========================
    # COUNTER UPDATE
    # =========================
    if winner != "Unentschieden":
        match_count[normalize(winner)] += 1
        match_count[normalize(loser)] += 1

    # =========================
    # RESPONSE
    # =========================
    if winner == "Unentschieden":
        await message.channel.send(f"🤝 Unentschieden {w_score}:{l_score}")
    else:
        await message.channel.send(
            f"🏆 Sieger: {winner} ({w_score}:{l_score})\n"
            f"🎮 {winner} noch {remaining(winner)} Spiele\n"
            f"🎮 {loser} noch {remaining(loser)} Spiele"
        )

        # ⚠️ WARNING 1 GAME LEFT
        for player in [winner, loser]:
            if remaining(player) == 1:
                await message.channel.send(
                    f"⚠️ {player} hat nur noch 1 Spiel übrig!"
                )

    # =========================
    # SECOND CHANNEL LOG (ONLY MATCH PLAYERS)
    # =========================
    log_channel = client.get_channel(LOG_CHANNEL_ID)

    if log_channel:
        await log_channel.send(
            f"📊 Match Update:\n"
            f"{p1} vs {p2}\n"
            f"Ergebnis: {w_score}:{l_score}"
        )

# =========================
# RUN BOT
# =========================
client.run(TOKEN)
