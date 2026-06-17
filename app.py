import os
import requests
import psycopg2
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
# Chave alterada para forçar o logout de quem estava com o ecrã antigo em cache
app.secret_key = 'arena_maquinas_2026_super_blindada'

# --- GESTÃO FÁCIL DE USUÁRIOS E SENHAS ---
USUARIOS_PERMITIDOS = {
    "Joao mano": "JMOV123", 
    "Lucas": "LCS123", 
    "Matheus": "MCINTRA123",
    "Pedro": "PHACY123", 
    "Joao Vitor": "JVND123", 
    "Magno": "GMAS123",
    "Salsicha": "AVRZ123", 
    "Sauer": "admin123",
    "Teste": "teste00",          
    "Enzo": "enzoflamengo123",    
    "Natan Sauer": "ns1234",      
    "Pedro Sauer": "ps5678",
    "Juliao": "carloscu2026"
    }

cache_dados = {"jogos_arena": [], "jogos_futuros": [], "classificacao": [], "artilheiros": [], "ultima_atualizacao": None, "tem_jogo_ao_vivo": False}
config_app = {"manutencao": False}

STAGE_ORDER = {
    'GROUP_STAGE': 1, 'LAST_16': 2, 'QUARTER_FINALS': 3,
    'SEMI_FINALS': 4, 'THIRD_PLACE': 5, 'FINAL': 6
}

@app.before_request
def checar_manutencao():
    if config_app["manutencao"] and request.endpoint not in ['login', 'admin_toggle_manutencao', 'admin_forcar_update'] and not request.path.startswith('/static'):
        if session.get('usuario') != 'Teste':
            return "<body style='background:#121212; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;'><h1 style='color:#ffcc00; font-family:sans-serif; text-align:center;'>🛠️ CALMA, ESTAMOS EM MANUTENÇÃO</h1></body>", 503

def obter_dados_copa():
    agora = datetime.now(timezone.utc)
    minutos_espera = 1 if cache_dados["tem_jogo_ao_vivo"] else 10
    
    if cache_dados["ultima_atualizacao"] and (agora - cache_dados["ultima_atualizacao"]) < timedelta(minutes=minutos_espera):
        return cache_dados
        
    headers = { 'X-Auth-Token': os.environ.get('API_KEY') }
    
    try:
        res_jogos = requests.get("https://api.football-data.org/v4/competitions/WC/matches", headers=headers).json()
        matches = res_jogos.get('matches', [])
        
        max_stage = 1
        for m in matches:
            if m.get('status') in ['IN_PLAY', 'PAUSED', 'FINISHED', 'AWARDED']:
                stg = m.get('stage', 'GROUP_STAGE')
                max_stage = max(max_stage, STAGE_ORDER.get(stg, 1))

        jogos_arena = []
        jogos_futuros = []
        tem_ao_vivo_agora = False
        limite_24h = agora + timedelta(hours=24)
        
        for match in matches:
            time_a = match.get('homeTeam', {}).get('shortName') or match.get('homeTeam', {}).get('name') or "A Definir"
            time_b = match.get('awayTeam', {}).get('shortName') or match.get('awayTeam', {}).get('name') or "A Definir"
            crest_a = match.get('homeTeam', {}).get('crest', '')
            crest_b = match.get('awayTeam', {}).get('crest', '')
            fase = match.get('stage', '').replace('_', ' ').title()
            grupo = match.get('group', '').replace('_', ' ') if match.get('group') else ''
            
            gols_a = match.get('score', {}).get('fullTime', {}).get('home')
            gols_b = match.get('score', {}).get('fullTime', {}).get('away')
            penaltis_a = match.get('score', {}).get('penalties', {}).get('home')
            penaltis_b = match.get('score', {}).get('penalties', {}).get('away')
            placar_penaltis = f" (Pên: {penaltis_a}x{penaltis_b})" if penaltis_a is not None else ""
            placar = "- x -" if gols_a is None else f"{gols_a} x {gols_b}{placar_penaltis}"
            status_api = match.get('status')
            
            if status_api in ['IN_PLAY', 'PAUSED']: status = "AO VIVO"; tem_ao_vivo_agora = True
            elif status_api in ['FINISHED', 'AWARDED']: status = "ENCERRADO"
            else: status = "EM BREVE..."
                
            dt_obj = datetime.strptime(match['utcDate'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            dt_local = dt_obj - timedelta(hours=4)
            
            jogo_formatado = {
                "id": match['id'], "time_a": time_a, "time_b": time_b, "crest_a": crest_a, "crest_b": crest_b,
                "placar": placar, "status": status, "info_fase": f"{fase} {grupo}".strip(), 
                "timestamp": dt_obj.timestamp(), "data_str": dt_local.strftime('%d/%m %H:%M'),
                "gols_a_real": str(gols_a) if gols_a is not None else "N/A",
                "gols_b_real": str(gols_b) if gols_b is not None else "N/A"
            }

            stg_level = STAGE_ORDER.get(match.get('stage', 'GROUP_STAGE'), 1)
            
            if status in ['AO VIVO', 'ENCERRADO']:
                if stg_level >= max_stage - 1: jogos_arena.append(jogo_formatado)
            else:
                if dt_obj <= limite_24h: jogos_arena.append(jogo_formatado)
                else: jogos_futuros.append(jogo_formatado)
            
        jogos_arena.sort(key=lambda x: x['timestamp'], reverse=True)
        jogos_futuros.sort(key=lambda x: x['timestamp'])
        
        res_art = requests.get("https://api.football-data.org/v4/competitions/WC/scorers", headers=headers).json()
        artilheiros = [{ "nome": s.get('player', {}).get('name'), "time": s.get('team', {}).get('name'), "gols": s.get('goals') } for s in res_art.get('scorers', [])[:5]]
            
        res_stand = requests.get("https://api.football-data.org/v4/competitions/WC/standings", headers=headers).json()
        classificacao = []
        if 'standings' in res_stand:
            for group in res_stand['standings']:
                if group['type'] == 'TOTAL':
                    classificacao.append({
                        'grupo': group.get('group', '').replace('_', ' '),
                        'times': [{'nome': t['team'].get('shortName') or t['team'].get('name'), 'crest': t['team'].get('crest', ''), 'pts': t['points'], 'pj': t['playedGames'], 'v': t['won'], 'e': t['draw'], 'd': t['lost'], 'sg': t['goalDifference']} for t in group['table']]
                    })

        cache_dados.update({"jogos_arena": jogos_arena, "jogos_futuros": jogos_futuros, "classificacao": classificacao, "artilheiros": artilheiros, "ultima_atualizacao": agora, "tem_jogo_ao_vivo": tem_ao_vivo_agora})
        return cache_dados
    except Exception as e: return cache_dados

def get_db_connection(): return psycopg2.connect(os.environ['DATABASE_URL'])

def criar_tabela():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''CREATE TABLE IF NOT EXISTS palpites (id SERIAL PRIMARY KEY, usuario VARCHAR(50), jogo_id INT, gols_a VARCHAR(10), gols_b VARCHAR(10), amarelos VARCHAR(50), vermelhos VARCHAR(50), subs VARCHAR(50), acrescimo VARCHAR(50), penaltis VARCHAR(50), autor_gol VARCHAR(50))''')
        conn.commit()

        def add_col(table, col, type_def):
            try:
                cur.execute(f'ALTER TABLE {table} ADD COLUMN {col} {type_def}')
                conn.commit()
            except Exception:
                conn.rollback()

        for col in ['amarelos', 'vermelhos', 'subs', 'acrescimo', 'penaltis', 'autor_gol']:
            add_col('palpites', col, 'VARCHAR(50)')
        
        add_col('palpites', 'turbo', 'BOOLEAN DEFAULT FALSE')
        add_col('palpites', 'data_registro', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        add_col('palpites', 'racha_desafio', 'VARCHAR(50)')

        cur.execute('''CREATE TABLE IF NOT EXISTS jogos_admin (jogo_id INT PRIMARY KEY, link_stream VARCHAR(255), amarelos VARCHAR(50), vermelhos VARCHAR(50), acrescimo VARCHAR(50), penaltis VARCHAR(50), artilheiro VARCHAR(50))''')
        conn.commit()
        
        add_col('jogos_admin', 'status_manual', 'VARCHAR(20)')
        
        cur.close()
        conn.close()
    except Exception as e:
        print("Erro crítico na tabela:", e)

criar_tabela()

def validar_num(valor):
    if valor is None or str(valor).strip() == '': return True
    try: return 0 <= int(valor) <= 99
    except: return False

def processar_ranking_e_financas():
    dados_api = obter_dados_copa()
    todos_jogos = {j['id']: j for j in dados_api.get("jogos_arena", []) + dados_api.get("jogos_futuros", [])}
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT jogo_id, link_stream, amarelos, vermelhos, acrescimo, penaltis, artilheiro, status_manual FROM jogos_admin")
    admin_data = {r[0]: {'link': r[1], 'amarelos': r[2], 'vermelhos': r[3], 'acrescimo': r[4], 'penaltis': r[5], 'artilheiro': r[6], 'status_manual': r[7]} for r in cur.fetchall()}
    
    cur.execute("SELECT id, usuario, jogo_id, gols_a, gols_b, amarelos, vermelhos, acrescimo, penaltis, autor_gol, turbo, racha_desafio FROM palpites")
    todos_palpites = cur.fetchall()
    cur.close(); conn.close()
    
    palpites_por_jogo = {}
    for p in todos_palpites:
        j_id = p[2]
        palpites_por_jogo.setdefault(j_id, []).append(p)
        
    usuarios_stats = {u: {"pontos": 0, "cravadas": 0, "vencedores": 0, "gasto_valido": 0.0, "total_palpites_validos": 0, "maior_erro": 0, "artilheiros_certos": 0, "historico_grafico": []} for u in USUARIOS_PERMITIDOS}
    total_pool_grupo = 0.0
    bingos_jogos = {} 
    na_trave_jogos = {} 
    
    for j_id, palpites in palpites_por_jogo.items():
        jogo = todos_jogos.get(j_id)
        adm = admin_data.get(j_id, {})
        
        status_final = jogo['status'] if jogo else 'EM BREVE...'
        if adm.get('status_manual'):
            if jogo and jogo['status'] == 'ENCERRADO' and adm['status_manual'] == 'AO VIVO': status_final = 'ENCERRADO'
            else: status_final = adm['status_manual']
            
        g_a_real = jogo['gols_a_real'] if jogo else 'N/A'
        g_b_real = jogo['gols_b_real'] if jogo else 'N/A'
        
        classes_apostadores = { 'placar': [], 'amarelos': [], 'vermelhos': [], 'acrescimo': [], 'penaltis': [], 'artilheiro': [] }
        classes_ganhadores = { 'placar': False, 'amarelos': False, 'vermelhos': False, 'acrescimo': False, 'penaltis': False, 'artilheiro': False }
        
        for p in palpites:
            pid, user, _, ga, gb, am, vm, ac, pe, art, turbo, racha = p
            if user not in usuarios_stats: continue
            if ga and gb and str(ga)!='None' and str(gb)!='None': classes_apostadores['placar'].append(p)
            if am and str(am)!='None': classes_apostadores['amarelos'].append(p)
            if vm and str(vm)!='None': classes_apostadores['vermelhos'].append(p)
            if ac and str(ac)!='None': classes_apostadores['acrescimo'].append(p)
            if pe and str(pe)!='None': classes_apostadores['penaltis'].append(p)
            if art and str(art)!='None': classes_apostadores['artilheiro'].append(p)

        if status_final == 'ENCERRADO' and g_a_real != 'N/A' and g_b_real != 'N/A':
            ga_r, gb_r = int(g_a_real), int(g_b_real)
            
            for p in classes_apostadores['placar']:
                if int(p[3]) == ga_r and int(p[4]) == gb_r: classes_ganhadores['placar'] = True
            for p in classes_apostadores['amarelos']:
                if adm.get('amarelos') and str(p[5]).strip() == str(adm['amarelos']).strip(): classes_ganhadores['amarelos'] = True
            for p in classes_apostadores['vermelhos']:
                if adm.get('vermelhos') and str(p[6]).strip() == str(adm['vermelhos']).strip(): classes_ganhadores['vermelhos'] = True
            for p in classes_apostadores['acrescimo']:
                if adm.get('acrescimo') and str(p[7]).strip() == str(adm['acrescimo']).strip(): classes_ganhadores['acrescimo'] = True
            for p in classes_apostadores['penaltis']:
                if adm.get('penaltis') and str(p[8]).strip().lower() == str(adm['penaltis']).strip().lower(): classes_ganhadores['penaltis'] = True
            for p in classes_apostadores['artilheiro']:
                if adm.get('artilheiro') and str(p[9]).strip().lower() == str(adm['artilheiro']).strip().lower(): classes_ganhadores['artilheiro'] = True

            pontos_jogo_usuario = {}
            for p in palpites:
                pid, user, _, ga, gb, am, vm, ac, pe, art, turbo, racha = p
                if user not in usuarios_stats: continue
                
                pts_ganhos = 0
                is_bingo = True 
                
                if ga and gb and str(ga)!='None' and str(gb)!='None':
                    ga_a, gb_a = int(ga), int(gb)
                    acertou_a = (ga_a == ga_r)
                    acertou_b = (gb_a == gb_r)
                    
                    if acertou_a and acertou_b:
                        pts_ganhos += 5; usuarios_stats[user]['cravadas'] += 1
                    elif acertou_a or acertou_b:
                        pts_ganhos += 1 
                        na_trave_jogos.setdefault(j_id, []).append(user)
                        is_bingo = False
                        if (ga_r > gb_r and ga_a > gb_a) or (ga_r < gb_r and ga_a < gb_a) or (ga_r == gb_r and ga_a == gb_a):
                            pts_ganhos += 2; usuarios_stats[user]['vencedores'] += 1
                    else:
                        is_bingo = False
                        if (ga_r > gb_r and ga_a > gb_a) or (ga_r < gb_r and ga_a < gb_a) or (ga_r == gb_r and ga_a == gb_a):
                            pts_ganhos += 2; usuarios_stats[user]['vencedores'] += 1
                        
                    erro = abs(ga_r - ga_a) + abs(gb_r - gb_a)
                    if erro > usuarios_stats[user]['maior_erro']: usuarios_stats[user]['maior_erro'] = erro
                else: is_bingo = False
                    
                if am and str(am)!='None':
                    if not (adm.get('amarelos') and str(am).strip() == str(adm['amarelos']).strip()): is_bingo = False
                if vm and str(vm)!='None':
                    if not (adm.get('vermelhos') and str(vm).strip() == str(adm['vermelhos']).strip()): is_bingo = False
                if ac and str(ac)!='None':
                    if not (adm.get('acrescimo') and str(ac).strip() == str(adm['acrescimo']).strip()): is_bingo = False
                if pe and str(pe)!='None':
                    if not (adm.get('penaltis') and str(pe).strip().lower() == str(adm['penaltis']).strip().lower()): is_bingo = False
                if art and str(art)!='None':
                    if adm.get('artilheiro') and str(art).strip().lower() == str(adm['artilheiro']).strip().lower():
                        usuarios_stats[user]['artilheiros_certos'] += 1
                    else: is_bingo = False

                if turbo: pts_ganhos *= 2
                pontos_jogo_usuario[user] = {"pts": pts_ganhos, "racha": racha, "is_bingo": is_bingo}

            for user, p_data in pontos_jogo_usuario.items():
                racha_alvo = p_data['racha']
                final_pts = p_data['pts']
                if racha_alvo in pontos_jogo_usuario:
                    if p_data['pts'] > pontos_jogo_usuario[racha_alvo]['pts']: final_pts *= 2
                
                usuarios_stats[user]['pontos'] += final_pts
                usuarios_stats[user]['historico_grafico'].append(final_pts)
                if p_data['is_bingo']: bingos_jogos.setdefault(j_id, []).append(user)

            for cl, lista_p in classes_apostadores.items():
                if len(lista_p) >= 2 and classes_ganhadores[cl]:
                    for p in lista_p:
                        u = p[1]
                        usuarios_stats[u]['gasto_valido'] += 0.50
                        usuarios_stats[u]['total_palpites_validos'] += 1
                        total_pool_grupo += 0.50

    return usuarios_stats, total_pool_grupo, bingos_jogos, na_trave_jogos

@app.route('/')
def index():
    if 'usuario' not in session: return redirect(url_for('login'))
    user_logado = session['usuario']
    
    stats, total_pool, bingos, na_trave = processar_ranking_e_financas()
    dados = obter_dados_copa()
    jogos = dados["jogos_arena"]
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT jogo_id, link_stream, amarelos, vermelhos, acrescimo, penaltis, artilheiro, status_manual FROM jogos_admin")
    admin_data = {r[0]: {'link': r[1], 'amarelos': r[2], 'vermelhos': r[3], 'acrescimo': r[4], 'penaltis': r[5], 'artilheiro': r[6], 'status_manual': r[7]} for r in cur.fetchall()}
    
    cur.execute("SELECT jogo_id FROM palpites WHERE usuario = %s", (user_logado,))
    jogos_palpitados = set([r[0] for r in cur.fetchall()])
    cur.close(); conn.close()
    
    for jogo in jogos:
        jogo['ja_palpitado'] = jogo['id'] in jogos_palpitados
        jogo['bingo_vencedores'] = bingos.get(jogo['id'], [])
        jogo['na_trave_vencedores'] = na_trave.get(jogo['id'], [])
    
    gasto_str = f"{total_pool:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    return render_template('index.html', usuario=user_logado, jogos=jogos, admin_data=admin_data, gasto=gasto_str, usuarios_lista=USUARIOS_PERMITIDOS.keys(), manutencao=config_app["manutencao"])

@app.route('/perfil')
def perfil():
    if 'usuario' not in session: return redirect(url_for('login'))
    user = session['usuario']
    
    stats, _, _, _ = processar_ranking_e_financas()
    user_stats = stats.get(user, {"pontos": 0, "cravadas": 0, "vencedores": 0, "gasto_valido": 0.0, "total_palpites_validos": 0, "maior_erro": 0, "artilheiros_certos": 0, "historico_grafico": []})
    
    total_validos = user_stats['total_palpites_validos']
    taxa = (user_stats['cravadas'] / total_validos * 100) if total_validos > 0 else 0
    user_stats['taxa'] = f"{taxa:.1f}%"
    
    conquistas = []
    if user_stats['maior_erro'] >= 5: conquistas.append({"nome": "🦶 PÉ FRIO / BOCA PODRE", "desc": "Errou um placar por uma diferença monumental de 5 ou mais gols. Calibra essa luneta!"})
    if user_stats['cravadas'] >= 3: conquistas.append({"nome": "🔮 MÃE DINÁH DA ARENA", "desc": "Cravou 3 ou mais placares cheios na mosca. Visão de águia!"})
    if user_stats['artilheiros_certos'] >= 2: conquistas.append({"nome": "⚽ CHEIRA-GOL", "desc": "Acertou o artilheiro oficial da partida por 2 ou mais vezes."})
    if user_stats['pontos'] >= 30: conquistas.append({"nome": "👑 CAMISA 10 DA RESENHA", "desc": "Passou a marca histórica dos 30 pontos globais no bolão."})
    if not conquistas: conquistas.append({"nome": "🏃 NO AQUECIMENTO", "desc": "Ainda pegando o ritmo de jogo na pista. Seus troféus vão aparecer aqui!"})

    return render_template('perfil.html', usuario=user, stats=user_stats, conquistas=conquistas)

@app.route('/info')
def info_torneio():
    if 'usuario' not in session: return redirect(url_for('login'))
    
    stats, _, _, _ = processar_ranking_e_financas()
    ranking = sorted([{"nome": u, "pontos": stats[u]["pontos"], "cravadas": stats[u]["cravadas"], "gasto": stats[u]["gasto_valido"]} for u in stats], key=lambda x: x['pontos'], reverse=True)[:3]
    
    dados = obter_dados_copa()
    return render_template('info.html', usuario=session['usuario'], ranking=ranking, classificacao=dados['classificacao'], jogos_futuros=dados['jogos_futuros'], artilheiros=dados['artilheiros'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario' in session: return redirect(url_for('index'))
    erro = None
    if request.method == 'POST':
        user = request.form.get('usuario')
        pwd = request.form.get('senha')
        if user in USUARIOS_PERMITIDOS and USUARIOS_PERMITIDOS[user] == pwd:
            session['usuario'] = user
            return redirect(url_for('index'))
        else: erro = "Acesso negado. Credenciais inválidas."
    return render_template('login.html', erro=erro)

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('login'))

@app.route('/apostar', methods=['POST'])
def apostar():
    if 'usuario' not in session: return jsonify({"sucesso": False, "erro": "Sessão expirada."}), 401
    dados = request.json
    jogo_id = dados.get('jogo_id')
    usa_turbo = dados.get('turbo', False)
    racha_target = dados.get('racha', '')
    
    campos_numericos = ['gols_a', 'gols_b', 'amarelos', 'vermelhos', 'acrescimo']
    if not all(validar_num(dados.get(c)) for c in campos_numericos):
        return jsonify({"sucesso": False, "erro": "Valores devem ser estritamente entre 0 e 99!"}), 400
        
    artilheiro = str(dados.get('artilheiro', '')).strip()
    if len(artilheiro) > 20: return jsonify({"sucesso": False, "erro": "O nome do artilheiro aceita no máximo 20 caracteres!"}), 400

    dados_api = obter_dados_copa()
    todos = dados_api.get("jogos_arena", []) + dados_api.get("jogos_futuros", [])
    jogo_atual = next((j for j in todos if str(j['id']) == str(jogo_id)), None)
    
    if jogo_atual:
        limite_aposta = jogo_atual['timestamp'] + (15 * 60)
        if datetime.now(timezone.utc).timestamp() > limite_aposta:
            return jsonify({"sucesso": False, "erro": "As apostas fecharam! Bola rolando a mais de 15 minutos."}), 400

    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id FROM palpites WHERE usuario = %s AND jogo_id = %s", (session['usuario'], jogo_id))
    if cur.fetchone(): cur.close(); conn.close(); return jsonify({"sucesso": False, "erro": "Aposta já enviada para este jogo!"}), 400
    
    if usa_turbo:
        cur.execute("SELECT COUNT(*) FROM palpites WHERE usuario = %s AND turbo = TRUE AND DATE(data_registro) = CURRENT_DATE", (session['usuario'],))
        if cur.fetchone()[0] > 0:
            cur.close(); conn.close()
            return jsonify({"sucesso": False, "erro": "Você já gastou seu Botão Booster de hoje!"}), 400

    cur.execute("INSERT INTO palpites (usuario, jogo_id, gols_a, gols_b, amarelos, vermelhos, acrescimo, penaltis, autor_gol, turbo, racha_desafio) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", 
                (session['usuario'], jogo_id, dados.get('gols_a'), dados.get('gols_b'), dados.get('amarelos', ''), dados.get('vermelhos', ''), dados.get('acrescimo', ''), dados.get('penaltis', ''), artilheiro, usa_turbo, racha_target))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"sucesso": True})

@app.route('/admin_forcar_update', methods=['POST'])
def admin_forcar_update():
    if session.get('usuario') == 'Teste':
        cache_dados['ultima_atualizacao'] = None
        obter_dados_copa()
        return jsonify({"sucesso": True})
    return jsonify({"sucesso": False})

@app.route('/admin_toggle_manutencao', methods=['POST'])
def toggle_manutencao():
    if session.get('usuario') == 'Teste':
        config_app['manutencao'] = not config_app['manutencao']
        return jsonify({"sucesso": True, "estado": config_app['manutencao']})
    return jsonify({"sucesso": False})

@app.route('/admin_salvar_jogo', methods=['POST'])
def admin_salvar_jogo():
    if session.get('usuario') != 'Teste': return jsonify({"sucesso": False, "erro": "Acesso negado."})
    d = request.json
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute('''INSERT INTO jogos_admin (jogo_id, link_stream, amarelos, vermelhos, acrescimo, penaltis, artilheiro, status_manual) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (jogo_id) DO UPDATE SET 
                       link_stream=EXCLUDED.link_stream, amarelos=EXCLUDED.amarelos, vermelhos=EXCLUDED.vermelhos, 
                       acrescimo=EXCLUDED.acrescimo, penaltis=EXCLUDED.penaltis, artilheiro=EXCLUDED.artilheiro, status_manual=EXCLUDED.status_manual''', 
                    (d.get('jogo_id'), d.get('link_stream'), d.get('amarelos'), d.get('vermelhos'), d.get('acrescimo'), d.get('penaltis'), d.get('artilheiro'), d.get('status_manual')))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"sucesso": True})
    except Exception as e: return jsonify({"sucesso": False, "erro": str(e)})

@app.route('/admin_editar_aposta', methods=['POST'])
def admin_editar_aposta():
    if session.get('usuario') != 'Teste': return jsonify({"sucesso": False, "erro": "Acesso negado."})
    d = request.json
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute('''UPDATE palpites SET gols_a=%s, gols_b=%s, amarelos=%s, vermelhos=%s, acrescimo=%s, penaltis=%s, autor_gol=%s WHERE id=%s''',
                    (d.get('gols_a'), d.get('gols_b'), d.get('amarelos'), d.get('vermelhos'), d.get('acrescimo'), d.get('penaltis'), d.get('artilheiro'), d.get('aposta_id')))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"sucesso": True})
    except Exception as e: return jsonify({"sucesso": False, "erro": str(e)})

@app.route('/apostas_publicas')
def apostas_publicas():
    if 'usuario' not in session: return redirect(url_for('login'))
    dados = obter_dados_copa()
    todos_jogos = dados["jogos_arena"] + dados["jogos_futuros"]
    mapa_jogos = {j['id']: f"{j['time_a']} x {j['time_b']}" for j in todos_jogos}
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT id, usuario, jogo_id, gols_a, gols_b, amarelos, vermelhos, acrescimo, penaltis, autor_gol, turbo FROM palpites ORDER BY jogo_id DESC, id DESC')
    
    apostas_agrupadas = {}
    for r in cur.fetchall():
        id_jogo = r[2]
        nome_jogo = mapa_jogos.get(id_jogo, f"Jogo #{id_jogo}")
        if nome_jogo not in apostas_agrupadas: apostas_agrupadas[nome_jogo] = []
        apostas_agrupadas[nome_jogo].append({
            'aposta_id': r[0], 'usuario': r[1], 'jogo_id': r[2], 'gols_a': r[3], 'gols_b': r[4],
            'amarelos': r[5], 'vermelhos': r[6], 'acrescimo': r[7], 'penaltis': r[8], 'artilheiro': r[9], 'turbo': r[10]
        })
        
    cur.execute("SELECT jogo_id, amarelos, vermelhos, acrescimo, penaltis, artilheiro FROM jogos_admin")
    admin_data = {r[0]: {'amarelos': r[1], 'vermelhos': r[2], 'acrescimo': r[3], 'penaltis': r[4], 'artilheiro': r[5]} for r in cur.fetchall()}
    cur.close(); conn.close()

    resultados_oficiais = {}
    for j in todos_jogos:
        adm = admin_data.get(j['id'], {})
        resultados_oficiais[j['id']] = {
            'gols_a': str(j.get('gols_a_real', 'N/A')), 'gols_b': str(j.get('gols_b_real', 'N/A')),
            'amarelos': str(adm.get('amarelos', '')), 'vermelhos': str(adm.get('vermelhos', '')),
            'acrescimo': str(adm.get('acrescimo', '')), 'penaltis': str(adm.get('penaltis', '')), 'artilheiro': str(adm.get('artilheiro', ''))
        }

    return render_template('apostas.html', apostas_agrupadas=apostas_agrupadas, resultados_oficiais=resultados_oficiais, usuario=session['usuario'])

@app.route('/zerar_banco_oficina_secreta')
def zerar_banco():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE palpites RESTART IDENTITY;")
        cur.execute("TRUNCATE TABLE jogos_admin;")
        conn.commit()
        cur.close()
        conn.close()
        return "<h1 style='color: green; text-align: center; margin-top: 50px;'>✅ Banco de dados zerado com sucesso! A pista está limpa.</h1>"
    except Exception as e:
        return f"Erro ao limpar: {e}"

if __name__ == '__main__': app.run()