import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = 'chave_secreta_super_segura'

# 1. Usuários e Senhas Restritos
USUARIOS_PERMITIDOS = {
    "Joao mano": "JMOV123",
    "Lucas": "LCS123",
    "Matheus": "MCINTRA123",
    "Pedro": "PHACY123",
    "Joao Vitor": "JVND123",
    "Magno": "GMAS123",
    "Salsicha": "AVRZ123",
    "Teste": "teste",
    "Sauer": "admin123"
}

# --- SISTEMA DE CACHE DINÂMICO ---
cache_jogos = {
    "dados": [],
    "ultima_atualizacao": None,
    "tem_jogo_ao_vivo": False
}

def obter_jogos_copa():
    agora = datetime.now(timezone.utc)
    
    minutos_espera = 4 if cache_jogos["tem_jogo_ao_vivo"] else 60
    
    if cache_jogos["ultima_atualizacao"] and (agora - cache_jogos["ultima_atualizacao"]) < timedelta(minutes=minutos_espera):
        return cache_jogos["dados"]
        
    # Endpoint e cabeçalho ajustados para a nova API (football-data.org)
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    headers = { 'X-Auth-Token': os.environ.get('API_KEY') }

    try:
        response = requests.get(url, headers=headers)
        dados_api = response.json()
        
        # Injeção de diagnóstico
        if 'errorCode' in dados_api or 'message' in dados_api:
            print("🚨 ERRO NA API:", dados_api.get('message', 'Erro desconhecido'))
            return cache_jogos["dados"]
            
        jogos_reais = []
        tem_ao_vivo_agora = False
        
        for match in dados_api.get('matches', []):
            # Tenta pegar o nome curto, se não tiver, pega o longo, se não, "A Definir"
            time_a = match.get('homeTeam', {}).get('shortName') or match.get('homeTeam', {}).get('name') or "A Definir"
            time_b = match.get('awayTeam', {}).get('shortName') or match.get('awayTeam', {}).get('name') or "A Definir"
            
            # Pega os gols no tempo normal (fullTime)
            gols_a = match.get('score', {}).get('fullTime', {}).get('home')
            gols_b = match.get('score', {}).get('fullTime', {}).get('away')
            
            status_api = match.get('status')
            
            placar = "- x -" if gols_a is None else f"{gols_a} x {gols_b}"
            
            # Ajuste dos status para a nova API
            if status_api in ['IN_PLAY', 'PAUSED']:
                status = "AO VIVO"
                tem_ao_vivo_agora = True
            elif status_api in ['FINISHED', 'AWARDED']:
                status = "RESULTADOS"
            else:
                status = "EM BREVE"
                
            # Converte a data da API para timestamp de comparação
            dt_obj = datetime.strptime(match['utcDate'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            timestamp = dt_obj.timestamp()
                
            jogos_reais.append({
                "id": match['id'],
                "time_a": time_a,
                "time_b": time_b,
                "placar": placar,
                "status": status,
                "timestamp": timestamp
            })
            
        jogos_reais.sort(key=lambda x: x['timestamp'])
        
        agora_ts = agora.timestamp()
        
        # Filtra os jogos de ontem pra frente
        jogos_futuros = [j for j in jogos_reais if j['timestamp'] > (agora_ts - 86400)]
        
        # Se não tiver jogo recente, exibe os últimos/próximos da lista
        if len(jogos_futuros) == 0 and len(jogos_reais) > 0:
            jogos_futuros = jogos_reais
            
        lista_final = jogos_futuros[:10]
        
        cache_jogos["dados"] = lista_final
        cache_jogos["ultima_atualizacao"] = agora
        cache_jogos["tem_jogo_ao_vivo"] = tem_ao_vivo_agora
        
        return lista_final

    except Exception as e:
        print("Erro Crítico na API:", e)
        return cache_jogos["dados"]

def get_db_connection():
    return psycopg2.connect(os.environ['DATABASE_URL'])

def criar_tabela():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS palpites (
                id SERIAL PRIMARY KEY,
                usuario VARCHAR(50),
                jogo_id INT,
                gols_a VARCHAR(10),
                gols_b VARCHAR(10),
                escanteios VARCHAR(10),
                amarelos VARCHAR(10),
                vermelhos VARCHAR(10),
                subs VARCHAR(10),
                acrescimo VARCHAR(10)
            )
        ''')
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("Erro ao criar tabela:", e)

criar_tabela()

@app.route('/')
def index():
    if 'usuario' not in session: 
        return redirect(url_for('login'))
        
    jogos_ao_vivo = obter_jogos_copa()
    return render_template('index.html', usuario=session['usuario'], jogos=jogos_ao_vivo)

@app.route('/login', methods=['GET', 'POST'])
def login():
    erro = None
    if request.method == 'POST':
        usuario = request.form['usuario']
        senha = request.form['senha']
        
        if usuario in USUARIOS_PERMITIDOS and USUARIOS_PERMITIDOS[usuario] == senha:
            session['usuario'] = usuario
            return redirect(url_for('index'))
        else:
            erro = "Acesso negado. Usuário ou senha incorretos."
            
    return render_template('login.html', erro=erro)

@app.route('/apostar', methods=['POST'])
def apostar():
    if 'usuario' not in session:
        return jsonify({"erro": "Não autorizado"}), 401
    
    dados = request.json
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO palpites (usuario, jogo_id, gols_a, gols_b, escanteios, amarelos, vermelhos, subs, acrescimo)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        session['usuario'], dados['jogo_id'], dados['gols_a'], dados['gols_b'], 
        dados['escanteios'], dados['amarelos'], dados['vermelhos'], 
        dados['subs'], dados['acrescimo']
    ))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({"sucesso": True})

@app.route('/apostas_publicas')
def apostas_publicas():
    if 'usuario' not in session: 
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM palpites ORDER BY id DESC')
    palpites_salvos = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('apostas.html', palpites=palpites_salvos)

if __name__ == '__main__':
    app.run(debug=True)
