#!/usr/bin/env python3
"""
interpret_briefing.py

Interpretation layer for Garmin health data.
Uses Google Gemini API to analyze the numerical data and generate a personalized training recommendation.
"""

import os
import sys
import json
from dotenv import load_dotenv

# Import the Google GenAI SDK
try:
    from google import genai
    from google.genai import errors
except ImportError:
    print("Error: google-genai library not installed. Run 'pip install -r requirements.txt'", file=sys.stderr)
    sys.exit(1)

# Load environment variables
load_dotenv()

def get_briefing_prompt(data):
    """Construct a clean, detailed prompt containing the Garmin data for Gemini."""
    metadata = data.get("metadata", {})
    metrics = data.get("metrics", {})
    
    raw_date = metadata.get('date', '')
    formatted_date = raw_date
    if '-' in raw_date:
        y, m, d = raw_date.split('-')
        formatted_date = f"{d}/{m}/{y}"
    
    # Format the data into a readable text chunk for the model
    data_str = json.dumps(metrics, indent=2, ensure_ascii=False)
    
    prompt = f"""
Você é um treinador de alto rendimento e cientista do esporte especialista em fisiologia da corrida e ciclismo.
Analise os seguintes dados fisiológicos e de performance do atleta para o dia {formatted_date} e gere um briefing curto, direto ao ponto e motivador.

Nota: Os dados podem incluir atividades de ciclismo indoor (MyWhoosh/Strava) e corrida (Garmin). Os campos com sufixo "_combined" representam métricas recalculadas considerando TODAS as atividades (corrida + ciclismo). Prefira esses valores combinados quando disponíveis. O campo "recentActivities" lista as atividades da última semana com o TRIMP calculado de cada uma.

Dados fisiológicos em formato JSON:
```json
{data_str}
```

Instruções para a análise:
1. **Recuperação**: Avalie com base no Sleep Score, Sleep Quality, HRV Status/Averages e Training Readiness. Determine o semáforo correspondente:
   - 🟢 (Verde): Excelente recuperação. Bons níveis de HRV e sono reparador.
   - 🟡 (Amarelo): Recuperação moderada. Cuidado com noites mal dormidas ou HRV em queda.
   - 🔴 (Vermelho): Recuperação precária. HRV desequilibrado, sono ruim ou prontidão muito baixa.
2. **Carga**: Avalie com base no ACWR (Acute:Chronic Workload Ratio), Carga Semanal (Acute/Chronic load) e status de treino.
   - 🟢 (Verde): ACWR na zona ideal (0.8 a 1.3). Carga balanceada.
   - 🟡 (Amarelo): ACWR ligeiramente fora da zona ideal (1.3 a 1.5 ou 0.5 a 0.8), sugerindo risco moderado de lesão ou destreino.
   - 🔴 (Vermelho): ACWR em zona de perigo (>1.5 indica alto risco de lesão por pico de carga, <0.5 indica destreino acentuado).
3. **Performance**: Avalie com base no VO2Max atual, peso recente e Previsões de Prova.
   - 🟢 (Verde): Performance evoluindo ou estável em patamar alto. Treinos produtivos.
   - 🟡 (Amarelo): Performance estagnada ou pequenos ajustes necessários (ex: peso flutuando ou status destreinado).
   - 🔴 (Vermelho): Queda de rendimento, destreino visível ou fadiga crônica impactando os tempos.

Gere o briefing de forma estruturada, em Português do Brasil, exatamente no formato abaixo. Seja curto e direto ao ponto (no máximo uma frase explicativa para cada categoria):

### 🔋 Briefing Diário - {formatted_date}

**Recuperação:** [Semáforo 🟢/🟡/🔴] [Uma frase concisa explicando a qualidade da recuperação baseado no sono, HRV e prontidão].

**Carga:** [Semáforo 🟢/🟡/🔴] [Uma frase concisa sobre a relação de carga aguda/crônica (ACWR: [valor]) e se o volume está adequado].

**Performance:** [Semáforo 🟢/🟡/🔴] [Uma frase concisa sobre o VO2Max ([valor] - use o combined se houver) e evolução recente nas previsões de prova].

**Ação do Dia:**
🎯 **[Nome da Ação]**: [Instrução direta e acionável do que o atleta deve fazer hoje: e.g. "Treino Regenerativo (rodagem muito leve de 30-40 min)", "Treino de Tiros/Intervalado de Alta Intensidade", "Treino de Volume/Longão em Z2", "Descanso Total / Recovery Passivo"].
"""
    return prompt

def generate_local_fallback(data):
    """Deterministic local text fallback when Gemini API key is missing."""
    metrics = data.get("metrics", {})
    summary = metrics.get("dailySummary", {})
    sleep = metrics.get("sleep", {})
    hrv = metrics.get("hrv", {})
    readiness = metrics.get("trainingReadiness", {})
    status = metrics.get("trainingStatus", {})
    
    # --- RECOVERY ---
    readiness_score = readiness.get("score")
    sleep_score = sleep.get("sleepScore")
    sleep_duration = sleep.get("durationSeconds")
    resting_hr = summary.get("restingHeartRate")
    resting_hr_7d = summary.get("restingHeartRate7dAvg")
    hrv_status = hrv.get("status")  # BALANCED, UNBALANCED, or None
    
    rec_val = "🟡"
    rec_desc = "Sem dados suficientes para avaliação completa."
    
    if readiness_score is not None and sleep_score is not None:
        # Full data path (newer devices)
        avg_rec = (readiness_score + sleep_score) / 2
        if avg_rec >= 75:
            rec_val = "🟢"
            rec_desc = f"Recuperação excelente. Prontidão: {readiness_score}/100, Sono: {sleep_score}/100."
        elif avg_rec >= 50:
            rec_val = "🟡"
            rec_desc = f"Recuperação moderada. Prontidão: {readiness_score}/100, Sono: {sleep_score}/100."
        else:
            rec_val = "🔴"
            rec_desc = f"Recuperação baixa. Prontidão: {readiness_score}/100, Sono: {sleep_score}/100."
    elif sleep_duration:
        # Fallback: use sleep duration + resting HR (older devices like FR 935)
        sleep_hours = sleep_duration / 3600.0
        sleep_fmt = sleep.get("durationFormatted", f"{sleep_hours:.1f}h")
        deep_secs = sleep.get("deepSleepSeconds") or 0
        deep_min = deep_secs // 60
        
        hr_delta = None
        if resting_hr and resting_hr_7d and resting_hr_7d > 0:
            hr_delta = resting_hr - resting_hr_7d  # positive = elevated = worse recovery
        
        if sleep_hours >= 7.5 and (hr_delta is None or hr_delta <= 3):
            rec_val = "🟢"
            rec_desc = f"Boa recuperação. Sono: {sleep_fmt} ({deep_min}min profundo)."
        elif sleep_hours >= 6.0:
            rec_val = "🟡"
            rec_desc = f"Recuperação moderada. Sono: {sleep_fmt} ({deep_min}min profundo)."
        else:
            rec_val = "🔴"
            rec_desc = f"Sono curto ({sleep_fmt}). Recuperação comprometida."
        
        if hr_delta is not None and hr_delta > 5:
            rec_val = "🔴"
            rec_desc += f" FC repouso elevada ({resting_hr} vs média 7d: {resting_hr_7d})."
        elif hr_delta is not None and hr_delta > 3:
            if rec_val == "🟢":
                rec_val = "🟡"
            rec_desc += f" FC repouso levemente elevada ({resting_hr} vs {resting_hr_7d})."
    
    # --- LOAD ---
    # Prefer combined ACWR (Garmin + Strava merged) over Garmin-only
    acwr = status.get("acwr_combined") or status.get("acwr") or status.get("acwr_estimated")
    weekly_load = status.get("weeklyLoadTrimp_combined") or status.get("weeklyTrainingLoad")
    load_tunnel_min = status.get("loadTunnelMin")
    load_tunnel_max = status.get("loadTunnelMax")
    training_label = status.get("trainingStatus")
    strava_cycling = status.get("stravaCyclingIncluded", False)
    
    load_val = "🟡"
    load_desc = "Carga indeterminada."
    
    if acwr is not None:
        if 0.8 <= acwr <= 1.3:
            load_val = "🟢"
            load_desc = f"Carga balanceada. ACWR: {acwr:.2f}."
        elif 1.3 < acwr <= 1.5 or 0.5 <= acwr < 0.8:
            load_val = "🟡"
            load_desc = f"Atenção na carga. ACWR: {acwr:.2f} (fora da zona ideal 0.8-1.3)."
        else:
            load_val = "🔴"
            load_desc = f"Carga em zona de risco! ACWR: {acwr:.2f}."
    elif weekly_load and load_tunnel_min and load_tunnel_max:
        # Fallback: compare weekly load to load tunnel
        if load_tunnel_min <= weekly_load <= load_tunnel_max:
            load_val = "🟢"
            load_desc = f"Carga semanal dentro do túnel ideal ({weekly_load} / {load_tunnel_min}-{load_tunnel_max})."
        elif weekly_load < load_tunnel_min:
            load_val = "🟡"
            load_desc = f"Carga semanal abaixo do ideal ({weekly_load} < {load_tunnel_min})."
        else:
            load_val = "🔴"
            load_desc = f"Carga semanal acima do túnel ({weekly_load} > {load_tunnel_max})."
    
    if training_label and training_label not in ("status",):
        load_desc += f" Status: {training_label}."
    if strava_cycling:
        load_desc += " (inclui ciclismo Strava)"
            
    # --- PERFORMANCE ---
    vo2max = status.get("estimated_vo2max_combined") or status.get("vo2Max")
    fitness_age = status.get("estimated_fitness_age_combined") or status.get("fitnessAge")
    perf_val = "🟡"
    perf_desc = f"VO2Max: {vo2max or 'n/a'}."
    
    if vo2max:
        if status.get("estimated_vo2max_combined"):
            perf_desc = f"VO2Max Combinado: {vo2max}."
        if vo2max >= 50:
            perf_val = "🟢"
            perf_desc = f"Performance forte. {perf_desc}"
        elif vo2max >= 40:
            perf_val = "🟡"
            perf_desc = f"Performance moderada. {perf_desc}"
        else:
            perf_val = "🔴"
            perf_desc = f"Performance abaixo do esperado. {perf_desc}"
        if fitness_age:
            if status.get("estimated_fitness_age_combined"):
                perf_desc += f" Idade fitness recalculada: {fitness_age}."
            else:
                perf_desc += f" Idade fitness: {fitness_age}."

    # --- ACTION ---
    action = "Treino Moderado Aeróbico"
    reason = "Equilíbrio geral de prontidão e carga."
    if rec_val == "🔴":
        action = "Descanso Total / Recovery Ativo Leve"
        reason = "Fisiologia indica alta fadiga. Priorize recuperação."
    elif load_val == "🔴":
        action = "Redução de Volume / Corrida Regenerativa"
        reason = "Carga fora da zona de segurança."
    elif rec_val == "🟢" and load_val == "🟢":
        action = "Treino de Alta Intensidade ou Intervalado"
        reason = "Janela de oportunidade fisiológica aberta para estímulo forte."
    elif rec_val == "🟢" and load_val == "🟡":
        action = "Treino de Volume (Longão/Z2)"
        reason = "Boa recuperação, carga precisa de atenção — volume aeróbio é ideal."

    raw_date = data.get("metadata", {}).get("date", "")
    formatted_date = raw_date
    if '-' in raw_date:
        y, m, d = raw_date.split('-')
        formatted_date = f"{d}/{m}/{y}"
    
    final_text = f"### 🔋 Briefing Diário - {formatted_date}\n\n"
    final_text += f"**Recuperação:** {rec_val} {rec_desc}\n\n"
    final_text += f"**Carga:** {load_val} {load_desc}\n\n"
    final_text += f"**Performance:** {perf_val} {perf_desc}\n\n"
    final_text += f"**Ação do Dia:**\n🎯 **{action}**: {reason}\n"
    return final_text

def main():
    if len(sys.argv) < 2:
        input_file = "garmin_data.json"
    else:
        input_file = sys.argv[1]

    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON data: {e}", file=sys.stderr)
        sys.exit(1)

    api_key = os.getenv("GEMINI_API_KEY")
    final_text = ""
    if not api_key:
        print("Warning: GEMINI_API_KEY environment variable not set. Using local deterministic fallback rules...", file=sys.stderr)
        final_text = generate_local_fallback(data)
    else:
        # Call Gemini API using google-genai
        try:
            client = genai.Client(api_key=api_key)
            prompt = get_briefing_prompt(data)
            
            # Use gemini-2.5-flash as the default fast and capable model
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            final_text = response.text
            
        except errors.APIError as err:
            print(f"Gemini API Error: {err}. Falling back to deterministic analysis...", file=sys.stderr)
            final_text = generate_local_fallback(data)
        except Exception as err:
            print(f"Unexpected error running interpretation: {err}. Falling back to deterministic analysis...", file=sys.stderr)
            final_text = generate_local_fallback(data)
            
    # Save to file
    with open("briefing.md", "w", encoding="utf-8") as f:
        f.write(final_text)

    print(final_text)

if __name__ == "__main__":
    main()
