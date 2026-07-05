"""
Encaminhador de Canais - Antes do Sino (via web publica do Telegram)
Le os posts publicos de canais do Telegram atraves da pagina t.me/s/canal
(sem precisar de login/sessao) e encaminha para o grupo Antes do Sino
via bot normal.
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


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"AVISO: Falha ao carregar estado ({e}). Resetando.")
    return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"ERRO CRÍTICO ao salvar estado: {e}")


def fetch_channel_posts(channel_username):
    channel_username = channel_username.lstrip("@").strip()
    url = f"https://t.me/s/{channel_username}"
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
        )
        if response.status_code != 200:
            print(f"AVISO: Status {response.status_code} para o canal {channel_username}")
            return []
        html_content = response.text
    except Exception as e:
        print(f"Erro ao buscar canal {channel_username}: {e}")
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
    """
    Remove agressivamente links do concorrente, sites, e-mails e assinaturas.
    """
    # 1. Remove links diretos do Telegram (ex: t.me/panoramajonasesteves)
    text = re.sub(r"https?://t\.me/\S+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"t\.me/\S+", "", text, flags=re.IGNORECASE)
    
    # 2. Remove o site e e-mails do Jonas Esteves
    text = re.sub(r"jonasesteves\.com\S*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\S+@jonasesteves\S+", "", text, flags=re.IGNORECASE)
    
    # 3. Remove assinaturas e termos fixos conhecidos
    text = re.sub(r"\n*Grupo Bovespa News\s*$", "", text, flags=re.IGNORECASE)
    
    # 4. Limpa espaços em branco e quebras de linha duplicadas que sobraram no fim
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def is_channel_bio(text):
    bio_markers = [
        "ver canal", "para entrar em contato", "@jonasesteves", 
        "contato@", "assine o premium", "clique aqui", "parcerias:"
    ]
    lower_text = text.lower()
    return any(marker in lower_text for marker in bio_markers)


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TARGET_CHAT_ID, 
        "text": text, 
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 429:
            retry_after = r.json().get("parameters", {}).get("retry_after", 5)
            time.sleep(retry_after)
            r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"Erro Telegram (status {r.status_code}): {r.text}")
        return r.status_code == 200
    except Exception as e:
        print(f"Erro Telegram: {e}")
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
            print(f"AVISO: nenhum post encontrado para {clean_channel}")
            continue

        if last_id == 0:
            state[clean_channel] = posts[-1]["id"]
            has_updates = True
            print(f"Inicializado {clean_channel} no post {posts[-1]['id']}")
            continue

        new_posts = [p for p in posts if p["id"] > last_id]

        for post in new_posts:
            clean_text = clean_post_text(post["text"])

            if is_channel_bio(clean_text):
                print(f"Ignorado (bio do canal): {clean_text[:60]}")
                continue

            if not clean_text:
                continue

            # --- PADRONIZAÇÃO DE LAYOUT DO ANTES DO SINO ---
            linhas = clean_text.split("\n")
            titulo = html_module.escape(linhas[0].strip(), quote=False)
            
            # O resto das linhas vira o corpo da notícia (se houver)
            if len(linhas) > 1:
                corpo_puro = "\n".join(linhas[1:]).strip()
                corpo = html_module.escape(corpo_puro, quote=False)
            else:
                corpo = ""
            
            fonte_tag = html_module.escape(clean_channel.upper(), quote=False)

            # Monta o design com tags HTML seguras
            if corpo:
                message = f"🔔 <b>{titulo}</b>\n\n{corpo}\n\n<i>Fonte: {fonte_tag}</i>"
            else:
                message = f"🔔 <b>{titulo}</b>\n\n<i>Fonte: {fonte_tag}</i>"

            # Envia formatado
            if send_telegram_message(message):
                print(f"Encaminhado de {clean_channel} (id {post['id']}): {clean_text[:40]}...")
                state[clean_channel] = post["id"]
                has_updates = True
                time.sleep(3)

    if has_updates:
        save_state(state)
        print("Histórico atualizado e salvo com sucesso.")
    else:
        print("Nenhum post novo para processar.")


if __name__ == "__main__":
    main()
