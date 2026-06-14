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

cache_dados = {"jogos": [], "artilheiros": [], "ultima_atualizacao": None, "tem_jogo_ao_vivo": False}

def obter_dados_copa():
    agora = datetime.now(timezone.utc)
    minutos_espera = 4 if cache_dados["tem_jogo_ao_vivo"] else 60
    
    if cache_dados["ultima_atualizacao"] and (agora - cache_dados["ultima_atualizacao"]) < timedelta(minutes=minutos_espera):
        return cache_dados
        
    headers = { 'X-Auth-Token': os.environ.get('API_KEY') }
    
    try:
        # 1. Puxando os Jogos (Fases, Escudos, Pênaltis)
        res_jogos = requests.get("https://api.football-data.org/v4/competitions/WC/matches", headers=headers).json()
        jogos_reais = []
        tem_ao_vivo_agora = False
        
        for match in res_jogos.get('matches', []):
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
            
            jogos_reais.append({
                "id": match['id'], "time_a": time_a, "time_b": time_b, "crest_a": crest_a, "crest_b": crest_b,
                "placar": placar, "status": status, "info_fase": info_fase, "timestamp": dt_obj.timestamp(),
                "gols_a_real": str(gols_a) if gols_a is not None else "N/A",
                "gols_b_real": str(gols_b) if gols_b is not None else "N/A"
            })
            
        # Ordenação reversa (Mais atuais/futuros no topo, antigos embaixo)
        jogos_reais.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # 2. Puxando os Artilheiros (Estatísticas Globais)
        res_art = requests.get("https://api.football-data.org/v4/competitions/WC/scorers", headers=headers).json()
        artilheiros = []
        for s in res_art.get('scorers', [])[:5]: # Pega o Top 5
            artilheiros.append({
                "nome": s.get('player', {}).get('name'),
                "time": s.get('team', {}).get('name'),
                "gols": s.get('goals')
            })
            
        cache_dados.update({"jogos": jogos_reais, "artilheiros": artilheiros, "ultima_atualizacao": agora, "tem_jogo_ao_vivo": tem_ao_vivo_agora})
        return cache_dados
    except Exception as e: 
        print(f"Erro API: {e}")
        return cache_dados

def get_db_connection(): return psycopg2.connect(os.environ['DATABASE_URL'])

def criar_tabela():
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS palpites (id SERIAL PRIMARY KEY, usuario VARCHAR(50), jogo_id INT, gols_a VARCHAR(10), gols_b VARCHAR(10), amarelos VARCHAR(10), vermelhos VARCHAR(10), subs VARCHAR(10), acrescimo VARCHAR(10))''')
        # Adicionando novas colunas (ignoraremos 'escanteios' no front-end a partir de agora)
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
    jogos = dados["jogos"]
    artilheiros = dados["artilheiros"]
    
    for jogo in jogos:
        jogo['vencedores_placar'] = []
        if jogo['status'] == 'RESULTADOS' and jogo['gols_a_real'] != "N/A":
            cur.execute("SELECT usuario FROM palpites WHERE jogo_id = %s AND gols_a = %s AND gols_b = %s", (jogo['id'], jogo['gols_a_real'], jogo['gols_b_real']))
            jogo['vencedores_placar'] = list(set([g[0] for g in cur.fetchall()]))
            
    cur.close(); conn.close()
    return render_template('index.html', usuario=session['usuario'], jogos=jogos, artilheiros=artilheiros, gasto=f"{gasto:,.2f}".replace('.', ','))

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
    mapa_jogos = {j['id']: f"{j['time_a']} x {j['time_b']}" for j in dados["jogos"]}
    
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
