# Health Connect — Sensores disponíveis no Home Assistant

Sensores do dispositivo **Samsung Galaxy S26 (Bruno)** integrados via Home Assistant Companion App + Health Connect.

> **Última verificação:** 2026-06-26  
> **Endpoint base:** `https://casa.brunolinsalves.com/api`

---

## 🏃 Atividade Física

| Entity ID | Descrição | Unidade | Valor atual |
|-----------|-----------|---------|-------------|
| `sensor.s26_bruno_daily_steps` | Passos diários | steps | 4.036 |
| `sensor.s26_bruno_daily_distance` | Distância diária | m | 3.084 |
| `sensor.s26_bruno_daily_elevation_gained` | Elevação ganha no dia | m | 0 |
| `sensor.s26_bruno_daily_floors` | Andares subidos | floors | 6 |
| `sensor.s26_bruno_active_calories_burned` | Calorias ativas queimadas | kcal | 133 |
| `sensor.s26_bruno_total_calories_burned` | Calorias totais queimadas | kcal | 1.729 |
| `sensor.s26_bruno_detected_activity` | Atividade detectada | — | still |

---

## ❤️ Cardiovascular

| Entity ID | Descrição | Unidade | Valor atual |
|-----------|-----------|---------|-------------|
| `sensor.s26_bruno_heart_rate` | Frequência cardíaca | bpm | 81 |
| `sensor.s26_bruno_resting_heart_rate` | Frequência cardíaca em repouso | bpm | 52 |
| `sensor.s26_bruno_heart_rate_variability` | Variabilidade da FC (HRV) | ms | unknown |
| `sensor.s26_bruno_oxygen_saturation` | Saturação de oxigênio (SpO2) | % | unknown |
| `sensor.s26_bruno_respiratory_rate` | Frequência respiratória | bpm | unknown |

---

## 😴 Sono

| Entity ID | Descrição | Unidade | Valor atual |
|-----------|-----------|---------|-------------|
| `sensor.s26_bruno_sleep_duration` | Duração do sono | min | 332 (~5h32) |
| `sensor.s26_bruno_sleep_confidence` | Confiança na detecção do sono | % | 2 |
| `sensor.s26_bruno_sleep_segment` | Segmento de sono | ms | unknown |

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

- Sensores com valor `unknown` não possuem dados sendo coletados no momento.
  Podem depender de dispositivos externos (balança inteligente, oxímetro, glicosímetro, etc.)
  ou de permissões adicionais no Health Connect.
- Os sensores mais ricos em histórico para análise são:
  - `heart_rate`
  - `resting_heart_rate`
  - `sleep_duration`
  - `daily_steps`
  - `active_calories_burned`
  - `total_calories_burned`
- A API de histórico é acessada via:
  ```
  GET /api/history/period/{start_time}?filter_entity_id={entity_id}&end_time={end_time}
  ```
  Timestamps devem estar em formato ISO-8601 UTC com sufixo `Z` (ex: `2026-06-26T20:00:00Z`).
  O `end_time` deve ser URL-encoded quando passado como query param.
