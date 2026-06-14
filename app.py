import os
import requests
import psycopg2
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = 'chave_secreta_super_segura'

USUARIOS_PERMITIDOS = {
    "Joao mano": "JMOV123", "Lucas": "LCS123", "Matheus": "MCINTRA123",
    "Pedro": "PHACY123", "Joao Vitor": "JVND123", "Magno": "GMAS123",
    "Salsicha": "AVRZ123", "Teste": "teste", "Sauer": "admin123"
}

cache_dados = {"jogos_arena": [], "jogos_futuros": [], "classificacao": [], "artilheiros": [], "ultima_atualizacao": None, "tem_jogo_ao_vivo": False}
config_app = {"manutencao": False}

STAGE_ORDER = {
    'GROUP_STAGE': 1, 'LAST_16': 2, 'QUARTER_FINALS': 3,
    'SEMI_FINALS': 4, 'THIRD_PLACE': 5, 'FINAL': 6
}

# --- TRAVA DE MANUTENÇÃO (CHAVE GERAL) ---
@app.before_request
def checar_manutencao():
    if config_app["manutencao"] and request.endpoint not in ['login', 'admin_toggle_manutencao'] and not request.path.startswith('/static'):
        if session.get('usuario') != 'Teste':
            return "<body style='background:#121212; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;'><h1 style='color:#ffcc00; font-family:sans-serif; text-align:center;'>🛠️ CALMA, ESTAMOS EM MANUTENÇÃO</h1></body>", 503

def obter_dados_copa():
    agora = datetime.now(timezone.utc)
    minutos_espera = 4 if cache_dados["tem_jogo_ao_vivo"] else 60
    
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
            
            # --- AJUSTE DE FUSO HORÁRIO ---
            dt_local = dt_obj - timedelta(hours=4)
            
            jogo_formatado = {
                "id": match['id'], "time_a": time_a, "time_b": time_b, "crest_a": crest_a, "crest_b": crest_b,
                "placar": placar, "status": status, "info_fase": f"{fase} {grupo}".strip(), 
                "timestamp": dt_obj.timestamp(), 
                "data_str": dt_local.strftime('%d/%m %H:%M'), 
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
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS palpites (id SERIAL PRIMARY KEY, usuario VARCHAR(50), jogo_id INT, gols_a VARCHAR(10), gols_b VARCHAR(10), amarelos VARCHAR(50), vermelhos VARCHAR(50), subs VARCHAR(50), acrescimo VARCHAR(50), penaltis VARCHAR(50), autor_gol VARCHAR(50))''')
        for col in ['amarelos', 'vermelhos', 'subs', 'acrescimo', 'penaltis', 'autor_gol']:
            try: cur.execute(f'ALTER TABLE palpites ADD COLUMN {col} VARCHAR(50)')
            except: conn.rollback()
        try: cur.execute('ALTER TABLE palpites ADD COLUMN turbo BOOLEAN DEFAULT FALSE')
        except: conn.rollback()
        try: cur.execute('ALTER TABLE palpites ADD COLUMN data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        except: conn.rollback()
            
        cur.execute('''CREATE TABLE IF NOT EXISTS jogos_admin (jogo_id INT PRIMARY KEY, link_stream VARCHAR(255), amarelos VARCHAR(50), vermelhos VARCHAR(50), acrescimo VARCHAR(50), penaltis VARCHAR(50), artilheiro VARCHAR(50))''')
        conn.commit(); cur.close(); conn.close()
    except Exception as e: print("Erro na tabela:", e)

criar_tabela()

def validar_num(valor):
    if not valor or str(valor).strip() == '': return True
    try: return 0 <= int(valor) <= 99
    except: return False

@app.route('/')
def index():
    if 'usuario' not in session: return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT gols_a, gols_b, amarelos, vermelhos, subs, acrescimo, penaltis, autor_gol FROM palpites WHERE usuario = %s", (session['usuario'],))
    apostas = cur.fetchall()
    gasto = sum([1 for p in apostas for f in p if f and str(f).strip()]) * 0.50
    
    cur.execute("SELECT jogo_id, link_stream, amarelos, vermelhos, acrescimo, penaltis, artilheiro FROM jogos_admin")
    admin_data = {r[0]: {'link': r[1], 'amarelos': r[2], 'vermelhos': r[3], 'acrescimo': r[4], 'penaltis': r[5], 'artilheiro': r[6]} for r in cur.fetchall()}
    
    dados = obter_dados_copa()
    jogos = dados["jogos_arena"]
    
    for jogo in jogos:
        jogo['vencedores_placar'] = []
        if jogo['status'] == 'ENCERRADO' and jogo['gols_a_real'] != "N/A":
            cur.execute("SELECT usuario FROM palpites WHERE jogo_id = %s AND gols_a = %s AND gols_b = %s", (jogo['id'], jogo['gols_a_real'], jogo['gols_b_real']))
            jogo['vencedores_placar'] = list(set([g[0] for g in cur.fetchall()]))
            
    cur.close(); conn.close()
    return render_template('index.html', usuario=session['usuario'], jogos=jogos, admin_data=admin_data, gasto=f"{gasto:,.2f}".replace('.', ','), manutencao=config_app["manutencao"])

@app.route('/perfil')
def perfil():
    if 'usuario' not in session: return redirect(url_for('login'))
    user = session['usuario']
    conn = get_db_connection(); cur = conn.cursor()
    
    cur.execute("SELECT jogo_id, gols_a, gols_b, turbo FROM palpites WHERE usuario = %s", (user,))
    apostas = cur.fetchall()
    cur.close(); conn.close()
    
    total_apostas = len(apostas)
    cravadas, acertos_venc, pontos, maior_erro = 0, 0, 0, 0
    dados = obter_dados_copa()
    todos_jogos = {j['id']: j for j in dados.get('jogos_arena', []) + dados.get('jogos_futuros', [])}
    
    for a in apostas:
        j_id, g_a, g_b, turbo = a
        jogo = todos_jogos.get(j_id)
        if jogo and jogo['status'] == 'ENCERRADO' and jogo['gols_a_real'] != 'N/A':
            try:
                ga_r, gb_r = int(jogo['gols_a_real']), int(jogo['gols_b_real'])
                ga_a, gb_a = int(g_a), int(g_b)
                mult = 2 if turbo else 1
                
                if ga_r == ga_a and gb_r == gb_a:
                    cravadas += 1; pontos += 5 * mult
                elif (ga_r > gb_r and ga_a > gb_a) or (ga_r < gb_r and ga_a < gb_a) or (ga_r == gb_r and ga_a == gb_a):
                    acertos_venc += 1; pontos += 2 * mult
                    
                erro_calc = abs(ga_r - ga_a) + abs(gb_r - gb_a)
                if erro_calc > maior_erro: maior_erro = erro_calc
            except: pass
            
    taxa = (cravadas / total_apostas * 100) if total_apostas > 0 else 0
    
    stats = {"total": total_apostas, "pontos": pontos, "cravadas": cravadas, "vencedor": acertos_venc, "taxa": f"{taxa:.1f}%", "maior_erro": maior_erro}
    return render_template('perfil.html', usuario=user, stats=stats)

@app.route('/info')
def info_torneio():
    if 'usuario' not in session: return redirect(url_for('login'))
    dados = obter_dados_copa()
    return render_template('info.html', usuario=session['usuario'], classificacao=dados['classificacao'], jogos_futuros=dados['jogos_futuros'], artilheiros=dados['artilheiros'])

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
    
    campos_numericos = ['gols_a', 'gols_b', 'amarelos', 'vermelhos', 'acrescimo']
    if not all(validar_num(dados.get(c)) for c in campos_numericos):
        return jsonify({"sucesso": False, "erro": "Valores devem ser entre 0 e 99!"}), 400
        
    artilheiro = str(dados.get('artilheiro', '')).strip()
    if len(artilheiro) > 20:
        return jsonify({"sucesso": False, "erro": "Artilheiro não pode ter mais que 20 caracteres!"}), 400

    dados_api = obter_dados_copa()
    todos = dados_api.get("jogos_arena", []) + dados_api.get("jogos_futuros", [])
    jogo_atual = next((j for j in todos if str(j['id']) == str(jogo_id)), None)
    
    if jogo_atual:
        limite_aposta = jogo_atual['timestamp'] + (15 * 60)
        if datetime.now(timezone.utc).timestamp() > limite_aposta:
            return jsonify({"sucesso": False, "erro": "Apostas encerradas! Bola rolando a mais de 15 minutos."}), 400

    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id FROM palpites WHERE usuario = %s AND jogo_id = %s", (session['usuario'], jogo_id))
    if cur.fetchone(): cur.close(); conn.close(); return jsonify({"sucesso": False, "erro": "Aposta já enviada para este jogo!"}), 400
    
    if usa_turbo:
        cur.execute("SELECT COUNT(*) FROM palpites WHERE usuario = %s AND turbo = TRUE AND DATE(data_registro) = CURRENT_DATE", (session['usuario'],))
        if cur.fetchone()[0] > 0:
            cur.close(); conn.close()
            return jsonify({"sucesso": False, "erro": "Você já gastou seu Botão Booster de hoje!"}), 400

    cur.execute("INSERT INTO palpites (usuario, jogo_id, gols_a, gols_b, amarelos, vermelhos, acrescimo, penaltis, autor_gol, turbo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", 
                (session['usuario'], jogo_id, dados.get('gols_a'), dados.get('gols_b'), dados.get('amarelos', ''), dados.get('vermelhos', ''), dados.get('acrescimo', ''), dados.get('penaltis', ''), artilheiro, usa_turbo))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"sucesso": True})

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
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('''INSERT INTO jogos_admin (jogo_id, link_stream, amarelos, vermelhos, acrescimo, penaltis, artilheiro) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (jogo_id) DO UPDATE SET 
                   link_stream=EXCLUDED.link_stream, amarelos=EXCLUDED.amarelos, vermelhos=EXCLUDED.vermelhos, 
                   acrescimo=EXCLUDED.acrescimo, penaltis=EXCLUDED.penaltis, artilheiro=EXCLUDED.artilheiro''', 
                (d.get('jogo_id'), d.get('link_stream'), d.get('amarelos'), d.get('vermelhos'), d.get('acrescimo'), d.get('penaltis'), d.get('artilheiro')))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"sucesso": True})

@app.route('/admin_editar_aposta', methods=['POST'])
def admin_editar_aposta():
    if session.get('usuario') != 'Teste': return jsonify({"sucesso": False, "erro": "Acesso negado."})
    d = request.json
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('''UPDATE palpites SET gols_a=%s, gols_b=%s, amarelos=%s, vermelhos=%s, acrescimo=%s, penaltis=%s, autor_gol=%s WHERE id=%s''',
                (d.get('gols_a'), d.get('gols_b'), d.get('amarelos'), d.get('vermelhos'), d.get('acrescimo'), d.get('penaltis'), d.get('artilheiro'), d.get('aposta_id')))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"sucesso": True})

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
            'aposta_id': r[0], 'usuario': r[1], 'gols_a': r[3], 'gols_b': r[4],
            'amarelos': r[5], 'vermelhos': r[6], 'acrescimo': r[7], 'penaltis': r[8], 'artilheiro': r[9], 'turbo': r[10]
        })
        
    cur.close(); conn.close()
    return render_template('apostas.html', apostas_agrupadas=apostas_agrupadas, usuario=session['usuario'])



if __name__ == '__main__': app.run()
