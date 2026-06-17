#!/usr/bin/env python3
"""
calc_training_load.py

Deterministic training load calculator.
Merges Garmin + Strava activities, deduplicates, calculates TRIMP per activity,
and computes ACWR using Exponentially Weighted Moving Average (EWMA).

This script ONLY does math — no API calls, no AI. Pure numbers.
"""

import argparse
import json
import math
import os
import sys
from datetime import date, datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Physiological parameters (from .env or defaults)
# ---------------------------------------------------------------------------

def parse_pace_to_seconds(pace_str: str) -> int:
    """Parse MM:SS pace string to total seconds per 100m/km."""
    try:
        parts = pace_str.strip().split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return int(float(pace_str))
    except Exception:
        return 120  # default fallback 2:00

def normalize_sport(sport: str) -> str:
    if not sport:
        return "unknown"
    s = sport.lower().replace("_", "").replace(" ", "")
    if any(x in s for x in ("run", "running", "treadmill")):
        return "run"
    if any(x in s for x in ("ride", "cycling", "bike")):
        return "ride"
    if "swim" in s:
        return "swim"
    if "walk" in s or "hike" in s:
        return "walk"
    if any(x in s for x in ("strength", "weight", "workout", "muscula", "forca", "força")):
        return "strength"
    return s

MAX_HR = int(os.getenv("MAX_HR", "189"))
RESTING_HR = int(os.getenv("RESTING_HR", "50"))
CYCLING_FTP = int(os.getenv("CYCLING_FTP", "178"))
RUNNING_LTHR = int(os.getenv("RUNNING_LTHR", "168"))
SWIM_PACE = os.getenv("SWIM_PACE", "2:00")
SWIM_PACE_SECS = parse_pace_to_seconds(SWIM_PACE)
RUNNING_ECONOMY_PENALTY = float(os.getenv("RUNNING_ECONOMY_PENALTY", "0.10"))

# EWMA decay constants
ACUTE_DAYS = 7
CHRONIC_DAYS = 28
LAMBDA_ACUTE = 2.0 / (ACUTE_DAYS + 1)     # ≈ 0.25
LAMBDA_CHRONIC = 2.0 / (CHRONIC_DAYS + 1)  # ≈ 0.069

# Deduplication tolerance (seconds)
DEDUP_TOLERANCE_SECS = 300  # 5 minutes


# ---------------------------------------------------------------------------
# TRIMP Calculation (Banister method)
# ---------------------------------------------------------------------------

def calc_trimp_banister(duration_min: float, avg_hr: float, max_hr: float, resting_hr: float) -> float:
    """
    Calculate TRIMP using the Banister (1991) exponential method for males.
    
    TRIMP = duration_min × HRR_fraction × 0.64 × e^(1.92 × HRR_fraction)
    
    Where HRR_fraction = (avg_hr - resting_hr) / (max_hr - resting_hr)
    """
    hr_range = max_hr - resting_hr
    if hr_range <= 0 or avg_hr <= resting_hr:
        return duration_min * 0.5  # minimal load fallback
    
    hrr = min((avg_hr - resting_hr) / hr_range, 1.0)  # clamp to [0, 1]
    trimp = duration_min * hrr * 0.64 * math.exp(1.92 * hrr)
    return round(trimp, 1)


def calc_trimp_power(duration_min: float, avg_watts: float, ftp: float) -> float:
    """
    Estimate TRIMP-equivalent from power data using IF (Intensity Factor).
    
    TSS ≈ (duration_sec × NP × IF) / (FTP × 3600) × 100
    Simplified: TSS ≈ duration_min × (avg_watts / ftp)² / 60 × 100
    
    We map TSS to TRIMP-equivalent scale (roughly 1:1 for comparison).
    """
    if ftp <= 0 or avg_watts <= 0:
        return duration_min * 0.5
    
    intensity_factor = avg_watts / ftp
    tss = (duration_min / 60.0) * (intensity_factor ** 2) * 100
    return round(tss, 1)


def calc_swim_load_pace(duration_min: float, distance_meters: float, threshold_pace_sec: float) -> float:
    """
    Calculate Swim Training Stress Score (sTSS) based on swim pace.
    
    sTSS = (duration_min / 60.0) * (Intensity Factor)^2 * 100
    Where Intensity Factor = threshold_pace_sec / average_pace_sec (seconds per 100m)
    """
    if not distance_meters or distance_meters <= 0 or not duration_min or duration_min <= 0 or threshold_pace_sec <= 0:
        return 0.0
    
    # Average pace in seconds per 100m
    avg_pace_sec = (duration_min * 60.0) / (distance_meters / 100.0)
    if avg_pace_sec <= 0:
        return 0.0
        
    intensity_factor = threshold_pace_sec / avg_pace_sec
    tss = (duration_min / 60.0) * (intensity_factor ** 2) * 100
    return round(tss, 1)


def calc_run_load_hrss(duration_min: float, avg_hr: float, max_hr: float, resting_hr: float, threshold_hr: float) -> float:
    """
    Calculate Heart Rate Stress Score (HRSS) as normalized TRIMP.
    
    HRSS = (TRIMP_activity / TRIMP_1_hour_at_threshold) * 100
    """
    if duration_min <= 0 or avg_hr <= 0:
        return 0.0
        
    trimp_act = calc_trimp_banister(duration_min, avg_hr, max_hr, resting_hr)
    trimp_lthr_1hour = calc_trimp_banister(60.0, threshold_hr, max_hr, resting_hr)
    
    if trimp_lthr_1hour <= 0:
        return 0.0
        
    hrss = (trimp_act / trimp_lthr_1hour) * 100
    return round(hrss, 1)


def calc_trimp_duration_only(duration_min: float, sport_type: str) -> float:
    """
    Fallback TRIMP estimate when no HR or power data is available.
    Uses sport-specific multipliers for rough estimation.
    """
    multipliers = {
        "Run": 1.0, "TrailRun": 1.1, "Hike": 0.6, "Walk": 0.4,
        "Ride": 0.8, "VirtualRide": 0.8, "MountainBikeRide": 0.9,
        "Swim": 0.7, "Workout": 0.6, "WeightTraining": 0.5,
        "Yoga": 0.3,
    }
    mult = multipliers.get(sport_type, 0.6)
    return round(duration_min * mult, 1)


def compute_activity_trimp(activity: dict) -> tuple[float, str]:
    """Compute TRIMP/HRSS/TSS for a single activity using the best available data and return (trimp, method)."""
    duration_sec = activity.get("moving_time_seconds") or activity.get("elapsed_time_seconds") or 0
    duration_min = duration_sec / 60.0
    
    if duration_min <= 0:
        return 0.0, "duration_only"
    
    sport_type = activity.get("sport_type") or activity.get("type") or "Unknown"
    norm_sport = normalize_sport(sport_type)
    
    if norm_sport == "strength":
        return 0.0, "ignored"
    
    avg_hr = activity.get("average_heartrate")
    avg_watts = activity.get("weighted_average_watts") or activity.get("average_watts")
    distance_meters = activity.get("distance_meters")
    
    # Rule 1: Swim -> Pace-based load (if distance is present)
    if norm_sport == "swim":
        if distance_meters and distance_meters > 0:
            load = calc_swim_load_pace(duration_min, distance_meters, SWIM_PACE_SECS)
            return load, "pace_swim_tss"
        # Fallback if no distance
        if avg_hr and avg_hr > RESTING_HR:
            return calc_run_load_hrss(duration_min, avg_hr, MAX_HR, RESTING_HR, RUNNING_LTHR), "hrss"
        return calc_trimp_duration_only(duration_min, sport_type), "duration_only"
        
    # Rule 2: Bike -> Power-based load (if power is present)
    elif norm_sport == "ride":
        if avg_watts and avg_watts > 0:
            return calc_trimp_power(duration_min, avg_watts, CYCLING_FTP), "power_tss"
        if avg_hr and avg_hr > RESTING_HR:
            return calc_run_load_hrss(duration_min, avg_hr, MAX_HR, RESTING_HR, RUNNING_LTHR), "hrss"
        return calc_trimp_duration_only(duration_min, sport_type), "duration_only"
        
    # Rule 3: Run -> HR-based load (if HR is present)
    elif norm_sport == "run":
        if avg_hr and avg_hr > RESTING_HR:
            return calc_run_load_hrss(duration_min, avg_hr, MAX_HR, RESTING_HR, RUNNING_LTHR), "hrss"
        return calc_trimp_duration_only(duration_min, sport_type), "duration_only"
        
    # Rule 4: Other sports -> HR if present, else duration
    else:
        if avg_hr and avg_hr > RESTING_HR:
            return calc_run_load_hrss(duration_min, avg_hr, MAX_HR, RESTING_HR, RUNNING_LTHR), "hrss"
        return calc_trimp_duration_only(duration_min, sport_type), "duration_only"


# ---------------------------------------------------------------------------
# VO2Max Estimation
# ---------------------------------------------------------------------------

def estimate_session_vo2max(activity: dict, max_hr: float, resting_hr: float, weight_kg: float) -> float | None:
    """
    Estimate VO2Max for a single session using the ACSM metabolic equations.
    """
    duration_sec = activity.get("moving_time_seconds") or activity.get("elapsed_time_seconds") or 0
    if duration_sec <= 0:
        return None
        
    avg_hr = activity.get("average_heartrate")
    if not avg_hr or avg_hr <= resting_hr:
        return None
        
    hr_range = max_hr - resting_hr
    if hr_range <= 0:
        return None
        
    hrr_fraction = min((avg_hr - resting_hr) / hr_range, 1.0)
    # We need a minimum effort to get a decent estimate (e.g. at least 40% HRR)
    if hrr_fraction < 0.4:
        return None
        
    sport_type = activity.get("sport_type") or activity.get("type") or "Unknown"
    
    # 1. Cycling VO2Max
    avg_watts = activity.get("weighted_average_watts") or activity.get("average_watts")
    if avg_watts and avg_watts > 0 and sport_type in ("Ride", "VirtualRide", "MountainBikeRide", "Cycling"):
        max_power_estimate = avg_watts / hrr_fraction
        # ACSM cycling formula: VO2 = (10.8 * W / M) + 7
        vo2max = (10.8 * max_power_estimate / weight_kg) + 7
        return round(vo2max, 2)
        
    # 2. Running VO2Max
    distance_meters = activity.get("distance_meters")
    if distance_meters and distance_meters > 0 and sport_type in ("Run", "TrailRun", "running"):
        duration_min = duration_sec / 60.0
        speed_m_per_min = distance_meters / duration_min
        max_speed_estimate = speed_m_per_min / hrr_fraction
        # ACSM running formula (flat): VO2 = (Speed * 0.2) + 3.5
        vo2max = (max_speed_estimate * 0.2) + 3.5
        return round(vo2max, 2)
        
    return None

def format_seconds_to_time(seconds):
    if not seconds: return "n/a"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0: return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def calculate_race_predictions_from_vo2(vo2max: float, penalty: float = 0.10) -> dict:
    """Calculate 5k, 10k, Half, and Marathon predictions using Daniels/Riegel combo."""
    if not vo2max or vo2max <= 0:
        return {}
        
    # Apply economy penalty to get "Effective VO2Max/VDOT"
    effective_vo2 = vo2max * (1.0 - penalty)
        
    # Solve Daniels VDOT velocity equation: 0.000104*v^2 + 0.182258*v - 4.6 - VO2 = 0
    a = 0.000104
    b = 0.182258
    c = -4.6 - effective_vo2
    
    discriminant = b**2 - 4 * a * c
    if discriminant < 0:
        return {}
        
    v_m_min = (-b + math.sqrt(discriminant)) / (2 * a)
    
    # Base distance: 5000m. Daniels equation pace roughly matches 3k-5k pace.
    t_5k_min = 5000 / v_m_min
    t_5k_sec = t_5k_min * 60
    
    # Riegel exponent for running
    exp = 1.06
    
    t_5k_sec_total = int(t_5k_sec)
    t_10k_sec_total = int(t_5k_sec * (10000/5000)**exp)
    t_half_sec_total = int(t_5k_sec * (21097.5/5000)**exp)
    t_mara_sec_total = int(t_5k_sec * (42195/5000)**exp)
    
    preds = {
        "5k": {
            "seconds": t_5k_sec_total, 
            "formatted": format_seconds_to_time(t_5k_sec_total),
            "pace_formatted": format_seconds_to_time(t_5k_sec_total / 5.0)
        },
        "10k": {
            "seconds": t_10k_sec_total, 
            "formatted": format_seconds_to_time(t_10k_sec_total),
            "pace_formatted": format_seconds_to_time(t_10k_sec_total / 10.0)
        },
        "halfMarathon": {
            "seconds": t_half_sec_total, 
            "formatted": format_seconds_to_time(t_half_sec_total),
            "pace_formatted": format_seconds_to_time(t_half_sec_total / 21.0975)
        },
        "marathon": {
            "seconds": t_mara_sec_total, 
            "formatted": format_seconds_to_time(t_mara_sec_total),
            "pace_formatted": format_seconds_to_time(t_mara_sec_total / 42.195)
        },
        "calculated_from_vo2": True
    }
    return preds

# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def parse_activity_time(act: dict) -> datetime | None:
    """Parse start_date from activity dict."""
    for key in ("start_date", "start_date_local", "startTimeLocal", "startTimeGMT"):
        val = act.get(key)
        if val:
            try:
                # Handle ISO format with or without Z
                val = val.replace("Z", "+00:00")
                return datetime.fromisoformat(val)
            except (ValueError, TypeError):
                continue
    return None


def deduplicate_activities(garmin_acts: list[dict], strava_acts: list[dict]) -> list[dict]:
    """
    Merge Garmin and Strava activities, removing duplicates.
    An activity is considered duplicate if start times are within DEDUP_TOLERANCE_SECS
    and the sport type is similar.
    """
    # Index Garmin activities by (normalized_sport, rounded_timestamp)
    garmin_index = set()
    for act in garmin_acts:
        t = parse_activity_time(act)
        sport = normalize_sport(act.get("sport_type") or act.get("activityType", {}).get("typeKey", ""))
        if t:
            # Round to nearest 5 min for matching
            rounded = int(t.timestamp()) // DEDUP_TOLERANCE_SECS
            garmin_index.add((sport, rounded))
            # Also add adjacent windows to catch near-misses
            garmin_index.add((sport, rounded - 1))
            garmin_index.add((sport, rounded + 1))

    # Filter Strava activities, keeping only those NOT in Garmin
    merged = list(garmin_acts)  # Start with all Garmin activities
    strava_added = 0
    strava_skipped = 0

    for act in strava_acts:
        t = parse_activity_time(act)
        sport = normalize_sport(act.get("sport_type") or act.get("type") or "")
        if t:
            rounded = int(t.timestamp()) // DEDUP_TOLERANCE_SECS
            if (sport, rounded) in garmin_index:
                strava_skipped += 1
                continue
        merged.append(act)
        strava_added += 1

    print(f"  Deduplication: {len(garmin_acts)} Garmin + {len(strava_acts)} Strava "
          f"→ {strava_added} Strava added, {strava_skipped} duplicates removed "
          f"→ {len(merged)} total")
    return merged


# ---------------------------------------------------------------------------
# EWMA ACWR Calculation
# ---------------------------------------------------------------------------

def calc_ewma_acwr(daily_loads: dict[str, float], target_date: str) -> dict:
    """
    Calculate ACWR using Exponentially Weighted Moving Average.
    
    Parameters:
        daily_loads: dict mapping 'YYYY-MM-DD' → total TRIMP for that day
        target_date: the date to calculate ACWR for (YYYY-MM-DD)
    
    Returns dict with acute, chronic, acwr, and daily breakdown.
    """
    target = date.fromisoformat(target_date)
    
    # We need at least CHRONIC_DAYS + some buffer of history
    start = target - timedelta(days=CHRONIC_DAYS + 7)
    
    acute_ewma = 0.0
    chronic_ewma = 0.0
    
    # Initialize EWMA by iterating through days chronologically
    current = start
    while current <= target:
        day_str = current.isoformat()
        load = daily_loads.get(day_str, 0.0)
        
        acute_ewma = load * LAMBDA_ACUTE + acute_ewma * (1 - LAMBDA_ACUTE)
        chronic_ewma = load * LAMBDA_CHRONIC + chronic_ewma * (1 - LAMBDA_CHRONIC)
        
        current += timedelta(days=1)
    
    # Calculate ACWR
    acwr = round(acute_ewma / chronic_ewma, 2) if chronic_ewma > 0 else None
    
    # Also calculate simple 7-day sum for weekly load
    week_start = target - timedelta(days=6)
    weekly_load = sum(
        daily_loads.get((week_start + timedelta(days=i)).isoformat(), 0.0)
        for i in range(7)
    )
    
    return {
        "acwr": acwr,
        "acuteEWMA": round(acute_ewma, 1),
        "chronicEWMA": round(chronic_ewma, 1),
        "weeklyLoadTrimp": round(weekly_load, 1),
    }


# ---------------------------------------------------------------------------
# Garmin activity fetching (from Garmin API via existing session)
# ---------------------------------------------------------------------------

def load_garmin_activities(garmin_data_path: str, days: int = 42) -> list[dict]:
    """
    Try to fetch Garmin activities. First check if garmin_data.json has them cached,
    then try the Garmin API directly.
    """
    # Try to get activities from the Garmin API
    try:
        from garminconnect import Garmin
        from pathlib import Path

        tokenstore = os.getenv("GARMINTOKENS", ".garminconnect")
        tokenstore_path = str(Path(tokenstore).expanduser().resolve())
        
        garmin = Garmin()
        garmin.login(tokenstore_path)
        
        end_date = date.today().isoformat()
        start_date = (date.today() - timedelta(days=days)).isoformat()
        
        activities = garmin.get_activities_by_date(start_date, end_date)
        
        if activities:
            simplified = []
            for act in activities:
                simplified.append({
                    "id": act.get("activityId"),
                    "name": act.get("activityName"),
                    "sport_type": act.get("activityType", {}).get("typeKey", "unknown"),
                    "start_date": act.get("startTimeLocal"),
                    "moving_time_seconds": act.get("movingDuration") or act.get("duration"),
                    "elapsed_time_seconds": act.get("duration"),
                    "distance_meters": act.get("distance"),
                    "average_heartrate": act.get("averageHR"),
                    "max_heartrate": act.get("maxHR"),
                    "average_watts": act.get("averagePower") or act.get("avgPower") or act.get("averageWatts"),
                    "weighted_average_watts": act.get("weightedAveragePower") or act.get("weightedAvgPower") or act.get("weightedAverageWatts"),
                    "source": "garmin",
                })
            return simplified
    except Exception as e:
        print(f"  Warning: Could not fetch Garmin activities: {e}", file=sys.stderr)

    return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_arguments():
    parser = argparse.ArgumentParser(description="Calculate combined training load and ACWR.")
    parser.add_argument("--garmin-data", type=str, default="garmin_data.json", help="Path to garmin_data.json")
    parser.add_argument("--strava-data", type=str, default="strava_activities.json", help="Path to strava_activities.json")
    parser.add_argument("--date", type=str, default=date.today().isoformat(), help="Target date for ACWR (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=42, help="Days of history for ACWR calculation")
    return parser.parse_args()


def main():
    args = parse_arguments()
    
    print(f"Calculating training load for {args.date}...")
    print(f"  Config: MAX_HR={MAX_HR}, RESTING_HR={RESTING_HR}, FTP={CYCLING_FTP}")
    
    # Load Garmin Data (to extract weight)
    garmin_report = {}
    user_weight_kg = 75.0
    if os.path.exists(args.garmin_data):
        with open(args.garmin_data, "r") as f:
            garmin_report = json.load(f)
        weight = garmin_report.get("metrics", {}).get("bodyComposition", {}).get("weightKg")
        if weight:
            user_weight_kg = float(weight)
        print(f"  Loaded weight for VO2Max calculation: {user_weight_kg} kg")
    
    # Load Strava activities
    strava_acts = []
    if os.path.exists(args.strava_data):
        with open(args.strava_data, "r") as f:
            strava_acts = json.load(f)
        print(f"  Loaded {len(strava_acts)} Strava activities from cache")
    else:
        print(f"  No Strava data file found at {args.strava_data}")

    # Load Garmin activities
    print("  Fetching Garmin activities...")
    garmin_acts = load_garmin_activities(args.garmin_data, days=args.days)
    print(f"  Loaded {len(garmin_acts)} Garmin activities")

    # Deduplicate
    all_activities = deduplicate_activities(garmin_acts, strava_acts)
    
    # Calculate TRIMP and VO2Max per activity
    for act in all_activities:
        act["trimp"], act["trimp_method"] = compute_activity_trimp(act)
        act["estimated_vo2max"] = estimate_session_vo2max(act, MAX_HR, RESTING_HR, user_weight_kg)
    
    # Aggregate daily TRIMP
    daily_loads = {}
    for act in all_activities:
        t = parse_activity_time(act)
        if t:
            day_str = t.strftime("%Y-%m-%d")
            daily_loads[day_str] = daily_loads.get(day_str, 0.0) + act["trimp"]
    
    # Calculate ACWR
    acwr_result = calc_ewma_acwr(daily_loads, args.date)
    
    print(f"\n  Results:")
    print(f"    Weekly Load (TRIMP): {acwr_result['weeklyLoadTrimp']}")
    print(f"    Acute EWMA:  {acwr_result['acuteEWMA']}")
    print(f"    Chronic EWMA: {acwr_result['chronicEWMA']}")
    print(f"    ACWR: {acwr_result['acwr']}")
    
    # Build activity breakdown for the last 7 days
    target = date.fromisoformat(args.date)
    week_start = target - timedelta(days=6)
    recent_activities = []
    for act in all_activities:
        t = parse_activity_time(act)
        if t and week_start <= t.date() <= target:
            recent_activities.append({
                "date": t.strftime("%Y-%m-%d"),
                "name": act.get("name", "?"),
                "sport": act.get("sport_type") or act.get("type", "?"),
                "duration_min": round((act.get("moving_time_seconds") or 0) / 60, 0),
                "avg_hr": act.get("average_heartrate"),
                "avg_watts": act.get("weighted_average_watts") or act.get("average_watts"),
                "trimp": act["trimp"],
                "method": act["trimp_method"],
                "estimated_vo2max": act.get("estimated_vo2max"),
                "source": act.get("source", "?"),
            })
    recent_activities.sort(key=lambda x: x["date"], reverse=True)

    # Calculate median VO2Max over the last 28 days
    vo2max_window_start = target - timedelta(days=28)
    cycling_vo2_values = []
    running_vo2_values = []
    
    for act in all_activities:
        t = parse_activity_time(act)
        if t and vo2max_window_start <= t.date() <= target:
            vo2 = act.get("estimated_vo2max")
            if vo2:
                sport_type = act.get("sport_type") or act.get("type") or ""
                if sport_type in ("Ride", "VirtualRide", "MountainBikeRide", "Cycling"):
                    cycling_vo2_values.append(vo2)
                elif sport_type in ("Run", "TrailRun", "running"):
                    running_vo2_values.append(vo2)
                    
    def calc_median(lst):
        if not lst: return None
        s = sorted(lst)
        m = len(s) // 2
        if len(s) % 2 == 0:
            return (s[m-1] + s[m]) / 2.0
        return s[m]
        
    est_cycling_vo2max = calc_median(cycling_vo2_values)
    est_running_vo2max = calc_median(running_vo2_values)
    all_vo2_values = cycling_vo2_values + running_vo2_values
    est_combined_vo2max = calc_median(all_vo2_values)
    
    if est_combined_vo2max:
        est_fitness_age_combined = int(round(110 - (1.6 * est_combined_vo2max)))
        print(f"    Estimated Combined VO2Max: {est_combined_vo2max:.1f} (Running: {est_running_vo2max or 'n/a'}, Cycling: {est_cycling_vo2max or 'n/a'})")
        print(f"    Estimated Combined Fitness Age: {est_fitness_age_combined}")
    else:
        est_fitness_age_combined = None

    # Enrich garmin_data.json
    if garmin_report:
        ts = garmin_report.get("metrics", {}).get("trainingStatus", {})
        ts["acwr_combined"] = acwr_result["acwr"]
        ts["acuteEWMA_combined"] = acwr_result["acuteEWMA"]
        ts["chronicEWMA_combined"] = acwr_result["chronicEWMA"]
        ts["weeklyLoadTrimp_combined"] = acwr_result["weeklyLoadTrimp"]
        ts["stravaCyclingIncluded"] = any(
            a.get("source") == "strava" and a.get("sport") in ("Ride", "VirtualRide", "MountainBikeRide", "Cycling")
            for a in recent_activities
        )
        ts["estimated_vo2max_combined"] = round(est_combined_vo2max, 1) if est_combined_vo2max else None
        ts["estimated_cycling_vo2max"] = round(est_cycling_vo2max, 1) if est_cycling_vo2max else None
        ts["estimated_running_vo2max"] = round(est_running_vo2max, 1) if est_running_vo2max else None
        ts["estimated_fitness_age_combined"] = est_fitness_age_combined
        ts["recentActivities"] = recent_activities
        ts["loadCalculationParams"] = {
            "maxHR": MAX_HR,
            "restingHR": RESTING_HR,
            "cyclingFTP": CYCLING_FTP,
            "acuteDays": ACUTE_DAYS,
            "chronicDays": CHRONIC_DAYS,
        }
        
        garmin_report["metrics"]["trainingStatus"] = ts
        
        # Inject Race Predictions if missing or previously calculated
        race_preds = garmin_report["metrics"].get("racePredictions", {})
        if "5k" not in race_preds or not race_preds.get("5k", {}).get("seconds") or race_preds.get("calculated_from_vo2"):
            vo2_for_pred = est_combined_vo2max or ts.get("vo2Max")
            if vo2_for_pred:
                garmin_report["metrics"]["racePredictions"] = calculate_race_predictions_from_vo2(vo2_for_pred, penalty=RUNNING_ECONOMY_PENALTY)
        
        with open(args.garmin_data, "w") as f:
            json.dump(garmin_report, f, indent=2, ensure_ascii=False)
        print(f"\n  Enriched {args.garmin_data} with combined training load data.")
    else:
        print(f"\n  Warning: {args.garmin_data} not found. Skipping enrichment.", file=sys.stderr)


if __name__ == "__main__":
    main()
