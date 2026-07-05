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

            # --- DETECÇÃO INTELIGENTE DE FONTE ---
            fonte_detectada = detect_real_source(clean_text, clean_channel)
            
            # Remove a palavra isolada da agência se ela estiver sobrando em uma linha única do texto limpo
            clean_text = re.sub(r'(?i)^\s*(reuters|bloomberg|cnbc|wsj)\s*$', '', clean_text, flags=re.MULTILINE).strip()

            # --- PADRONIZAÇÃO DE LAYOUT DO ANTES DO SINO ---
            linhas = [l.strip() for l in clean_text.split("\n") if l.strip()]
            
            # CORRIGIDO AQUI: mudado de 'lines' para 'linhas'
            if not linhas:
                continue
                
            titulo = html_module.escape(linhas[0], quote=False)
            
            # O resto das linhas vira o corpo da notícia (se houver)
            if len(linhas) > 1:
                corpo_puro = "\n".join(linhas[1:]).strip()
                corpo = html_module.escape(corpo_puro, quote=False)
            else:
                corpo = ""
            
            fonte_tag = html_module.escape(fonte_detectada, quote=False)

            # Monta o design com as tags HTML estruturadas e limpas
            if corpo:
                message = f"<b>🔔 {titulo}</b>\n\n{corpo}\n\n<i>Fonte: {fonte_tag}</i>"
            else:
                message = f"<b>🔔 {titulo}</b>\n\n<i>Fonte: {fonte_tag}</i>"

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
