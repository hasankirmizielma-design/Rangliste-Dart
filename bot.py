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
LOG_CHANNEL_ID = 1492394175906320605
CHANNEL_NAME = "bullseye-rangliste-ergebnisse"
MAX_MATCHES_PER_DAY = 5

# =========================
# DISCORD SETUP
# =========================
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# =========================
# GOOGLE SHEETS (ENV)
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
    return name.strip().lower().replace("\u00A0", "")


def remaining(player):
    return MAX_MATCHES_PER_DAY - match_count[normalize(player)]


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

    result = resolve_names(message, message.content)

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
            await message.channel.send(f"⚠️ {winner} hat heute keine Spiele mehr übrig.")
            return

        if match_count[normalize(loser)] >= MAX_MATCHES_PER_DAY:
            await message.channel.send(f"⚠️ {loser} hat heute keine Spiele mehr übrig.")
            return

    # =========================
    # SHEET WRITE
    # =========================
    try:
        sheet.append_row([
            winner,
            loser,
            w_score,
            l_score,
            p1,
            p2
        ])
    except Exception as e:
        print("❌ SHEETS ERROR:", e)
        await message.channel.send("❌ Fehler beim Speichern!")
        return

    # =========================
    # COUNTER UPDATE
    # =========================
    if winner != "Unentschieden":
        match_count[normalize(winner)] += 1
        match_count[normalize(loser)] += 1

    # =========================
    # MAIN RESPONSE
    # =========================
    if winner == "Unentschieden":
        await message.channel.send(f"🤝 Unentschieden {w_score}:{l_score}")
    else:
        await message.channel.send(
            f"🏆 Sieger: {winner} ({w_score}:{l_score})\n"
            f"🎮 {winner} noch {remaining(winner)} Spiele\n"
            f"🎮 {loser} noch {remaining(loser)} Spiele"
        )

    # =========================
    # LOG CHANNEL OUTPUT
    # =========================
    try:
        log_channel = await client.fetch_channel(LOG_CHANNEL_ID)

        msg = "📊 Offene Spiele:\n"
        for player in match_count.keys():
            rest = remaining(player)
            if rest > 0:
                msg += f"{player} hat noch {rest} Spiele\n"

        await log_channel.send(msg)

    except Exception as e:
        print("❌ LOG CHANNEL ERROR:", e)


client.run(TOKEN)
