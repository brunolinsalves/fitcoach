#!/usr/bin/env python3
"""
generate_dashboard.py

Generates a static, dynamic, and modern HTML dashboard summarizing 
the Garmin/Strava training data and the AI Briefing.
"""

import json
import os
import re
from datetime import date

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Treino Dashboard | {date}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Inter', sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            min-height: 100vh;
            padding: 2rem;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
        }}

        .glass-panel {{
            background: #1e293b;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}

        .hero-briefing {{
            font-size: 1.1rem;
            line-height: 1.6;
        }}

        /* Metrics */
        .metric-card h3 {{
            font-size: 0.9rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
        }}

        .metric-value {{
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }}

        .metric-sub {{
            font-size: 0.85rem;
            color: #94a3b8;
        }}

        /* Dynamic Colors */
        .color-green {{ color: #10b981; }}
        .color-yellow {{ color: #f59e0b; }}
        .color-red {{ color: #ef4444; }}
        .color-gray {{ color: #94a3b8; }}
        .color-blue {{ color: #3b82f6; }}
        .color-purple {{ color: #8b5cf6; }}

        /* Gauge styles */
        .gauge-container {{
            margin-top: 1rem;
            margin-bottom: 1rem;
        }}
        
        .gauge-header {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 0.5rem;
        }}

        .gauge-value {{
            font-size: 2.2rem;
            font-weight: 700;
        }}

        .gauge-zone {{
            font-size: 0.8rem;
            font-weight: 600;
            padding: 0.2rem 0.6rem;
            border-radius: 6px;
        }}

        .zone-gray {{
            background: rgba(148, 163, 184, 0.15);
            color: #94a3b8;
            border: 1px solid rgba(148, 163, 184, 0.3);
        }}
        .zone-green {{
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}
        .zone-yellow {{
            background: rgba(245, 158, 11, 0.15);
            color: #f59e0b;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }}
        .zone-red {{
            background: rgba(239, 68, 68, 0.15);
            color: #ef4444;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }}
        .zone-blue {{
            background: rgba(59, 130, 246, 0.15);
            color: #3b82f6;
            border: 1px solid rgba(59, 130, 246, 0.3);
        }}
        .zone-purple {{
            background: rgba(139, 92, 246, 0.15);
            color: #8b5cf6;
            border: 1px solid rgba(139, 92, 246, 0.3);
        }}

        .gauge-bar-container {{
            position: relative;
            height: 10px;
            background: linear-gradient(to right, 
                #64748b 0%, #64748b 40%, 
                #10b981 40%, #10b981 65%, 
                #f59e0b 65%, #f59e0b 75%, 
                #ef4444 75%, #ef4444 100%
            );
            border-radius: 5px;
            margin-bottom: 0.5rem;
        }}

        .gauge-marker {{
            width: 8px;
            height: 18px;
            background-color: #ffffff;
            border-radius: 4px;
            box-shadow: 0 0 5px rgba(255,255,255,0.8);
            position: relative;
            top: -4px;
        }}

        /* Activities Section */
        .activities-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
        }}
        
        .activities-header h2 {{
            font-size: 1.5rem;
            color: #f8fafc;
        }}



        /* Table */
        .table-container {{
            overflow-x: auto;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }}

        th, td {{
            padding: 1rem;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}

        th {{
            font-size: 0.85rem;
            color: #94a3b8;
            text-transform: uppercase;
            font-weight: 600;
        }}

        tbody tr {{
            transition: background 0.2s ease;
        }}

        tbody tr:hover {{
            background: rgba(255,255,255,0.03);
        }}
        
        .source-badge {{
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: bold;
            text-transform: uppercase;
        }}
        
        .no-data {{
            text-align: center;
            padding: 2rem;
            color: #94a3b8;
        }}

        /* Responsive styling for mobile/email clients */
        @media (max-width: 600px) {{
            body {{ padding: 1rem; }}
            .responsive-table tr {{
                display: block !important;
                width: 100% !important;
            }}
            .responsive-table td {{
                display: block !important;
                width: 100% !important;
                padding-right: 0 !important;
                margin-bottom: 1rem !important;
            }}
            .activities-header {{
                flex-direction: column;
                align-items: flex-start;
                gap: 1rem;
            }}
        }}
    </style>
</head>
<body>

<div class="container">
    <div class="glass-panel hero-briefing" id="briefing-content">
        {briefing_html}
    </div>

    <table class="responsive-table" cellpadding="0" cellspacing="0" style="width: 100%; border: none; margin-bottom: 1.5rem;">
        <tr>
            <td valign="top" style="width: 32%; padding-right: 2%; border: none;">
                <div class="glass-panel" style="min-height: 200px; margin-bottom: 0;">
                    <h3 style="font-size: 0.9rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 1rem;">Carga / ACWR</h3>
                    {acwr_gauge_html}
                    <div style="font-size: 0.85rem; color: #94a3b8; line-height: 1.4;">
                        Aguda: {acute_val} | Crônica: {chronic_val}<br>
                        Semanal: {weekly_val}
                    </div>
                </div>
            </td>
            
            <td valign="top" style="width: 32%; padding-right: 2%; border: none;">
                <div class="glass-panel" style="min-height: 200px; margin-bottom: 0;">
                    <h3 style="font-size: 0.9rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 1rem;">VO2 Máx</h3>
                    {vo2_gauge_html}
                    <div style="font-size: 0.85rem; color: #94a3b8; line-height: 1.4;">
                        Idade Fitness: {fitness_age} anos<br>
                        Corrida: {run_vo2} | Ciclismo: {cyc_vo2}
                    </div>
                </div>
            </td>
            
            <td valign="top" style="width: 32%; border: none;">
                <div class="glass-panel" style="min-height: 200px; margin-bottom: 0;">
                    <h3 style="font-size: 0.9rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 1rem;">Recuperação (Sono)</h3>
                    <div class="metric-value {sleep_color}">{sleep_duration}</div>
                    <div style="font-size: 0.85rem; color: #94a3b8; line-height: 1.4;">
                        FC Repouso: {rhr} bpm (Média 7d: {rhr7d})
                    </div>
                </div>
            </td>
        </tr>
    </table>

    {race_predictions_html}

    <div class="glass-panel">
        <div class="activities-header">
            <h2 style="color: #f8fafc;">Histórico de Atividades</h2>
        </div>
        
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; font-weight: 600;">Data</th>
                        <th style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; font-weight: 600;">Esporte</th>
                        <th style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; font-weight: 600;">Nome</th>
                        <th style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; font-weight: 600;">Duração (min)</th>
                        <th style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; font-weight: 600;">FC Média</th>
                        <th style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; font-weight: 600;">TRIMP</th>
                        <th style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; font-weight: 600;">VO2 Estimado</th>
                        <th style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; font-weight: 600;">Origem</th>
                    </tr>
                </thead>
                <tbody id="activities-body">
                    {activities_html}
                </tbody>
            </table>
        </div>
    </div>
</div>

<script>
    // Injected Data (kept for backwards compatibility/browser features)
    const rawBriefing = {briefing_json};
    const activities = {activities_json};
    

</script>

</body>
</html>
"""

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

def get_vo2_percentage_and_zone(vo2: float, sex: str, age: int):
    # Get table based on gender
    table = VO2_TABLE_WOMEN if sex == 'F' else VO2_TABLE_MEN
    
    # Get age group
    if age < 20:
        age_group = "20-29"
    elif age > 79:
        age_group = "70-79"
    else:
        tens = int(age // 10)
        age_group = f"{tens}0-{tens}9"
        
    thresholds = table[age_group]
    t_sat = thresholds["Satisfatório"]
    t_bom = thresholds["Bom"]
    t_exc = thresholds["Excelente"]
    t_sup = thresholds["Superior"]
    
    # Range configuration: we set min_val to t_sat - 6.0 (at least 15.0) and max_val to t_sup + 6.0
    min_val = max(15.0, t_sat - 6.0)
    max_val = t_sup + 6.0
    
    # Pieces of 20% each
    if vo2 <= min_val:
        pct = 0.0
        zone = "Fraco"
        color_class = "color-red"
        zone_class = "zone-red"
    elif vo2 < t_sat:
        pct = (vo2 - min_val) / (t_sat - min_val) * 20.0
        zone = "Fraco"
        color_class = "color-red"
        zone_class = "zone-red"
    elif vo2 < t_bom:
        pct = 20.0 + (vo2 - t_sat) / (t_bom - t_sat) * 20.0
        zone = "Satisfatório"
        color_class = "color-yellow"
        zone_class = "zone-yellow"
    elif vo2 < t_exc:
        pct = 40.0 + (vo2 - t_bom) / (t_exc - t_bom) * 20.0
        zone = "Bom"
        color_class = "color-blue"
        zone_class = "zone-blue"
    elif vo2 < t_sup:
        pct = 60.0 + (vo2 - t_exc) / (t_sup - t_exc) * 20.0
        zone = "Excelente"
        color_class = "color-green"
        zone_class = "zone-green"
    else:
        if vo2 >= max_val:
            pct = 100.0
        else:
            pct = 80.0 + (vo2 - t_sup) / (max_val - t_sup) * 20.0
        zone = "Superior"
        color_class = "color-purple"
        zone_class = "zone-purple"
        
    return pct, zone, color_class, zone_class, min_val, t_sat, t_bom, t_exc, t_sup, max_val

def markdown_to_html(md_text):
    if not md_text:
        return "<p style='color: #94a3b8;'>Nenhum briefing encontrado.</p>"
        
    html_lines = []
    in_list = False
    
    lines = md_text.split('\n')
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            continue
            
        # Headers
        if line_stripped.startswith('### '):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3 style='color: #3b82f6; font-size: 1.25rem; font-weight: 600; margin-top: 16px; margin-bottom: 8px;'>{line_stripped[4:]}</h3>")
            continue
        elif line_stripped.startswith('## '):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2 style='color: #3b82f6; font-size: 1.5rem; font-weight: 600; margin-top: 20px; margin-bottom: 10px;'>{line_stripped[3:]}</h2>")
            continue
        elif line_stripped.startswith('# '):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1 style='color: #f8fafc; font-size: 1.75rem; font-weight: 700; margin-top: 24px; margin-bottom: 12px;'>{line_stripped[2:]}</h1>")
            continue
            
        # Lists
        is_list_item = False
        list_content = ""
        if line_stripped.startswith('- '):
            is_list_item = True
            list_content = line_stripped[2:]
        elif line_stripped.startswith('* '):
            is_list_item = True
            list_content = line_stripped[2:]
        elif line_stripped.startswith('🎯 '):
            is_list_item = True
            list_content = line_stripped
        elif line_stripped.startswith('🏃 '):
            is_list_item = True
            list_content = line_stripped
            
        if is_list_item:
            if not in_list:
                html_lines.append("<ul style='margin-left: 20px; margin-top: 8px; margin-bottom: 16px; padding-left: 0;'>")
                in_list = True
            html_lines.append(f"<li style='margin-bottom: 8px; color: #cbd5e1;'>{list_content}</li>")
            continue
            
        if in_list:
            html_lines.append("</ul>")
            in_list = False
            
        html_lines.append(f"<p style='margin-bottom: 12px; color: #cbd5e1;'>{line_stripped}</p>")
        
    if in_list:
        html_lines.append("</ul>")
        
    html = "\n".join(html_lines)
    html = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color: #ffffff;">\1</strong>', html)
    return html

def generate_activities_html(activities):
    if not activities:
        return '<tr id="empty-state-row"><td colspan="8" class="no-data" style="text-align: center; padding: 2rem; color: #94a3b8;">Nenhuma atividade recente encontrada.</td></tr>'
        
    sport_map = {
        'ride': 'Ciclismo',
        'virtualride': 'Ciclismo Virtual',
        'cycling': 'Ciclismo',
        'mountainbikeride': 'Mountain Bike',
        'indoorcycling': 'Ciclismo Virtual',
        'indoor_cycling': 'Ciclismo Virtual',
        'run': 'Corrida',
        'running': 'Corrida',
        'treadmill_running': 'Corrida na Esteira',
        'street_running': 'Corrida de Rua',
        'trailrun': 'Corrida em Trilha',
        'swim': 'Natação',
        'poolswim': 'Natação (Piscina)',
        'openwaterswim': 'Natação (Águas Abertas)',
        'lap_swimming': 'Natação',
        'weighttraining': 'Musculação',
        'strength_training': 'Musculação',
        'workout': 'Treino',
        'yoga': 'Yoga',
        'walk': 'Caminhada',
        'hike': 'Trilha'
    }
    
    rows = []
    for act in activities:
        date_str = act.get("date", "")
        date_parts = date_str.split("-")
        formatted_date = f"{date_parts[2]}/{date_parts[1]}/{date_parts[0]}" if len(date_parts) == 3 else date_str
        
        sport_key = act.get("sport", "").lower()
        translated_sport = sport_map.get(sport_key, act.get("sport", "-"))
        
        name = act.get("name", "-")
        duration = act.get("duration_min", "-")
        hr = act.get("avg_hr", "-")
        if hr is None or hr == "":
            hr = "-"
        
        trimp = act.get("trimp")
        trimp_str = f"{trimp:.1f}" if isinstance(trimp, (int, float)) else "-"
        
        vo2 = act.get("estimated_vo2max")
        vo2_str = f"{vo2:.1f}" if isinstance(vo2, (int, float)) else "-"
        
        source = act.get("source", "")
        source_style = "background: rgba(252, 76, 2, 0.15); color: #fc4c02; border: 1px solid rgba(252, 76, 2, 0.3);" if source == "strava" else "background: rgba(0, 124, 195, 0.15); color: #007cc3; border: 1px solid rgba(0, 124, 195, 0.3);"
        source_badge = f'<span class="source-badge" style="{source_style}">{source}</span>'
        
        try:
            act_date = date.fromisoformat(date_str)
            days_ago = (date.today() - act_date).days
        except Exception:
            days_ago = 999
            
        rows.append(f"""
        <tr class="activity-row" data-days-ago="{days_ago}">
            <td style="padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); color: #cbd5e1;">{formatted_date}</td>
            <td style="padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); color: #cbd5e1;">{translated_sport}</td>
            <td style="padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); color: #cbd5e1;">{name}</td>
            <td style="padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); color: #cbd5e1;">{duration}</td>
            <td style="padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); color: #cbd5e1;">{hr}</td>
            <td style="padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); color: #cbd5e1;">{trimp_str}</td>
            <td style="padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); color: #cbd5e1;">{vo2_str}</td>
            <td style="padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.1);">{source_badge}</td>
        </tr>
        """)
        
    return "\n".join(rows)

def get_color_class(val: float, type_metric: str) -> str:
    """Return appropriate CSS color class based on the metric value."""
    if val is None:
        return ""
    if type_metric == "acwr":
        if val < 0.8: return "color-gray"
        if 0.8 <= val <= 1.3: return "color-green"
        if 1.3 < val <= 1.5: return "color-yellow"
        return "color-red"
    if type_metric == "vo2":
        if val >= 50: return "color-green"
        if val >= 40: return "color-yellow"
        return "color-red"
    return ""

def main():
    import argparse
    from pathlib import Path
    project_dir = Path(__file__).parent.resolve()
    
    parser = argparse.ArgumentParser(description="Generate HTML Dashboard.")
    parser.add_argument(
        "--garmin-data",
        type=str,
        default="garmin_data.json",
        help="Path to the Garmin JSON data file"
    )
    parser.add_argument(
        "--briefing",
        type=str,
        default="briefing.md",
        help="Path to the Briefing Markdown file"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="dashboard.html",
        help="Path to output HTML file"
    )
    args = parser.parse_args()
    
    json_path = args.garmin_data
    if not os.path.isabs(json_path):
        json_path = os.path.abspath(project_dir / json_path)
        
    briefing_path = args.briefing
    if not os.path.isabs(briefing_path):
        briefing_path = os.path.abspath(project_dir / briefing_path)
    
    # Read Data
    data = {}
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
    metadata = data.get("metadata", {})
    raw_date = metadata.get("date", date.today().isoformat())

    # 1. Determine gender (sex)
    gender_raw = metadata.get("gender") # "MALE" or "FEMALE" or None
    sex = None
    if gender_raw == "MALE":
        sex = "M"
    elif gender_raw == "FEMALE":
        sex = "F"
        
    # Fallback to strava_tokens.json
    if not sex:
        strava_tokens_path = "strava_tokens.json"
        if not os.path.isabs(strava_tokens_path):
            strava_tokens_path = os.path.abspath(project_dir / strava_tokens_path)
        if os.path.exists(strava_tokens_path):
            try:
                with open(strava_tokens_path, "r", encoding="utf-8") as sf:
                    strava_tokens = json.load(sf)
                    athlete = strava_tokens.get("athlete", {})
                    sex_raw = athlete.get("sex")
                    if sex_raw in ("M", "F"):
                        sex = sex_raw
            except Exception:
                pass
    if not sex:
        sex = "M" # default fallback
        
    # 2. Determine age
    age = None
    birth_date_str = metadata.get("birthDate")
    if birth_date_str:
        try:
            birth_date_obj = date.fromisoformat(birth_date_str)
            ref_date = date.fromisoformat(raw_date) if raw_date else date.today()
            age = ref_date.year - birth_date_obj.year - ((ref_date.month, ref_date.day) < (birth_date_obj.month, birth_date_obj.day))
        except Exception:
            pass
            
    # Fallback to fitnessAge / chronologicalAge
    if age is None:
        metrics = data.get("metrics", {})
        fitness_age_obj = metrics.get("fitnessAge", {})
        if isinstance(fitness_age_obj, dict):
            age = fitness_age_obj.get("chronologicalAge")
            
    # Second Fallback to trainingStatus's fitnessAge
    if age is None:
        ts = data.get("metrics", {}).get("trainingStatus", {})
        age = ts.get("fitnessAge")
        
    if age is None:
        age = 39 # default fallback
            
    briefing_text = ""
    if os.path.exists(briefing_path):
        with open(briefing_path, "r", encoding="utf-8") as f:
            briefing_text = f.read()
            
    metrics = data.get("metrics", {})
    ts = metrics.get("trainingStatus", {})
    sleep = metrics.get("sleep", {})
    summary = metrics.get("dailySummary", {})
    
    # Extract Values
    acwr_val = ts.get("acwr_combined") or ts.get("acwr")
    acute_val = ts.get("acuteEWMA_combined") or "n/a"
    chronic_val = ts.get("chronicEWMA_combined") or "n/a"
    weekly_val = ts.get("weeklyLoadTrimp_combined") or ts.get("weeklyTrainingLoad") or "n/a"
    
    vo2_val = ts.get("estimated_vo2max_combined") or ts.get("vo2Max")
    run_vo2 = ts.get("estimated_running_vo2max") or "n/a"
    cyc_vo2 = ts.get("estimated_cycling_vo2max") or "n/a"
    fitness_age = ts.get("estimated_fitness_age_combined") or ts.get("fitnessAge") or "n/a"
    
    sleep_duration = sleep.get("durationFormatted", "n/a")
    rhr = summary.get("restingHeartRate", "n/a")
    rhr7d = summary.get("restingHeartRate7dAvg", "n/a")
    
    activities = ts.get("recentActivities", [])
    
    # Formatting
    acwr_color = get_color_class(acwr_val, "acwr") if acwr_val else ""
    vo2_color = get_color_class(vo2_val, "vo2") if vo2_val else ""

    # Build ACWR gauge HTML
    if isinstance(acwr_val, (int, float)):
        val_float = float(acwr_val)
        if val_float < 0.8:
            zone_name = "Subtreinamento"
            zone_class = "zone-gray"
            val_color_class = "color-gray"
        elif 0.8 <= val_float <= 1.3:
            zone_name = "Sweet Spot (Ideal)"
            zone_class = "zone-green"
            val_color_class = "color-green"
        elif 1.3 < val_float <= 1.5:
            zone_name = "Zona de Cautela"
            zone_class = "zone-yellow"
            val_color_class = "color-yellow"
        else:
            zone_name = "Zona de Perigo"
            zone_class = "zone-red"
            val_color_class = "color-red"
        
        clamped_val = min(max(val_float, 0.0), 2.0)
        percentage = (clamped_val / 2.0) * 100
        
        acwr_gauge_html = f"""
        <div class="gauge-container">
            <div class="gauge-header">
                <span class="gauge-value {val_color_class}">{val_float:.2f}</span>
                <span class="gauge-zone {zone_class}">{zone_name}</span>
            </div>
            <div class="gauge-bar-container">
                <div class="gauge-marker" style="margin-left: {percentage}%;"></div>
            </div>
            <table cellpadding="0" cellspacing="0" style="width: 100%; font-size: 11px; color: #94a3b8; margin-top: 4px; border: none;">
                <tr>
                    <td style="width: 40%; text-align: left; border: none; padding: 0;">0.0</td>
                    <td style="width: 25%; text-align: left; border: none; padding: 0; font-weight: 500;">0.8</td>
                    <td style="width: 10%; text-align: left; border: none; padding: 0; font-weight: 500;">1.3</td>
                    <td style="width: 15%; text-align: left; border: none; padding: 0; font-weight: 500;">1.5</td>
                    <td style="width: 10%; text-align: right; border: none; padding: 0;">2.0+</td>
                </tr>
            </table>
        </div>
        """
    else:
        acwr_gauge_html = """
        <div class="gauge-container">
            <div class="gauge-header">
                <span class="gauge-value">n/a</span>
                <span class="gauge-zone zone-gray">Sem dados</span>
            </div>
            <div class="gauge-bar-container" style="background: #334155;"></div>
        </div>
        """

    # Build VO2 Max gauge HTML
    if isinstance(vo2_val, (int, float)):
        val_float = float(vo2_val)
        pct, zone_name, val_color_class, zone_class, min_val, t_sat, t_bom, t_exc, t_sup, max_val = get_vo2_percentage_and_zone(val_float, sex, age)
        
        vo2_gauge_html = f"""
        <div class="gauge-container">
            <div class="gauge-header">
                <span class="gauge-value {val_color_class}">{val_float:.1f}</span>
                <span class="gauge-zone {zone_class}">{zone_name}</span>
            </div>
            <div class="gauge-bar-container" style="background: linear-gradient(to right, 
                #ef4444 0%, #ef4444 20%, 
                #f59e0b 20%, #f59e0b 40%, 
                #3b82f6 40%, #3b82f6 60%, 
                #10b981 60%, #10b981 80%, 
                #8b5cf6 80%, #8b5cf6 100%
            );">
                <div class="gauge-marker" style="margin-left: {pct}%;"></div>
            </div>
            <table cellpadding="0" cellspacing="0" style="width: 100%; font-size: 11px; color: #94a3b8; margin-top: 4px; border: none;">
                <tr>
                    <td style="width: 20%; text-align: left; border: none; padding: 0;">{min_val:.1f}</td>
                    <td style="width: 20%; text-align: left; border: none; padding: 0; font-weight: 500;">{t_sat:.1f}</td>
                    <td style="width: 20%; text-align: left; border: none; padding: 0; font-weight: 500;">{t_bom:.1f}</td>
                    <td style="width: 20%; text-align: left; border: none; padding: 0; font-weight: 500;">{t_exc:.1f}</td>
                    <td style="width: 10%; text-align: left; border: none; padding: 0; font-weight: 500;">{t_sup:.1f}</td>
                    <td style="width: 10%; text-align: right; border: none; padding: 0;">{max_val:.1f}+</td>
                </tr>
            </table>
        </div>
        """
    else:
        vo2_gauge_html = """
        <div class="gauge-container">
            <div class="gauge-header">
                <span class="gauge-value">n/a</span>
                <span class="gauge-zone zone-gray">Sem dados</span>
            </div>
            <div class="gauge-bar-container" style="background: #334155;"></div>
        </div>
        """
    # Sleep color simple logic: >7h green, >6h yellow, else red
    sleep_color = "color-yellow"
    if sleep.get("durationSeconds"):
        h = sleep["durationSeconds"] / 3600
        if h >= 7.0: sleep_color = "color-green"
        elif h < 6.0: sleep_color = "color-red"
    
    # Process Race Predictions
    race_preds = metrics.get("racePredictions", {})
    race_preds_html = ""
    if race_preds and race_preds.get("5k", {}).get("formatted"):
        pred_5k = race_preds.get("5k", {}).get("formatted", "-")
        pace_5k = race_preds.get("5k", {}).get("pace_formatted", "-")
        
        pred_10k = race_preds.get("10k", {}).get("formatted", "-")
        pace_10k = race_preds.get("10k", {}).get("pace_formatted", "-")
        
        pred_half = race_preds.get("halfMarathon", {}).get("formatted", "-")
        pace_half = race_preds.get("halfMarathon", {}).get("pace_formatted", "-")
        
        pred_mara = race_preds.get("marathon", {}).get("formatted", "-")
        pace_mara = race_preds.get("marathon", {}).get("pace_formatted", "-")
        
        race_preds_html = f"""
        <div class="glass-panel" style="background: #1e293b; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 24px; margin-bottom: 24px;">
            <div style="margin-bottom: 16px;">
                <h2 style="color: #f8fafc; font-size: 1.5rem; font-weight: 600;">Previsões de Prova</h2>
            </div>
            <table class="responsive-table" cellpadding="0" cellspacing="0" style="width: 100%; border: none;">
                <tr>
                    <td valign="top" style="width: 23%; padding-right: 2%; border: none;">
                        <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 16px;">
                            <h3 style="font-size: 0.9rem; color: #94a3b8; margin-bottom: 8px; text-transform: uppercase;">5K</h3>
                            <div style="color: #f8fafc; font-size: 1.8rem; font-weight: 700; margin-bottom: 8px;">{pred_5k}</div>
                            <div class="pace-badge" style="display: inline-block; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); padding: 4px 8px; border-radius: 6px; font-size: 0.8rem; color: #cbd5e1;">🏃 Pace: {pace_5k}/km</div>
                        </div>
                    </td>
                    <td valign="top" style="width: 23%; padding-right: 2%; border: none;">
                        <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 16px;">
                            <h3 style="font-size: 0.9rem; color: #94a3b8; margin-bottom: 8px; text-transform: uppercase;">10K</h3>
                            <div style="color: #f8fafc; font-size: 1.8rem; font-weight: 700; margin-bottom: 8px;">{pred_10k}</div>
                            <div class="pace-badge" style="display: inline-block; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); padding: 4px 8px; border-radius: 6px; font-size: 0.8rem; color: #cbd5e1;">🏃 Pace: {pace_10k}/km</div>
                        </div>
                    </td>
                    <td valign="top" style="width: 23%; padding-right: 2%; border: none;">
                        <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 16px;">
                            <h3 style="font-size: 0.9rem; color: #94a3b8; margin-bottom: 8px; text-transform: uppercase;">Meia Maratona</h3>
                            <div style="color: #f8fafc; font-size: 1.8rem; font-weight: 700; margin-bottom: 8px;">{pred_half}</div>
                            <div class="pace-badge" style="display: inline-block; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); padding: 4px 8px; border-radius: 6px; font-size: 0.8rem; color: #cbd5e1;">🏃 Pace: {pace_half}/km</div>
                        </div>
                    </td>
                    <td valign="top" style="width: 23%; border: none;">
                        <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 16px;">
                            <h3 style="font-size: 0.9rem; color: #94a3b8; margin-bottom: 8px; text-transform: uppercase;">Maratona</h3>
                            <div style="color: #f8fafc; font-size: 1.8rem; font-weight: 700; margin-bottom: 8px;">{pred_mara}</div>
                            <div class="pace-badge" style="display: inline-block; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); padding: 4px 8px; border-radius: 6px; font-size: 0.8rem; color: #cbd5e1;">🏃 Pace: {pace_mara}/km</div>
                        </div>
                    </td>
                </tr>
            </table>
        </div>
        """

    raw_date = data.get("metadata", {}).get("date", date.today().isoformat())
    header_date = raw_date
    if "-" in raw_date:
        y, m, d = raw_date.split("-")
        header_date = f"{d}/{m}/{y}"

    briefing_html = markdown_to_html(briefing_text)
    activities_html = generate_activities_html(activities)

    # Inject into HTML
    html = HTML_TEMPLATE.format(
        date=header_date,
        acwr_val=f"{acwr_val:.2f}" if isinstance(acwr_val, float) else (acwr_val or "n/a"),
        acwr_gauge_html=acwr_gauge_html,
        vo2_gauge_html=vo2_gauge_html,
        acute_val=acute_val,
        chronic_val=chronic_val,
        weekly_val=weekly_val,
        acwr_color=acwr_color,
        vo2_val=f"{vo2_val:.1f}" if isinstance(vo2_val, float) else (vo2_val or "n/a"),
        run_vo2=run_vo2,
        cyc_vo2=cyc_vo2,
        fitness_age=fitness_age,
        vo2_color=vo2_color,
        sleep_duration=sleep_duration,
        sleep_color=sleep_color,
        rhr=rhr,
        rhr7d=rhr7d,
        briefing_html=briefing_html,
        activities_html=activities_html,
        briefing_json=json.dumps(briefing_text),
        activities_json=json.dumps(activities),
        race_predictions_html=race_preds_html
    )
    
    out_file = args.output
    if not os.path.isabs(out_file):
        out_file = os.path.abspath(project_dir / out_file)
        
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html)
        
    print(f"  Dashboard gerado com sucesso em {out_file}")

if __name__ == "__main__":
    main()
