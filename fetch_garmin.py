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

    # Check if today's data is empty — fall back to yesterday
    if not daily_sleep.get("sleepTimeSeconds"):
        yesterday = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
        print(f"  Sleep data empty for {target_date}, trying {yesterday}...")
        success2, sleep_raw2, err2 = safe_api_call(api.get_sleep_data, yesterday)
        if success2 and sleep_raw2:
            daily_sleep2 = sleep_raw2.get("dailySleepDTO", {})
            if daily_sleep2.get("sleepTimeSeconds"):
                daily_sleep = daily_sleep2
                sleep_raw = sleep_raw2
                target_date = yesterday

    if not daily_sleep or not daily_sleep.get("sleepTimeSeconds"):
        return {"status": "Sem dados de sono disponíveis (relógio não registrou ou ainda não sincronizou)"}

    # Extract sleep score
    sleep_score = None
    if success and sleep_raw:
        sleep_score = sleep_raw.get("sleepScore") or sleep_raw.get("overallScore")
    if not sleep_score and daily_sleep:
        sleep_score = daily_sleep.get("sleepScore")

    # Sleep quality / scores
    sleep_scores_dto = daily_sleep.get("sleepScores") or (sleep_raw.get("sleepScores") if sleep_raw else None)
    if not sleep_score and sleep_scores_dto and isinstance(sleep_scores_dto, dict):
        sleep_score = sleep_scores_dto.get("overall", {}).get("value")

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
        "sleepStartLocal": daily_sleep.get("sleepStartTimestampLocal"),
        "sleepEndLocal": daily_sleep.get("sleepEndTimestampLocal"),
        "restingHeartRate": daily_sleep.get("restingHeartRate"),
        "avgOvernightHrv": daily_sleep.get("avgOvernightHrv"),
        "bodyBatteryChange": daily_sleep.get("bodyBatteryChange"),
        "sleepScores": sleep_scores_dto,
    }

def extract_hrv_data(api, target_date):
    """
    Extract Heart Rate Variability (HRV) metrics.
    Forerunner 265 provides overnight average, 5-min peak, baseline range, and status.
    """
    success, hrv_raw, err = safe_api_call(api.get_hrv_data, target_date)

    # If today is empty, try yesterday
    if success and (not hrv_raw or hrv_raw == {}):
        yesterday = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
        success, hrv_raw, err = safe_api_call(api.get_hrv_data, yesterday)

    if not success:
        return {"status": f"Erro ao buscar HRV: {err}"}
    if not hrv_raw or hrv_raw == {}:
        return {"status": "HRV não disponível"}

    summary = hrv_raw.get("hrvSummary", {})
    if not summary:
        return {"status": "HRV retornou dados mas sem resumo (hrvSummary)"}

    baseline_obj = summary.get("baseline")
    if not baseline_obj and (summary.get("baselineBalancedLow") is not None or summary.get("baselineBalancedUpper") is not None):
        baseline_obj = {
            "low": summary.get("baselineBalancedLow"),
            "upper": summary.get("baselineBalancedUpper")
        }

    return {
        "status": summary.get("status"),  # e.g., BALANCED, UNBALANCED, POOR, NONE
        "lastNightAvg": summary.get("lastNightAvg"),  # ms
        "lastNight5MinHigh": summary.get("lastNight5MinHigh"),  # ms
        "weeklyAvg": summary.get("weeklyAvg"),  # ms
        "baseline": baseline_obj,
        "feedbackPhrase": summary.get("feedbackPhrase"),
    }

def extract_training_readiness(api, target_date):
    """
    Extract Training Readiness & Recovery metrics for Forerunner 265.
    """
    # Try general training readiness list first (contains most recent post-exercise or morning snapshot)
    success_list, readiness_list, err_list = safe_api_call(api.get_training_readiness, target_date)
    if success_list and readiness_list and isinstance(readiness_list, list) and len(readiness_list) > 0:
        # Prefer the latest snapshot of the day
        latest = readiness_list[0] if len(readiness_list) > 0 else None
        for item in readiness_list:
            if isinstance(item, dict) and item.get("score") is not None:
                latest = item
                break
        return _parse_readiness(latest or readiness_list[0])

    # Fallback to morning training readiness (AFTER_WAKEUP_RESET)
    success, readiness_data, err = safe_api_call(api.get_morning_training_readiness, target_date)
    if success and readiness_data:
        return _parse_readiness(readiness_data)

    return {"status": "Training Readiness não disponível"}

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

    # Recovery time parsing (Garmin returns recovery time in minutes/seconds/hours depending on context)
    rec_time_raw = readiness_data.get("recoveryTime")
    rec_hours = None
    if rec_time_raw is not None:
        if rec_time_raw > 100:  # In minutes or seconds
            rec_hours = round(rec_time_raw / 60.0 if rec_time_raw < 10000 else rec_time_raw / 3600.0, 1)
        else:
            rec_hours = rec_time_raw

    return {
        "score": readiness_data.get("score"),
        "level": readiness_data.get("level"),
        "recoveryTimeHours": rec_hours,
        "recoveryTimeChangePhrase": readiness_data.get("recoveryTimeChangePhrase"),
        "sleepScore": readiness_data.get("sleepScore"),
        "acuteLoad": readiness_data.get("acuteLoad"),
        "hrvWeeklyAverage": readiness_data.get("hrvWeeklyAverage"),
        "feedbackShort": readiness_data.get("feedbackShort"),
        "feedbackLong": readiness_data.get("feedbackLong"),
        "inputContext": readiness_data.get("inputContext"),
        "components": components if components else None
    }

def extract_body_battery(api, target_date, summary_data=None):
    """
    Extract Body Battery data, recharge, drain, dynamic feedback, and events.
    """
    bb_res = {
        "current": None,
        "highest": None,
        "lowest": None,
        "charged": None,
        "drained": None,
        "duringSleep": None,
        "atWakeTime": None,
        "dynamicFeedback": None,
        "events": []
    }

    if summary_data and isinstance(summary_data, dict):
        bb_res["current"] = summary_data.get("bodyBatteryMostRecentValue")
        bb_res["highest"] = summary_data.get("bodyBatteryHighestValue")
        bb_res["lowest"] = summary_data.get("bodyBatteryLowestValue")
        bb_res["charged"] = summary_data.get("bodyBatteryChargedValue")
        bb_res["drained"] = summary_data.get("bodyBatteryDrainedValue")
        bb_res["duringSleep"] = summary_data.get("bodyBatteryDuringSleep")
        bb_res["atWakeTime"] = summary_data.get("bodyBatteryAtWakeTime")

    # Fetch detailed Body Battery event log
    success, bb_raw, err = safe_api_call(api.get_body_battery, target_date)
    if success and bb_raw:
        item = bb_raw[-1] if isinstance(bb_raw, list) and bb_raw else (bb_raw if isinstance(bb_raw, dict) else {})
        if item:
            if bb_res["charged"] is None:
                bb_res["charged"] = item.get("charged")
            if bb_res["drained"] is None:
                bb_res["drained"] = item.get("drained")

            dyn = item.get("bodyBatteryDynamicFeedbackEvent")
            if dyn and isinstance(dyn, dict):
                bb_res["dynamicFeedback"] = {
                    "level": dyn.get("bodyBatteryLevel"),
                    "feedbackShort": dyn.get("feedbackShortType"),
                    "feedbackLong": dyn.get("feedbackLongType")
                }

            events = item.get("bodyBatteryActivityEvent") or []
            parsed_events = []
            for ev in events:
                if isinstance(ev, dict):
                    parsed_events.append({
                        "type": ev.get("eventType"),
                        "impact": ev.get("bodyBatteryImpact"),
                        "feedback": ev.get("shortFeedback"),
                        "durationMin": round((ev.get("durationInMilliseconds") or 0) / 60000.0, 0)
                    })
            bb_res["events"] = parsed_events

    return bb_res

def extract_training_status(api, target_date):
    """
    Extract training status, acute load, chronic load, load balance, VO2Max, and fitness trend.
    """
    success, status_raw, err = safe_api_call(api.get_training_status, target_date)
    if not success or not status_raw:
        return {"status": f"Erro ao buscar training status: {err}"}

    result = {}

    # --- VO2Max ---
    vo2max_obj = status_raw.get("mostRecentVO2Max") or {}
    if vo2max_obj and isinstance(vo2max_obj, dict):
        generic = vo2max_obj.get("generic") or {}
        if generic and isinstance(generic, dict):
            result["vo2Max"] = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
            result["vo2MaxDate"] = generic.get("calendarDate")
            result["fitnessAge"] = generic.get("fitnessAge")

        cycling = vo2max_obj.get("cycling") or {}
        if cycling and isinstance(cycling, dict):
            result["vo2MaxCycling"] = cycling.get("vo2MaxPreciseValue") or cycling.get("vo2MaxValue")

    # --- Training Status (nested inside mostRecentTrainingStatus) ---
    most_recent = status_raw.get("mostRecentTrainingStatus") or {}
    latest_data = (most_recent.get("latestTrainingStatusData") or {}) if isinstance(most_recent, dict) else {}

    device_status = None
    device_name = None
    if latest_data and isinstance(latest_data, dict):
        for device_id, data in latest_data.items():
            if isinstance(data, dict):
                device_status = data
                recorded_devices = (most_recent.get("recordedDevices") or []) if isinstance(most_recent, dict) else []
                for dev in (recorded_devices or []):
                    if isinstance(dev, dict) and str(dev.get("deviceId")) == str(device_id):
                        device_name = dev.get("deviceName")
                break

    if device_status:
        ts_code = device_status.get("trainingStatus")
        ts_labels = {
            0: "NOT_APPLICABLE",
            1: "DETRAINING",
            2: "UNPRODUCTIVE",
            3: "MAINTAINING",
            4: "MAINTAINING",
            5: "RECOVERY",
            6: "PEAKING",
            7: "PRODUCTIVE",
            8: "OVERREACHING",
            9: "STRAINED",
        }
        result["trainingStatus"] = ts_labels.get(ts_code, f"UNKNOWN({ts_code})")
        result["trainingStatusCode"] = ts_code
        result["trainingStatusFeedbackPhrase"] = device_status.get("trainingStatusFeedbackPhrase")
        result["weeklyTrainingLoad"] = device_status.get("weeklyTrainingLoad")
        result["loadTunnelMin"] = device_status.get("loadTunnelMin")
        result["loadTunnelMax"] = device_status.get("loadTunnelMax")
        result["sport"] = device_status.get("sport")
        result["fitnessTrend"] = device_status.get("fitnessTrend")
        result["deviceName"] = device_name

        acute_dto = device_status.get("acuteTrainingLoadDTO")
        if acute_dto and isinstance(acute_dto, dict):
            result["acuteLoad"] = acute_dto.get("dailyTrainingLoadAcute") or acute_dto.get("acuteTrainingLoad")
            result["chronicLoad"] = acute_dto.get("dailyTrainingLoadChronic") or acute_dto.get("chronicTrainingLoad")
            result["acwr"] = acute_dto.get("dailyAcuteChronicWorkloadRatio")
            result["acwrStatus"] = acute_dto.get("acwrStatus")
            result["acwrStatusFeedback"] = acute_dto.get("acwrStatusFeedback")
            if not result.get("acwr") and result.get("acuteLoad") and result.get("chronicLoad") and result["chronicLoad"] > 0:
                result["acwr"] = round(result["acuteLoad"] / result["chronicLoad"], 2)

    # --- Training Load Balance (Aerobic Low, Aerobic High, Anaerobic) ---
    load_balance = status_raw.get("mostRecentTrainingLoadBalance") or {}
    balance_map = (load_balance.get("metricsTrainingLoadBalanceDTOMap") or {}) if isinstance(load_balance, dict) else {}
    if balance_map and isinstance(balance_map, dict):
        for dev_id, b_data in balance_map.items():
            if isinstance(b_data, dict):
                result["loadBalance"] = {
                    "aerobicLow": b_data.get("monthlyLoadAerobicLow"),
                    "aerobicLowTargetMin": b_data.get("monthlyLoadAerobicLowTargetMin"),
                    "aerobicLowTargetMax": b_data.get("monthlyLoadAerobicLowTargetMax"),
                    "aerobicHigh": b_data.get("monthlyLoadAerobicHigh"),
                    "aerobicHighTargetMin": b_data.get("monthlyLoadAerobicHighTargetMin"),
                    "aerobicHighTargetMax": b_data.get("monthlyLoadAerobicHighTargetMax"),
                    "anaerobic": b_data.get("monthlyLoadAnaerobic"),
                    "anaerobicTargetMin": b_data.get("monthlyLoadAnaerobicTargetMin"),
                    "anaerobicTargetMax": b_data.get("monthlyLoadAnaerobicTargetMax"),
                    "feedbackPhrase": b_data.get("trainingBalanceFeedbackPhrase"),
                }
                break

    if not result:
        return {"status": "Training status retornou dados mas sem informações de treino"}

    return result

def extract_lactate_threshold(api):
    """
    Extract Lactate Threshold metrics (LTHR & Threshold Pace/Speed).
    """
    success, lt_raw, err = safe_api_call(api.get_lactate_threshold)
    if not success or not lt_raw or not isinstance(lt_raw, dict):
        return None

    speed_hr = lt_raw.get("speed_and_heart_rate", {})
    if speed_hr and isinstance(speed_hr, dict):
        hr = speed_hr.get("heartRate")
        speed_mps = speed_hr.get("speed")
        pace_sec = int(1000.0 / speed_mps) if speed_mps and speed_mps > 0 else None
        return {
            "heartRate": hr,
            "speedMps": speed_mps,
            "paceFormatted": format_seconds_to_time(pace_sec) if pace_sec else None,
            "calendarDate": speed_hr.get("calendarDate"),
        }
    return None

def extract_race_predictions(api):
    """
    Extract race prediction metrics directly from Garmin Connect.
    """
    success, pred_raw, err = safe_api_call(api.get_race_predictions)
    if not success or not pred_raw or not isinstance(pred_raw, dict):
        return {"status": "Race predictions não disponível"}

    p5k = pred_raw.get("time5K")
    p10k = pred_raw.get("time10K")
    phalf = pred_raw.get("timeHalfMarathon")
    pmara = pred_raw.get("timeMarathon")

    if not any([p5k, p10k, phalf, pmara]):
        return {"status": "Race predictions vazio"}

    return {
        "5k": {
            "seconds": p5k,
            "formatted": format_seconds_to_time(p5k),
            "pace_formatted": format_seconds_to_time(p5k / 5.0) if p5k else "-"
        },
        "10k": {
            "seconds": p10k,
            "formatted": format_seconds_to_time(p10k),
            "pace_formatted": format_seconds_to_time(p10k / 10.0) if p10k else "-"
        },
        "halfMarathon": {
            "seconds": phalf,
            "formatted": format_seconds_to_time(phalf),
            "pace_formatted": format_seconds_to_time(phalf / 21.0975) if phalf else "-"
        },
        "marathon": {
            "seconds": pmara,
            "formatted": format_seconds_to_time(pmara),
            "pace_formatted": format_seconds_to_time(pmara / 42.195) if pmara else "-"
        }
    }

def extract_daily_summary(api, target_date):
    """
    Extract general summary metrics for steps, calories, stress, RHR, SpO2, respiration.
    """
    success, summary, err = safe_api_call(api.get_user_summary, target_date)
    if not success or not summary:
        return {"error": f"Erro ao buscar resumo diário: {err}"}

    steps = summary.get("totalSteps") or 0
    step_goal = summary.get("dailyStepGoal") or summary.get("stepGoal") or 0
    active_cal = summary.get("activeKilocalories")
    if active_cal is None:
        total_cal = summary.get("totalKilocalories") or 0
        bmr_cal = summary.get("bmrKilocalories") or 0
        active_cal = max(0, int(total_cal - bmr_cal)) if total_cal and bmr_cal else 0

    total_dist = summary.get("totalDistanceMeters") or 0.0
    dist_km = round(total_dist / 1000.0, 2)

    # Resting Heart Rate
    resting_hr = summary.get("restingHeartRate")
    last_7d_hr = summary.get("lastSevenDaysAvgRestingHeartRate")
    if not resting_hr:
        success_hr, hr_data, _ = safe_api_call(api.get_heart_rates, target_date)
        if success_hr and hr_data:
            resting_hr = hr_data.get("restingHeartRate")
            last_7d_hr = last_7d_hr or hr_data.get("lastSevenDaysAvgRestingHeartRate")

    # Stress
    stress_avg = summary.get("averageStressLevel")
    stress_max = summary.get("maxStressLevel")
    stress_rest_dur = summary.get("restStressDuration")
    stress_qualifier = summary.get("stressQualifier")

    # Respiration
    resp_waking = summary.get("avgWakingRespirationValue")
    resp_lowest = summary.get("lowestRespirationValue")
    resp_highest = summary.get("highestRespirationValue")

    # SpO2
    spo2_avg = summary.get("averageSpo2")
    spo2_lowest = summary.get("lowestSpo2")
    spo2_latest = summary.get("latestSpo2")

    # Additional Respiration Endpoint check
    success_resp, resp_raw, _ = safe_api_call(api.get_respiration_data, target_date)
    resp_sleep = None
    if success_resp and resp_raw and isinstance(resp_raw, dict):
        resp_waking = resp_waking or resp_raw.get("avgWakingRespirationValue")
        resp_sleep = resp_raw.get("avgSleepRespirationValue")
        resp_lowest = resp_lowest or resp_raw.get("lowestRespirationValue")
        resp_highest = resp_highest or resp_raw.get("highestRespirationValue")

    # Additional SpO2 Endpoint check
    if spo2_avg is None:
        success_spo2, spo2_raw, _ = safe_api_call(api.get_spo2_data, target_date)
        if success_spo2 and spo2_raw and isinstance(spo2_raw, dict):
            spo2_avg = spo2_raw.get("averageSpO2")
            spo2_lowest = spo2_raw.get("lowestSpO2")
            spo2_latest = spo2_raw.get("latestSpO2")

    return {
        "steps": steps,
        "stepGoal": step_goal,
        "activeCalories": int(active_cal) if active_cal else 0,
        "distanceKm": dist_km,
        "restingHeartRate": resting_hr,
        "restingHeartRate7dAvg": last_7d_hr,
        "stress": {
            "average": stress_avg,
            "max": stress_max,
            "restDurationSeconds": stress_rest_dur,
            "qualifier": stress_qualifier
        },
        "respiration": {
            "waking": resp_waking,
            "sleep": resp_sleep,
            "lowest": resp_lowest,
            "highest": resp_highest
        },
        "spO2": {
            "average": spo2_avg,
            "lowest": spo2_lowest,
            "latest": spo2_latest
        },
        "_rawSummary": summary
    }

def extract_fitness_age(api, target_date):
    """
    Extract official Garmin Fitness Age and components.
    """
    success, data, err = safe_api_call(api.get_fitnessage_data, target_date)
    if not success or not data or not isinstance(data, dict):
        return None

    if data.get("fitnessAge"):
        comps = data.get("components", {})
        parsed_comps = {}
        for k, v in comps.items():
            if isinstance(v, dict):
                parsed_comps[k] = v.get("value")

        return {
            "chronologicalAge": data.get("chronologicalAge"),
            "fitnessAge": round(data.get("fitnessAge"), 1) if isinstance(data.get("fitnessAge"), (int, float)) else data.get("fitnessAge"),
            "achievableFitnessAge": round(data.get("achievableFitnessAge"), 1) if isinstance(data.get("achievableFitnessAge"), (int, float)) else data.get("achievableFitnessAge"),
            "components": parsed_comps if parsed_comps else None
        }
    return None

def extract_endurance_score(api, target_date):
    """Extract endurance score if available."""
    success, data, err = safe_api_call(api.get_endurance_score, target_date)
    if not success or not data or not isinstance(data, dict):
        return None
    score = data.get("overallScore") or data.get("enduranceScore")
    if score:
        return {"score": score, "raw": data}
    return None

def extract_weight_data(api, target_date, output_path="garmin_data.json"):
    """
    Extract latest recorded weight from Garmin without any hard-coded defaults.
    Strategy:
    1. Daily weigh-in on target_date.
    2. Body composition history (expanded search up to 365 days) to find the latest weigh-in.
    3. User profile settings in Garmin Connect (userData.weight registered in Garmin account).
    4. Last known weight from existing local cache file if API is temporarily unavailable.
    """
    end_date = date.fromisoformat(target_date)

    # 1. Daily weigh-ins on target_date
    success, weighins, err = safe_api_call(api.get_daily_weigh_ins, target_date)
    if success and weighins and isinstance(weighins, dict):
        entries = weighins.get("dateWeightList", [])
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

    # 2. Historical body composition: search up to 365 days back to find the most recent weigh-in
    search_end = max(end_date, date.today())
    start_date = (search_end - timedelta(days=365)).isoformat()
    success2, comp_raw, err2 = safe_api_call(api.get_body_composition, start_date, search_end.isoformat())
    if success2 and comp_raw and isinstance(comp_raw, dict):
        list_dto = comp_raw.get("dateWeightList", [])
        if list_dto:
            valid_entries = [e for e in list_dto if e.get("weight")]
            if valid_entries:
                latest_entry = max(valid_entries, key=lambda x: str(x.get("calendarDate") or ""))
                weight_g = latest_entry.get("weight")
                if weight_g:
                    return {
                        "weightKg": round(weight_g / 1000.0, 2) if weight_g > 1000 else round(weight_g, 2),
                        "bmi": latest_entry.get("bmi"),
                        "bodyFatPercent": latest_entry.get("bodyFat"),
                        "date": latest_entry.get("calendarDate"),
                        "source": "body_composition"
                    }

    # 3. User profile settings in Garmin Connect (weight stored in Garmin account profile)
    success3, settings_raw, err3 = safe_api_call(api.connectapi, '/userprofile-service/userprofile/user-settings')
    if success3 and settings_raw and isinstance(settings_raw, dict):
        user_data = settings_raw.get('userData', {})
        if isinstance(user_data, dict):
            weight_g = user_data.get('weight')
            if weight_g:
                weight_val = float(weight_g)
                return {
                    "weightKg": round(weight_val / 1000.0, 2) if weight_val > 1000 else round(weight_val, 2),
                    "bmi": None,
                    "bodyFatPercent": None,
                    "date": None,
                    "source": "garmin_user_profile"
                }

    # 4. Fallback: check existing local cache file for the last known Garmin weight
    if output_path and os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            cached_weight = cached_data.get("metrics", {}).get("bodyComposition", {})
            if cached_weight.get("weightKg"):
                return {
                    "weightKg": cached_weight.get("weightKg"),
                    "bmi": cached_weight.get("bmi"),
                    "bodyFatPercent": cached_weight.get("bodyFatPercent"),
                    "date": cached_weight.get("date"),
                    "source": "cached_garmin_fallback"
                }
        except Exception:
            pass

    return {"status": "Sem dados de peso registrados no Garmin"}

def main():
    args = parse_arguments()
    target_date = args.date
    output_path = args.output

    print(f"Initializing Garmin API to fetch data for date: {target_date}")
    api = init_api()
    if not api:
        print("Error: Could not initialize Garmin client.", file=sys.stderr)
        sys.exit(1)

    print("Fetching daily activity summary...")
    daily_summary = extract_daily_summary(api, target_date)
    raw_summary = daily_summary.pop("_rawSummary", {})

    print("Fetching sleep data...")
    sleep_data = extract_sleep_data(api, target_date)

    print("Fetching HRV data (VFC)...")
    hrv_data = extract_hrv_data(api, target_date)

    print("Fetching Body Battery...")
    body_battery_data = extract_body_battery(api, target_date, summary_data=raw_summary)

    print("Fetching training readiness...")
    readiness_data = extract_training_readiness(api, target_date)

    print("Fetching training status & workload...")
    training_status = extract_training_status(api, target_date)

    print("Fetching lactate threshold...")
    lactate_threshold = extract_lactate_threshold(api)

    print("Fetching body composition (weight)...")
    weight_data = extract_weight_data(api, target_date, output_path=output_path)

    print("Fetching race predictions...")
    race_predictions = extract_race_predictions(api)

    print("Fetching endurance score...")
    endurance_score = extract_endurance_score(api, target_date)

    print("Fetching fitness age...")
    fitness_age = extract_fitness_age(api, target_date)

    print("Fetching profile user settings (gender, birthdate, profile weight)...")
    success_settings, settings_raw, err_settings = safe_api_call(api.connectapi, '/userprofile-service/userprofile/user-settings')
    gender = None
    birth_date = None
    user_weight_profile_kg = None
    if success_settings and settings_raw and isinstance(settings_raw, dict):
        user_data = settings_raw.get('userData', {})
        if isinstance(user_data, dict):
            gender = user_data.get('gender')
            birth_date = user_data.get('birthDate')
            w_g = user_data.get('weight')
            if w_g:
                w_val = float(w_g)
                user_weight_profile_kg = round(w_val / 1000.0, 2) if w_val > 1000 else round(w_val, 2)

    # Ensure bodyComposition has weightKg if user profile weight is available
    if isinstance(weight_data, dict) and not weight_data.get("weightKg") and user_weight_profile_kg:
        weight_data["weightKg"] = user_weight_profile_kg
        weight_data["source"] = weight_data.get("source") or "garmin_user_profile"

    print("Fetching planned workouts (Runna & Garmin)...")
    planned_workouts = []
    try:
        from garmin_calendar import fetch_planned_workouts_for_date
        planned_workouts = fetch_planned_workouts_for_date(target_date, api=api)
        print(f"Found {len(planned_workouts)} planned workout(s) for {target_date}.")
    except Exception as err_pw:
        print(f"Warning: Could not fetch planned workouts for date: {err_pw}", file=sys.stderr)

    # Compile all data into a structured deterministic document
    garmin_report = {
        "metadata": {
            "date": target_date,
            "userDisplayName": api.display_name,
            "fetchedAt": date.today().isoformat(),
            "gender": gender,
            "birthDate": birth_date,
            "userProfileWeightKg": user_weight_profile_kg
        },
        "metrics": {
            "dailySummary": daily_summary,
            "sleep": sleep_data,
            "hrv": hrv_data,
            "bodyBattery": body_battery_data,
            "trainingReadiness": readiness_data,
            "trainingStatus": training_status,
            "bodyComposition": weight_data,
            "racePredictions": race_predictions,
            "plannedWorkouts": planned_workouts,
        }
    }

    if lactate_threshold:
        garmin_report["metrics"]["lactateThreshold"] = lactate_threshold
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

