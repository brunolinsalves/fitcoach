from dotenv import load_dotenv
import requests, os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

load_dotenv()

HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")
HOME_ASSISTANT_URL   = os.getenv("HOME_ASSISTANT_URL")

# Configurações do servidor
ENTITY_ID = "sensor.s26_bruno_heart_rate"


headers = {
    "Authorization": f"Bearer {HOME_ASSISTANT_TOKEN}",
    "Content-Type": "application/json",
}

def extrair_janela_hr(horas_atras=24):
    """Extrai leituras de frequência cardíaca do Home Assistant.

    Args:
        horas_atras: Quantas horas para trás a janela de consulta deve cobrir.
                     Padrão: 24h (cobre o dia inteiro, incluindo tarde e noite).
    """
    # Usa UTC explicitamente para evitar inconsistências com o sufixo "Z"
    agora = datetime.now(timezone.utc)
    inicio = agora - timedelta(hours=horas_atras)

    # Formato ISO-8601 com "Z" (UTC) — necessário para a API do Home Assistant
    start_time = inicio.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time   = agora.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"Buscando dados de {start_time} até {end_time} (UTC)")

    # end_time precisa ser URL-encoded pois vai como query param
    url = f"{HOME_ASSISTANT_URL}/api/history/period/{start_time}?filter_entity_id={ENTITY_ID}&end_time={quote(end_time)}"

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        # A API de histórico retorna uma lista de listas [[conteudo]]
        dados_historicos = response.json()

        if not dados_historicos or len(dados_historicos[0]) == 0:
            print("Nenhum dado encontrado para este período.")
            return []

        leituras = dados_historicos[0]
        pontos_hr = []

        for leitura in leituras:
            try:
                valor = float(leitura.get("state"))
                # timestamp de quando essa leitura específica foi gravada
                timestamp = leitura.get("last_changed")

                pontos_hr.append({
                    "timestamp": timestamp,
                    "hr": valor
                })
            except ValueError:
                # Ignora estados indisponíveis ou desconhecidos ('unknown', 'unavailable')
                continue

        return pontos_hr
    else:
        print(f"Erro ao acessar histórico: {response.status_code} - {response.text}")
        return []


# Executa a extração da série temporal (últimas 24 horas)
historico = extrair_janela_hr(horas_atras=24)
print(f"Total de amostras coletadas: {len(historico)}")
for item in historico:
    print(item)