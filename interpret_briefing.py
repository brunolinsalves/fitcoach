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
    
    ref_dt = None
    day_of_week_str = ""
    is_weekend = False
    if raw_date:
        try:
            from datetime import date as dt_date
            ref_dt = dt_date.fromisoformat(raw_date)
            weekdays_pt = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
            day_of_week_str = weekdays_pt[ref_dt.weekday()]
            is_weekend = ref_dt.weekday() >= 5
        except Exception:
            pass

    # Check for planned workouts in metrics or fetch live if missing
    planned_workouts = metrics.get("plannedWorkouts")
    if planned_workouts is None:
        try:
            from garmin_calendar import fetch_planned_workouts_for_date
            planned_workouts = fetch_planned_workouts_for_date(raw_date)
        except Exception:
            planned_workouts = []

    planned_info_text = ""
    if planned_workouts:
        pw_list = []
        for pw in planned_workouts:
            pw_list.append(f"- Título: {pw.get('title')}\n  Origem: {pw.get('origin', 'RUNNA Plan')}\n  Modalidade: {pw.get('sport')}\n  Descrição/Detalhes: {pw.get('description')}")
        planned_info_text = "\n".join(pw_list)
    else:
        planned_info_text = f"Nenhum treino de corrida agendado no calendário RUNNA para esta data ({day_of_week_str})."

    # Format the data into a readable text chunk for the model
    data_str = json.dumps(metrics, indent=2, ensure_ascii=False)
    
    prompt = f"""
Você é um treinador de alto rendimento e cientista do esporte especialista em fisiologia da corrida e ciclismo.

Analise os seguintes dados fisiológicos e de performance do atleta (Sexo: {sex_str}, Idade: {age} anos) para a data {formatted_date} ({day_of_week_str}) e gere um briefing detalhado, direto ao ponto e motivador.

**Sobre os dados:**
- Os dados incluem métricas fisiológicas, atividades recentes e treinos planejados no calendário (RUNNA / Garmin).
- Campos com sufixo "_combined" representam métricas recalculadas considerando TODAS as atividades. **Sempre prefira esses valores quando disponíveis.**
- O campo "recentActivities" lista as atividades da última semana com o TRIMP calculado de cada uma — use para identificar padrão de carga e tendência.

Dados fisiológicos e de treinos em formato JSON:
```json
{data_str}
```

**TREINO(S) AGENDADO(S) NO CALENDÁRIO PARA HOJE ({formatted_date} - {day_of_week_str}):**
{planned_info_text}

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
**Esta seção é obrigatória.** Cruze as três dimensões acima e identifique o padrão dominante do atleta hoje. Escreva 2–3 frases sintetizando o estado geral e a lógica da recomendação.

---

### 5. 🎯 Ação do Dia
Com base na análise integrada e no **Calendário do Atleta (RUNNA/Garmin)**, prescreva **uma ação específica e acionável**.

**REGRAS DE OURO PARA A PRESCRIÇÃO DA AÇÃO DO DIA:**

1. **SE HOUVER TREINO AGENDADO NO RUNNA/GARMIN HOJE:**
   - A recomendação principal **DEVE SER a realização do treino agendado no RUNNA**, fornecendo orientações precisas de execução (distância, ritmo target, zonas de FC e estratégia).
   - Se a recuperação for Boa/Moderada (🟢/🟡): Recomende a execução do treino do RUNNA. Se a recuperação for excelente (🟢), você pode sugerir um complemento leve em outro horário (ex: 10–15 min de mobilidade/core).
   - Se a recuperação for Ruim (🔴) ou ACWR > 1.5: Prescreva a **adaptação/redução consciente** do treino do RUNNA (ex: reduzir distância ou ritmo para Z1).

2. **SE NÃO HOUVER TREINO AGENDADO NO RUNNA/GARMIN HOJE:**
   - **É ESTRITAMENTE PROIBIDO RECOMENDAR CORRIDA:** O atleta segue a planilha de corrida do RUNNA estritamente. Se não há corrida agendada no RUNNA hoje, não prescreva corrida.
   - **PRESCREVA CROSS-TRAINING (CICLISMO OU NATAÇÃO):** Se a recuperação for boa ou moderada (🟢/🟡), **recomende um treino de Ciclismo (Cycling) ou Natação (Swimming)**. O atleta QUER treinar nesses dias sem corrida.
   - **PREFERÊNCIA POR CICLISMO NOS FINAIS DE SEMANA ({day_of_week_str}):** Nos finais de semana (Sábado e Domingo), **priorize o Ciclismo** (pois a natação no condomínio é mais complexa no fim de semana).
   - **SUGESTÃO DE WORKOUT DO MYWHOOSH PARA CICLISMO:** Sempre que recomendar Ciclismo (especialmente indoor), **indique explicitamente um treino/workout específico do MyWhoosh** (consultando treinos em https://mywhooshinfo.com/workouts/, como ex: "MyWhoosh Zone 2 / Endurance - 45 a 60 min", "MyWhoosh Sweet Spot - 3x8 min", "MyWhoosh Tempo 45min", "MyWhoosh VO2Max 5min Max Aerobic", "MyWhoosh Cadence Builder", etc., ajustando duração e intensidade à fisiologia de hoje).
   - **DESCANSO TOTAL APENAS QUANDO ESTRITAMENTE NECESSÁRIO:** Só prescreva descanso passivo total se a fisiologia exigir **estritamente** (ex: Recuperação 🔴 Vermelha, HRV muito desequilibrado ou risco severo de overreaching ACWR > 1.5). Caso a recuperação seja 🟢 Verde ou 🟡 Amarela, **RECOMENDE TREINO DE CICLISMO (MYWHOOSH) OU NATAÇÃO!**

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
[Prescrição específica: se houver treino RUNNA, detalhe a execução do RUNNA. Se NÃO houver treino RUNNA, recomende Ciclismo (com workout do MyWhoosh) ou Natação, reservando Descanso Total apenas se a recuperação for 🔴 Vermelha.]
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
    
    rec_val = "🟡"
    rec_desc = "Sem dados suficientes para avaliação completa."
    
    if readiness_score is not None and sleep_score is not None:
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
        sleep_hours = sleep_duration / 3600.0
        sleep_fmt = sleep.get("durationFormatted", f"{sleep_hours:.1f}h")
        
        hr_delta = None
        if resting_hr and resting_hr_7d and resting_hr_7d > 0:
            hr_delta = resting_hr - resting_hr_7d
        
        if sleep_hours >= 7.5 and (hr_delta is None or hr_delta <= 3):
            rec_val = "🟢"
            rec_desc = f"Boa recuperação. Sono: {sleep_fmt}."
        elif sleep_hours >= 6.0:
            rec_val = "🟡"
            rec_desc = f"Recuperação moderada. Sono: {sleep_fmt}."
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
    acwr = status.get("acwr_combined") or status.get("acwr") or status.get("acwr_estimated")
    weekly_load = status.get("weeklyLoadTrimp_combined") or status.get("weeklyTrainingLoad")
    load_tunnel_min = status.get("loadTunnelMin")
    load_tunnel_max = status.get("loadTunnelMax")
    training_label = status.get("trainingStatus")
    
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
        if load_tunnel_min <= weekly_load <= load_tunnel_max:
            load_val = "🟢"
            load_desc = f"Carga semanal dentro do túnel ideal ({weekly_load} / {load_tunnel_min}-{load_tunnel_max})."
        elif weekly_load < load_tunnel_min:
            load_val = "🟡"
            load_desc = f"Carga semanal abaixo do ideal ({weekly_load} < {load_tunnel_min})."
        else:
            load_val = "🔴"
            load_desc = f"Carga semanal acima do túnel ({weekly_load} > {load_tunnel_max})."
    
    # --- PERFORMANCE ---
    metadata = data.get("metadata", {})
    raw_date = metadata.get("date", "")
    vo2max = status.get("estimated_vo2max_combined") or status.get("vo2Max")
    perf_val = "🟡"
    perf_desc = f"VO2Max: {vo2max or 'n/a'}."
    
    if vo2max:
        gender_raw = metadata.get("gender")
        sex = "M" if gender_raw == "MALE" else ("F" if gender_raw == "FEMALE" else "M")
        age = 39
        if metadata.get("birthDate"):
            try:
                from datetime import date as dt_date
                bdate = dt_date.fromisoformat(metadata.get("birthDate"))
                rdate = dt_date.fromisoformat(raw_date) if raw_date else dt_date.today()
                age = rdate.year - bdate.year - ((rdate.month, rdate.day) < (bdate.month, bdate.day))
            except Exception:
                pass
            
        label, semaphor = classify_vo2max(float(vo2max), sex, age)
        perf_val = semaphor
        perf_desc = f"Performance {label}. VO2Max: {vo2max}."

    # --- ACTION ---
    planned_workouts = metrics.get("plannedWorkouts")
    if planned_workouts is None:
        try:
            from garmin_calendar import fetch_planned_workouts_for_date
            planned_workouts = fetch_planned_workouts_for_date(raw_date)
        except Exception:
            planned_workouts = []

    action = "Ciclismo Indoor MyWhoosh (Zone 2 Endurance)"
    reason = "Sem treino RUNNA agendado. Treino aeróbico de ciclismo sem impacto nas articulações."
    
    if planned_workouts:
        pw = planned_workouts[0]
        title = pw.get("title", "Treino do Plano")
        desc = (pw.get("description") or "").strip()
        first_line = desc.splitlines()[0] if desc else title
        origin = pw.get("origin", "Runna Plan")
        
        if rec_val == "🔴" or load_val == "🔴":
            action = f"Ajustar/Reduzir Treino do {origin} ({title})"
            reason = f"O plano prevê '{title}', porém seus dados fisiológicos (recuperação/carga) exigem cautela. Reduza o volume/intensidade ou troque por descanso."
        else:
            action = f"Executar Treino do {origin}: {title}"
            reason = f"Realize o treino agendado no seu plano. {first_line}"
    else:
        # No RUNNA workout scheduled for today
        if rec_val == "🔴" or load_val == "🔴":
            action = "Descanso Total / Recovery Ativo Leve"
            reason = "Sem treino RUNNA hoje e sua fisiologia indica alta fadiga/sobrecarga (estritamente necessário descansar)."
        else:
            is_weekend_day = False
            if raw_date:
                try:
                    from datetime import date as dt_date
                    is_weekend_day = dt_date.fromisoformat(raw_date).weekday() >= 5
                except Exception:
                    pass
            
            if is_weekend_day or rec_val == "🟢":
                action = "Ciclismo Indoor MyWhoosh (Sessão Endurance Z2 / Sweetspot)"
                reason = "Sem treino RUNNA hoje. Aproveite a boa recuperação para treinar ciclismo no MyWhoosh (ex: MyWhoosh Zone 2 Endurance 45-60 min ou Sweetspot)."
            else:
                action = "Natação ou Ciclismo Indoor (MyWhoosh)"
                reason = "Sem treino RUNNA hoje. Mantenha o condicionamento aeróbico com natação ou treino de ciclismo no MyWhoosh."

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
