import discord
import re
import os
import json
import random
from collections import defaultdict
from datetime import date, datetime
import asyncio

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("TOKEN")
LOG_CHANNEL_ID = 1492394175906320605
STATS_CHANNEL_ID = 1513493210910167170
CHANNEL_NAME = "bullseye-rangliste-ergebnisse"
MAX_MATCHES_PER_DAY = 5
LANZI_NAME = "lanzi_90"

# 🔐 ADMIN ROLE ID
ADMIN_ROLE_IDS = [1463106884595880031]

lanzi_insult_index = 0

# 🤝 UNENTSCHIEDEN-SPRÜCHE
UNENTSCHIEDEN_SPRUECHE = [
    "Unentschieden?! Selbst die KI schüttelt den Kopf 🤖",
    "Ein Unentschieden beim Dart... das schafft auch nur ihr 😂",
    "🤝 Keiner gewinnt, keiner verliert — beide Verlierer 😂",
    "Unentschieden? Habt ihr überhaupt getroffen? 🎯",
    "Die KI weint gerade... Unentschieden beim Dart 😭",
]

# 🏆 DOMINANZ-SPRÜCHE
def get_dominanz_spruch(winner, score_diff):
    if score_diff >= 3:
        sprueche = [
            f"Jemand hat heute zu viel geübt 😏",
            f"Die Dartscheibe hat Angst bekommen 🎯😂",
            f"Selbst der Schiedsrichter hat gelacht 😂",
            f"War das Dart oder ein Kunstwerk? 🎨",
            f"Die Pfeile wussten wo sie hingehören 🏹",
            f"Jemand hat heute seinen Spinat gegessen 🥬💪",
            f"Die Schwerkraft hat heute mitgespielt 🌍",
            f"Statistisch unmöglich — aber hier sind wir 📊",
            f"Der Gegner braucht jetzt erstmal Urlaub 🏖️",
            f"So trifft man, wenn man die Augen zumacht 😎",
        ]
        return random.choice(sprueche)
    return None

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
today_matches = []  # für Tagesauswertung: liste von dicts

# =========================
# REGEX
# =========================
pattern = re.compile(
    r"(.+?)\s*(?:vs|gegen)\s*(.+?)\s*[\(\[]?\s*(\d+)\s*:\s*(\d+)",
    re.IGNORECASE
)

# =========================
# HELPERS
# =========================
def reset_daily():
    global match_count, last_reset, today_matches
    if date.today() != last_reset:
        match_count = defaultdict(int)
        last_reset = date.today()
        today_matches = []


def normalize(name):
    return name.strip().lower().replace("\u00A0", "")


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

    p1, p2, s1, s2 = match.groups()
    p1 = re.sub(r"[\(\[\s]+$", "", p1).strip()
    p2 = re.sub(r"[\(\[\s]+$", "", p2).strip()

    return p1, p2, s1, s2


def get_stats_from_sheet():
    """Liest alle Zeilen und berechnet Statistiken pro Spieler."""
    rows = sheet.get_all_values()
    stats = defaultdict(lambda: {"siege": 0, "niederlagen": 0, "spiele": 0})

    for row in rows:
        if len(row) < 2:
            continue
        winner = row[0].strip()
        loser = row[1].strip()
        if not winner or not loser or winner == "Unentschieden":
            continue
        stats[winner]["siege"] += 1
        stats[winner]["spiele"] += 1
        stats[loser]["niederlagen"] += 1
        stats[loser]["spiele"] += 1

    return stats


def get_streak_from_sheet(player_name):
    """Berechnet aktuelle Siegesserie eines Spielers."""
    rows = sheet.get_all_values()
    streak = 0
    for row in reversed(rows):
        if len(row) < 2:
            continue
        winner = row[0].strip()
        loser = row[1].strip()
        if normalize(winner) == normalize(player_name):
            streak += 1
        elif normalize(loser) == normalize(player_name):
            break
    return streak


async def midnight_auswertung():
    """Läuft täglich um Mitternacht und postet Tagesauswertung."""
    await client.wait_until_ready()
    while not client.is_closed():
        now = datetime.now()
        # Sekunden bis Mitternacht berechnen
        seconds_until_midnight = (
            (24 - now.hour - 1) * 3600 +
            (60 - now.minute - 1) * 60 +
            (60 - now.second)
        )
        await asyncio.sleep(seconds_until_midnight)

        try:
            stats_channel = await client.fetch_channel(STATS_CHANNEL_ID)

            if not today_matches:
                await stats_channel.send("📊 Tagesauswertung: Heute wurden keine Spiele gespielt.")
            else:
                # Siege zählen
                player_wins = defaultdict(int)
                player_games = defaultdict(int)
                for m in today_matches:
                    if m["winner"] != "Unentschieden":
                        player_wins[m["winner"]] += 1
                    player_games[m["p1"]] += 1
                    player_games[m["p2"]] += 1

                most_games_player = max(player_games, key=player_games.get)
                most_wins_player = max(player_wins, key=player_wins.get) if player_wins else None

                msg = f"🌙 **Tagesauswertung {date.today().strftime('%d.%m.%Y')}**\n\n"
                msg += f"🎮 Gespielte Matches heute: {len(today_matches)}\n"
                msg += f"🏅 Meiste Spiele: {most_games_player} ({player_games[most_games_player]} Spiele)\n"
                if most_wins_player:
                    msg += f"🏆 Meiste Siege: {most_wins_player} ({player_wins[most_wins_player]} Siege)\n"

                await stats_channel.send(msg)

        except Exception as e:
            print("❌ MIDNIGHT ERROR:", e)

        await asyncio.sleep(60)  # kurz warten damit es nicht doppelt feuert


# =========================
# BOT READY
# =========================
@client.event
async def on_ready():
    print(f"✅ Online als {client.user}")
    client.loop.create_task(midnight_auswertung())


# =========================
# MESSAGE HANDLER
# =========================
@client.event
async def on_message(message):
    global lanzi_insult_index

    if message.author.bot:
        return

    # Stats-Commands auch im Stats-Channel erlauben
    is_stats_channel = message.channel.id == STATS_CHANNEL_ID
    is_main_channel = message.channel.name == CHANNEL_NAME

    if not is_main_channel and not is_stats_channel:
        return

    reset_daily()

    content = message.content

    # =========================
    # !stats Spieler
    # =========================
    if content.lower().startswith("!stats"):
        if not is_stats_channel:
            return

        WARTELISTE_ROLE_ID = 1492563010395312301

        # Rollen-Stats: !stats @Warteliste
        is_role_stats = (message.role_mentions and any(r.id == WARTELISTE_ROLE_ID for r in message.role_mentions)) or str(WARTELISTE_ROLE_ID) in content or "warteliste" in content.lower()
        if is_role_stats:
            try:
                stats = get_stats_from_sheet()
                guild = message.guild
                role = guild.get_role(WARTELISTE_ROLE_ID)
                if not role:
                    await message.channel.send("❌ Rolle nicht gefunden.")
                    return

                members_with_role = [m for m in role.members]
                if not members_with_role:
                    await message.channel.send("❌ Keine Mitglieder mit dieser Rolle.")
                    return

                await message.channel.send(f"📊 **Stats für alle Spieler mit Rolle {role.name}:**")

                for member in members_with_role:
                    player = member.display_name
                    s = stats.get(player)
                    if not s:
                        for k, v in stats.items():
                            if normalize(k) == normalize(player):
                                s = v
                                break

                    if not s or s["spiele"] == 0:
                        await message.channel.send(f"➖ **{player}** — Noch keine Spiele im Sheet.")
                    else:
                        winrate = round(s["siege"] / s["spiele"] * 100, 1)
                        msg = (
                            f"📊 **{player}**\n"
                            f"🎮 Spiele: {s['spiele']} | 🏆 Siege: {s['siege']} | 💀 Niederlagen: {s['niederlagen']} | 📈 Win-Rate: {winrate}%"
                        )
                        await message.channel.send(msg)

            except Exception as e:
                print("❌ STATS ROLLE ERROR:", e)
                await message.channel.send("❌ Fehler beim Laden der Rollen-Stats.")
            return

        # Einzelspieler-Stats
        parts = content.split(None, 1)
        if message.mentions:
            player = message.mentions[0].display_name
        elif len(parts) > 1:
            player = parts[1].strip()
        else:
            await message.channel.send("❌ Nutzung: !stats Spielername oder !stats @Warteliste")
            return

        try:
            stats = get_stats_from_sheet()
            s = stats.get(player)
            if not s:
                for k, v in stats.items():
                    if normalize(k) == normalize(player):
                        s = v
                        player = k
                        break

            if not s or s["spiele"] == 0:
                await message.channel.send(f"❌ Keine Daten für {player} gefunden.")
                return

            winrate = round(s["siege"] / s["spiele"] * 100, 1)
            msg = (
                f"📊 **Stats für {player}**\n"
                f"🎮 Spiele gesamt: {s['spiele']}\n"
                f"🏆 Siege: {s['siege']}\n"
                f"💀 Niederlagen: {s['niederlagen']}\n"
                f"📈 Win-Rate: {winrate}%"
            )
            await message.channel.send(msg)
        except Exception as e:
            print("❌ STATS ERROR:", e)
            await message.channel.send("❌ Fehler beim Laden der Stats.")
        return

    # =========================
    # !top — Rangliste Top 10
    # =========================
    if content.lower().startswith("!top") or content.lower().startswith("!rangliste"):
        if not is_stats_channel:
            return
        try:
            stats = get_stats_from_sheet()
            if not stats:
                await message.channel.send("❌ Keine Daten gefunden.")
                return

            sorted_players = sorted(
                stats.items(),
                key=lambda x: (x[1]["siege"], -x[1]["niederlagen"]),
                reverse=True
            )[:10]

            msg = "🏆 **Top 10 Rangliste**\n\n"
            medals = ["🥇", "🥈", "🥉"]
            for i, (player, s) in enumerate(sorted_players):
                medal = medals[i] if i < 3 else f"{i+1}."
                winrate = round(s["siege"] / s["spiele"] * 100, 1) if s["spiele"] > 0 else 0
                msg += f"{medal} {player} — {s['siege']}S / {s['niederlagen']}N ({winrate}%)\n"

            await message.channel.send(msg)
        except Exception as e:
            print("❌ TOP ERROR:", e)
            await message.channel.send("❌ Fehler beim Laden der Rangliste.")
        return

    # =========================
    # !streak Spieler
    # =========================
    if content.lower().startswith("!streak"):
        if not is_stats_channel:
            return
        parts = content.split(None, 1)
        if message.mentions:
            player = message.mentions[0].display_name
        elif len(parts) > 1:
            player = parts[1].strip()
        else:
            await message.channel.send("❌ Nutzung: !streak Spielername")
            return

        try:
            streak = get_streak_from_sheet(player)
            if streak == 0:
                await message.channel.send(f"😬 {player} hat gerade keine Siegesserie.")
            elif streak == 1:
                await message.channel.send(f"🔥 {player} hat 1 Sieg in Folge!")
            else:
                await message.channel.send(f"🔥 {player} ist auf einer {streak}er Siegesserie!")
        except Exception as e:
            print("❌ STREAK ERROR:", e)
            await message.channel.send("❌ Fehler beim Laden der Streak-Daten.")
        return

    # =========================
    # !undo — letztes Ergebnis löschen
    # =========================
    if content.lower().startswith("!undo"):
        if not is_main_channel:
            return
        if not is_admin(message.author):
            await message.channel.send("⛔ Nur Admins dürfen das.")
            return
        try:
            all_rows = sheet.get_all_values()
            if not all_rows:
                await message.channel.send("❌ Keine Einträge zum Löschen.")
                return
            last_row_index = len(all_rows)  # gspread: 1-basiert, get_all_values gibt direkt die Zeilenzahl
            sheet.delete_rows(last_row_index)
            await message.channel.send("🗑️ Letzter Eintrag wurde gelöscht!")
        except Exception as e:
            print("❌ UNDO ERROR:", e)
            await message.channel.send("❌ Fehler beim Löschen.")
        return

    # Ab hier nur im Hauptchannel
    if not is_main_channel:
        return

    # =========================
    # ADMIN COMMAND !add
    # =========================
    if content.lower().startswith("!add"):
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
        await message.channel.send("Selbst die KI schüttelt den Kopf 🤖\n❌ Format: Spieler A vs Spieler B 3:0")
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

    # Tages-Tracking
    today_matches.append({"p1": p1, "p2": p2, "winner": winner})

    # =========================
    # MAIN RESPONSE
    # =========================
    if winner == "Unentschieden":
        await message.channel.send(random.choice(UNENTSCHIEDEN_SPRUECHE))
    else:
        await message.channel.send(
            f"🏆 Sieger: {winner} ({w_score}:{l_score})\n"
            f"🎮 {winner} noch {remaining(winner)} Spiele\n"
            f"🎮 {loser} noch {remaining(loser)} Spiele"
        )

        # ⚠️ 1 GAME WARNING
        for player in [winner, loser]:
            if remaining(player) == 1:
                await message.channel.send(
                    f"⚠️ {player} hat nur noch 1 Spiel übrig!"
                )

    # =========================
    # SPIELABSPRACHEN: Dominanz + Lanzi
    # =========================
    try:
        spielabsprachen = await client.fetch_channel(LOG_CHANNEL_ID)

        # 🔥 DOMINANZ-SPRUCH
        if winner != "Unentschieden":
            score_diff = w_score - l_score
            spruch = get_dominanz_spruch(winner, score_diff)
            if spruch:
                await spielabsprachen.send(spruch)

        # 📊 RESTSPIELE
        msg = "📊 Match Update:\n"
        msg += f"{p1} vs {p2}\n\n"
        msg += "🎮 Restspiele (nur Beteiligte):\n"
        for player in [p1, p2]:
            msg += f"- {player}: {remaining(player)}\n"
        await spielabsprachen.send(msg)



    except Exception as e:
        print("❌ SPIELABSPRACHEN ERROR:", e)

# =========================
# RUN
# =========================
client.run(TOKEN)
