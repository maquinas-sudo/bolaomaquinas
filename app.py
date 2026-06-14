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
    "Salsicha": "AVRZ123", "Teste": "teste00", "Sauer": "admin123"
}

cache_dados = {"jogos_arena": [], "jogos_futuros": [], "classificacao": [], "artilheiros": [], "ultima_atualizacao": None, "tem_jogo_ao_vivo": False}
config_app = {"manutencao": False}

STAGE_ORDER = {
    'GROUP_STAGE': 1, 'LAST_16': 2, 'QUARTER_FINALS': 3,
    'SEMI_FINALS': 4, 'THIRD_PLACE': 5, 'FINAL': 6
}

# --- TRAVA DE MANUTENÇÃO (CHAVE GERAL) ---
@app.before_request
def checar_manutencao():
    if config_app["manutencao"] and request.endpoint not in ['login', 'admin_toggle_manutencao'] and not request.path.startswith('/static'):
        if session.get('usuario') != 'Teste':
            return "<body style='background:#121212; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;'><h1 style='color:#ffcc00; font-family:sans-serif; text-align:center;'>🛠️ CALMA, ESTAMOS EM MANUTENÇÃO</h1></body>", 503

def obter_dados_copa():
    agora = datetime.now(timezone.utc)
    minutos_espera = 4 if cache_dados["tem_jogo_ao_vivo"] else 60
    
    if cache_dados["ultima_atualizacao"] and (agora - cache_dados["ultima_atualizacao"]) < timedelta(minutes=minutos_espera):
        return cache_dados
        
    headers = { 'X-Auth-Token': os.environ.get('API_KEY') }
    
    try:
        res_jogos = requests.get("https://api.football-data.org/v4/competitions/WC/matches", headers=headers).json()
        matches = res_jogos.get('matches', [])
        
        max_stage = 1
        for m in matches:
            if m.get('status') in ['IN_PLAY', 'PAUSED', 'FINISHED', 'AWARDED']:
                stg = m.get('stage', 'GROUP_STAGE')
                max_stage = max(max_stage, STAGE_ORDER.get(stg, 1))

        jogos_arena = []
        jogos_futuros = []
        tem_ao_vivo_agora = False
        limite_24h = agora + timedelta(hours=24)
        
        for match in matches:
            time_a = match.get('homeTeam', {}).get('shortName') or match.get('homeTeam', {}).get('name') or "A Definir"
            time_b = match.get('awayTeam', {}).get('shortName') or match.get('awayTeam', {}).get('name') or "A Definir"
            crest_a = match.get('homeTeam', {}).get('crest', '')
            crest_b = match.get('awayTeam', {}).get('crest', '')
            fase = match.get('stage', '').replace('_', ' ').title()
            grupo = match.get('group', '').replace('_', ' ') if match.get('group') else ''
            
            gols_a = match.get('score', {}).get('fullTime', {}).get('home')
            gols_b = match.get('score', {}).get('fullTime', {}).get('away')
            penaltis_a = match.get('score', {}).get('penalties', {}).get('home')
            penaltis_b = match.get('score', {}).get('penalties', {}).get('away')
            placar_penaltis = f" (Pên: {penaltis_a}x{penaltis_b})" if penaltis_a is not None else ""
            placar = "- x -" if gols_a is None else f"{gols_a} x {gols_b}{placar_penaltis}"
            status_api = match.get('status')
            
            if status_api in ['IN_PLAY', 'PAUSED']: status = "AO VIVO"; tem_ao_vivo_agora = True
            elif status_api in ['FINISHED', 'AWARDED']: status = "ENCERRADO"
            else: status = "EM BREVE..."
                
            dt_obj = datetime.strptime(match['utcDate'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            
            # --- AJUSTE DE FUSO HORÁRIO (Campo Grande - MS | UTC-4) ---
            dt_local = dt_obj - timedelta(hours=4)
            
            jogo_formatado = {
                "id": match['id'], "time_a": time_a, "time_b": time_b, "crest_a": crest_a, "crest_b": crest_b,
                "placar": placar, "status": status, "info_fase": f"{fase} {grupo}".strip(), 
                "timestamp": dt_obj.timestamp(), 
                "data_str": dt_local.strftime('%d/%m %H:%M'), # Mostra o horário ajustado
                "gols_a_real": str(gols_a) if gols_a is not None else "N/A",
                "gols_b_real": str(gols_b) if gols_b is not None else "N/A"
            }

            stg_level = STAGE_ORDER.get(match.get('stage', 'GROUP_STAGE'), 1)
            
            if status in ['AO VIVO', 'ENCERRADO']:
                if stg_level >= max
