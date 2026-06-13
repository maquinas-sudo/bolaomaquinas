import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = 'chave_secreta_super_segura'

USUARIOS_PERMITIDOS = {
    "Joao mano": "JMOV123", "Lucas": "LCS123", "Matheus": "MCINTRA123",
    "Pedro": "PHACY123", "Joao Vitor": "JVND123", "Magno": "GMAS123",
    "Salsicha": "AVRZ123", "Teste": "teste", "Sauer": "admin123"
}

cache_jogos = {"dados": [], "ultima_atualizacao": None, "tem_jogo_ao_vivo": False}

def obter_jogos_copa():
    agora = datetime.now(timezone.utc)
    minutos_espera = 4 if cache_jogos["tem_jogo_ao_vivo"] else 60
    
    if cache_jogos["ultima_atualizacao"] and (agora - cache_jogos["ultima_atualizacao"]) < timedelta(minutes=minutos_espera):
        return cache_jogos["dados"]
        
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    headers = { 'X-Auth-Token': os.environ.get('API_KEY') }

    try:
        response = requests.get(url, headers=headers)
        dados_api = response.json()
        
        if 'matches' not in dados_api: return cache_jogos["dados"]
            
        jogos_reais = []
        tem_ao_vivo_agora = False
        
        for match in dados_api.get('matches', []):
            time_a = match.get('homeTeam', {}).get('shortName') or match.get('homeTeam', {}).get('name') or "A Definir"
            time_b = match.get('awayTeam', {}).get('shortName') or match.get('awayTeam', {}).get('name') or "A Definir"
            
            gols_a = match.get('score', {}).get('fullTime', {}).get('home')
            gols_b = match.get('score', {}).get('fullTime', {}).get('away')
            
            status_api = match.get('status')
            placar = "- x -" if gols_a is None else f"{gols_a} x {gols_b}"
            
            status = "AO VIVO" if status_api in ['IN_PLAY', 'PAUSED'] else ("RESULTADOS" if status_api in ['FINISHED', 'AWARDED'] else "EM BREVE")
            if status == "AO VIVO": tem_ao_vivo_agora = True
                
            dt_obj = datetime.strptime(match['utcDate'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            
            jogos_reais.append({
                "id": match['id'],
                "time_a": time_a, "time_b": time_b, "placar": placar,
                "status": status, "timestamp": dt_obj.timestamp(),
                "gols_a_real": str(gols_a) if gols_a is not None else "N/A",
                "gols_b_real": str(gols_b) if gols_b is not None else "N/A"
            })
            
        jogos_reais.sort(key=lambda x: x['timestamp'])
        cache_jogos.update({"dados": jogos_reais[:10], "ultima_atualizacao": agora, "tem_jogo_ao_vivo": tem_ao_vivo_agora})
        return cache_jogos["dados"]
    except: return cache_jogos["dados"]

def get_db_connection(): return psycopg2.connect(os.environ['DATABASE_URL'])

@app.route('/')
def index():
    if 'usuario' not in session: return redirect(url_for('login'))
    usuario_atual = session['usuario']
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM palpites WHERE usuario = %s", (usuario_atual,))
    apostas_user = cur.fetchall()
    gasto = sum([1 for p in apostas_user for field in [p['gols_a'], p['gols_b'], p['escanteios'], p['amarelos'], p['vermelhos'], p['subs'], p['acrescimo']] if field and field.strip()]) * 0.50
    
    jogos = obter_jogos_copa()
    for jogo in jogos:
        jogo['vencedores_placar'] = []
        if jogo['status'] == 'RESULTADOS' and jogo['gols_a_real'] != "N/A":
            cur.execute("SELECT usuario FROM palpites WHERE jogo_id = %s AND gols_a = %s AND gols_b = %s", (jogo['id'], jogo['gols_a_real'], jogo['gols_b_real']))
            jogo['vencedores_placar'] = list(set([g['usuario'] for g in cur.fetchall()]))
    
    cur.close(); conn.close()
    return render_template('index.html', usuario=usuario_atual, jogos=jogos, gasto=f"{gasto:,.2f}".replace('.', ','))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['usuario'] in USUARIOS_PERMITIDOS and USUARIOS_PERMITIDOS[request.form['usuario']] == request.form['senha']:
            session['usuario'] = request.form['usuario']
            return redirect(url_for('index'))
    return render_template('login.html', erro="Acesso negado." if request.method == 'POST' else None)

@app.route('/apostar', methods=['POST'])
def apostar():
    dados = request.json
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id FROM palpites WHERE usuario = %s AND jogo_id = %s", (session['usuario'], dados['jogo_id']))
    if cur.fetchone(): cur.close(); conn.close(); return jsonify({"sucesso": False, "erro": "Aposta já enviada!"}), 400
    cur.execute("INSERT INTO palpites (usuario, jogo_id, gols_a, gols_b, escanteios, amarelos, vermelhos, subs, acrescimo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", 
                (session['usuario'], dados['jogo_id'], dados['gols_a'], dados['gols_b'], dados['escanteios'], dados['amarelos'], dados['vermelhos'], dados['subs'], dados['acrescimo']))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"sucesso": True})

@app.route('/apostas_publicas')
def apostas_publicas():
    if 'usuario' not in session: return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM palpites ORDER BY id DESC')
    palpites = cur.fetchall(); cur.close(); conn.close()
    return render_template('apostas.html', palpites=palpites)

if __name__ == '__main__': app.run()
