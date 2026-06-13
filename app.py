import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, session, redirect, url_for, jsonify

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

# 2. Jogos (Simulados por enquanto)
JOGOS_ATUAIS = [
    {"id": 1, "time_a": "Brasil", "time_b": "França", "placar": "1 x 1", "status": "AO VIVO"},
    {"id": 2, "time_a": "Argentina", "time_b": "Croácia", "placar": "2 x 0", "status": "RESULTADOS"},
    {"id": 3, "time_a": "Inglaterra", "time_b": "Espanha", "placar": "- x -", "status": "EM BREVE"}
]

# Função para conectar ao Banco de Dados Neon
def get_db_connection():
    # Ele vai pegar a DATABASE_URL lá do Render
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    return conn

# Cria a tabela automaticamente se ela não existir
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

# Roda a criação da tabela assim que o app inicia
criar_tabela()

@app.route('/')
def index():
    if 'usuario' not in session: 
        return redirect(url_for('login'))
    return render_template('index.html', usuario=session['usuario'], jogos=JOGOS_ATUAIS)

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
    
    # Salva o palpite permanentemente no Banco de Dados Neon
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
        
    # Busca todas as apostas do Banco de Dados Neon
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor) # Retorna como Dicionário igual o Flask gosta
    cur.execute('SELECT * FROM palpites ORDER BY id DESC')
    palpites_salvos = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('apostas.html', palpites=palpites_salvos)

if __name__ == '__main__':
    app.run(debug=True)
