import os
from flask import Flask, render_template, request, session, redirect, url_for, jsonify

app = Flask(__name__)
app.secret_key = 'chave_secreta_super_segura'

# 1. Usuários e Senhas Restritos (Fornecidos por você)
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

# 3. Memória temporária para os palpites
palpites_salvos = []

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
    dados['usuario'] = session['usuario']
    palpites_salvos.append(dados)
    
    return jsonify({"sucesso": True})

@app.route('/apostas_publicas')
def apostas_publicas():
    if 'usuario' not in session: 
        return redirect(url_for('login'))
    return render_template('apostas.html', palpites=palpites_salvos)

if __name__ == '__main__':
    app.run(debug=True)
