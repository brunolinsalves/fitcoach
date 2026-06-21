import sys
import os
import datetime
import urllib.request
import re
from pathlib import Path
from dotenv import load_dotenv

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

# Sport type mapping to Portuguese translations and icons
SPORT_MAPPING = {
    "running": "🏃 Corrida",
    "cycling": "🚴 Ciclismo",
    "swimming": "🏊 Natação",
    "fitness_equipment": "💪 Musculação / Funcional",
    "walking": "🚶 Caminhada",
    "hiking": "🥾 Trilha",
}

def format_date_br(date_str):
    """Format date string YYYY-MM-DD to DD/MM (Day of week) in Portuguese."""
    try:
        dt = datetime.date.fromisoformat(date_str)
        weekdays = {
            0: "Segunda-feira",
            1: "Terça-feira",
            2: "Quarta-feira",
            3: "Quinta-feira",
            4: "Sexta-feira",
            5: "Sábado",
            6: "Domingo"
        }
        return f"{dt.day:02d}/{dt.month:02d} ({weekdays[dt.weekday()]})"
    except Exception:
        return date_str

def format_duration(seconds):
    """Convert duration in seconds to a human-readable string."""
    if not seconds:
        return ""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
    return f"{minutes}m"

def format_distance(meters):
    """Convert distance in meters to a human-readable string in km."""
    if not meters:
        return ""
    km = meters / 1000.0
    return f"{km:.2f} km"

def init_api() -> Garmin:
    """Initialize Garmin API, utilizing local token cache to avoid rate limits."""
    tokenstore = os.getenv("GARMINTOKENS", ".garminconnect")
    tokenstore_path = str(Path(tokenstore).expanduser().resolve())
    os.makedirs(tokenstore_path, exist_ok=True)

    # Attempt login using stored tokens
    try:
        garmin = Garmin()
        garmin.login(tokenstore_path)
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

def fetch_future_workouts(api: Garmin):
    """Fetch all planned future workouts from the calendar for the next 12 months."""
    today = datetime.date.today()
    today_str = today.isoformat()
    
    calendar_items = []
    
    # Fetch current month and the next 11 months (total 12 months)
    print("Fetching calendar items from Garmin Connect...")
    for offset in range(12):
        month = today.month + offset
        year = today.year
        # Handle year overflow
        while month > 12:
            month -= 12
            year += 1
            
        print(f"  Fetching calendar for {year}-{month:02d}...")
        try:
            data = api.get_scheduled_workouts(year, month)
            if data and "calendarItems" in data:
                calendar_items.extend(data["calendarItems"])
        except Exception as e:
            print(f"  Warning: Failed to fetch calendar for {year}-{month:02d}: {e}", file=sys.stderr)

    # Deduplicate items by ID
    unique_items = {}
    for item in calendar_items:
        item_id = item.get("id")
        if item_id:
            unique_items[item_id] = item

    # Filter for future workouts
    future_workouts = []
    for item in unique_items.values():
        item_date = item.get("date")
        item_type = item.get("itemType")
        
        # We want items from today onwards that are planned (workout or event)
        if item_date and item_date >= today_str and item_type in ("workout", "event"):
            future_workouts.append(item)

    # Sort chronologically
    future_workouts.sort(key=lambda x: x.get("date", ""))
    return future_workouts

def fetch_workout_details(api: Garmin, workout_id: int):
    """Safely fetch workout details by ID."""
    try:
        return api.get_workout_by_id(workout_id)
    except Exception as e:
        print(f"  Warning: Could not fetch details for workout {workout_id}: {e}", file=sys.stderr)
        return None

def fetch_runna_workouts(url: str):
    """Fetch and parse future workouts from the Runna iCal feed."""
    try:
        print("Fetching Runna workouts from iCal feed...")
        # Add User-Agent to avoid getting blocked by WAF/Firewall
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            ics_text = response.read().decode('utf-8')
    except Exception as e:
        print(f"  Warning: Failed to fetch Runna iCal feed: {e}", file=sys.stderr)
        if "404" in str(e) or "401" in str(e):
            print("  -> Dica: Verifique se a sua agenda está configurada como 'Pública' ou use o 'Endereço Secreto no formato iCal' da agenda.", file=sys.stderr)
        return []

    # Unfold lines (iCal format folds lines with CRLF followed by a space/tab)
    unfolded = re.sub(r'\r?\n[ \t]', '', ics_text)
    
    events = []
    current_event = None
    today_str = datetime.date.today().isoformat()
    
    for line in unfolded.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("BEGIN:VEVENT"):
            current_event = {}
        elif line.startswith("END:VEVENT"):
            if current_event:
                events.append(current_event)
            current_event = None
        elif current_event is not None:
            if ":" in line:
                key_part, value = line.split(":", 1)
                key = key_part.split(";")[0].upper()
                current_event[key] = value
                
    runna_workouts = []
    for ev in events:
        summary = ev.get("SUMMARY", "Sem título")
        summary = summary.replace("\\,", ",").replace("\\;", ";").replace("\\n", "\n").replace("\\", "")
        
        description = ev.get("DESCRIPTION", "")
        description = description.replace("\\,", ",").replace("\\;", ";").replace("\\n", "\n").replace("\\", "")
        
        dtstart = ev.get("DTSTART", "")
        date_str = ""
        if len(dtstart) >= 8:
            date_str = f"{dtstart[0:4]}-{dtstart[4:6]}-{dtstart[6:8]}"
            
        if date_str and date_str >= today_str:
            # Infer sport type from title/description
            sport = "running"
            summary_lower = summary.lower()
            if any(word in summary_lower for word in ["força", "strength", "pilates", "musculação", "funcional"]):
                sport = "fitness_equipment"
            elif any(word in summary_lower for word in ["natação", "swim", "piscina"]):
                sport = "swimming"
            elif any(word in summary_lower for word in ["ciclismo", "bike", "pedal", "giro"]):
                sport = "cycling"
                
            # Attempt to parse distance/duration from description if available
            distance_meters = None
            duration_secs = None
            
            dist_match = re.search(r'(?:distancia|distância|distance):\s*([\d.,]+)\s*k?m', description, re.IGNORECASE)
            if dist_match:
                try:
                    dist_val = float(dist_match.group(1).replace(",", "."))
                    distance_meters = int(dist_val * 1000)
                except ValueError:
                    pass
            
            dur_match = re.search(r'(?:duracao|duração|duration):\s*([\d.,]+)\s*(?:min|m)', description, re.IGNORECASE)
            if dur_match:
                try:
                    dur_val = float(dur_match.group(1).replace(",", "."))
                    duration_secs = int(dur_val * 60)
                except ValueError:
                    pass
            
            runna_workouts.append({
                "id": ev.get("UID", f"runna-{date_str}-{summary}"),
                "date": date_str,
                "title": summary,
                "sportTypeKey": sport,
                "description": description,
                "duration": duration_secs,
                "distance": distance_meters,
                "is_runna": True
            })
            
    runna_workouts.sort(key=lambda x: x.get("date", ""))
    return runna_workouts

def merge_workouts(garmin_workouts, runna_workouts):
    """Merge Garmin and Runna workouts, deduplicating workouts on the same day with similar titles."""
    merged = []
    by_date = {}
    
    # Prioritize Runna workouts since they contain the full schedule and detailed descriptions
    for w in runna_workouts:
        date = w["date"]
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(w)
        
    # Add Garmin workouts if they do not duplicate Runna workouts
    for gw in garmin_workouts:
        date = gw["date"]
        is_duplicate = False
        
        if date in by_date:
            for rw in by_date[date]:
                # If they are both of the same sport type on the same day, they are likely duplicates
                # (since Runna is syncing a subset to Garmin Connect)
                if gw.get("sportTypeKey") == rw.get("sportTypeKey") or (gw.get("sportTypeKey") == "running" and rw.get("sportTypeKey") == "running"):
                    is_duplicate = True
                    break
                    
        if not is_duplicate:
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(gw)
            
    # Flatten and sort
    for date in by_date:
        by_date[date].sort(key=lambda x: x.get("title", ""))
        merged.extend(by_date[date])
        
    merged.sort(key=lambda x: x.get("date", ""))
    return merged

def generate_markdown(api, workouts, display_name, has_runna_url):
    """Generate a clean, professional markdown content for garmin_calendar.md."""
    today_str = datetime.date.today().isoformat()
    now_str = datetime.datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    
    md = []
    md.append(f"# 📅 Calendário de Atividades Garmin & Runna - {display_name}")
    md.append("")
    md.append(f"> [!NOTE]")
    md.append(f"> Gerado automaticamente em {now_str}. Contém todas as atividades futuras planejadas a partir de {format_date_br(today_str)} para os próximos 12 meses.")
    md.append("")
    
    if not has_runna_url:
        md.append("> [!IMPORTANT]")
        md.append("> **Planilha Completa do Runna Não Sincronizada!**")
        md.append("> Para obter todos os treinos do seu plano do Runna (de vários meses) e salvá-los aqui automaticamente:")
        md.append("> 1. Abra o aplicativo **Runna** no seu celular.")
        md.append("> 2. Acesse o seu **Perfil** (ícone no canto superior direito).")
        md.append("> 3. Vá em **Connected Apps & Watches** (ou *Connected Apps & Devices*).")
        md.append("> 4. Selecione **Connect Calendar** -> **Other Calendar** (Outro Calendário).")
        md.append("> 5. Copie a URL do Calendário (ex: `https://.../ical/...`).")
        md.append("> 6. Abra o arquivo `.env` do seu projeto e adicione a seguinte linha:")
        md.append(">    ```env")
        md.append(">    RUNNA_CALENDAR_URL=sua_url_do_runna_aqui")
        md.append(">    ```")
        md.append("> 7. Execute o script novamente para ver a planilha completa!")
        md.append("")
    else:
        md.append("> [!TIP]")
        md.append("> **Sincronização com o Runna Ativa!**")
        md.append("> O calendário abaixo foi integrado com a planilha completa do Runna via iCal. Os treinos que ainda não estão no Garmin Connect foram adicionados e mesclados automaticamente.")
        md.append("")

    if not workouts:
        md.append("Nenhuma atividade futura planejada encontrada no calendário.")
        return "\n".join(md)
        
    md.append("## 🏃 Resumo dos Treinos")
    md.append("")
    md.append("| Data | Título | Modalidade | Distância Estimada | Duração Estimada | Origem |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    
    details_section = []
    details_section.append("## 📝 Detalhes das Atividades")
    details_section.append("")

    for i, workout in enumerate(workouts):
        date_str = workout.get("date")
        title = workout.get("title", "Sem título")
        sport_raw = workout.get("sportTypeKey")
        sport = SPORT_MAPPING.get(sport_raw, sport_raw.capitalize() if sport_raw else "Outro")
        origin = "👟 Runna Plan" if workout.get("is_runna") else "⌚ Garmin Connect"
        
        # Details variables
        description = workout.get("description")
        duration = format_duration(workout.get("duration"))
        distance = format_distance(workout.get("distance"))
        
        workout_id = workout.get("workoutId")
        if workout_id and not workout.get("is_runna"):
            # Fetch rich details for Garmin Connect workouts
            details = fetch_workout_details(api, workout_id)
            if details:
                description = details.get("description")
                duration = format_duration(details.get("estimatedDurationInSecs"))
                distance = format_distance(details.get("estimatedDistanceInMeters"))
        
        # Clean up defaults
        duration_disp = duration if duration else "-"
        distance_disp = distance if distance else "-"
        
        # Add to summary table
        md.append(f"| {format_date_br(date_str)} | [{title}](#treino-{i+1}) | {sport} | {distance_disp} | {duration_disp} | {origin} |")
        
        # Add to details section
        details_section.append(f"### <a name='treino-{i+1}'></a>{i+1}. {title}")
        details_section.append(f"- **Data:** {format_date_br(date_str)} ({date_str})")
        details_section.append(f"- **Modalidade:** {sport}")
        details_section.append(f"- **Origem:** {origin}")
        if duration:
            details_section.append(f"- **Duração Estimada:** {duration}")
        if distance:
            details_section.append(f"- **Distância Estimada:** {distance}")
        details_section.append("")
        
        if description:
            details_section.append("#### Descrição / Estrutura do Treino:")
            details_section.append("```text")
            details_section.append(description.strip())
            details_section.append("```")
        else:
            details_section.append("*Sem descrição cadastrada.*")
        details_section.append("")
        details_section.append("---")
        details_section.append("")
        
    md.append("")
    md.extend(details_section)
    
    return "\n".join(md)

def main():
    print("Initializing Garmin & Runna Calendar script...")
    api = init_api()
    if not api:
        print("Error: Could not initialize Garmin client.", file=sys.stderr)
        sys.exit(1)
        
    display_name = api.display_name or "Usuário Garmin"
    
    # 1. Fetch Garmin Connect planned workouts
    garmin_workouts = fetch_future_workouts(api)
    print(f"Found {len(garmin_workouts)} future workouts in Garmin Connect.")
    
    # 2. Fetch Runna planned workouts if URL is configured
    runna_url = os.getenv("RUNNA_CALENDAR_URL")
    runna_workouts = []
    if runna_url:
        runna_workouts = fetch_runna_workouts(runna_url)
        print(f"Found {len(runna_workouts)} future workouts in Runna Calendar.")
    else:
        print("Warning: RUNNA_CALENDAR_URL is not configured in .env.")
        
    # 3. Merge and deduplicate
    combined_workouts = merge_workouts(garmin_workouts, runna_workouts)
    print(f"Merged total: {len(combined_workouts)} planned workouts.")
    
    # Generate Markdown
    md_content = generate_markdown(api, combined_workouts, display_name, has_runna_url=bool(runna_url))
    
    # Save to file
    output_path = "garmin_calendar.md"
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"Success! Calendar saved to {output_path}")
    except Exception as e:
        print(f"Error saving markdown file: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
