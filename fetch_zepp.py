#!/usr/bin/env python3
"""
fetch_zepp.py

Comprehensive data collection script for Zepp Cloud API (Amazfit / Huami).
Reverse-engineered from official Zepp mobile app API endpoints.

Fetches ALL available metrics exposed by Zepp Cloud API:
  - Granular HRV RMSSD & SDNN time-series samples
  - Daily VFC (RMSSD) calculated per sleep session (reproducing Zepp app numbers: mean, min, max, exact count)
  - Heart Rate samples & resting HR
  - Training Load (SPORT_LOAD) & VO2 Max
  - Sleep sessions & band sync payloads
  - Readiness score & Daily Health summaries
  - Body Battery (Charge real_data) & Stress
  - SpO2 (Blood oxygen) & PAI Health Info
  - Respiratory Rate & Emotion & Lactate Threshold
  - Weight records & Workouts history (run, walking, ride, swimming)
  - User profile & Blood Pressure

Requires ZEPP_APP_TOKEN and ZEPP_USER_ID configured in .env.
"""

import argparse
import base64
import json
import os
import sys
import uuid
import requests
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

# Fuso horário local — Aracaju/SE, Brasil (GMT-3)
LOCAL_TZ = ZoneInfo("America/Maceio")

ZEPP_APP_TOKEN = os.getenv("ZEPP_APP_TOKEN")
ZEPP_USER_ID = os.getenv("ZEPP_USER_ID")
ZEPP_HOST = os.getenv("ZEPP_HOST", "api-mifit-us3.zepp.com")

HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")
HOME_ASSISTANT_URL = os.getenv("HOME_ASSISTANT_URL")


def _parse_iso_timestamp(ts_str):
    """Parse an ISO-8601 timestamp string into a timezone-aware UTC datetime."""
    if not ts_str:
        return None
    ts_str = str(ts_str).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def extract_item_datetime(item: dict) -> datetime | None:
    """Extract UTC datetime from an API response item handling epoch ms, epoch s, or ISO str."""
    if not isinstance(item, dict):
        return None
    for k in ("time", "timestamp", "startTime", "start_time", "date", "createTime", "last_changed", "date_time"):
        raw = item.get(k)
        if raw is not None:
            if isinstance(raw, (int, float)):
                if raw > 1e11:  # ms
                    return datetime.fromtimestamp(raw / 1000.0, tz=timezone.utc)
                elif raw > 1e8:  # s
                    return datetime.fromtimestamp(raw, tz=timezone.utc)
            elif isinstance(raw, str):
                if raw.isdigit():
                    val = float(raw)
                    if val > 1e11:
                        return datetime.fromtimestamp(val / 1000.0, tz=timezone.utc)
                    elif val > 1e8:
                        return datetime.fromtimestamp(val, tz=timezone.utc)
                dt = _parse_iso_timestamp(raw)
                if dt:
                    return dt
    return None


def extract_numeric_value(val_raw, preferred_keys=("rmssd", "val", "value", "score", "hrv", "sdnn", "rate", "spo2", "stress", "data", "wtlSum", "currnetDayTrainLoad", "skinTempCalibrated")) -> float | None:
    """Extract float numeric value from scalar, string, dictionary, or nested dict."""
    if val_raw is None:
        return None
    if isinstance(val_raw, (int, float)):
        return float(val_raw)
    if isinstance(val_raw, str):
        try:
            return float(val_raw)
        except ValueError:
            pass
    if isinstance(val_raw, dict):
        for k in preferred_keys:
            if k in val_raw and val_raw[k] is not None:
                sub_v = extract_numeric_value(val_raw[k], preferred_keys)
                if sub_v is not None:
                    return sub_v
        for v in val_raw.values():
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v)
                except ValueError:
                    pass
    return None


ZEPP_TOKEN_CACHE_FILE = ".zepp_tokens.json"


class ZeppAPIClient:
    """Comprehensive client for Zepp (Huami) Cloud API endpoints."""

    def __init__(self, apptoken: str, user_id: str, host: str = "api-mifit-us3.zepp.com"):
        self.apptoken = apptoken.strip() if apptoken else ""
        self.user_id = str(user_id).strip() if user_id else ""
        self.host = host.strip() if host else "api-mifit-us3.zepp.com"
        self.base_url = f"https://{self.host}"
        self.session = requests.Session()
        self.session.headers.update({
            "apptoken": self.apptoken,
            "appname": "com.huami.midong",
            "appplatform": "ios_phone",
            "v": "2.0",
            "user-agent": "Zepp/10.2.5 (iPhone; iOS 26.3.1; Scale/3.00)",
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br",
            "timezone": "UTC",
            "lang": "en",
        })
        self._retried_401 = False

    def _get_json(self, path: str, params: dict) -> list | dict | None:
        q = {"r": str(uuid.uuid4()).upper(), **params}
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.get(url, params=q, timeout=20)
            if resp.status_code == 401:
                if not self._retried_401:
                    self._retried_401 = True
                    old_uid = self.user_id
                    print(f"Aviso Zepp API: Token expirou (HTTP 401) em {path}. Renovando autenticação...", file=sys.stderr)
                    new_token, new_uid = obtain_zepp_credentials(force_refresh=True)
                    if new_token and new_uid:
                        self.apptoken = new_token
                        self.user_id = new_uid
                        self.session.headers["apptoken"] = new_token
                        
                        # Atualiza URL caso o user_id tenha mudado
                        if old_uid and old_uid != new_uid:
                            url = url.replace(old_uid, new_uid)

                        # Executa o RETRY imediatamente da requisição que havia falhado
                        q["r"] = str(uuid.uuid4()).upper()
                        retry_resp = self.session.get(url, params=q, timeout=20)
                        if retry_resp.ok:
                            return retry_resp.json()
                print(f"Aviso Zepp API: Token não aceito (HTTP 401) em {path}.", file=sys.stderr)
                return None
            elif resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Erro ao consultar Zepp API ({path}): {e}", file=sys.stderr)
            return None

    # 1. Watch events stream (/v2/users/me/events)
    def get_watch_events(self, event_type: str, sub_type: str, start_dt: datetime, end_dt: datetime, limit: int = 2000) -> list[dict]:
        res = self._get_json("/v2/users/me/events", {
            "eventType": event_type,
            "subType": sub_type,
            "from": int(start_dt.timestamp() * 1000),
            "to": int(end_dt.timestamp() * 1000),
            "limit": limit,
            "reverse": 0,
        })
        if not res:
            return []
        items = res.get("items") or res.get("data") if isinstance(res, dict) else res
        return items if isinstance(items, list) else []

    # 2. User events timeline (/users/{id}/events)
    def get_user_events(self, event_type: str, start_dt: datetime, end_dt: datetime, sub_type: str | None = None, limit: int = 2000) -> list[dict]:
        params = {
            "eventType": event_type,
            "from": int(start_dt.timestamp() * 1000),
            "to": int(end_dt.timestamp() * 1000),
            "limit": limit,
            "reverse": 0,
            "userId": self.user_id,
        }
        if sub_type:
            params["subType"] = sub_type
        res = self._get_json(f"/users/{self.user_id}/events", params)
        if not res:
            return []
        items = res.get("items") or res.get("data") if isinstance(res, dict) else res
        return items if isinstance(items, list) else []

    # 3. User events ISO date range (/users/{id}/events/dateString)
    def get_user_events_day(self, event_type: str, sub_type: str, start_dt: datetime, end_dt: datetime, limit: int = 999) -> list[dict]:
        res = self._get_json(f"/users/{self.user_id}/events/dateString", {
            "eventType": event_type,
            "subType": sub_type,
            "from": start_dt.strftime("%Y-%m-%dT00:00:00"),
            "to": end_dt.strftime("%Y-%m-%dT23:59:59"),
            "timeZone": "UTC",
            "limit": limit,
            "reverse": 0,
            "userId": self.user_id,
        })
        if not res:
            return []
        items = res.get("items") or res.get("data") if isinstance(res, dict) else res
        return items if isinstance(items, list) else []

    # 4. Heart rate (/users/{id}/heartRate)
    def get_heart_rate(self, start_dt: datetime, end_dt: datetime, limit: int = 1000) -> list[dict]:
        res = self._get_json(f"/users/{self.user_id}/heartRate", {
            "startTime": int(start_dt.timestamp()),
            "endTime": int(end_dt.timestamp()),
            "limit": limit,
            "type": 2,
        })
        if not res:
            return []
        items = res.get("items") if isinstance(res, dict) else res
        return items if isinstance(items, list) else []

    # 5. Training load (SPORT_LOAD)
    def get_sport_load(self, start_date: date, end_date: date) -> list[dict]:
        res = self._get_json(f"/v2/watch/users/{self.user_id}/WatchSportStatistics/SPORT_LOAD", {
            "startDay": start_date.isoformat(),
            "endDay": end_date.isoformat(),
            "limit": 900,
            "isReverse": "true",
        })
        if not res:
            return []
        items = res.get("items") if isinstance(res, dict) else res
        return items if isinstance(items, list) else []

    # 6. VO2 Max
    def get_vo2_max(self, start_date: date, end_date: date) -> list[dict]:
        res = self._get_json(f"/v2/watch/users/{self.user_id}/WatchSportStatistics/VO2_MAX", {
            "startDay": start_date.isoformat(),
            "endDay": end_date.isoformat(),
            "limit": 900,
            "isReverse": "true",
        })
        if not res:
            return []
        items = res.get("items") if isinstance(res, dict) else res
        return items if isinstance(items, list) else []

    # 7. Weight records
    def get_weight_records(self, start_dt: datetime, end_dt: datetime, limit: int = 300) -> list[dict]:
        res = self._get_json(f"/users/{self.user_id}/members/-1/weightRecords", {
            "fromTime": int(start_dt.timestamp()),
            "toTime": int(end_dt.timestamp()),
            "limit": limit,
            "isForward": 0,
        })
        if not res:
            return []
        items = res.get("items") or res.get("weightRecords") if isinstance(res, dict) else res
        return items if isinstance(items, list) else []

    # 8. Workouts history
    def get_sport_history(self, sport: str = "run") -> list[dict]:
        res = self._get_json(f"/v1/sport/{sport}/history.json", {
            "userid": self.user_id,
            "startTrackId": 0,
            "stopTrackId": 0,
            "need_sub_data": 1,
            "type": "",
        })
        if not res:
            return []
        items = res.get("data", {}).get("history") if isinstance(res, dict) and isinstance(res.get("data"), dict) else res.get("items") if isinstance(res, dict) else []
        return items if isinstance(items, list) else []

    # 9. Band data (/v1/data/band_data.json)
    def get_band_data(self, start_date: date, end_date: date) -> list[dict]:
        res = self._get_json("/v1/data/band_data.json", {
            "userid": self.user_id,
            "from_date": start_date.isoformat(),
            "to_date": end_date.isoformat(),
            "query_type": "detail",
            "byteLength": 8,
            "device_type": 0,
        })
        if not res:
            return []
        items = res.get("data") or res.get("items") if isinstance(res, dict) else res
        return items if isinstance(items, list) else []

    # 10. Manual data (/v1/user/manualData.json)
    def get_manual_data(self, manual_type: str = "sleep") -> list[dict]:
        res = self._get_json("/v1/user/manualData.json", {
            "userid": self.user_id,
            "type": manual_type,
        })
        if not res:
            return []
        items = res.get("data") or res.get("items") if isinstance(res, dict) else res
        return items if isinstance(items, list) else []

    # 11. User info
    def get_user_info(self) -> dict:
        res = self._get_json("/huami.health.getUserInfo.json", {
            "userid": self.user_id,
        })
        return res if isinstance(res, dict) else {}

    # 12. Blood pressure
    def get_blood_pressure(self, days: int = 7) -> list[dict]:
        td = datetime.now(timezone.utc).date().isoformat()
        res = self._get_json("/users/me/bloodPressure", {
            "days": days,
            "sourceArrayStr": "com.huami.midong.associated,com.huami.midong",
            "toDate": td,
        })
        if not res:
            return []
        items = res.get("items") or res.get("data") if isinstance(res, dict) else res
        return items if isinstance(items, list) else []


def parse_blood_pressure_events(events_bp: list[dict]) -> tuple[list[dict], dict | None]:
    """
    Parse blood pressure events (both manual additions and automatic measurements) into GMT-3 formatted records.
    Returns (records_list, latest_record).
    """
    if not events_bp or not isinstance(events_bp, list):
        return [], None

    records = []
    for ev in events_bp:
        val = ev.get("value", {}) if isinstance(ev, dict) else {}
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                val = {}

        ms = val.get("measureTime") or ev.get("timestamp")
        sbp = val.get("sbp")
        dbp = val.get("dbp")

        if ms and sbp and dbp:
            try:
                dt_utc = datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
                dt_local = dt_utc.astimezone(LOCAL_TZ)
                records.append({
                    "date": dt_local.date().isoformat(),
                    "time": dt_local.strftime("%H:%M:%S"),
                    "timestampIso": dt_local.isoformat(),
                    "systolic": int(sbp),
                    "diastolic": int(dbp),
                    "formatted": f"{int(sbp)}/{int(dbp)} mmHg",
                    "subType": ev.get("subType", "manually_add_data")
                })
            except Exception:
                pass

    records.sort(key=lambda r: r["timestampIso"])
    latest = records[-1] if records else None
    return records, latest


def parse_band_data_sleep_scores(band_payload: list[dict]) -> dict[str, dict]:
    """
    Decode Base64 encoded summary blobs from /v1/data/band_data.json and extract sleep scores & breakdown per date.
    Returns a dictionary keyed by date string (YYYY-MM-DD).
    """
    scores_by_date = {}
    if not band_payload or not isinstance(band_payload, list):
        return scores_by_date

    for item in band_payload:
        if not isinstance(item, dict):
            continue
        summary_b64 = item.get("summary")
        if not summary_b64:
            continue
        try:
            summary_dict = json.loads(base64.b64decode(summary_b64).decode("utf-8"))
            slp = summary_dict.get("slp", {})
            if not isinstance(slp, dict):
                continue
            
            sleep_score = slp.get("ss")
            rhr = slp.get("rhr")
            st = slp.get("st")
            ed = slp.get("ed")
            
            dt_start_local = (
                datetime.fromtimestamp(st, tz=timezone.utc).astimezone(LOCAL_TZ)
                if st else None
            )
            dt_end_local = (
                datetime.fromtimestamp(ed, tz=timezone.utc).astimezone(LOCAL_TZ)
                if ed else None
            )
            date_key = dt_end_local.date().isoformat() if dt_end_local else item.get("date_time")

            dp_min = int(slp.get("dp", 0)) if slp.get("dp") else 0
            lt_min = int(slp.get("lt", 0)) if slp.get("lt") else 0
            rem_min = int(slp.get("dt", 0)) if slp.get("dt") else 0
            wk_min = int(slp.get("wk", 0)) if slp.get("wk") else 0

            # Calculate actual sleep duration (deep + light + REM)
            if dp_min or lt_min or rem_min:
                duration_min = float(dp_min + lt_min + rem_min)
            elif st and ed:
                duration_min = max(0.0, (ed - st) / 60.0 - wk_min)
            else:
                duration_min = 0.0

            h = int(duration_min // 60)
            m = int(duration_min % 60)
            dur_fmt = f"{h:02d}:{m:02d}"

            if date_key and (sleep_score is not None or duration_min > 0):
                scores_by_date[date_key] = {
                    "sleepScore": int(sleep_score) if isinstance(sleep_score, (int, float)) else None,
                    "deepSleepMinutes": dp_min,
                    "lightSleepMinutes": lt_min,
                    "remSleepMinutes": rem_min,
                    "awakeMinutes": wk_min,
                    "durationMinutes": round(duration_min, 1),
                    "durationFormatted": dur_fmt,
                    "sleepStart": dt_start_local.isoformat() if dt_start_local else None,
                    "sleepEnd": dt_end_local.isoformat() if dt_end_local else None,
                    "restingHeartRate": int(rhr) if rhr else None,
                }
        except Exception:
            pass

    return scores_by_date


def parse_vfc_diaria_zepp_events(raw_events_hrv: list[dict]) -> list[dict]:
    """
    Parse daily VFC (RMSSD) directly from Zepp HRVRMSSD event blocks and sample arrays.
    Reproduces exact numbers shown in Zepp app (mean, min, max, sample count, GMT-3 wake date).
    """
    resultados = []

    for ev in raw_events_hrv:
        val = ev.get("value")
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                pass

        if not isinstance(val, dict):
            continue

        start_ms = val.get("startTime") or ev.get("timestamp")
        samples = val.get("samples") or []

        if not start_ms or not isinstance(samples, list) or len(samples) == 0:
            continue

        # Extract all RMSSD values from samples array
        hrv_vals = []
        max_offset_ms = 0
        for s in samples:
            if isinstance(s, dict):
                h_val = s.get("hrv") or s.get("val") or s.get("rmssd")
                offset_ms = s.get("s", 0)
                if offset_ms > max_offset_ms:
                    max_offset_ms = offset_ms
                if h_val is not None and isinstance(h_val, (int, float)) and h_val > 0:
                    hrv_vals.append(float(h_val))

        if not hrv_vals:
            continue

        sleep_start_utc = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc)
        sleep_end_utc = datetime.fromtimestamp((start_ms + max_offset_ms) / 1000.0, tz=timezone.utc)

        sleep_start_local = sleep_start_utc.astimezone(LOCAL_TZ)
        sleep_end_local = sleep_end_utc.astimezone(LOCAL_TZ)

        # Wake-up date in GMT-3
        data_atribuida = sleep_end_local.date().isoformat()

        media = sum(hrv_vals) / len(hrv_vals)
        valor_arredondado = round(media)

        resultados.append({
            "date": data_atribuida,
            "sleepStart": sleep_start_local.isoformat(),
            "sleepEnd": sleep_end_local.isoformat(),
            "readingCount": len(hrv_vals),
            "min": float(min(hrv_vals)),
            "max": float(max(hrv_vals)),
            "mean": round(media, 2),
            "roundedValue": valor_arredondado,
        })

    # Deduplicate results by date (keep most complete block per date)
    by_date = {}
    for r in resultados:
        d = r["date"]
        if d not in by_date or r["readingCount"] > by_date[d]["readingCount"]:
            by_date[d] = r

    final_results = list(by_date.values())
    final_results.sort(key=lambda r: r["date"])
    return final_results


def save_cached_zepp_tokens(app_token: str, user_id: str):
    """Salva os tokens do Zepp no arquivo de cache .zepp_tokens.json."""
    data = {
        "app_token": app_token,
        "user_id": user_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    try:
        with open(ZEPP_TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Aviso: Não foi possível salvar o cache de tokens Zepp em {ZEPP_TOKEN_CACHE_FILE}: {e}", file=sys.stderr)


def obtain_zepp_credentials(force_refresh: bool = False) -> tuple[str, str]:
    """
    Obtém app_token e user_id para autenticação na API do Zepp.
    1. Se force_refresh == False, verifica se existe token válido salvo em .zepp_tokens.json.
    2. Se não houver cache ou se force_refresh == True (e.g. 401), realiza autenticação via huami_token,
       salva o novo token no cache e o retorna.
    """
    # 1. Tentar ler do cache local se não for um refresh forçado
    if not force_refresh and os.path.exists(ZEPP_TOKEN_CACHE_FILE):
        try:
            with open(ZEPP_TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            cached_token = cache.get("app_token")
            cached_uid = cache.get("user_id")
            if cached_token and cached_uid:
                print(f"Usando app_token do Zepp salvo em cache ({ZEPP_TOKEN_CACHE_FILE}).")
                return str(cached_token), str(cached_uid)
        except Exception as e:
            print(f"Aviso: Erro ao ler cache de tokens {ZEPP_TOKEN_CACHE_FILE}: {e}", file=sys.stderr)

    # 2. Se force_refresh ou sem cache, autenticar via ZEPP_EMAIL e ZEPP_PASSWORD
    app_token = os.getenv("ZEPP_APP_TOKEN")
    user_id = os.getenv("ZEPP_USER_ID")
    email = os.getenv("ZEPP_EMAIL")
    password = os.getenv("ZEPP_PASSWORD")

    if email and password:
        print(f"Autenticando na plataforma Zepp ({email}) via huami_token...")
        try:
            from huami_token.zepp import ZeppSession
            session = ZeppSession(username=email, password=password)
            session.login()
            if session.app_token and session.user_id:
                print(f"Login Zepp realizado com sucesso! User ID: {session.user_id}")
                t_str, u_str = str(session.app_token), str(session.user_id)
                save_cached_zepp_tokens(t_str, u_str)
                return t_str, u_str
        except Exception as e:
            print(f"Aviso: Falha na autenticação via biblioteca Python (huami_token): {e}. Tentando CLI...", file=sys.stderr)

        try:
            import subprocess
            cmd = ["huami-token", "-m", "amazfit", "-e", email, "-p", password, "-n"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
            token_found, uid_found = None, None
            for line in res.stdout.splitlines():
                if "app_token=" in line:
                    token_found = line.split("app_token=")[1].strip()
                if "User id:" in line:
                    uid_found = line.split("User id:")[1].strip()
            if token_found and uid_found:
                print(f"Login Zepp via CLI realizado com sucesso! User ID: {uid_found}")
                save_cached_zepp_tokens(token_found, uid_found)
                return token_found, uid_found
        except Exception as e:
            print(f"Erro ao executar CLI huami-token: {e}", file=sys.stderr)

    if app_token and user_id and app_token != "your_zepp_app_token":
        save_cached_zepp_tokens(app_token, user_id)
        return app_token, user_id

    print("Erro: ZEPP_EMAIL e ZEPP_PASSWORD (ou ZEPP_APP_TOKEN/ZEPP_USER_ID) precisam estar configurados no .env.", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Coletar TODAS as métricas disponíveis da API Cloud do Zepp.")
    parser.add_argument("--output", type=str, default="zepp_data.json", help="Caminho do arquivo JSON de saída")
    parser.add_argument("--days", type=int, default=7, help="Número de dias de histórico a buscar (default: 7)")
    args = parser.parse_args()

    app_token, user_id = obtain_zepp_credentials()

    print(f"Coletando dados completos da API Cloud do Zepp ({ZEPP_HOST}) para os últimos {args.days} dias...")
    client = ZeppAPIClient(app_token, user_id, ZEPP_HOST)

    agora = datetime.now(timezone.utc)
    inicio = agora - timedelta(days=args.days)
    inicio_date = inicio.date()
    agora_date = agora.date()

    # ── Coleta de todos os endpoints da API Zepp ──
    print("  -> Coletando eventos (HRV RMSSD, SDNN, Readiness, Body Battery, Estresse, Resp, etc.)...")
    events_hrv_rmssd = client.get_watch_events("HRVRMSSD", "real_data", inicio, agora)
    events_hrv_sdnn = client.get_watch_events("hrv_sdnn", "real_data", inicio, agora)
    events_readiness = client.get_watch_events("readiness", "watch_score", inicio, agora)
    events_daily_health = client.get_watch_events("DailyHealth", "summary", inicio, agora)
    events_body_battery = client.get_watch_events("Charge", "real_data", inicio, agora)
    events_stress = client.get_watch_events("Charge", "stress_data", inicio, agora)
    events_respiratory = client.get_watch_events("RespiratoryRate", "real_data", inicio, agora)
    events_blood_pressure = client.get_watch_events("blood_pressure", None, inicio, agora)
    events_emotion = client.get_watch_events("Emotion", "real_data", inicio, agora)
    events_lactate = client.get_watch_events("LactateThreshold", "summary", inicio, agora)

    print("  -> Coletando linha do tempo do usuário (All-day Stress, PAI, SpO2)...")
    user_all_day_stress = client.get_user_events("all_day_stress", inicio, agora)
    user_pai = client.get_user_events("PaiHealthInfo", inicio, agora)
    user_spo2 = client.get_user_events("blood_oxygen", inicio, agora, sub_type="click")
    user_spo2_odi = client.get_user_events_day("blood_oxygen", "odi", inicio, agora)
    user_spo2_osa = client.get_user_events_day("blood_oxygen", "osa_event", inicio, agora)

    print("  -> Coletando frequência cardíaca, carga de treino, VO2 Max e peso...")
    heart_rate_data = client.get_heart_rate(inicio, agora)
    sport_load_data = client.get_sport_load(inicio_date, agora_date)
    vo2_max_data = client.get_vo2_max(inicio_date, agora_date)
    weight_data = client.get_weight_records(inicio, agora)

    print("  -> Coletando dados de treino, sono e perfil do usuário...")
    workouts_run = client.get_sport_history("run")
    band_payload = client.get_band_data(inicio_date, agora_date)
    manual_sleep = client.get_manual_data("sleep")
    user_info = client.get_user_info()
    blood_pressure_logs = client.get_blood_pressure(days=args.days)

    # ── Parse do VFC Diário, Pressão Arterial e Notas do Sono ──
    vfc_resultados = parse_vfc_diaria_zepp_events(events_hrv_rmssd)
    bp_records, latest_bp = parse_blood_pressure_events(events_blood_pressure)
    sleep_scores_map = parse_band_data_sleep_scores(band_payload)

    # Merge sleepScore into vfcDiaria entries
    for r in vfc_resultados:
        sc_info = sleep_scores_map.get(r["date"])
        if sc_info:
            r["sleepScore"] = sc_info.get("sleepScore")

    # Extração das métricas mais recentes para o objeto cardiovascular e sono
    latest_hrv = vfc_resultados[-1]["roundedValue"] if vfc_resultados else None
    latest_hrv_date = vfc_resultados[-1]["date"] if vfc_resultados else None

    latest_sleep_rhr = None
    if events_readiness and isinstance(events_readiness, list):
        for ev in sorted(events_readiness, key=lambda x: x.get("timestamp", 0)):
            val = ev.get("value", {})
            if isinstance(val, dict) and val.get("sleepRHR"):
                latest_sleep_rhr = int(val.get("sleepRHR"))

    latest_hr = None
    if heart_rate_data and isinstance(heart_rate_data, list):
        for hr_item in reversed(heart_rate_data):
            if isinstance(hr_item, dict) and hr_item.get("heartRate"):
                latest_hr = float(hr_item["heartRate"])
                break

    sleep_summary = {}
    target_date = vfc_resultados[-1]["date"] if vfc_resultados else agora_date.isoformat()
    latest_sc = sleep_scores_map.get(target_date) or (list(sleep_scores_map.values())[-1] if sleep_scores_map else {})

    ultimo_vfc = vfc_resultados[-1] if vfc_resultados else {}

    sleep_start = latest_sc.get("sleepStart") or ultimo_vfc.get("sleepStart")
    sleep_end = latest_sc.get("sleepEnd") or ultimo_vfc.get("sleepEnd")
    dur_min = latest_sc.get("durationMinutes")

    if dur_min is None and sleep_start and sleep_end:
        try:
            s_dt = _parse_iso_timestamp(sleep_start)
            e_dt = _parse_iso_timestamp(sleep_end)
            dur_min = (e_dt - s_dt).total_seconds() / 60.0 if s_dt and e_dt else 0.0
        except Exception:
            dur_min = 0.0

    if dur_min is not None and dur_min > 0:
        h = int(dur_min // 60)
        m = int(dur_min % 60)
        dur_fmt = f"{h:02d}:{m:02d}"
    else:
        dur_min = 0.0
        dur_fmt = "n/a"

    sleep_summary = {
        "date": target_date,
        "sleepScore": latest_sc.get("sleepScore"),
        "deepSleepMinutes": latest_sc.get("deepSleepMinutes"),
        "lightSleepMinutes": latest_sc.get("lightSleepMinutes"),
        "remSleepMinutes": latest_sc.get("remSleepMinutes"),
        "awakeMinutes": latest_sc.get("awakeMinutes"),
        "sleepStart": sleep_start,
        "sleepEnd": sleep_end,
        "durationMinutes": round(dur_min, 1) if dur_min else None,
        "durationFormatted": dur_fmt,
        "restingHeartRate": latest_sleep_rhr or latest_sc.get("restingHeartRate"),
        "readingCount": ultimo_vfc.get("readingCount"),
        "source": "Zepp Cloud API (Amazfit Helio Strap)"
    }

    output_data = {
        "source": "Zepp Cloud API (Amazfit Helio Strap)",
        "fetchedAt": agora.isoformat(),
        "userProfile": user_info,
        "cardiovascular": {
            "heartRate": latest_hr,
            "restingHeartRate": latest_sleep_rhr,
            "bloodPressure": latest_bp["formatted"] if latest_bp else None,
            "bloodPressureDetails": latest_bp,
            "heartRateVariability": latest_hrv,
            "heartRateVariabilitySource": "Zepp Cloud API RMSSD samples mean",
            "heartRateVariabilityDate": latest_hrv_date,
            "heartRateSamplesCount": len(heart_rate_data) if isinstance(heart_rate_data, list) else 0
        },
        "sleep": sleep_summary,
        "vfcDiaria": vfc_resultados,
        "trainingLoad": sport_load_data,
        "vo2Max": vo2_max_data,
        "weightRecords": weight_data,
        "workouts": {
            "run": workouts_run,
        },
        "readiness": events_readiness,
        "dailyHealth": events_daily_health,
        "bodyBattery": events_body_battery,
        "stress": events_stress,
        "allDayStress": user_all_day_stress,
        "respiratoryRate": events_respiratory,
        "spO2": {
            "clicks": user_spo2,
            "odi": user_spo2_odi,
            "osa": user_spo2_osa,
        },
        "pai": user_pai,
        "bloodPressure": {
            "latest": latest_bp,
            "records": bp_records,
            "logs": blood_pressure_logs,
            "rawEvents": events_blood_pressure,
        },
        "emotion": events_emotion,
        "lactateThreshold": events_lactate,
        "sleepData": {
            "manualSessions": manual_sleep,
            "bandPayload": band_payload,
        },
        "rawEvents": {
            "hrvRmssd": events_hrv_rmssd,
            "hrvSdnn": events_hrv_sdnn,
        }
    }

    if vfc_resultados:
        print(f"\nVFC diária por sessão de sono — últimos {args.days} dias (horários em GMT-3):")
        print(f"{'Data':<12} {'Início (BRT)':>20} {'Fim (BRT)':>20} {'Leituras':>9} {'Mín':>5} {'Máx':>5} {'Média':>7} {'VFC':>4}")
        print("-" * 95)
        for r in vfc_resultados:
            s_fmt = r["sleepStart"][:19].replace("T", " ")
            e_fmt = r["sleepEnd"][:19].replace("T", " ")
            print(f"{r['date']:<12} {s_fmt:>20} {e_fmt:>20} {r['readingCount']:>9} {r['min']:>5.0f} {r['max']:>5.0f} {r['mean']:>7.2f} {r['roundedValue']:>4}")

    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"\nSucesso! Todas as métricas da API Zepp salvos em: {args.output}")
    except Exception as e:
        print(f"Erro ao salvar JSON de saída: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
