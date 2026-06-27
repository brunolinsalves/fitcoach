#!/usr/bin/env python3
"""
fetch_garmin.py

Deterministic data collection script for Garmin Connect.
Fetches daily physiological and performance data and saves it to a clean JSON file.
"""

import argparse
import sys
import os
import json
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Import garminconnect and handle authentication errors
try:
    from garminconnect import (
        Garmin,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    )
except ImportError:
    print("Error: garminconnect library not installed. Run 'pip install -r requirements.txt'", file=sys.stderr)
    sys.exit(1)

# Load environment variables
load_dotenv()

def safe_api_call(func, *args, **kwargs):
    """
    Safely execute a Garmin API method.
    Returns (success, result, error_message) to prevent crashing on missing features.
    """
    try:
        result = func(*args, **kwargs)
        return True, result, None
    except Exception as e:
        err_msg = str(e)
        return False, None, err_msg

def parse_arguments():
    parser = argparse.ArgumentParser(description="Deterministic Garmin Connect data collector.")
    parser.add_argument(
        "--date",
        type=str,
        default=date.today().isoformat(),
        help="Date to fetch in YYYY-MM-DD format (default: today)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="garmin_data.json",
        help="Output JSON file path (default: garmin_data.json)"
    )
    return parser.parse_args()

def init_api() -> Garmin:
    """Initialize Garmin API, utilizing local token cache to avoid rate limits."""
    tokenstore = os.getenv("GARMINTOKENS", ".garminconnect")
    tokenstore_path = str(Path(tokenstore).expanduser().resolve())
    os.makedirs(tokenstore_path, exist_ok=True)

    # Attempt login using stored tokens
    try:
        garmin = Garmin()
        garmin.login(tokenstore_path)
        # Verify token is still valid by accessing display name
        if garmin.display_name:
            print(f"Authenticated successfully using cached tokens for: {garmin.display_name}")
            return garmin
    except (GarminConnectAuthenticationError, GarminConnectConnectionError, Exception) as err:
        print(f"Could not login with cached tokens ({err}). Attempting fresh login...", file=sys.stderr)

    # Fresh login with credentials from environment
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    if not email or not password:
        print("Error: GARMIN_EMAIL and GARMIN_PASSWORD must be configured in your .env file.", file=sys.stderr)
        sys.exit(1)

    try:
        garmin = Garmin(
            email=email,
            password=password,
            prompt_mfa=lambda: input("Please enter your Garmin MFA code: ").strip()
        )
        garmin.login(tokenstore_path)
        print(f"Login successful! Tokens saved to {tokenstore_path} for user: {garmin.display_name}")
        return garmin
    except GarminConnectTooManyRequestsError as err:
        print(f"Error: Rate limit exceeded (Too Many Requests). Try again later. Details: {err}", file=sys.stderr)
        sys.exit(1)
    except GarminConnectAuthenticationError as err:
        print(f"Error: Authentication failed. Check your GARMIN_EMAIL and GARMIN_PASSWORD. Details: {err}", file=sys.stderr)
        sys.exit(1)
    except Exception as err:
        print(f"Error: Unexpected login failure. Details: {err}", file=sys.stderr)
        sys.exit(1)

def format_seconds_to_time(seconds):
    """Convert duration in seconds to HH:MM:SS format."""
    if not seconds:
        return "n/a"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def extract_sleep_data(api, target_date):
    """
    Extract sleep metrics.
    Garmin associates sleep with the date you WOKE UP.
    If today's data is empty (e.g. early morning before sync), fall back to yesterday.
    """
    success, sleep_raw, err = safe_api_call(api.get_sleep_data, target_date)

    daily_sleep = sleep_raw.get("dailySleepDTO", {}) if success and sleep_raw else {}

    # Check if today's data is empty (all nulls) — fall back to yesterday
    if not daily_sleep.get("sleepTimeSeconds"):
        yesterday = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
        print(f"  Sleep data empty for {target_date}, trying {yesterday}...")
        success2, sleep_raw2, err2 = safe_api_call(api.get_sleep_data, yesterday)
        if success2 and sleep_raw2:
            daily_sleep2 = sleep_raw2.get("dailySleepDTO", {})
            if daily_sleep2.get("sleepTimeSeconds"):
                daily_sleep = daily_sleep2
                target_date = yesterday

    if not daily_sleep or not daily_sleep.get("sleepTimeSeconds"):
        return {"status": "Sem dados de sono disponíveis (relógio não registrou ou ainda não sincronizou)"}

    # Calculate sleep score: Garmin may not provide it on older watches.
    # We'll extract it from the top-level response if available.
    sleep_score = None
    if success and sleep_raw:
        sleep_score = sleep_raw.get("sleepScore") or sleep_raw.get("overallScore")
    if not sleep_score and daily_sleep:
        sleep_score = daily_sleep.get("sleepScore")

    return {
        "date": daily_sleep.get("calendarDate", target_date),
        "sleepScore": sleep_score,
        "durationSeconds": daily_sleep.get("sleepTimeSeconds"),
        "durationFormatted": format_seconds_to_time(daily_sleep.get("sleepTimeSeconds")),
        "deepSleepSeconds": daily_sleep.get("deepSleepSeconds"),
        "deepSleepFormatted": format_seconds_to_time(daily_sleep.get("deepSleepSeconds")),
        "lightSleepSeconds": daily_sleep.get("lightSleepSeconds"),
        "lightSleepFormatted": format_seconds_to_time(daily_sleep.get("lightSleepSeconds")),
        "remSleepSeconds": daily_sleep.get("remSleepSeconds"),
        "remSleepFormatted": format_seconds_to_time(daily_sleep.get("remSleepSeconds")),
        "awakeSeconds": daily_sleep.get("awakeSleepSeconds"),
        "awakeFormatted": format_seconds_to_time(daily_sleep.get("awakeSleepSeconds")),
    }

def extract_hrv_data(api, target_date):
    """
    Extract Heart Rate Variability (HRV) metrics.
    Note: Older devices like Forerunner 935 do NOT support HRV via this endpoint.
    """
    success, hrv_raw, err = safe_api_call(api.get_hrv_data, target_date)

    # If today is empty, try yesterday
    if success and (not hrv_raw or hrv_raw == {}):
        yesterday = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
        success, hrv_raw, err = safe_api_call(api.get_hrv_data, yesterday)

    if not success:
        return {"status": f"Erro ao buscar HRV: {err}"}
    if not hrv_raw or hrv_raw == {}:
        return {"status": "HRV não disponível (dispositivo pode não suportar este recurso)"}

    summary = hrv_raw.get("hrvSummary", {})
    if not summary:
        return {"status": "HRV retornou dados mas sem resumo (hrvSummary)"}

    return {
        "status": summary.get("status"),  # e.g., BALANCED, UNBALANCED
        "lastNightAvg": summary.get("lastNightAvg"),  # ms
        "weeklyAvg": summary.get("weeklyAvg"),  # ms
        "baseline": {
            "low": summary.get("baselineBalancedLow"),
            "upper": summary.get("baselineBalancedUpper")
        }
    }

def extract_training_readiness(api, target_date):
    """
    Extract Training Readiness metrics.
    Note: This feature requires newer devices (e.g. Fenix 7+, FR 265+).
    Forerunner 935 does NOT support Training Readiness.
    """
    # Try morning readiness first (AFTER_WAKEUP_RESET)
    success, readiness_data, err = safe_api_call(api.get_morning_training_readiness, target_date)

    if success and readiness_data:
        return _parse_readiness(readiness_data)

    # Fallback to general training readiness list
    success_list, readiness_list, err_list = safe_api_call(api.get_training_readiness, target_date)
    if success_list and readiness_list and isinstance(readiness_list, list) and len(readiness_list) > 0:
        return _parse_readiness(readiness_list[-1])

    return {"status": "Training Readiness não disponível (dispositivo pode não suportar este recurso)"}

def _parse_readiness(readiness_data):
    """Parse a single readiness snapshot dict."""
    if not readiness_data or not isinstance(readiness_data, dict):
        return {"status": "Training Readiness retornou dados inválidos"}

    # Extract component scores if available
    components = {}
    for component_key in [
        "sleepHistoryRequirement", "recoveryTimeRequirement", "hrvStatusRequirement",
        "sleepRequirement", "acuteLoadRequirement", "stressHistoryRequirement"
    ]:
        comp = readiness_data.get(component_key, {})
        if comp and isinstance(comp, dict):
            components[component_key.replace("Requirement", "")] = {
                "score": comp.get("score"),
                "feedback": comp.get("feedbackShort"),
                "level": comp.get("level")
            }

    return {
        "score": readiness_data.get("score"),
        "level": readiness_data.get("level"),
        "components": components if components else None
    }

def extract_training_status(api, target_date):
    """
    Extract training status, weekly load, VO2Max, and fitness trend.
    The response structure is heavily nested with device-keyed data.
    """
    success, status_raw, err = safe_api_call(api.get_training_status, target_date)
    if not success or not status_raw:
        return {"status": f"Erro ao buscar training status: {err}"}

    result = {}

    # --- VO2Max ---
    vo2max_obj = status_raw.get("mostRecentVO2Max", {})
    if vo2max_obj:
        generic = vo2max_obj.get("generic", {})
        if generic:
            result["vo2Max"] = generic.get("vo2MaxPreciseValue")
            result["vo2MaxDate"] = generic.get("calendarDate")
            result["fitnessAge"] = generic.get("fitnessAge")

        cycling = vo2max_obj.get("cycling", {})
        if cycling:
            result["vo2MaxCycling"] = cycling.get("vo2MaxPreciseValue")

    # --- Training Status (nested inside mostRecentTrainingStatus) ---
    most_recent = status_raw.get("mostRecentTrainingStatus", {})
    latest_data = most_recent.get("latestTrainingStatusData", {})
    
    # latestTrainingStatusData is keyed by deviceId (e.g. "3982518093")
    # We iterate to find any device's data
    device_status = None
    device_name = None
    if latest_data and isinstance(latest_data, dict):
        for device_id, data in latest_data.items():
            if isinstance(data, dict):
                device_status = data
                # Try to find device name
                recorded_devices = most_recent.get("recordedDevices", [])
                for dev in (recorded_devices or []):
                    if str(dev.get("deviceId")) == str(device_id):
                        device_name = dev.get("deviceName")
                break

    if device_status:
        # Map numeric training status codes to readable labels
        ts_code = device_status.get("trainingStatus")
        ts_labels = {
            0: "NOT_APPLICABLE",
            1: "DETRAINING",
            2: "RECOVERY",
            3: "MAINTAINING", 
            4: "MAINTAINING",      # Validado no site da garmin connect
            5: "PEAKING",
            6: "OVERREACHING",
            7: "PRODUCTIVE",       # Validado no site da garmin connect
            8: "UNPRODUCTIVE",
            9: "STRAINED",
        }
        result["trainingStatus"] = ts_labels.get(ts_code, f"UNKNOWN({ts_code})")
        result["trainingStatusCode"] = ts_code
        result["weeklyTrainingLoad"] = device_status.get("weeklyTrainingLoad")
        result["loadTunnelMin"] = device_status.get("loadTunnelMin")
        result["loadTunnelMax"] = device_status.get("loadTunnelMax")
        result["sport"] = device_status.get("sport")
        result["fitnessTrend"] = device_status.get("fitnessTrend")
        result["deviceName"] = device_name

        # Calculate ACWR if acute load data is available
        acute_dto = device_status.get("acuteTrainingLoadDTO")
        if acute_dto and isinstance(acute_dto, dict):
            result["acuteLoad"] = acute_dto.get("acuteTrainingLoad")
            result["chronicLoad"] = acute_dto.get("chronicTrainingLoad")
            if result.get("acuteLoad") and result.get("chronicLoad") and result["chronicLoad"] > 0:
                result["acwr"] = round(result["acuteLoad"] / result["chronicLoad"], 2)
        
        # If no acute DTO, try to estimate ACWR from weekly load and tunnel
        if "acwr" not in result and result.get("weeklyTrainingLoad") and result.get("loadTunnelMin"):
            tunnel_mid = (result["loadTunnelMin"] + result["loadTunnelMax"]) / 2
            if tunnel_mid > 0:
                result["acwr_estimated"] = round(result["weeklyTrainingLoad"] / tunnel_mid, 2)
                result["acwr_note"] = "Estimativa baseada em carga semanal / ponto médio do túnel de carga"

    if not result:
        return {"status": "Training status retornou dados mas sem informações de treino"}

    return result

def extract_weight_data(api, target_date):
    """
    Extract weight data using get_daily_weigh_ins and get_body_composition.
    Falls back to get_weigh_ins with a wider range.
    """
    end_date = date.fromisoformat(target_date)
    
    # Try get_daily_weigh_ins first (more specific)
    success, weighins, err = safe_api_call(api.get_daily_weigh_ins, target_date)
    if success and weighins:
        entries = weighins.get("dateWeightList", []) if isinstance(weighins, dict) else []
        if entries:
            latest = entries[-1]
            weight_g = latest.get("weight")
            if weight_g:
                return {
                    "weightKg": round(weight_g / 1000.0, 2) if weight_g > 1000 else round(weight_g, 2),
                    "bmi": latest.get("bmi"),
                    "bodyFatPercent": latest.get("bodyFat"),
                    "date": latest.get("calendarDate"),
                    "source": "daily_weigh_ins"
                }

    # Fallback: get_body_composition with wider range (30 days)
    start_date = (end_date - timedelta(days=30)).isoformat()
    success2, comp_raw, err2 = safe_api_call(api.get_body_composition, start_date, target_date)
    if success2 and comp_raw:
        list_dto = comp_raw.get("dateWeightList", [])
        if list_dto:
            latest_entry = list_dto[-1]
            weight_g = latest_entry.get("weight")
            if weight_g:
                return {
                    "weightKg": round(weight_g / 1000.0, 2) if weight_g > 1000 else round(weight_g, 2),
                    "bmi": latest_entry.get("bmi"),
                    "bodyFatPercent": latest_entry.get("bodyFat"),
                    "date": latest_entry.get("calendarDate"),
                    "source": "body_composition"
                }

    # Fallback: get_weigh_ins with wider range
    success3, weighins3, err3 = safe_api_call(api.get_weigh_ins, start_date, target_date)
    if success3 and weighins3:
        entries = weighins3 if isinstance(weighins3, list) else weighins3.get("dailyWeightSummaries", []) if isinstance(weighins3, dict) else []
        if entries:
            latest = entries[-1] if isinstance(entries, list) else entries
            weight_val = latest.get("weight") or latest.get("averageWeight")
            if weight_val:
                return {
                    "weightKg": round(weight_val / 1000.0, 2) if weight_val > 1000 else round(weight_val, 2),
                    "date": latest.get("calendarDate"),
                    "source": "weigh_ins"
                }

    return {"status": "Sem dados de peso encontrados (sem balança conectada ou sem registros recentes)"}

def extract_race_predictions(api):
    """
    Extract race prediction metrics.
    Note: Not all devices/accounts have race predictions available.
    """
    success, pred_raw, err = safe_api_call(api.get_race_predictions)
    if not success:
        return {"status": f"Erro ao buscar race predictions: {err}"}
    if not pred_raw or pred_raw == {}:
        return {"status": "Race predictions não disponível (dispositivo pode não suportar ou sem atividades recentes suficientes)"}

    p5k = pred_raw.get("time5K")
    p10k = pred_raw.get("time10K")
    phalf = pred_raw.get("timeHalfMarathon")
    pmara = pred_raw.get("timeMarathon")

    if not any([p5k, p10k, phalf, pmara]):
        return {"status": "Race predictions vazio (sem corridas recentes suficientes para gerar previsões)"}

    return {
        "5k": {"seconds": p5k, "formatted": format_seconds_to_time(p5k)},
        "10k": {"seconds": p10k, "formatted": format_seconds_to_time(p10k)},
        "halfMarathon": {"seconds": phalf, "formatted": format_seconds_to_time(phalf)},
        "marathon": {"seconds": pmara, "formatted": format_seconds_to_time(pmara)}
    }

def extract_daily_summary(api, target_date):
    """Extract general summary metrics for steps, calories, stress, body battery, etc."""
    success, summary, err = safe_api_call(api.get_user_summary, target_date)
    if not success or not summary:
        return {"error": f"Erro ao buscar resumo diário: {err}"}

    # Steps and calories
    steps = summary.get("totalSteps", 0)
    step_goal = summary.get("dailyStepGoal") or summary.get("stepGoal", 0)
    active_cal = summary.get("activeKilocalories")

    # If active calories is not direct, compute it: Total - BMR
    if active_cal is None:
        total_cal = summary.get("totalKilocalories", 0)
        bmr_cal = summary.get("bmrKilocalories", 0)
        active_cal = max(0, int(total_cal - bmr_cal)) if total_cal and bmr_cal else 0

    dist_km = round(summary.get("totalDistanceMeters", 0) / 1000.0, 2)

    # Body Battery (not available on all devices, e.g. FR 935)
    bb_max = summary.get("bodyBatteryHighestValue")
    bb_min = summary.get("bodyBatteryLowestValue")
    bb_charged = summary.get("bodyBatteryChargedValue")
    bb_drained = summary.get("bodyBatteryDrainedValue")
    bb_current = summary.get("bodyBatteryMostRecentValue")

    body_battery = None
    if any(v is not None for v in [bb_current, bb_max, bb_min, bb_charged, bb_drained]):
        body_battery = {
            "current": bb_current,
            "max": bb_max,
            "min": bb_min,
            "charged": bb_charged,
            "drained": bb_drained
        }

    # Stress
    stress_avg = summary.get("averageStressLevel")
    stress_max = summary.get("maxStressLevel")

    # Heart Rate
    resting_hr = summary.get("restingHeartRate")
    last_7d_hr = summary.get("lastSevenDaysAvgRestingHeartRate")
    
    if not resting_hr:
        # Fallback to get_heart_rates
        success_hr, hr_data, _ = safe_api_call(api.get_heart_rates, target_date)
        if success_hr and hr_data:
            resting_hr = hr_data.get("restingHeartRate")
            last_7d_hr = last_7d_hr or hr_data.get("lastSevenDaysAvgRestingHeartRate")

    return {
        "steps": steps,
        "stepGoal": step_goal,
        "activeCalories": int(active_cal) if active_cal else 0,
        "distanceKm": dist_km,
        "restingHeartRate": resting_hr,
        "restingHeartRate7dAvg": last_7d_hr,
        "stress": {
            "average": stress_avg,
            "max": stress_max
        },
        "bodyBattery": body_battery,
    }

def extract_endurance_score(api, target_date):
    """Extract endurance score if available."""
    success, data, err = safe_api_call(api.get_endurance_score, target_date)
    if not success or not data:
        return None
    # Only return if there's meaningful data
    if isinstance(data, dict) and data:
        score = data.get("overallScore") or data.get("enduranceScore")
        if score:
            return {"score": score, "raw": data}
    return None

def extract_fitness_age(api, target_date):
    """Extract fitness age if available as standalone."""
    success, data, err = safe_api_call(api.get_fitnessage_data, target_date)
    if not success or not data:
        return None
    if isinstance(data, dict) and data.get("chronologicalAge"):
        return {
            "chronologicalAge": data.get("chronologicalAge"),
            "fitnessAge": data.get("fitnessAge"),
        }
    return None

def main():
    args = parse_arguments()
    target_date = args.date
    output_path = args.output

    print(f"Initializing Garmin API to fetch data for date: {target_date}")
    api = init_api()
    if not api:
        print("Error: Could not initialize Garmin client.", file=sys.stderr)
        sys.exit(1)

    print("Fetching sleep data...")
    sleep_data = extract_sleep_data(api, target_date)

    print("Fetching HRV data...")
    hrv_data = extract_hrv_data(api, target_date)

    print("Fetching training readiness...")
    readiness_data = extract_training_readiness(api, target_date)

    print("Fetching training status & workload...")
    training_status = extract_training_status(api, target_date)

    print("Fetching body composition (weight)...")
    weight_data = extract_weight_data(api, target_date)

    print("Fetching race predictions...")
    race_predictions = extract_race_predictions(api)

    print("Fetching daily activity summary...")
    daily_summary = extract_daily_summary(api, target_date)

    print("Fetching endurance score...")
    endurance_score = extract_endurance_score(api, target_date)

    print("Fetching fitness age...")
    fitness_age = extract_fitness_age(api, target_date)

    print("Fetching profile user settings (gender, birthdate)...")
    success_settings, settings_raw, err_settings = safe_api_call(api.connectapi, '/userprofile-service/userprofile/user-settings')
    gender = None
    birth_date = None
    if success_settings and settings_raw and isinstance(settings_raw, dict):
        user_data = settings_raw.get('userData', {})
        if isinstance(user_data, dict):
            gender = user_data.get('gender')
            birth_date = user_data.get('birthDate')

    # Compile all data into a structured deterministic document
    garmin_report = {
        "metadata": {
            "date": target_date,
            "userDisplayName": api.display_name,
            "fetchedAt": date.today().isoformat(),
            "gender": gender,
            "birthDate": birth_date
        },
        "metrics": {
            "dailySummary": daily_summary,
            "sleep": sleep_data,
            "hrv": hrv_data,
            "trainingReadiness": readiness_data,
            "trainingStatus": training_status,
            "bodyComposition": weight_data,
            "racePredictions": race_predictions,
        }
    }

    # Add optional metrics only if they returned data
    if endurance_score:
        garmin_report["metrics"]["enduranceScore"] = endurance_score
    if fitness_age:
        garmin_report["metrics"]["fitnessAge"] = fitness_age

    # Write out the JSON document
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(garmin_report, f, indent=2, ensure_ascii=False)
        print(f"\nSuccess! Garmin daily data written to: {output_path}")
    except Exception as e:
        print(f"Error writing output file: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
