import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = 'chave_secreta_super_segura'

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
        
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    headers = { 'X-Auth-Token': os.environ.get('API_KEY') }

    try:
        response = requests.get(url, headers=headers)
        dados_api = response.json()
        
        if 'errorCode' in dados_api or 'message' in dados_api:
            print("🚨 ERRO NA API:", dados_api.get('message', 'Erro desconhecido'))
            return cache_jogos["dados"]
            
        jogos_reais = []
        tem_ao_vivo_agora = False
        
        for match in dados_api.get('matches', []):
            time_a = match.get('homeTeam', {}).get('shortName') or match.get('homeTeam', {}).get('name') or "A Definir"
            time_b = match.get('awayTeam', {}).get('shortName') or match.get('awayTeam', {}).get('name') or "A Definir"
            
            gols_a = match.get('score', {}).get('fullTime', {}).get('home')
            gols_b = match.get('score', {}).get('fullTime', {}).get('away')
            
            status_api = match.get('status')
            placar = "- x -" if gols_a is None else f"{gols_a} x {gols_b}"
            
            if status_api in ['IN_PLAY', 'PAUSED']:
                status = "AO VIVO"
                tem_ao_vivo_agora = True
            elif status_api in ['FINISHED', 'AWARDED']:
                status = "RESULTADOS"
            else:
                status = "EM BREVE"
                
            dt_obj = datetime.strptime(match['utcDate'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            
            jogos_reais.append({
                "id": match['id'],
                "time_a": time_a,
                "time_b": time_b,
                "placar": placar,
                "status": status,
                "timestamp": dt_obj.timestamp(),
                "gols_a_real": str(gols_a) if gols_a is not None else None,
                "gols_b_real": str(gols_b) if gols_b is not None else None
            })
            
        jogos_reais.sort(key=lambda x: x['timestamp'])
        agora_ts = agora.timestamp()
        
        jogos_futuros = [j for j in jogos_reais if j['timestamp'] > (agora_ts - 86400)]
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
        pass

criar_tabela()

@app.route('/')
def index():
    if 'usuario' not in session: 
        return redirect(url_for('login'))
        
    usuario_atual = session['usuario']
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # 1. Hodômetro: Calcula o gasto total do usuário
    cur.execute("SELECT * FROM palpites WHERE usuario = %s", (usuario_atual,))
    apostas_user = cur.fetchall()
    total_campos = 0
    for p in apostas_user:
        if p['gols_a'] or p['gols_b']: total_campos += 1
        if p['escanteios']: total_campos += 1
        if p['amarelos']: total_campos += 1
        if p['vermelhos']: total_campos += 1
        if p['subs']: total_campos += 1
        if p['acrescimo']: total_campos += 1
    
    gasto_total = total_campos * 0.50
    
    # 2. Dinamômetro: Acha os vencedores dos jogos finalizados
    jogos = obter_jogos_copa()
    for jogo in jogos:
        jogo['vencedores_placar'] = []
        if jogo['status'] == 'RESULTADOS' and jogo['gols_a_real'] and jogo['gols_b_real']:
            cur.execute(
                "SELECT usuario FROM palpites WHERE jogo_id = %s AND gols_a = %s AND gols_b = %s", 
                (jogo['id'], jogo['gols_a_real'], jogo['gols_b_real'])
            )
            ganhadores = cur.fetchall()
            # Adiciona os nomes na lista, sem duplicar
            jogo['vencedores_placar'] = list(set([g['usuario'] for g in ganhadores]))

    cur.close()
    conn.close()
    
    # Formata para reais
    gasto_formatado = f"{gasto_total:,.2f}".replace('.', ',')
    
    return render_template('index.html', usuario=usuario_atual, jogos=jogos, gasto=gasto_formatado)

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
    usuario = session['usuario']
    jogo_id = dados['jogo_id']
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 3. Trava de Segurança: Verifica se o usuário já apostou
    cur.execute("SELECT id FROM palpites WHERE usuario = %s AND jogo_id = %s", (usuario, jogo_id))
    aposta_existente = cur.fetchone()
    
    if aposta_existente:
        cur.close()
        conn.close()
        return jsonify({"sucesso": False, "erro": "Você já enviou seus palpites para este jogo! Apenas 1 aposta por partida."}), 400

    cur.execute('''
        INSERT INTO palpites (usuario, jogo_id, gols_a, gols_b, escanteios, amarelos, vermelhos, subs, acrescimo)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        usuario, jogo_id, dados['gols_a'], dados['gols_b'], 
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
