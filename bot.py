import discord
import re
import os
import json
import random
import io
from collections import defaultdict
from datetime import date, datetime
import asyncio
from PIL import Image, ImageDraw, ImageFont

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("TOKEN")
LOG_CHANNEL_ID = 1492394175906320605
STATS_CHANNEL_ID = 1513493210910167170
TABELLE_CHANNEL_ID = 1492394072369922118
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
# MEILENSTEINE
# =========================
SPIELE_MEILENSTEINE = {
    10: "10 Spiele — der Anfang einer Legende! Weiter so! 🚀",
    25: "25 Spiele — du meinst es ernst! Die Scheibe hat Respekt! 🎯",
    50: "50 Spiele — halbe Hundert! Du bist nicht mehr aufzuhalten! 💪",
    100: "100 Spiele — absolute Legende! Die Halle gehört dir! 👑",
}

SIEGE_MEILENSTEINE = {
    10: "10 Siege — Bronzerang verdient! Die Gegner zittern! 🥉",
    25: "25 Siege — Silber! Du weißt wie man gewinnt! 🥈",
    50: "50 Siege — Gold! Eine Klasse für sich! 🥇",
    100: "100 Siege — unsterblich! Niemand kommt dir gleich! 👑",
}


async def check_meilensteine(spieler_name, spielabsprachen_channel):
    """Prüft ob ein Spieler einen Meilenstein erreicht hat."""
    try:
        stats = get_stats_from_sheet()
        s = None
        for k, v in stats.items():
            if normalize(k) == normalize(spieler_name):
                s = v
                break
        if not s:
            return

        for milestone, spruch in SPIELE_MEILENSTEINE.items():
            if s["spiele"] == milestone:
                await spielabsprachen_channel.send(
                    f"🎉 **Meilenstein fuer {spieler_name}!**\n{spruch}"
                )

        for milestone, spruch in SIEGE_MEILENSTEINE.items():
            if s["siege"] == milestone:
                await spielabsprachen_channel.send(
                    f"🎉 **Meilenstein fuer {spieler_name}!**\n{spruch}"
                )
    except Exception as e:
        print("❌ MEILENSTEIN ERROR:", e)


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
    r"(.+?)\s*(?:vs\.?|gegen)\s*(.+?)\s*[\(\[]?\s*(\d+)\s*[:\-]\s*(\d+)",
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
    """Liest alle Zeilen und berechnet Statistiken pro Spieler.
    Spalten: A=SpielerA, B=SpielerB, C=LegsA, D=LegsB, G=Gewinner
    """
    rows = sheet.get_all_values()
    stats = defaultdict(lambda: {"siege": 0, "niederlagen": 0, "spiele": 0})

    for row in rows:
        if len(row) < 7:
            continue
        p1 = row[0].strip()
        p2 = row[1].strip()
        winner = row[6].strip()
        if not p1 or not p2 or p1.lower() == "spieler a":
            continue
        stats[p1]["spiele"] += 1
        stats[p2]["spiele"] += 1
        if winner and winner.lower() != "unentschieden":
            if normalize(winner) == normalize(p1):
                stats[p1]["siege"] += 1
                stats[p2]["niederlagen"] += 1
            elif normalize(winner) == normalize(p2):
                stats[p2]["siege"] += 1
                stats[p1]["niederlagen"] += 1

    return stats


def get_streak_from_sheet(player_name):
    """Berechnet aktuelle Siegesserie eines Spielers.
    Spalten: A=SpielerA, B=SpielerB, G=Gewinner
    """
    rows = sheet.get_all_values()
    streak = 0
    for row in reversed(rows):
        if len(row) < 7:
            continue
        p1 = row[0].strip()
        p2 = row[1].strip()
        winner = row[6].strip()
        if p1.lower() == "spieler a":
            continue
        if normalize(p1) == normalize(player_name) or normalize(p2) == normalize(player_name):
            if normalize(winner) == normalize(player_name):
                streak += 1
            else:
                break
    return streak


def get_tabelle():
    """Berechnet die komplette Rangliste aus dem Sheet.
    Spalten: A=SpielerA, B=SpielerB, C=LegsA, D=LegsB, G=Gewinner (index 6)
    """
    rows = sheet.get_all_values()
    stats = {}

    for row in rows:
        # Überspringe Header oder unvollständige Zeilen
        if len(row) < 7:
            continue
        p1 = row[0].strip()
        p2 = row[1].strip()
        try:
            legs_a = int(row[2])
            legs_b = int(row[3])
        except:
            continue
        winner = row[6].strip()

        if not p1 or not p2:
            continue
        # Header-Zeile überspringen
        if p1.lower() == "spieler a":
            continue

        for p in [p1, p2]:
            if p not in stats:
                stats[p] = {"spiele": 0, "siege": 0, "niederlagen": 0, "legs_plus": 0, "legs_minus": 0}

        stats[p1]["spiele"] += 1
        stats[p1]["legs_plus"] += legs_a
        stats[p1]["legs_minus"] += legs_b

        stats[p2]["spiele"] += 1
        stats[p2]["legs_plus"] += legs_b
        stats[p2]["legs_minus"] += legs_a

        if winner and winner.lower() != "unentschieden":
            if winner in stats:
                stats[winner]["siege"] += 1
            loser = p2 if normalize(winner) == normalize(p1) else p1
            if loser in stats:
                stats[loser]["niederlagen"] += 1

    # Punkte berechnen: 3 pro Sieg
    result = []
    for name, s in stats.items():
        punkte = s["siege"] * 3
        leg_dif = s["legs_plus"] - s["legs_minus"]
        result.append({
            "name": name,
            "spiele": s["spiele"],
            "siege": s["siege"],
            "niederlagen": s["niederlagen"],
            "legs_plus": s["legs_plus"],
            "legs_minus": s["legs_minus"],
            "leg_dif": leg_dif,
            "punkte": punkte,
        })

    # Sortieren: Punkte desc, dann Leg-Differenz desc
    result.sort(key=lambda x: (x["punkte"], x["leg_dif"]), reverse=True)
    return result


def generate_tabelle_image(tabelle, title):
    """Generiert die Tabelle als Bild."""
    FONT_SIZE = 16
    PADDING = 16
    ROW_HEIGHT = 24
    BG_COLOR = (44, 47, 51)
    HEADER_COLOR = (255, 255, 255)
    ROW_COLOR = (220, 220, 220)
    ALT_ROW_COLOR = (180, 180, 180)
    SEP_COLOR = (100, 100, 100)
    TITLE_COLOR = (255, 255, 255)

    # Font laden
    import urllib.request, tempfile
    font_file = "/tmp/mono.ttf"
    if not os.path.exists(font_file):
        try:
            urllib.request.urlretrieve(
                "https://github.com/google/fonts/raw/main/apache/roboto/static/RobotoMono-Regular.ttf",
                font_file
            )
        except:
            font_file = None

    try:
        font = ImageFont.truetype(font_file, FONT_SIZE) if font_file else ImageFont.load_default()
        title_font = ImageFont.truetype(font_file, 18) if font_file else font
    except:
        font = ImageFont.load_default()
        title_font = font

    # Spalten definieren
    cols = ["Rg", "Name", "Sp", "S", "N", "L+", "L-", "Dif", "Pkt"]
    col_widths = [35, 180, 35, 35, 35, 45, 45, 45, 45]
    total_width = sum(col_widths) + PADDING * 2

    num_rows = len(tabelle)
    total_height = PADDING + 30 + ROW_HEIGHT + 4 + (num_rows * ROW_HEIGHT) + PADDING

    img = Image.new("RGB", (total_width, total_height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    y = PADDING
    # Titel
    draw.text((PADDING, y), title, font=title_font, fill=TITLE_COLOR)
    y += 30

    # Header
    x = PADDING
    for col, w in zip(cols, col_widths):
        draw.text((x, y), col, font=font, fill=HEADER_COLOR)
        x += w
    y += ROW_HEIGHT

    # Trennlinie
    draw.line([(PADDING, y), (total_width - PADDING, y)], fill=SEP_COLOR, width=1)
    y += 4

    # Zeilen
    for i, p in enumerate(tabelle):
        color = ALT_ROW_COLOR if i % 2 == 0 else ROW_COLOR
        values = [
            str(i + 1),
            p["name"],
            str(p["spiele"]),
            str(p["siege"]),
            str(p["niederlagen"]),
            str(p["legs_plus"]),
            str(p["legs_minus"]),
            str(p["leg_dif"]),
            str(p["punkte"]),
        ]
        x = PADDING
        for val, w in zip(values, col_widths):
            draw.text((x, y), val, font=font, fill=color)
            x += w
        y += ROW_HEIGHT

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def post_tabelle():
    """Postet die Tabelle in den Tabellen-Channel."""
    try:
        tabelle = get_tabelle()
        if not tabelle:
            return
        channel = await client.fetch_channel(TABELLE_CHANNEL_ID)
        title = f"Aktuelle Tabelle  {datetime.now().strftime('%d.%m.%Y %H:%M')} Uhr"
        img_buf = generate_tabelle_image(tabelle, title)
        await channel.send(file=discord.File(img_buf, filename="tabelle.png"))
    except Exception as e:
        print("❌ TABELLE ERROR:", e)


async def tabelle_scheduler():
    """Postet die Tabelle um 07:00, 14:00 und 22:00 Uhr (Europe/Berlin)."""
    await client.wait_until_ready()
    from datetime import timedelta, timezone
    # UTC Zeiten für 07:00, 14:00, 22:00 Europe/Berlin (UTC+2 im Sommer, UTC+1 im Winter)
    # Wir rechnen mit UTC+2 (Sommerzeit)
    UTC_OFFSET = 2
    post_times_local = [(7, 0), (14, 0), (22, 0)]
    post_times_utc = [((h - UTC_OFFSET) % 24, m) for h, m in post_times_local]

    while not client.is_closed():
        now = datetime.utcnow()
        next_post = None
        for hour, minute in sorted(post_times_utc):
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate > now:
                next_post = candidate
                break
        if next_post is None:
            next_post = (now + timedelta(days=1)).replace(
                hour=post_times_utc[0][0], minute=post_times_utc[0][1], second=0, microsecond=0
            )

        wait_seconds = (next_post - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        await post_tabelle()


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
    client.loop.create_task(tabelle_scheduler())


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
    if content.lower().startswith("!tabelle"):
        if not is_stats_channel:
            return
        try:
            tabelle = get_tabelle()
            if not tabelle:
                await message.channel.send("❌ Keine Daten gefunden.")
                return
            title = f"Aktuelle Tabelle  {datetime.now().strftime('%d.%m.%Y %H:%M')} Uhr"
            img_buf = generate_tabelle_image(tabelle, title)
            await message.channel.send(file=discord.File(img_buf, filename="tabelle.png"))
        except Exception as e:
            print("❌ TABELLE CMD ERROR:", e)
            await message.channel.send(f"❌ Fehler beim Laden der Tabelle: `{e}`")
        return

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
    # Prüfen ob beide Spieler als @ markiert wurden
    if len(message.mentions) < 2:
        await message.channel.send(
            "Ohne @ bin ich blind. Ich bin ein Bot, kein Hellseher 🔮\n"
            "⚠️ **Bitte Spieler mit @ markieren!**\n"
            "Beispiel: `@Red_Apple17 vs @Lanzi_90 3:2`"
        )
        return

    result = resolve_names(message, content)

    if not result:
        await message.channel.send("Selbst die KI schüttelt den Kopf 🤖\n❌ Format: Spieler A vs Spieler B 3:0")
        return

    p1, p2, s1, s2 = result
    s1 = int(s1)
    s2 = int(s2)

    # =========================
    # GLEICHER SPIELER CHECK
    # =========================
    if normalize(p1) == normalize(p2):
        await message.channel.send("🤦 Niemand kann gegen sich selbst spielen... oder doch? ❌")
        return

    # =========================
    # SCORE VALIDIERUNG
    # =========================
    if s1 == 0 and s2 == 0:
        await message.channel.send("0:0? Hat überhaupt jemand gespielt? 😂 ❌")
        return
    if s1 > 20 or s2 > 20:
        await message.channel.send("❌ Das ist Dart, kein Fußball. Unrealistischer Score!")
        return

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
    # MEILENSTEIN CHECK
    # =========================
    try:
        spielabsprachen = await client.fetch_channel(LOG_CHANNEL_ID)
        for player in [p1, p2]:
            await check_meilensteine(player, spielabsprachen)
    except Exception as e:
        print("❌ MEILENSTEIN FETCH ERROR:", e)

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
