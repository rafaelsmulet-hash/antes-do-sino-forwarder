def fetch_channel_posts(channel_username):
    channel_username = channel_username.lstrip("@").strip()
    url = f"https://t.me/s/{channel_username}"
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
            timeout=15,
        )
        # ADICIONADO PARA DIAGNÓSTICO: Se o Telegram bloquear o IP do GitHub, avisará no log
        if response.status_code != 200:
            print(f"🔴 ERRO DE CONEXÃO: O Telegram barrou o robô com Status {response.status_code} no canal {channel_username}")
            return []
            
        html_content = response.text
    except Exception as e:
        print(f"Erro de rede ao buscar canal {channel_username}: {e}")
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

    # ADICIONADO PARA DIAGNÓSTICO: Monitora se o Regex falhou em ler as mensagens
    if html_content and not posts:
        print(f"⚠️ ALERTA: O Telegram abriu a página de {channel_username}, mas o Regex não encontrou mensagens. O layout do HTML pode ter mudado.")

    posts.sort(key=lambda p: p["id"])
    return posts
