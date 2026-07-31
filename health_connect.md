# Health Connect — Sensores disponíveis no Home Assistant

Sensores do dispositivo **Samsung Galaxy S26 (Bruno)** e **Amazfit Helio Strap** integrados via Zepp + Health Connect + Home Assistant Companion App.

> **Última verificação:** 2026-07-31  
> **Endpoint base:** `https://casa.brunolinsalves.com/api`

---

## 🏃 Atividade Física

| Entity ID | Descrição | Unidade | Valor atual |
|-----------|-----------|---------|-------------|
| `sensor.s26_bruno_daily_steps` | Passos diários | steps | 1.139 |
| `sensor.s26_bruno_daily_distance` | Distância diária | m | 438,7 |
| `sensor.s26_bruno_daily_elevation_gained` | Elevação ganha no dia | m | 0 |
| `sensor.s26_bruno_daily_floors` | Andares subidos | floors | 0 |
| `sensor.s26_bruno_active_calories_burned` | Calorias ativas queimadas | kcal | 399 |
| `sensor.s26_bruno_total_calories_burned` | Calorias totais queimadas | kcal | 516,45 |
| `sensor.s26_bruno_detected_activity` | Atividade detectada | — | still |

---

## ❤️ Cardiovascular

| Entity ID | Descrição | Unidade | Valor atual |
|-----------|-----------|---------|-------------|
| `sensor.s26_bruno_heart_rate` | Frequência cardíaca | bpm | 58 |
| `sensor.s26_bruno_resting_heart_rate` | Frequência cardíaca em repouso | bpm | 53 |
| `sensor.s26_bruno_heart_rate_variability` | Variabilidade da FC (HRV) | ms | 53 |
| `sensor.s26_bruno_oxygen_saturation` | Saturação de oxigênio (SpO2) | % | 99 |
| `sensor.s26_bruno_respiratory_rate` | Frequência respiratória | bpm | 17 |

---

## 😴 Sono

| Entity ID | Descrição | Unidade | Valor atual |
|-----------|-----------|---------|-------------|
| `sensor.s26_bruno_sleep_duration` | Duração do sono | min | 384 (~6h24) |
| `sensor.s26_bruno_sleep_confidence` | Confiança na detecção do sono | % | 50 |
| `sensor.s26_bruno_sleep_segment` | Segmento de sono | ms | 20.160.000 (~5h36) |

---

## 🏋️ Composição Corporal & Metabolismo

| Entity ID | Descrição | Unidade | Valor atual |
|-----------|-----------|---------|-------------|
| `sensor.s26_bruno_weight` | Peso | g | 83.000 (83 kg) |
| `sensor.s26_bruno_height` | Altura | m | 1,82 |
| `sensor.s26_bruno_basal_metabolic_rate` | Taxa metabólica basal | kcal/day | 1.739,5 |
| `sensor.s26_bruno_body_fat` | Percentual de gordura corporal | % | unknown |
| `sensor.s26_bruno_lean_body_mass` | Massa magra | g | unknown |
| `sensor.s26_bruno_body_water_mass` | Massa de água corporal | g | unknown |
| `sensor.s26_bruno_bone_mass` | Massa óssea | g | unknown |
| `sensor.s26_bruno_vo2_max` | VO2 máximo | mL/kg/min | unknown |

---

## 🩺 Sinais Vitais & Outros

| Entity ID | Descrição | Unidade | Valor atual |
|-----------|-----------|---------|-------------|
| `sensor.s26_bruno_blood_glucose` | Glicose no sangue | mg/dL | unknown |
| `sensor.s26_bruno_diastolic_blood_pressure` | Pressão arterial diastólica | mmHg | unknown |
| `sensor.s26_bruno_systolic_blood_pressure` | Pressão arterial sistólica | mmHg | unknown |
| `sensor.s26_bruno_body_temperature` | Temperatura corporal | °C | unknown |
| `sensor.s26_bruno_basal_body_temperature` | Temperatura basal do corpo | °C | unknown |
| `sensor.s26_bruno_daily_hydration` | Hidratação diária | mL | 0 |

---

## 📝 Observações

- Com o uso do **Amazfit Helio Strap** (conectado via Zepp ao Health Connect), novos dados passaram a ser populados com sucesso no Home Assistant:
  - **Variabilidade da FC (HRV):** `heart_rate_variability` (53 ms)
  - **Saturação de Oxigênio (SpO2):** `oxygen_saturation` (99%)
  - **Frequência Respiratória:** `respiratory_rate` (17 bpm)
  - **Segmento de Sono:** `sleep_segment` (20.160.000 ms)
- Sensores que permanecem `unknown` exigem medições específicas não fornecidas ou não gravadas no Health Connect (balança de bioimpedância inteligente, glicosímetro, medidor de pressão arterial, termômetro).
- Os sensores mais ricos em histórico para análise contínua são:
  - `heart_rate`
  - `resting_heart_rate`
  - `heart_rate_variability` (HRV)
  - `oxygen_saturation` (SpO2)
  - `respiratory_rate`
  - `sleep_duration` & `sleep_segment`
  - `daily_steps`
  - `active_calories_burned`
  - `total_calories_burned`
- A API de histórico é acessada via:
  ```
  GET /api/history/period/{start_time}?filter_entity_id={entity_id}&end_time={end_time}
  ```
  Timestamps devem estar em formato ISO-8601 UTC com sufixo `Z` (ex: `2026-07-31T20:00:00Z`).
  O `end_time` deve ser URL-encoded quando passado como query param.
