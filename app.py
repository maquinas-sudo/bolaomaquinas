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

STAGE_ORDER = {
    'GROUP_STAGE': 1, 'LAST_16': 2, 'QUARTER_FINALS': 3,
    'SEMI_FINALS': 4, 'THIRD_PLACE': 5, 'FINAL': 6
}

def obter_dados_copa():
    agora = datetime.now(timezone.utc)
    minutos_espera = 4 if cache_dados["tem_jogo_ao_vivo"] else 60
    
    if cache_dados["ultima_atualizacao"] and (agora - cache_dados["ultima_atualizacao"]) < timedelta(minutes=minutos_espera):
        return cache_dados
        
    headers = { 'X-Auth-Token': os.environ.get('API_KEY') }
    
    try:
        # 1. Busca todos os Jogos
        res_jogos = requests.get("https://api.football-data.org/v4/competitions/WC/matches", headers=headers).json()
        matches = res_jogos.get('matches', [])
        
        # Descobre qual é a fase atual do torneio
        max_stage = 1
        for m in matches:
            if m.get('status') in ['IN_PLAY', 'PAUSED', 'FINISHED', 'AWARDED']:
                stg = m.get('stage', 'GROUP_STAGE')
                max_stage = max(max_stage, STAGE_ORDER.get(stg, 1))

        jogos_arena = []
        jogos_futuros = []
        tem_ao_vivo_agora = False
        limite_48h = agora + timedelta(hours=48)
        
        for match in matches:
            time_a = match.get('homeTeam', {}).get('shortName') or match.get('homeTeam', {}).get('name') or "A Definir"
            time_b = match.get('awayTeam', {}).get('shortName') or match.get('awayTeam', {}).get('name') or "A Definir"
            crest_a = match.get('homeTeam', {}).get('crest', '')
            crest_b = match.get('awayTeam', {}).get('crest', '')
            
            fase = match.get('stage', '').replace('_', ' ').title()
            grupo = match.get('group', '').replace('_', ' ') if match.get('group') else ''
            info_fase = f"{fase} {grupo}".strip()
            
            gols_a = match.get('score', {}).get('fullTime', {}).get('home')
            gols_b = match.get('score', {}).get('fullTime', {}).get('away')
            
            penaltis_a = match.get('score', {}).get('penalties', {}).get('home')
            penaltis_b = match.get('score', {}).get('penalties', {}).get('away')
            placar_penaltis = f" (Pên: {penaltis_a}x{penaltis_b})" if penaltis_a is not None else ""
            
            placar = "- x -" if gols_a is None else f"{gols_a} x {gols_b}{placar_penaltis}"
            status_api = match.get('status')
            
            if status_api in ['IN_PLAY', 'PAUSED']:
                status = "AO VIVO"
                tem_ao_vivo_agora = True
            elif status_api in ['FINISHED', 'AWARDED']:
                status = "RESULTADOS"
            else:
                status = "EM BREVE..."
                
            dt_obj = datetime.strptime(match['utcDate'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            data_formatada = dt_obj.strftime('%d/%m %H:%M')
            
            jogo_formatado = {
                "id": match['id'], "time_a": time_a, "time_b": time_b, "crest_a": crest_a, "crest_b": crest_b,
                "placar": placar, "status": status, "info_fase": info_fase, "timestamp": dt_obj.timestamp(),
                "data_str": data_formatada, "gols_a_real": str(gols_a) if gols_a is not None else "N/A",
                "gols_b_real": str(gols_b) if gols_b is not None else "N/A"
            }

            stg_level = STAGE_ORDER.get(match.get('stage', 'GROUP_STAGE'), 1)
            
            # Lógica de Filtro Inteligente (Arena vs Futuros)
            if status in ['AO VIVO', 'RESULTADOS']:
                # Mostra o histórico só da fase atual e da imediatamente anterior
                if stg_level >= max_stage - 1:
                    jogos_arena.append(jogo_formatado)
            else:
                # Mostra jogos na arena apenas se acontecerem em até 48 horas
                if dt_obj <= limite_48h:
                    jogos_arena.append(jogo_formatado)
                else:
                    jogos_futuros.append(jogo_formatado)
            
        # Ordenação: Recentes no topo na Arena, cronológico na Agenda
        jogos_arena.sort(key=lambda x: x['timestamp'], reverse=True)
        jogos_futuros.sort(key=lambda x: x['timestamp'])
        
        # 2. Artilheiros
        res_art = requests.get("https://api.football-data.org/v4/competitions/WC/scorers", headers=headers).json()
        artilheiros = []
        for s in res_art.get('scorers', [])[:5]:
            artilheiros.append({ "nome": s.get('player', {}).get('name'), "time": s.get('team', {}).get('name'), "gols": s.get('goals') })
            
        # 3. Classificação
        res_stand = requests.get("https://api.football-data.org/v4/competitions/WC/standings", headers=headers).json()
        classificacao = []
        if 'standings' in res_stand:
            for group in res_stand['standings']:
                if group['type'] == 'TOTAL':
                    classificacao.append({
                        'grupo': group.get('group', '').replace('_', ' '),
                        'times': [{
                            'nome': t['team'].get('shortName') or t['team'].get('name'),
                            'crest': t['team'].get('crest', ''),
                            'pts': t['points'], 'pj': t['playedGames'],
                            'v': t['won'], 'e': t['draw'], 'd': t['lost'], 'sg': t['goalDifference']
                        } for t in group['table']]
                    })

        cache_dados.update({"jogos_arena": jogos_arena, "jogos_futuros": jogos_futuros, "classificacao": classificacao, "artilheiros": artilheiros, "ultima_atualizacao": agora, "tem_jogo_ao_vivo": tem_ao_vivo_agora})
        return cache_dados
    except Exception as e: 
        print(f"Erro API: {e}")
        return cache_dados

def get_db_connection(): return psycopg2.connect(os.environ['DATABASE_URL'])

def criar_tabela():
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS palpites (id SERIAL PRIMARY KEY, usuario VARCHAR(50), jogo_id INT, gols_a VARCHAR(10), gols_b VARCHAR(10), amarelos VARCHAR(50), vermelhos VARCHAR(50), subs VARCHAR(50), acrescimo VARCHAR(50), penaltis VARCHAR(50), autor_gol VARCHAR(50))''')
        for col in ['amarelos', 'vermelhos', 'subs', 'acrescimo', 'penaltis', 'autor_gol']:
            try: cur.execute(f'ALTER TABLE palpites ADD COLUMN {col} VARCHAR(50)')
            except: conn.rollback()
        conn.commit(); cur.close(); conn.close()
    except Exception as e: print("Erro na tabela:", e)

criar_tabela()

@app.route('/')
def index():
    if 'usuario' not in session: return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT gols_a, gols_b, amarelos, vermelhos, subs, acrescimo, penaltis, autor_gol FROM palpites WHERE usuario = %s", (session['usuario'],))
    apostas = cur.fetchall()
    gasto = sum([1 for p in apostas for f in p if f and f.strip()]) * 0.50
    
    dados = obter_dados_copa()
    jogos = dados["jogos_arena"]
    artilheiros = dados["artilheiros"]
    
    for jogo in jogos:
        jogo['vencedores_placar'] = []
        if jogo['status'] == 'RESULTADOS' and jogo['gols_a_real'] != "N/A":
            cur.execute("SELECT usuario FROM palpites WHERE jogo_id = %s AND gols_a = %s AND gols_b = %s", (jogo['id'], jogo['gols_a_real'], jogo['gols_b_real']))
            jogo['vencedores_placar'] = list(set([g[0] for g in cur.fetchall()]))
            
    cur.close(); conn.close()
    return render_template('index.html', usuario=session['usuario'], jogos=jogos, artilheiros=artilheiros, gasto=f"{gasto:,.2f}".replace('.', ','))

@app.route('/info')
def info_torneio():
    if 'usuario' not in session: return redirect(url_for('login'))
    dados = obter_dados_copa()
    return render_template('info.html', usuario=session['usuario'], classificacao=dados['classificacao'], jogos_futuros=dados['jogos_futuros'])

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
        else:
            erro = "Acesso negado. Credenciais inválidas."
    return render_template('login.html', erro=erro)

@app.route('/apostar', methods=['POST'])
def apostar():
    dados = request.json
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id FROM palpites WHERE usuario = %s AND jogo_id = %s", (session['usuario'], dados['jogo_id']))
    if cur.fetchone(): cur.close(); conn.close(); return jsonify({"sucesso": False, "erro": "Aposta já enviada para este jogo!"}), 400
    
    cur.execute("INSERT INTO palpites (usuario, jogo_id, gols_a, gols_b, amarelos, vermelhos, subs, acrescimo, penaltis, autor_gol) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", 
                (session['usuario'], dados['jogo_id'], dados['gols_a'], dados['gols_b'], dados['amarelos'], dados['vermelhos'], dados['subs'], dados['acrescimo'], dados.get('penaltis', ''), dados.get('autor_gol', '')))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"sucesso": True})

@app.route('/apostas_publicas')
def apostas_publicas():
    if 'usuario' not in session: return redirect(url_for('login'))
    dados = obter_dados_copa()
    todos_jogos = dados["jogos_arena"] + dados["jogos_futuros"]
    mapa_jogos = {j['id']: f"{j['time_a']} x {j['time_b']}" for j in todos_jogos}
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT usuario, jogo_id, gols_a, gols_b, amarelos, vermelhos, subs, acrescimo, penaltis, autor_gol FROM palpites ORDER BY jogo_id DESC, id DESC')
    
    apostas_agrupadas = {}
    for r in cur.fetchall():
        id_jogo = r[1]
        nome_jogo = mapa_jogos.get(id_jogo, f"Jogo #{id_jogo}")
        if nome_jogo not in apostas_agrupadas: apostas_agrupadas[nome_jogo] = []
            
        apostas_agrupadas[nome_jogo].append({
            'usuario': r[0], 'gols_a': r[2], 'gols_b': r[3],
            'amarelos': r[4], 'vermelhos': r[5], 'subs': r[6], 'acrescimo': r[7], 'penaltis': r[8], 'autor_gol': r[9]
        })
        
    cur.close(); conn.close()
    return render_template('apostas.html', apostas_agrupadas=apostas_agrupadas)

if __name__ == '__main__': app.run()
