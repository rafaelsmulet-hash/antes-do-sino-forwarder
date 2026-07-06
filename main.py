"""
Encaminhador de Canais - Antes do Sino (via web publica do Telegram)
Le os posts publicos de canais do Telegram atraves da pagina t.me/s/canal
(sem precisar de login/sessao) e encaminha para o grupo Antes do Sino
via bot normal, no mesmo layout visual do bot de noticias principal.
"""

import requests
import re
import os
import json
import time
import html as html_module

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TARGET_CHAT_ID = os.environ.get("TARGET_CHAT_ID", "")

SOURCE_CHANNELS = [
    os.environ.get("SOURCE_CHANNEL_1", ""),
    os.environ.get("SOURCE_CHANNEL_2", ""),
]

STATE_FILE = "forwarder_state.json"

CHANNEL_DISPLAY_NAMES = {
    "panoramajonasesteves": "Panorama Jonas Esteves",
    "grupobovespanews": "Grupo Bovespa News",
}

KNOWN_AGENCIES = ["Reuters", "Bloomberg", "CNBC", "WSJ", "AFP", "Bovespa News"]


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def fetch_channel_posts(channel_username):
    channel_username = channel_username.lstrip("@")
    url = "https://t.me/s/" + channel_username
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
        )
        html_content = response.text
    except Exception as e:
        print("Erro ao buscar canal " + channel_username + ": " + str(e))
        return []

    pattern = re.compile(
        r'data-post="' + re.escape(channel_username) + r'/(\d+)"(.*?)(?=data-post="' + re.escape(channel_username) + r'/\d+"|$)',
        re.DOTALL | re.IGNORECASE,
    )

    posts = []
    for match in pattern.finditer(html_content):
        post_id = int(match.group(1))
        block = match.group(2)

        text_match = re.search(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            block,
            re.DOTALL,
        )
        if not text_match:
            continue

        raw_text = text_match.group(1)
        raw_text = re.sub(r"<br\s*/?>", "\n", raw_text)
        clean_text = re.sub(r"<[^>]+>", "", raw_text)
        clean_text = html_module.unescape(clean_text).strip()

        if clean_text:
            posts.append({"id": post_id, "text": clean_text})

    posts.sort(key=lambda p: p["id"])
    return posts


def clean_post_text(text):
    text = re.sub(r"\n*Grupo Bovespa News\s*$", "", text, flags=re.IGNORECASE).strip()
    return text


def is_channel_bio(text):
    bio_markers = ["ver canal", "para entrar em contato", "@jonasesteves", "contato@"]
    lower_text = text.lower()
    return any(marker in lower_text for marker in bio_markers)


def detect_real_source(clean_text, clean_channel):
    for agency in KNOWN_AGENCIES:
        if agency.lower() in clean_text.lower():
            return agency
    return CHANNEL_DISPLAY_NAMES.get(clean_channel.lower(), clean_channel)


def send_telegram_message(text):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    payload = {"chat_id": TARGET_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 429:
            retry_after = r.json().get("parameters", {}).get("retry_after", 5)
            time.sleep(retry_after)
            r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print("Erro Telegram (status " + str(r.status_code) + "): " + r.text)
        return r.status_code == 200
    except Exception as e:
        print("Erro Telegram: " + str(e))
        return False


def main():
    if not TELEGRAM_BOT_TOKEN or not TARGET_CHAT_ID:
        print("ERRO: configure TELEGRAM_BOT_TOKEN e TARGET_CHAT_ID.")
        return

    state = load_state()
    has_updates = False

    for channel in SOURCE_CHANNELS:
        if not channel:
            continue

        clean_channel = channel.lstrip("@").strip()
        last_id = state.get(clean_channel, 0)
        posts = fetch_channel_posts(clean_channel)

        if not posts:
            print("AVISO: nenhum post encontrado para " + clean_channel)
            continue

        if last_id == 0:
            print("Inicializando " + clean_channel + ". Pegando a ultima noticia agora (id " + str(posts[-1]["id"]) + ").")
            new_posts = [posts[-1]]
        else:
            new_posts = [p for p in posts if p["id"] > last_id]

        for post in new_posts:
            clean_text = clean_post_text(post["text"])

            if is_channel_bio(clean_text):
                print("Ignorado (bio do canal): " + clean_text[:60])
                continue

            if not clean_text:
                continue

            fonte_detectada = detect_real_source(clean_text, clean_channel)

            clean_text = re.sub(
                r'(?i)^\s*(reuters|bloomberg|cnbc|wsj)\s*$', '', clean_text, flags=re.MULTILINE
            ).strip()

            linhas = [l.strip() for l in clean_text.split("\n") if l.strip()]

            if not linhas:
                continue

            titulo_puro = linhas[0]

            titulo_lower = titulo_puro.lower()
            if any(w in titulo_lower for w in ["alta", "sobe", "lucro", "dispara", "recorde", "bullish"]):
                emoji_marcador = "\U0001F7E2 <b>[ALTA]</b>"
            elif any(w in titulo_lower for w in ["queda", "cai", "prejuizo", "desaba", "recua", "bearish"]):
                emoji_marcador = "\U0001F7E1 <b>[BAIXA]</b>"
            else:
                emoji_marcador = "\u26AA <b>[INFORMATIVO]</b>"

            titulo = html_module.escape(titulo_puro, quote=False)

            if len(linhas) > 1:
                corpo_puro = "\n".join(linhas[1:]).strip()
                corpo_puro = re.sub(r"(?i)pontos[- ]chave:?", "", corpo_puro)
                corpo = html_module.escape(corpo_puro, quote=False)
            else:
                corpo = ""

            fonte_tag = html_module.escape(fonte_detectada, quote=False)

            if corpo:
                message = emoji_marcador + " <b>" + titulo + "</b>\n\n" + corpo + "\n\n<i>Fonte: " + fonte_tag + "</i>"
            else:
                message = emoji_marcador + " <b>" + titulo + "</b>\n\n<i>Fonte: " + fonte_tag + "</i>"

            if len(message) > 3900:
                message = message[:3900] + "..."

            if send_telegram_message(message):
                print("Encaminhado de " + clean_channel + " (id " + str(post["id"]) + "): " + clean_text[:40] + "...")
                state[clean_channel] = post["id"]
                has_updates = True
                time.sleep(3)

    if has_updates:
        save_state(state)
        print("Historico atualizado e salvo com sucesso.")
    else:
        print("Nenhum post novo para processar.")


if __name__ == "__main__":
    main()
