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

        # --- CORREÇÃO: ENVIO IMEDIATO NO CANAL NOVO ---
        if last_id == 0:
            print(f"Inicializando {clean_channel}. Pegando a última notícia agora (id {posts[-1]['id']}).")
            # Em vez de ignorar, pega o post mais recente para enviar como teste
            new_posts = [posts[-1]]
        else:
            new_posts = [p for p in posts if p["id"] > last_id]

        for post in new_posts:
            clean_text = clean_post_text(post["text"])

            if is_channel_bio(clean_text):
                print(f"Ignorado (bio do canal): {clean_text[:60]}")
                continue

            if not clean_text:
                continue

            # Detecção inteligente de fonte
            fonte_detectada = detect_real_source(clean_text, clean_channel)
            
            # Remove a palavra isolada da agência se ela estiver sobrando
            clean_text = re.sub(r'(?i)^\s*(reuters|bloomberg|cnbc|wsj)\s*$', '', clean_text, flags=re.MULTILINE).strip()

            # Padronização de layout do Antes do Sino
            linhas = [l.strip() for l in clean_text.split("\n") if l.strip()]
            
            if not linhas:
                continue
                
            titulo_puro = linhas[0]
            
            # Análise básica de sentimento por palavra-chave
            titulo_lower = titulo_puro.lower()
            if any(w in titulo_lower for w in ["alta", "sobe", "lucro", "dispara", "recorde", "bullish"]):
                emoji_marcador = "🟢 <b>[ALTA]</b>"
            elif any(w in titulo_lower for w in ["queda", "cai", "prejuizo", "desaba", "recua", "bearish"]):
                emoji_marcador = "🟡 <b>[BAIXA]</b>"
            else:
                emoji_marcador = "⚪ <b>[INFORMATIVO]</b>"
                
            titulo = html_module.escape(titulo_puro, quote=False)
            
            # O resto das linhas vira o corpo da notícia (se houver)
            if len(linhas) > 1:
                corpo_puro = "\n".join(linhas[1:]).strip()
                # Remove também termos como "pontos-chave"
                corpo_puro = re.sub(r"(?i)pontos[- ]chave:?", "", corpo_puro)
                corpo = html_module.escape(corpo_puro, quote=False)
            else:
                corpo = ""
            
            fonte_tag = html_module.escape(fonte_detectada, quote=False)

            # Monta o design com as tags HTML estruturadas e limpas
            if corpo:
                message = f"{emoji_marcador} <b>{titulo}</b>\n\n{corpo}\n\n<i>Fonte: {fonte_tag}</i>"
            else:
                message = f"{emoji_marcador} <b>{titulo}</b>\n\n<i>Fonte: {fonte_tag}</i>"

            # Envia formatado
            if send_telegram_message(message):
                print(f"Encaminhado de {clean_channel} (id {post['id']}): {clean_text[:40]}...")
                state[clean_channel] = post["id"]
                has_updates = True
                time.sleep(3)

    if has_updates:
        save_state(state)
        print("Histórico updated e salvo com sucesso.")
    else:
        print("Nenhum post novo para processar.")
