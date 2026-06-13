import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta

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

# --- SISTEMA DE CACHE DINÂMICO (O "Mapa de Injeção") ---
cache_jogos = {
    "dados": [],
    "ultima_atualizacao": None,
    "tem_jogo_ao_vivo": False  # Sensor para saber se o motor está acelerado
}

def obter_jogos_copa():
    agora = datetime.now()
    
    # Se tem jogo rolando, atualiza a cada 4 minutos (preserva as 100 requisições). 
    # Se não tem, entra em marcha lenta (60 minutos).
    minutos_espera = 4 if cache_jogos["tem_jogo_ao_vivo"] else 60
    
    if cache_jogos["ultima_atualizacao"] and (agora - cache_jogos["ultima_atualizacao"]) < timedelta(minutes=minutos_espera):
        return cache_jogos["dados"]
        
    url = "https://v3.football.api-sports.io/fixtures"
    querystring = {"league": "1", "season": "2026"}
    
    headers = {
        'x-apisports-key': os.environ.get('API_KEY'),
        'x-apisports-host': 'v3.football.api-sports.io'
    }

    try:
        response = requests.get(url, headers=headers, params=querystring)
        dados_api = response.json()
        
        jogos_reais = []
        tem_ao_vivo_agora = False
        
        for fixture in dados_api.get('response', []):
            time_a = fixture['teams']['home']['name']
            time_b = fixture['teams']['away']['name']
            gols_a = fixture['goals']['home']
            gols_b = fixture['goals']['away']
            status_api = fixture['fixture']['status']['short']
            timestamp = fixture['fixture']['timestamp']
            
            placar = "- x -" if gols_a is None else f"{gols_a} x {gols_b}"
            
            # Tradução e ativação do sensor de AO VIVO
            if status_api in ['1H', 'HT', '2H', 'ET', 'P', 'LIVE']:
                status = "AO VIVO"
                tem_ao_vivo_agora = True
            elif status_api in ['FT', 'AET', 'PEN']:
                status = "RESULTADOS"
            else:
                status = "EM BREVE"
                
            jogos_reais.append({
                "id": fixture['fixture']['id'],
                "time_a": time_a,
                "time_b": time_b,
                "placar": placar,
                "status": status,
                "timestamp": timestamp
            })
            
        jogos_reais.sort(key=lambda x: x['timestamp'])
        
        agora_ts = agora.timestamp()
        um_dia_em_segundos = 86400
        
        # Filtra os jogos de ontem, hoje e amanhã
        jogos_relevantes = [j for j in jogos_reais if j['timestamp'] > (agora_ts - um_dia_em_segundos)]
        lista_final = jogos_relevantes[:10]
        
        # Salva na memória do servidor
        cache_jogos["dados"] = lista_final
        cache_jogos["ultima_atualizacao"] = agora
        cache_jogos["tem_jogo_ao_vivo"] = tem_ao_vivo_agora
        
        return lista_final

    except Exception as e:
        print("Erro na API:", e)
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
