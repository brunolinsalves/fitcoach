#!/usr/bin/env python3
"""
fetch_health_connect.py

Data collection script for Health Connect sensors exposed in Home Assistant Companion App.
Fetches physiological and activity metrics (HR, Resting HR, HRV, SpO2, Respiratory Rate,
Sleep duration/segment, Steps, Calories, etc.) collected via Zepp / Amazfit Helio Strap
and Health Connect integration.
"""

import argparse
import json
import os
import sys
import requests
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")
HOME_ASSISTANT_URL = os.getenv("HOME_ASSISTANT_URL")

SENSOR_MAP = {
    # Cardiovascular
    "sensor.s26_bruno_heart_rate": ("heartRate", "bpm", float),
    "sensor.s26_bruno_resting_heart_rate": ("restingHeartRate", "bpm", float),
    "sensor.s26_bruno_heart_rate_variability": ("heartRateVariability", "ms", float),
    "sensor.s26_bruno_oxygen_saturation": ("oxygenSaturation", "%", float),
    "sensor.s26_bruno_respiratory_rate": ("respiratoryRate", "bpm", float),
    # Sleep
    "sensor.s26_bruno_sleep_duration": ("sleepDurationMinutes", "min", float),
    "sensor.s26_bruno_sleep_confidence": ("sleepConfidence", "%", float),
    "sensor.s26_bruno_sleep_segment": ("sleepSegmentMs", "ms", float),
    # Physical Activity
    "sensor.s26_bruno_daily_steps": ("steps", "steps", float),
    "sensor.s26_bruno_daily_distance": ("distanceMeters", "m", float),
    "sensor.s26_bruno_daily_elevation_gained": ("elevationGainedMeters", "m", float),
    "sensor.s26_bruno_daily_floors": ("floors", "floors", float),
    "sensor.s26_bruno_active_calories_burned": ("activeCalories", "kcal", float),
    "sensor.s26_bruno_total_calories_burned": ("totalCalories", "kcal", float),
    "sensor.s26_bruno_detected_activity": ("detectedActivity", "", str),
    # Body Composition & Metabolism
    "sensor.s26_bruno_weight": ("weightGrams", "g", float),
    "sensor.s26_bruno_height": ("heightMeters", "m", float),
    "sensor.s26_bruno_basal_metabolic_rate": ("basalMetabolicRate", "kcal/day", float),
    "sensor.s26_bruno_body_fat": ("bodyFatPercent", "%", float),
    "sensor.s26_bruno_lean_body_mass": ("leanBodyMassGrams", "g", float),
    "sensor.s26_bruno_body_water_mass": ("bodyWaterMassGrams", "g", float),
    "sensor.s26_bruno_bone_mass": ("boneMassGrams", "g", float),
    "sensor.s26_bruno_vo2_max": ("vo2Max", "mL/kg/min", float),
    # Vitals & Other
    "sensor.s26_bruno_blood_glucose": ("bloodGlucose", "mg/dL", float),
    "sensor.s26_bruno_diastolic_blood_pressure": ("diastolicBloodPressure", "mmHg", float),
    "sensor.s26_bruno_systolic_blood_pressure": ("systolicBloodPressure", "mmHg", float),
    "sensor.s26_bruno_body_temperature": ("bodyTemperature", "°C", float),
    "sensor.s26_bruno_basal_body_temperature": ("basalBodyTemperature", "°C", float),
    "sensor.s26_bruno_daily_hydration": ("dailyHydration", "mL", float),
}

def format_minutes_to_time(minutes: float) -> str:
    """Format minutes float to HH:MM:SS string."""
    if not minutes or minutes <= 0:
        return "n/a"
    total_seconds = int(minutes * 60)
    hours = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"

def fetch_health_connect_metrics():
    """Fetch current state of all Health Connect / Zepp entities from Home Assistant."""
    if not HOME_ASSISTANT_URL or not HOME_ASSISTANT_TOKEN:
        print("Warning: HOME_ASSISTANT_URL or HOME_ASSISTANT_TOKEN not set in .env", file=sys.stderr)
        return None

    headers = {
        "Authorization": f"Bearer {HOME_ASSISTANT_TOKEN}",
        "Content-Type": "application/json",
    }

    url = f"{HOME_ASSISTANT_URL}/api/states"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Error fetching HA states: {response.status_code} - {response.text}", file=sys.stderr)
            return None
        
        states = response.json()
    except Exception as e:
        print(f"Error connecting to Home Assistant: {e}", file=sys.stderr)
        return None

    state_dict = {s["entity_id"]: s for s in states}

    metrics = {
        "source": "Health Connect / Zepp (Amazfit Helio Strap)",
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "cardiovascular": {},
        "sleep": {},
        "activity": {},
        "bodyComposition": {},
        "vitals": {},
        "rawSensors": {}
    }

    for entity_id, (key, unit, cast_type) in SENSOR_MAP.items():
        state_obj = state_dict.get(entity_id)
        if not state_obj:
            metrics["rawSensors"][key] = None
            continue

        raw_state = state_obj.get("state")
        last_updated = state_obj.get("last_updated")

        parsed_val = None
        if raw_state not in (None, "unknown", "unavailable"):
            try:
                parsed_val = cast_type(raw_state)
            except (ValueError, TypeError):
                parsed_val = raw_state

        metrics["rawSensors"][key] = {
            "entityId": entity_id,
            "value": parsed_val,
            "unit": unit,
            "lastUpdated": last_updated
        }

    # Cardiovascular mapping
    cardio_raw = metrics["rawSensors"]
    metrics["cardiovascular"] = {
        "heartRate": cardio_raw.get("heartRate", {}).get("value") if cardio_raw.get("heartRate") else None,
        "restingHeartRate": cardio_raw.get("restingHeartRate", {}).get("value") if cardio_raw.get("restingHeartRate") else None,
        "heartRateVariability": cardio_raw.get("heartRateVariability", {}).get("value") if cardio_raw.get("heartRateVariability") else None,
        "oxygenSaturation": cardio_raw.get("oxygenSaturation", {}).get("value") if cardio_raw.get("oxygenSaturation") else None,
        "respiratoryRate": cardio_raw.get("respiratoryRate", {}).get("value") if cardio_raw.get("respiratoryRate") else None,
    }

    # Sleep mapping
    sleep_min = cardio_raw.get("sleepDurationMinutes", {}).get("value") if cardio_raw.get("sleepDurationMinutes") else None
    sleep_seg_ms = cardio_raw.get("sleepSegmentMs", {}).get("value") if cardio_raw.get("sleepSegmentMs") else None
    
    metrics["sleep"] = {
        "durationMinutes": sleep_min,
        "durationFormatted": format_minutes_to_time(sleep_min) if isinstance(sleep_min, (int, float)) else None,
        "sleepConfidence": cardio_raw.get("sleepConfidence", {}).get("value") if cardio_raw.get("sleepConfidence") else None,
        "sleepSegmentMs": sleep_seg_ms,
        "sleepSegmentFormatted": format_minutes_to_time(sleep_seg_ms / 60000.0) if isinstance(sleep_seg_ms, (int, float)) else None,
    }

    # Activity mapping
    metrics["activity"] = {
        "steps": cardio_raw.get("steps", {}).get("value") if cardio_raw.get("steps") else None,
        "distanceMeters": cardio_raw.get("distanceMeters", {}).get("value") if cardio_raw.get("distanceMeters") else None,
        "elevationGainedMeters": cardio_raw.get("elevationGainedMeters", {}).get("value") if cardio_raw.get("elevationGainedMeters") else None,
        "floors": cardio_raw.get("floors", {}).get("value") if cardio_raw.get("floors") else None,
        "activeCalories": cardio_raw.get("activeCalories", {}).get("value") if cardio_raw.get("activeCalories") else None,
        "totalCalories": cardio_raw.get("totalCalories", {}).get("value") if cardio_raw.get("totalCalories") else None,
        "detectedActivity": cardio_raw.get("detectedActivity", {}).get("value") if cardio_raw.get("detectedActivity") else None,
    }

    # Body Composition mapping
    weight_g = cardio_raw.get("weightGrams", {}).get("value") if cardio_raw.get("weightGrams") else None
    metrics["bodyComposition"] = {
        "weightKg": round(weight_g / 1000.0, 2) if isinstance(weight_g, (int, float)) and weight_g > 100 else weight_g,
        "heightMeters": cardio_raw.get("heightMeters", {}).get("value") if cardio_raw.get("heightMeters") else None,
        "basalMetabolicRate": cardio_raw.get("basalMetabolicRate", {}).get("value") if cardio_raw.get("basalMetabolicRate") else None,
        "bodyFatPercent": cardio_raw.get("bodyFatPercent", {}).get("value") if cardio_raw.get("bodyFatPercent") else None,
        "leanBodyMassGrams": cardio_raw.get("leanBodyMassGrams", {}).get("value") if cardio_raw.get("leanBodyMassGrams") else None,
        "bodyWaterMassGrams": cardio_raw.get("bodyWaterMassGrams", {}).get("value") if cardio_raw.get("bodyWaterMassGrams") else None,
        "boneMassGrams": cardio_raw.get("boneMassGrams", {}).get("value") if cardio_raw.get("boneMassGrams") else None,
        "vo2Max": cardio_raw.get("vo2Max", {}).get("value") if cardio_raw.get("vo2Max") else None,
    }

    # Vitals mapping
    metrics["vitals"] = {
        "bloodGlucose": cardio_raw.get("bloodGlucose", {}).get("value") if cardio_raw.get("bloodGlucose") else None,
        "diastolicBloodPressure": cardio_raw.get("diastolicBloodPressure", {}).get("value") if cardio_raw.get("diastolicBloodPressure") else None,
        "systolicBloodPressure": cardio_raw.get("systolicBloodPressure", {}).get("value") if cardio_raw.get("systolicBloodPressure") else None,
        "bodyTemperature": cardio_raw.get("bodyTemperature", {}).get("value") if cardio_raw.get("bodyTemperature") else None,
        "basalBodyTemperature": cardio_raw.get("basalBodyTemperature", {}).get("value") if cardio_raw.get("basalBodyTemperature") else None,
        "dailyHydration": cardio_raw.get("dailyHydration", {}).get("value") if cardio_raw.get("dailyHydration") else None,
    }

    return metrics

def extrair_janela_hr(horas_atras=24):
    """Extrai leituras de frequência cardíaca do Home Assistant para série temporal."""
    if not HOME_ASSISTANT_URL or not HOME_ASSISTANT_TOKEN:
        return []
    
    agora = datetime.now(timezone.utc)
    inicio = agora - timedelta(hours=horas_atras)
    start_time = inicio.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time = agora.strftime("%Y-%m-%dT%H:%M:%SZ")
    entity_id = "sensor.s26_bruno_heart_rate"

    url = f"{HOME_ASSISTANT_URL}/api/history/period/{start_time}?filter_entity_id={entity_id}&end_time={quote(end_time)}"
    headers = {
        "Authorization": f"Bearer {HOME_ASSISTANT_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            dados_historicos = response.json()
            if not dados_historicos or len(dados_historicos[0]) == 0:
                return []
            leituras = dados_historicos[0]
            pontos_hr = []
            for leitura in leituras:
                try:
                    valor = float(leitura.get("state"))
                    timestamp = leitura.get("last_changed")
                    pontos_hr.append({"timestamp": timestamp, "hr": valor})
                except (ValueError, TypeError):
                    continue
            return pontos_hr
    except Exception as e:
        print(f"Erro ao extrair janela de HR: {e}", file=sys.stderr)
    return []

def main():
    parser = argparse.ArgumentParser(description="Collect Health Connect metrics from Home Assistant.")
    parser.add_argument("--output", type=str, default="health_connect_data.json", help="Output JSON file path")
    args = parser.parse_args()

    print("Coletando métricas do Health Connect (Zepp / Amazfit Helio Strap) do Home Assistant...")
    metrics = fetch_health_connect_metrics()
    if metrics:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2, ensure_ascii=False)
            print(f"Sucesso! Métricas do Health Connect salvas em: {args.output}")
            print(f"Cardiovascular: HRV={metrics['cardiovascular']['heartRateVariability']} ms, "
                  f"SpO2={metrics['cardiovascular']['oxygenSaturation']}%, "
                  f"Frequência Respiratória={metrics['cardiovascular']['respiratoryRate']} bpm, "
                  f"FC Repouso={metrics['cardiovascular']['restingHeartRate']} bpm")
            print(f"Sono: Duração={metrics['sleep']['durationFormatted']}, Segmento={metrics['sleep']['sleepSegmentFormatted']}")
        except Exception as e:
            print(f"Erro ao salvar arquivo JSON: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Erro: Não foi possível obter dados do Health Connect.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()