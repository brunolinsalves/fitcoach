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

VO2_TABLE_MEN = {
    "20-29": {"Satisfatório": 41.7, "Bom": 45.4, "Excelente": 51.1, "Superior": 55.4},
    "30-39": {"Satisfatório": 40.5, "Bom": 44.0, "Excelente": 48.3, "Superior": 54.0},
    "40-49": {"Satisfatório": 38.5, "Bom": 42.4, "Excelente": 46.4, "Superior": 52.5},
    "50-59": {"Satisfatório": 35.6, "Bom": 39.2, "Excelente": 43.4, "Superior": 48.9},
    "60-69": {"Satisfatório": 32.3, "Bom": 35.5, "Excelente": 39.5, "Superior": 45.7},
    "70-79": {"Satisfatório": 29.4, "Bom": 32.3, "Excelente": 36.7, "Superior": 42.1},
}

VO2_TABLE_WOMEN = {
    "20-29": {"Satisfatório": 36.1, "Bom": 39.5, "Excelente": 43.9, "Superior": 49.6},
    "30-39": {"Satisfatório": 34.4, "Bom": 37.8, "Excelente": 42.4, "Superior": 47.4},
    "40-49": {"Satisfatório": 33.0, "Bom": 36.3, "Excelente": 39.7, "Superior": 45.3},
    "50-59": {"Satisfatório": 30.1, "Bom": 33.0, "Excelente": 36.7, "Superior": 41.1},
    "60-69": {"Satisfatório": 27.5, "Bom": 30.0, "Excelente": 33.0, "Superior": 37.8},
    "70-79": {"Satisfatório": 25.9, "Bom": 28.1, "Excelente": 30.9, "Superior": 36.7},
}

def classify_vo2max(vo2: float, sex: str, age: int):
    table = VO2_TABLE_WOMEN if sex == 'F' else VO2_TABLE_MEN
    if age < 20:
        age_group = "20-29"
    elif age > 79:
        age_group = "70-79"
    else:
        tens = int(age // 10)
        age_group = f"{tens}0-{tens}9"
        
    thresholds = table[age_group]
    if vo2 < thresholds["Satisfatório"]:
        return "Fraco", "🔴"
    elif vo2 < thresholds["Bom"]:
        return "Satisfatório", "🟡"
    elif vo2 < thresholds["Excelente"]:
        return "Bom", "🟢"
    elif vo2 < thresholds["Superior"]:
        return "Excelente", "🟢"
    else:
        return "Superior", "🟢"

def get_briefing_prompt(data):
    """Construct a clean, detailed prompt containing the Garmin data for Gemini."""
    metadata = data.get("metadata", {})
    metrics = data.get("metrics", {})
    
    raw_date = metadata.get('date', '')
    formatted_date = raw_date
    if '-' in raw_date:
        y, m, d = raw_date.split('-')
        formatted_date = f"{d}/{m}/{y}"
        
    # Calculate age and sex for Gemini prompt
    gender_raw = metadata.get("gender")
    sex_str = "Masculino" if gender_raw == "MALE" else ("Feminino" if gender_raw == "FEMALE" else "Masculino")
    
    birth_date_str = metadata.get("birthDate")
    age = 39 # default fallback
    if birth_date_str:
        try:
            from datetime import date as dt_date
            birth_date_obj = dt_date.fromisoformat(birth_date_str)
            ref_date = dt_date.fromisoformat(raw_date) if raw_date else dt_date.today()
            age = ref_date.year - birth_date_obj.year - ((ref_date.month, ref_date.day) < (birth_date_obj.month, birth_date_obj.day))
        except Exception:
            pass
    else:
        fitness_age_obj = metrics.get("fitnessAge", {})
        if isinstance(fitness_age_obj, dict) and fitness_age_obj.get("chronologicalAge"):
            age = fitness_age_obj.get("chronologicalAge")
        else:
            ts = metrics.get("trainingStatus", {})
            age = ts.get("fitnessAge") or 39
            
    # Get the age ranges for prompt description
    men_range = VO2_TABLE_MEN.get(
        "20-29" if age < 20 else ("70-79" if age > 79 else f"{int(age // 10)}0-{int(age // 10)}9")
    )
    women_range = VO2_TABLE_WOMEN.get(
        "20-29" if age < 20 else ("70-79" if age > 79 else f"{int(age // 10)}0-{int(age // 10)}9")
    )
    
    # Format the data into a readable text chunk for the model
    data_str = json.dumps(metrics, indent=2, ensure_ascii=False)
    
    prompt = f"""
Você é um treinador de alto rendimento e cientista do esporte especialista em fisiologia da corrida e ciclismo.

Analise os seguintes dados fisiológicos e de performance do atleta (Sexo: {sex_str}, Idade: {age} anos) para o dia {formatted_date} e gere um briefing detalhado, direto ao ponto e motivador.

**Sobre os dados:**
- Os dados podem incluir atividades de ciclismo indoor (MyWhoosh/Strava) e corrida (Garmin).
- Campos com sufixo "_combined" representam métricas recalculadas considerando TODAS as atividades. **Sempre prefira esses valores quando disponíveis.**
- O campo "recentActivities" lista as atividades da última semana com o TRIMP calculado de cada uma — use para identificar padrão de carga e tendência.

Dados fisiológicos em formato JSON:
```json
{data_str}
```

---

**INSTRUÇÕES DE ANÁLISE:**

### 1. 🔋 Recuperação
Avalie com base em: Sleep Score, Sleep Quality, HRV Status, HRV Averages e Training Readiness.

**Semáforo:**
- 🟢 Verde: Excelente — HRV estável ou em alta, sono reparador, prontidão elevada.
- 🟡 Amarelo: Moderada — HRV em queda leve, sono fragmentado ou prontidão intermediária.
- 🔴 Vermelho: Precária — HRV desequilibrado, sono ruim ou prontidão muito baixa.

**Detalhe esperado na saída (2–3 frases):**
- Qualidade objetiva do sono (score e duração se disponível)
- Estado do HRV: estável, em alta ou em queda, e o que isso indica fisiologicamente
- Nível de prontidão e implicação prática para o treino de hoje

---

### 2. ⚡ Carga de Treino
Avalie com base em: ACWR, Acute Load (carga aguda), Chronic Load (carga crônica), TRIMP das atividades recentes e status de treino.

**Semáforo:**
- 🟢 Verde: ACWR entre 0.8 e 1.3 — zona ideal de adaptação.
- 🟡 Amarelo: ACWR entre 1.3–1.5 ou 0.5–0.8 — risco moderado (sobrecarga ou destreino leve).
- 🔴 Vermelho: ACWR > 1.5 (alto risco de lesão) ou < 0.5 (destreino acentuado).

**Detalhe esperado na saída (2–3 frases):**
- Valores de ACWR, carga aguda e crônica com interpretação
- Tendência da semana baseada no "recentActivities" (carga crescente, estável ou decrescente?)
- Se houver risco de overreaching ou janela de adaptação favorável, mencionar explicitamente

---

### 3. 🏆 Performance
Use "estimated_vo2max_combined" se disponível; caso contrário, use o VO2Max disponível.

**Classificações Cooper por sexo e idade ({age} anos):**
- Homem: Fraco (<{men_range['Satisfatório']}), Satisfatório ({men_range['Satisfatório']}–{men_range['Bom']}), Bom ({men_range['Bom']}–{men_range['Excelente']}), Excelente ({men_range['Excelente']}–{men_range['Superior']}), Superior (≥{men_range['Superior']})
- Mulher: Fraco (<{women_range['Satisfatório']}), Satisfatório ({women_range['Satisfatório']}–{women_range['Bom']}), Bom ({women_range['Bom']}–{women_range['Excelente']}), Excelente ({women_range['Excelente']}–{women_range['Superior']}), Superior (≥{women_range['Superior']})

**Semáforo:**
- 🟢 Verde: Bom, Excelente ou Superior.
- 🟡 Amarelo: Satisfatório — há espaço de evolução.
- 🔴 Vermelho: Fraco ou queda visível em relação a registros anteriores.

**Detalhe esperado na saída (2 frases):**
- VO2Max atual com classificação e contexto (próximo ao limite superior/inferior da faixa?)
- Se houver tendência recente de melhora ou estagnação, comentar

---

### 4. 🔍 Análise Integrada
**Esta seção é obrigatória.** Cruze as três dimensões acima e identifique o padrão dominante do atleta hoje. Exemplos de raciocínio esperado:
- Recuperação 🔴 + Carga 🔴 + Performance 🟢 → "Você está produzindo resultados, mas o sistema está no limite. Risco real de overreaching se não houver recuo agora."
- Recuperação 🟢 + Carga 🟡 + Performance 🟢 → "Janela favorável para um estímulo de qualidade hoje. A carga pode subir com segurança."
- Recuperação 🟡 + Carga 🟢 + Performance 🟡 → "Momento de consistência. Treino moderado hoje consolida a base sem adicionar risco."

Escreva 2–3 frases sintetizando o estado geral e a lógica do que recomendar.

---

### 5. 🎯 Ação do Dia
Com base na análise integrada, prescreva **uma ação específica e acionável**. Seja concreto: inclua intensidade (zona), duração estimada e objetivo fisiológico da sessão.

**Exemplos de nível de detalhe esperado:**
- ✅ "Rodagem regenerativa de 35–40 min em Z1 (abaixo de 130 bpm) para estimular recuperação ativa sem adicionar carga ao sistema nervoso central."
- ✅ "Intervalado 6×4 min em Z4 (85–90% FCmax) com 3 min de recuperação ativa. Objetivo: estímulo de VO2Max aproveitando a boa prontidão de hoje."
- ✅ "Descanso total ou mobilidade de 20 min. Seu sistema não está em condições de absorver treino produtivo hoje — recuperação passiva é a prescrição correta."
- ❌ (evitar) "Faça um treino leve." — vago demais.

---

**FORMATO DE SAÍDA — siga exatamente:**

🔋 Briefing Diário — {formatted_date}

**Recuperação:** [🟢/🟡/🔴]
[2–3 frases: sono + HRV + prontidão com interpretação]

**Carga:** [🟢/🟡/🔴]
[2–3 frases: ACWR + tendência semanal + risco ou oportunidade]

**Performance:** [🟢/🟡/🔴]
[2 frases: VO2Max com classificação + tendência]

**Análise Integrada:** 🔍
[2–3 frases cruzando as três dimensões e explicando a lógica da recomendação]

**Ação do Dia:** 🎯
[Prescrição específica com zona de intensidade, duração e objetivo fisiológico]
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
    metadata = data.get("metadata", {})
    raw_date = metadata.get("date", "")
    vo2max = status.get("estimated_vo2max_combined") or status.get("vo2Max")
    fitness_age = status.get("estimated_fitness_age_combined") or status.get("fitnessAge")
    perf_val = "🟡"
    perf_desc = f"VO2Max: {vo2max or 'n/a'}."
    
    if vo2max:
        # Determine sex
        gender_raw = metadata.get("gender")
        sex = None
        if gender_raw == "MALE":
            sex = "M"
        elif gender_raw == "FEMALE":
            sex = "F"
            
        if not sex:
            strava_tokens_path = "strava_tokens.json"
            if os.path.exists(strava_tokens_path):
                try:
                    with open(strava_tokens_path, "r", encoding="utf-8") as sf:
                        strava_tokens = json.load(sf)
                        athlete = strava_tokens.get("athlete", {})
                        sex_raw = athlete.get("sex")
                        if sex_raw in ("M", "F"):
                            sex = sex_raw
                except Exception:
                    pass
        if not sex:
            sex = "M"
            
        # Determine age
        birth_date_str = metadata.get("birthDate")
        age = None
        if birth_date_str:
            try:
                from datetime import date as dt_date
                birth_date_obj = dt_date.fromisoformat(birth_date_str)
                ref_date = dt_date.fromisoformat(raw_date) if raw_date else dt_date.today()
                age = ref_date.year - birth_date_obj.year - ((ref_date.month, ref_date.day) < (birth_date_obj.month, birth_date_obj.day))
            except Exception:
                pass
        if age is None:
            fitness_age_obj = metrics.get("fitnessAge", {})
            if isinstance(fitness_age_obj, dict):
                age = fitness_age_obj.get("chronologicalAge")
        if age is None:
            age = status.get("fitnessAge")
        if age is None:
            age = 39
            
        label, semaphor = classify_vo2max(float(vo2max), sex, age)
        perf_val = semaphor
        
        if status.get("estimated_vo2max_combined"):
            perf_desc = f"Performance {label}. VO2Max Combinado: {vo2max}."
        else:
            perf_desc = f"Performance {label}. VO2Max: {vo2max}."
            
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
    from pathlib import Path
    project_dir = Path(__file__).parent.resolve()

    if len(sys.argv) < 2:
        input_file = "garmin_data.json"
    else:
        input_file = sys.argv[1]

    if not os.path.isabs(input_file):
        input_file = os.path.abspath(project_dir / input_file)

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
        import time
        import random
        
        models_to_try = ["gemini-3.5-flash", "gemini-2.5-flash"]
        success = False
        
        try:
            client = genai.Client(api_key=api_key)
        except Exception as e:
            print(f"Error initializing Gemini client: {e}. Falling back to deterministic analysis...", file=sys.stderr)
            final_text = generate_local_fallback(data)
            client = None
            
        if client:
            prompt = get_briefing_prompt(data)
            
            for model_name in models_to_try:
                if success:
                    break
                    
                print(f"Trying model: {model_name}...", file=sys.stderr)
                start_time = time.time()
                attempt = 0
                max_attempts = 3
                base_delay = 5.0
                factor = 2.0
                max_delay = 120.0
                max_total_time = 900.0  # 15 minutes limit per model
                
                while attempt < max_attempts:
                    attempt += 1
                    
                    # Check overall time budget for this model
                    elapsed = time.time() - start_time
                    if elapsed >= max_total_time:
                        print(f"Time limit of 15 minutes exceeded for model {model_name} ({elapsed:.1f}s elapsed).", file=sys.stderr)
                        break
                    
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                        )
                        final_text = response.text
                        success = True
                        break
                    except errors.APIError as err:
                        # Do not retry on client configuration/permission errors
                        if err.code in (400, 401, 403, 404):
                            print(f"Gemini API Client Error (non-retryable) on model {model_name}: {err}.", file=sys.stderr)
                            break
                        
                        print(f"[Attempt {attempt}/{max_attempts}] Gemini API Error on model {model_name}: {err}.", file=sys.stderr)
                    except KeyboardInterrupt:
                        print("\nOperation cancelled by user.", file=sys.stderr)
                        sys.exit(1)
                    except Exception as err:
                        print(f"[Attempt {attempt}/{max_attempts}] Unexpected error on model {model_name}: {err}.", file=sys.stderr)
                    
                    if attempt < max_attempts:
                        # Calculate delay with exponential backoff + jitter
                        delay = min(base_delay * (factor ** (attempt - 1)), max_delay)
                        jitter = random.uniform(0.1, 1.0)
                        total_delay = delay + jitter
                        
                        remaining_time = max_total_time - (time.time() - start_time)
                        if remaining_time <= 0:
                            print(f"Time limit of 15 minutes reached for model {model_name} during backoff.", file=sys.stderr)
                            break
                        
                        sleep_time = min(total_delay, remaining_time)
                        print(f"Retrying model {model_name} in {sleep_time:.2f} seconds...", file=sys.stderr)
                        time.sleep(sleep_time)
                
                if success:
                    print(f"Successfully generated briefing using model {model_name}!", file=sys.stderr)
                    break
                else:
                    print(f"Model {model_name} failed all attempts or timed out.", file=sys.stderr)
            
            if not success:
                print("All models and retry attempts failed. Falling back to deterministic analysis...", file=sys.stderr)
                final_text = generate_local_fallback(data)
            
    # Save to file
    briefing_out = project_dir / "briefing.md"
    with open(briefing_out, "w", encoding="utf-8") as f:
        f.write(final_text)

    print(final_text)

if __name__ == "__main__":
    main()
