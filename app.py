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
            
            jogos_reais
