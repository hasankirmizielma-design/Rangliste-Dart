import discord
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials

import os
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Google Sheets Setup
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

import json
import os

creds_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gs_client = gspread.authorize(creds)

sheet = gs_client.open_by_key("19Ax_hj9exjwfM6NPyw9JBL2ad3qW1_LOkMHddJ6stlc").worksheet("Ergebnisse")

pattern = r"(.+?) vs (.+?) (\d+):(\d+)"

@client.event
async def on_ready():
    print(f"✅ Bot ist online als {client.user}")

import re

pattern = r"(.+?)\s+vs\s+(.+?)\s+(\d+):(\d+)"

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.channel.name != "bullseye-rangliste-ergebnisse":
        return

    content = message.content

    match = re.search(pattern, content)

    if not match:
        await message.channel.send("❌ Format: Name vs Name 5:4")
        return

    p1_text, p2_text, s1, s2 = match.groups()
    s1, s2 = int(s1), int(s2)

    # 👉 Mentions sauber extrahieren
    mentions = message.mentions

    if len(mentions) == 2:
        # Reihenfolge anhand Text prüfen
        if mentions[0].display_name.lower() in p1_text.lower():
            p1 = mentions[0].display_name
            p2 = mentions[1].display_name
        else:
            p1 = mentions[1].display_name
            p2 = mentions[0].display_name
    else:
        # fallback: Text verwenden
        p1 = p1_text.strip()
        p2 = p2_text.strip()

    # 👉 Debug (optional)
    print(f"{p1} vs {p2} → {s1}:{s2}")

    # 👉 Google Sheet
    sheet.append_row([
        p1,
        p2,
        s1,
        s2
    ])

    # 👉 Gewinner bestimmen
    if s1 > s2:
        winner = p1
    elif s2 > s1:
        winner = p2
    else:
        winner = "Unentschieden"

    await message.channel.send(
        f"✅ {p1} {s1}:{s2} {p2} eingetragen\n🏆 Gewinner: {winner}"
    )

    else:
        await message.channel.send("❌ Format: Name vs Name 5:4")

client.run(TOKEN)
