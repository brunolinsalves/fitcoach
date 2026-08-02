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
from zoneinfo import ZoneInfo
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

# Fuso horário local — Aracaju/SE, Brasil (GMT-3)
LOCAL_TZ = ZoneInfo("America/Maceio")

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

def _fetch_entity_history(entity_id, start_iso, end_iso):
    """Fetch state history for a single entity from the HA API.

    Returns the raw list of state objects (dicts with 'state', 'last_changed',
    'attributes', …) or an empty list on failure.
    """
    if not HOME_ASSISTANT_URL or not HOME_ASSISTANT_TOKEN:
        return []

    url = (
        f"{HOME_ASSISTANT_URL}/api/history/period/{start_iso}"
        f"?filter_entity_id={entity_id}&end_time={quote(end_iso)}"
    )
    headers = {
        "Authorization": f"Bearer {HOME_ASSISTANT_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0 and len(data[0]) > 0:
                return data[0]
    except Exception as e:
        print(f"Erro ao buscar histórico de {entity_id}: {e}", file=sys.stderr)
    return []


def extrair_janela_hr(horas_atras=24):
    """Extrai leituras de frequência cardíaca do Home Assistant para série temporal."""
    if not HOME_ASSISTANT_URL or not HOME_ASSISTANT_TOKEN:
        return []

    agora = datetime.now(timezone.utc)
    inicio = agora - timedelta(hours=horas_atras)
    start_time = inicio.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time = agora.strftime("%Y-%m-%dT%H:%M:%SZ")
    entity_id = "sensor.s26_bruno_heart_rate"

    leituras = _fetch_entity_history(entity_id, start_time, end_time)
    pontos_hr = []
    for leitura in leituras:
        try:
            valor = float(leitura.get("state"))
            timestamp = leitura.get("last_changed")
            pontos_hr.append({"timestamp": timestamp, "hr": valor})
        except (ValueError, TypeError):
            continue
    return pontos_hr


def _parse_iso_timestamp(ts_str):
    """Parse an ISO-8601 timestamp string into a timezone-aware datetime.

    Handles timestamps with or without timezone info (assumes UTC when absent).
    """
    if ts_str is None:
        return None
    # Remove trailing 'Z' and replace with +00:00 for fromisoformat compatibility
    ts_str = ts_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def calcular_vfc_diaria_por_sessao_sono(dias=7):
    """Calcula o valor diário de VFC (RMSSD) a partir dos dados do Health Connect,
    reproduzindo exatamente o número exibido no aplicativo Zepp.

    FONTE DOS DADOS
    ----------------
    Usa apenas os registros de HRV RMSSD e as sessões de sono cujo app de
    origem seja o Zepp (oriundos do Health Connect).

    DEFINIÇÃO DA JANELA
    --------------------
    A unidade de cálculo é a sessão de sono, não o dia do calendário.
    Para cada sessão, considera-se seu horário de início e de término.
    Seleciona todas as leituras de RMSSD cujo instante caia dentro dessa
    janela, inclusive nos limites.

    CÁLCULO
    --------
    Aplica a média aritmética simples dos valores de RMSSD da janela.
    Sem descartar outliers, sem mediana, sem ponderação.
    Arredonda o resultado para o inteiro mais próximo.

    ATRIBUIÇÃO DE DATA
    -------------------
    Rotula o resultado com a data do término da sessão (o dia em que a
    pessoa acordou).

    Returns:
        list[dict]: Lista de dicts, um por noite, com campos:
            - date: data atribuída (YYYY-MM-DD, dia em que acordou)
            - sleepStart: ISO timestamp do início da sessão de sono
            - sleepEnd: ISO timestamp do fim da sessão de sono
            - readingCount: número de leituras de RMSSD na janela
            - min: valor mínimo de RMSSD
            - max: valor máximo de RMSSD
            - mean: média aritmética (float)
            - roundedValue: valor arredondado para inteiro (resultado final)
    """
    if not HOME_ASSISTANT_URL or not HOME_ASSISTANT_TOKEN:
        print("Warning: HOME_ASSISTANT_URL or HOME_ASSISTANT_TOKEN not set.", file=sys.stderr)
        return []

    agora = datetime.now(timezone.utc)
    # Look back enough days to cover sleep sessions (add 1 extra day for
    # sessions starting the night before)
    inicio = agora - timedelta(days=dias + 1)
    start_iso = inicio.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = agora.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── 1. Obter sessões de sono do sensor de segmento de sono ──
    SLEEP_SEGMENT_ENTITY = "sensor.s26_bruno_sleep_segment"
    SLEEP_DURATION_ENTITY = "sensor.s26_bruno_sleep_duration"

    sleep_segment_history = _fetch_entity_history(
        SLEEP_SEGMENT_ENTITY, start_iso, end_iso
    )
    sleep_duration_history = _fetch_entity_history(
        SLEEP_DURATION_ENTITY, start_iso, end_iso
    )

    # Build a mapping of last_changed → duration_minutes from sleep_duration
    # history to help derive sleep start times
    duration_map = {}
    for entry in sleep_duration_history:
        ts = _parse_iso_timestamp(entry.get("last_changed"))
        if ts is None:
            continue
        try:
            duration_min = float(entry.get("state"))
            if duration_min > 0:
                duration_map[ts.isoformat()] = duration_min
        except (ValueError, TypeError):
            continue

    # Identify sleep sessions from sleep_segment changes.
    # Each state change represents a sleep session report from Zepp.
    # The attributes contain 'start' and 'end' as epoch milliseconds.
    sessoes_sono = []
    seen_sessions = set()  # deduplicate by (start, end) pair

    for entry in sleep_segment_history:
        state_val = entry.get("state")
        if state_val in (None, "unknown", "unavailable"):
            continue

        last_changed = _parse_iso_timestamp(entry.get("last_changed"))
        if last_changed is None:
            continue

        attrs = entry.get("attributes", {}) or {}

        # The start/end attributes from Health Connect sleep_segment are
        # epoch timestamps in milliseconds
        sleep_start = None
        sleep_end = None

        start_attr = attrs.get("start")
        end_attr = attrs.get("end")

        if start_attr is not None and end_attr is not None:
            try:
                start_epoch_ms = float(start_attr)
                end_epoch_ms = float(end_attr)
                if start_epoch_ms > 0 and end_epoch_ms > 0:
                    sleep_start = datetime.fromtimestamp(
                        start_epoch_ms / 1000.0, tz=timezone.utc
                    )
                    sleep_end = datetime.fromtimestamp(
                        end_epoch_ms / 1000.0, tz=timezone.utc
                    )
            except (ValueError, TypeError, OSError):
                pass

        # Fallback: try parsing as ISO strings
        if sleep_start is None or sleep_end is None:
            sleep_start = _parse_iso_timestamp(start_attr)
            sleep_end = _parse_iso_timestamp(end_attr)

        # Last fallback: derive from sleep_segment value and last_changed
        if sleep_start is None or sleep_end is None:
            try:
                segment_ms = float(state_val)
                if segment_ms <= 0:
                    continue
            except (ValueError, TypeError):
                continue

            # Try to find a matching sleep_duration entry nearby to get a
            # more accurate total duration
            duration_min = None
            for dur_ts_iso, dur_val in duration_map.items():
                dur_ts = _parse_iso_timestamp(dur_ts_iso)
                if dur_ts and abs((dur_ts - last_changed).total_seconds()) < 300:
                    duration_min = dur_val
                    break

            if duration_min is not None:
                total_seconds = duration_min * 60
            else:
                total_seconds = segment_ms / 1000.0

            sleep_end = last_changed
            sleep_start = sleep_end - timedelta(seconds=total_seconds)

        # Deduplicate by the actual sleep window (same start/end = same session)
        session_key = (
            sleep_start.isoformat(),
            sleep_end.isoformat(),
        )
        if session_key in seen_sessions:
            continue
        seen_sessions.add(session_key)

        sessoes_sono.append({
            "start": sleep_start,
            "end": sleep_end,
        })

    if not sessoes_sono:
        print("VFC: Nenhuma sessão de sono encontrada no período.", file=sys.stderr)
        return []

    # Sort by end time
    sessoes_sono.sort(key=lambda s: s["end"])

    # ── 2. Obter leituras de HRV RMSSD do Home Assistant (Health Connect) ──
    HRV_ENTITY = "sensor.s26_bruno_heart_rate_variability"
    earliest_start = min(s["start"] for s in sessoes_sono)
    hrv_start_iso = earliest_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    hrv_history = _fetch_entity_history(HRV_ENTITY, hrv_start_iso, end_iso)

    hrv_readings = []
    seen_hrv = set()  # deduplicate by (measurement_time, value)
    for entry in hrv_history:
        state_val = entry.get("state")
        if state_val in (None, "unknown", "unavailable"):
            continue

        attrs = entry.get("attributes", {}) or {}

        # Filter by Zepp source if attribute is present
        source = attrs.get("source", "")
        if source and source != "com.huami.watch.hmwatchmanager":
            continue

        # Prefer the 'date' attribute (actual measurement time from Zepp)
        measurement_ts = _parse_iso_timestamp(attrs.get("date"))
        if measurement_ts is None:
            measurement_ts = _parse_iso_timestamp(entry.get("last_changed"))
        if measurement_ts is None:
            continue

        try:
            val = float(state_val)
        except (ValueError, TypeError):
            continue

        # Deduplicate by measurement time + value (same reading re-synced)
        reading_key = (measurement_ts.isoformat(), val)
        if reading_key in seen_hrv:
            continue
        seen_hrv.add(reading_key)

        hrv_readings.append((measurement_ts, val))

    # Sort by timestamp
    hrv_readings.sort(key=lambda r: r[0])

    if not hrv_readings:
        print("VFC: Nenhuma leitura de HRV RMSSD encontrada no período.", file=sys.stderr)
        return []

    # ── 3. Para cada sessão, filtrar leituras e calcular média ──
    # Zepp batches HRV readings and reports measurement timestamps at or
    # shortly after the formal sleep session end. Instead of a fixed buffer,
    # attribute each HRV reading to the session whose start ≤ reading_time
    # < next_session_start. This naturally captures morning post-sleep
    # readings regardless of sync delay.
    resultados = []

    for i, sessao in enumerate(sessoes_sono):
        sleep_start = sessao["start"]
        sleep_end = sessao["end"]

        # Upper bound: start of the next session, or "now" for the last one
        if i + 1 < len(sessoes_sono):
            match_end = sessoes_sono[i + 1]["start"]
        else:
            match_end = agora

        # Filter RMSSD readings: from sleep_start up to (but not including)
        # the next session's start
        rmssd_na_janela = [
            val for ts, val in hrv_readings
            if sleep_start <= ts < match_end
        ]

        if not rmssd_na_janela:
            continue

        media = sum(rmssd_na_janela) / len(rmssd_na_janela)
        valor_arredondado = round(media)

        # Date attribution: date of the session end in LOCAL timezone
        # (the day the person woke up, in BRT)
        sleep_end_local = sleep_end.astimezone(LOCAL_TZ)
        sleep_start_local = sleep_start.astimezone(LOCAL_TZ)
        data_atribuida = sleep_end_local.date().isoformat()

        resultados.append({
            "date": data_atribuida,
            "sleepStart": sleep_start_local.isoformat(),
            "sleepEnd": sleep_end_local.isoformat(),
            "readingCount": len(rmssd_na_janela),
            "min": min(rmssd_na_janela),
            "max": max(rmssd_na_janela),
            "mean": round(media, 2),
            "roundedValue": valor_arredondado,
        })

    # Print summary
    if resultados:
        print(f"\nVFC diária por sessão de sono — últimos {dias} dias (horários em GMT-3):")
        print(f"{'Data':<12} {'Início (BRT)':>20} {'Fim (BRT)':>20} {'Leituras':>9} "
              f"{'Mín':>5} {'Máx':>5} {'Média':>7} {'VFC':>4}")
        print("-" * 95)
        for r in resultados:
            # Format local timestamps to be more readable (already in BRT)
            start_fmt = r["sleepStart"][:19].replace("T", " ")
            end_fmt = r["sleepEnd"][:19].replace("T", " ")
            print(f"{r['date']:<12} {start_fmt:>20} {end_fmt:>20} "
                  f"{r['readingCount']:>9} {r['min']:>5.0f} {r['max']:>5.0f} "
                  f"{r['mean']:>7.2f} {r['roundedValue']:>4}")
    else:
        print("VFC: Nenhuma noite com leituras de RMSSD dentro das sessões de sono.",
              file=sys.stderr)

    return resultados

def main():
    parser = argparse.ArgumentParser(description="Collect Health Connect metrics from Home Assistant.")
    parser.add_argument("--output", type=str, default="health_connect_data.json", help="Output JSON file path")
    parser.add_argument("--dias-vfc", type=int, default=7,
                        help="Número de dias para calcular VFC diária por sessão de sono (default: 7)")
    args = parser.parse_args()

    print("Coletando métricas do Health Connect (Zepp / Amazfit Helio Strap) do Home Assistant...")
    metrics = fetch_health_connect_metrics()
    if metrics:
        # Calculate daily VFC (RMSSD) from sleep sessions
        print(f"\nCalculando VFC diária por sessão de sono (últimos {args.dias_vfc} dias)...")
        vfc_resultados = calcular_vfc_diaria_por_sessao_sono(dias=args.dias_vfc)
        metrics["vfcDiaria"] = vfc_resultados

        # Update the cardiovascular HRV with the most recent session-based value
        if vfc_resultados:
            ultimo = vfc_resultados[-1]  # Most recent session (sorted by end time)
            metrics["cardiovascular"]["heartRateVariability"] = float(ultimo["roundedValue"])
            metrics["cardiovascular"]["heartRateVariabilitySource"] = "Zepp sleep session RMSSD mean"
            metrics["cardiovascular"]["heartRateVariabilityDate"] = ultimo["date"]

        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2, ensure_ascii=False)
            print(f"\nSucesso! Métricas do Health Connect salvas em: {args.output}")
            print(f"Cardiovascular: HRV={metrics['cardiovascular']['heartRateVariability']} ms, "
                  f"SpO2={metrics['cardiovascular']['oxygenSaturation']}%, "
                  f"Frequência Respiratória={metrics['cardiovascular']['respiratoryRate']} bpm, "
                  f"FC Repouso={metrics['cardiovascular']['restingHeartRate']} bpm")
            print(f"Sono: Duração={metrics['sleep']['durationFormatted']}, Segmento={metrics['sleep']['sleepSegmentFormatted']}")
            if vfc_resultados:
                print(f"VFC diária (última noite): {vfc_resultados[-1]['roundedValue']} ms "
                      f"({vfc_resultados[-1]['readingCount']} leituras, "
                      f"data={vfc_resultados[-1]['date']})")
        except Exception as e:
            print(f"Erro ao salvar arquivo JSON: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Erro: Não foi possível obter dados do Health Connect.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()