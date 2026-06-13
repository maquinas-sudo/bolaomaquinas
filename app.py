import os
import psycopg2
from flask import Flask, render_template, request, session, redirect, url_for

app = Flask(__name__)
app.secret_key = 'chave_secreta_super_segura'

def get_db():
    # O Render vai injetar a DATABASE_URL do Neon aqui automaticamente
    return psycopg2.connect(os.environ['DATABASE_URL'])

@app.route('/')
def index():
    if 'usuario' not in session: return redirect(url_for('login'))
    return render_template('index.html', usuario=session['usuario'], saldo=50.0)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['usuario'] = request.form['usuario']
        return redirect(url_for('index'))
    return render_template('login.html')

if __name__ == '__main__':
    app.run()
