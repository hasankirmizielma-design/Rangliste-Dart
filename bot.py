import discord
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials

import os
TOKEN = os.getenv("MTQ5MjM4NTk5MDIzMTE5NTY0OA.GuXZkr.8B-U6_ff4xtIIPpYEICKi0nxOgPZVE60-vqTT8")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Google Sheets Setup
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
gs_client = gspread.authorize(creds)

sheet = gs_client.open_by_key("19Ax_hj9exjwfM6NPyw9JBL2ad3qW1_LOkMHddJ6stlc").worksheet("Ergebnisse")

pattern = r"(.+?) vs (.+?) (\d+):(\d+)"

@client.event
async def on_ready():
    print(f"✅ Bot ist online als {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.channel.name != "bullseye-rangliste-ergebnisse":
        return

    match = re.match(pattern, message.content)

    if match:
        p1, p2, s1, s2 = match.groups()

        # Mentions erkennen
        if message.mentions:
            if len(message.mentions) >= 1:
                p1 = message.mentions[0].display_name
            if len(message.mentions) >= 2:
                p2 = message.mentions[1].display_name

        sheet.append_row([
            p1.strip(),
            p2.strip(),
            int(s1),
            int(s2)
        ])

        await message.channel.send(f"✅ Eingetragen: {p1} {s1}:{s2} {p2}")

    else:
        await message.channel.send("❌ Format: Name vs Name 5:4")

client.run(TOKEN)
