import os
import psycopg2
from flask import Flask, render_template, request, session, redirect, url_for

app = Flask(__name__)
app.secret_key = 'chave_secreta_super_segura'

# 1. Sistema de Login Restrito
USUARIOS_PERMITIDOS = {
    "Joao mano": "JMOV123",
    "Lucas": "LCS123",
    "Matheus": "MCINTRA123",
    "Pedro": "PHACY123",
    "Joao Vitor": "JVND123",
    "Magno": "GMAS123",
    "Salsicha": "AVRZ123",
    "Teste": "teste"
}

def get_db():
    return psycopg2.connect(os.environ['DATABASE_URL'])

@app.route('/')
def index():
    if 'usuario' not in session: 
        return redirect(url_for('login'))
    
    # 2. Estrutura de Jogos Reais (Isso será substituído pela API real no futuro)
    jogos = [
        {"id": 1, "time_a": "Brasil", "time_b": "França", "gols_a": 1, "gols_b": 0, "status": "AO VIVO"},
        {"id": 2, "time_a": "Alemanha", "time_b": "Japão", "gols_a": 2, "gols_b": 2, "status": "RESULTADOS"},
        {"id": 3, "time_a": "Argentina", "time_b": "Inglaterra", "gols_a": "-", "gols_b": "-", "status": "EM BREVE"}
    ]

    return render_template('index.html', usuario=session['usuario'], jogos=jogos)

@app.route('/login', methods=['GET', 'POST'])
def login():
    erro = None
    if request.method == 'POST':
        usuario = request.form['usuario']
        senha = request.form['senha']
        
        # Verifica se o usuário e senha batem exatamente com a sua lista
        if usuario in USUARIOS_PERMITIDOS and USUARIOS_PERMITIDOS[usuario] == senha:
            session['usuario'] = usuario
            return redirect(url_for('index'))
        else:
            erro = "Acesso negado. Usuário ou senha incorretos."
            
    return render_template('login.html', erro=erro)

@app.route('/apostas_publicas')
def apostas_publicas():
    # Rota futura para listar as apostas de todo mundo
    if 'usuario' not in session: return redirect(url_for('login'))
    return "Aqui vai aparecer o painel com as apostas de todos os jogadores."

if __name__ == '__main__':
    app.run()
