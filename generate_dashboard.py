#!/usr/bin/env python3
"""
generate_dashboard.py

Generates a static, dynamic, and modern HTML dashboard summarizing 
the Garmin/Strava training data and the AI Briefing.
"""

import json
import os
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
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        :root {{
            --bg-base: #0f172a;
            --bg-card: rgba(30, 41, 59, 0.7);
            --bg-card-hover: rgba(30, 41, 59, 0.9);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-green: #10b981;
            --accent-yellow: #f59e0b;
            --accent-red: #ef4444;
            --accent-blue: #3b82f6;
            --border-light: rgba(255, 255, 255, 0.1);
            --glow-spread: 15px;
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-base);
            color: var(--text-main);
            min-height: 100vh;
            padding: 2rem;
            background-image: 
                radial-gradient(circle at 15% 50%, rgba(59, 130, 246, 0.15), transparent 25%),
                radial-gradient(circle at 85% 30%, rgba(16, 185, 129, 0.1), transparent 25%);
            background-attachment: fixed;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        header {{
            margin-bottom: 2rem;
            text-align: center;
        }}
        
        header h1 {{
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, #fff, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}

        /* Glassmorphism Cards */
        .glass-panel {{
            background: var(--bg-card);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--border-light);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            transition: transform 0.2s ease, background 0.2s ease;
        }}
        
        .glass-panel:hover {{
            background: var(--bg-card-hover);
            transform: translateY(-2px);
        }}

        /* Briefing Hero */
        .hero-briefing {{
            margin-bottom: 2rem;
            font-size: 1.1rem;
            line-height: 1.6;
        }}
        
        .hero-briefing h3 {{
            color: var(--accent-blue);
            margin-top: 1rem;
            margin-bottom: 0.5rem;
        }}
        
        .hero-briefing ul {{
            margin-left: 1.5rem;
            margin-bottom: 1rem;
        }}

        .hero-briefing p {{
            margin-bottom: 1rem;
        }}
        
        .hero-briefing strong {{
            color: #fff;
        }}

        /* Metrics Grid */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }}

        .metric-card h3 {{
            font-size: 0.9rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 1rem;
        }}

        .metric-value {{
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }}

        .metric-sub {{
            font-size: 0.85rem;
            color: var(--text-muted);
        }}

        .pace-badge {{
            display: inline-block;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 0.2rem 0.6rem;
            border-radius: 6px;
            font-size: 0.8rem;
            color: #cbd5e1;
            margin-top: 0.2rem;
        }}

        /* Dynamic Colors */
        .color-green {{ color: var(--accent-green); text-shadow: 0 0 var(--glow-spread) rgba(16, 185, 129, 0.4); }}
        .color-yellow {{ color: var(--accent-yellow); text-shadow: 0 0 var(--glow-spread) rgba(245, 158, 11, 0.4); }}
        .color-red {{ color: var(--accent-red); text-shadow: 0 0 var(--glow-spread) rgba(239, 68, 68, 0.4); }}
        .color-blue {{ color: var(--accent-blue); text-shadow: 0 0 var(--glow-spread) rgba(59, 130, 246, 0.4); }}

        /* Activities Section */
        .activities-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }}
        
        .activities-header h2 {{
            font-size: 1.5rem;
        }}

        .filters {{
            display: flex;
            gap: 0.5rem;
        }}

        .filter-btn {{
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--border-light);
            color: var(--text-muted);
            padding: 0.4rem 1rem;
            border-radius: 20px;
            cursor: pointer;
            font-family: inherit;
            font-size: 0.85rem;
            transition: all 0.2s ease;
        }}

        .filter-btn:hover {{
            background: rgba(255,255,255,0.1);
            color: #fff;
        }}

        .filter-btn.active {{
            background: var(--accent-blue);
            color: #fff;
            border-color: var(--accent-blue);
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
            border-bottom: 1px solid var(--border-light);
        }}

        th {{
            font-size: 0.85rem;
            color: var(--text-muted);
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
        .source-strava {{ background: rgba(252, 76, 2, 0.2); color: #fc4c02; border: 1px solid rgba(252, 76, 2, 0.4); }}
        .source-garmin {{ background: rgba(0, 124, 195, 0.2); color: #007cc3; border: 1px solid rgba(0, 124, 195, 0.4); }}
        
        .no-data {{
            text-align: center;
            padding: 2rem;
            color: var(--text-muted);
        }}
        
        @media (max-width: 768px) {{
            .metrics-grid {{ grid-template-columns: 1fr; }}
            .activities-header {{ flex-direction: column; align-items: flex-start; gap: 1rem; }}
        }}
    </style>
</head>
<body>

<div class="container">
    <header>
        <h1>Treino Dashboard</h1>
        <p class="metric-sub" id="current-date">{date}</p>
    </header>

    <div class="glass-panel hero-briefing" id="briefing-content">
        <!-- Briefing injected here -->
        <p class="no-data">Carregando briefing...</p>
    </div>

    <div class="metrics-grid">
        <div class="glass-panel metric-card">
            <h3>Carga / ACWR</h3>
            <div class="metric-value {acwr_color}" id="acwr-val">{acwr_val}</div>
            <div class="metric-sub">
                Aguda: {acute_val} | Crônica: {chronic_val}<br>
                Semanal: {weekly_val}
            </div>
        </div>
        
        <div class="glass-panel metric-card">
            <h3>Performance (Combinada)</h3>
            <div class="metric-value {vo2_color}" id="vo2-val">{vo2_val}</div>
            <div class="metric-sub">
                Idade Fitness: {fitness_age} anos<br>
                Corrida: {run_vo2} | Ciclismo: {cyc_vo2}
            </div>
        </div>
        
        <div class="glass-panel metric-card">
            <h3>Recuperação (Sono)</h3>
            <div class="metric-value {sleep_color}" id="sleep-val">{sleep_duration}</div>
            <div class="metric-sub">
                FC Repouso: {rhr} bpm (Média 7d: {rhr7d})
            </div>
        </div>
    </div>

    {race_predictions_html}

    <div class="glass-panel">
        <div class="activities-header">
            <h2>Histórico de Atividades</h2>
            <div class="filters">
                <button class="filter-btn active" data-filter="all">Todos</button>
                <button class="filter-btn" data-filter="7">Últimos 7 Dias</button>
                <button class="filter-btn" data-filter="30">Últimos 30 Dias</button>
            </div>
        </div>
        
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>Data</th>
                        <th>Esporte</th>
                        <th>Nome</th>
                        <th>Duração (min)</th>
                        <th>FC Média</th>
                        <th>TRIMP</th>
                        <th>VO2 Estimado</th>
                        <th>Origem</th>
                    </tr>
                </thead>
                <tbody id="activities-body">
                    <!-- JS will inject rows -->
                </tbody>
            </table>
        </div>
    </div>
</div>

<script>
    // Injected Data
    const rawBriefing = {briefing_json};
    const activities = {activities_json};
    
    // Parse Markdown for the briefing
    document.getElementById('briefing-content').innerHTML = marked.parse(rawBriefing || "*Nenhum briefing encontrado.*", {{breaks: true}});
    
    // Header Date Formatting
    const headerDateEl = document.getElementById('current-date');
    if (headerDateEl && headerDateEl.innerText.includes('-')) {{
        const [y, m, d] = headerDateEl.innerText.split('-');
        headerDateEl.innerText = `${{d}}/${{m}}/${{y}}`;
    }}

    // Table Rendering
    const tbody = document.getElementById('activities-body');
    const sportMap = {{
        'ride': 'Ciclismo',
        'virtualride': 'Ciclismo Virtual',
        'cycling': 'Ciclismo',
        'mountainbikeride': 'Mountain Bike',
        'indoorcycling': 'Ciclismo Indoor',
        'run': 'Corrida',
        'running': 'Corrida',
        'treadmill_running': 'Corrida na Esteira',
        'street_running': 'Corrida de Rua',
        'trailrun': 'Corrida em Trilha',
        'swim': 'Natação',
        'poolswim': 'Natação (Piscina)',
        'openwaterswim': 'Natação (Águas Abertas)',
        'weighttraining': 'Musculação',
        'strength_training': 'Musculação',
        'workout': 'Treino',
        'yoga': 'Yoga',
        'walk': 'Caminhada',
        'hike': 'Trilha'
    }};
    
    function renderTable(daysFilter) {{
        tbody.innerHTML = '';
        
        if (!activities || activities.length === 0) {{
            tbody.innerHTML = '<tr><td colspan="8" class="no-data">Nenhuma atividade encontrada.</td></tr>';
            return;
        }}
        
        const now = new Date();
        const cutoff = new Date();
        if (daysFilter !== 'all') {{
            cutoff.setDate(now.getDate() - parseInt(daysFilter));
        }}
        
        let count = 0;
        activities.forEach(act => {{
            const actDate = new Date(act.date + 'T00:00:00'); 
            if (daysFilter !== 'all' && actDate < cutoff) return;
            
            count++;
            const tr = document.createElement('tr');
            
            const sourceClass = act.source === 'strava' ? 'source-strava' : 'source-garmin';
            const sourceBadge = `<span class="source-badge ${{sourceClass}}">${{act.source}}</span>`;
            
            const vo2Cell = act.estimated_vo2max ? act.estimated_vo2max.toFixed(1) : '-';
            const hrCell = act.avg_hr ? act.avg_hr : '-';
            
            // Format Date DD/MM/YYYY
            const [y, m, d] = act.date.split('-');
            const formattedDate = `${{d}}/${{m}}/${{y}}`;
            
            // Translate Sport
            const sportKey = (act.sport || '').toLowerCase();
            const translatedSport = sportMap[sportKey] || act.sport;
            
            tr.innerHTML = `
                <td>${{formattedDate}}</td>
                <td>${{translatedSport}}</td>
                <td>${{act.name || '-'}}</td>
                <td>${{act.duration_min}}</td>
                <td>${{hrCell}}</td>
                <td>${{act.trimp ? act.trimp.toFixed(1) : '-'}}</td>
                <td>${{vo2Cell}}</td>
                <td>${{sourceBadge}}</td>
            `;
            tbody.appendChild(tr);
        }});
        
        if (count === 0) {{
            tbody.innerHTML = '<tr><td colspan="8" class="no-data">Nenhuma atividade neste período.</td></tr>';
        }}
    }}
    
    // Filter Event Listeners
    document.querySelectorAll('.filter-btn').forEach(btn => {{
        btn.addEventListener('click', (e) => {{
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            renderTable(e.target.dataset.filter);
        }});
    }});
    
    // Initial Render
    renderTable('all');
</script>

</body>
</html>
"""

def get_color_class(val: float, type_metric: str) -> str:
    """Return appropriate CSS color class based on the metric value."""
    if val is None:
        return ""
    if type_metric == "acwr":
        if 0.8 <= val <= 1.3: return "color-green"
        if 1.3 < val <= 1.5 or 0.5 <= val < 0.8: return "color-yellow"
        return "color-red"
    if type_metric == "vo2":
        if val >= 50: return "color-green"
        if val >= 40: return "color-yellow"
        return "color-red"
    return ""

def main():
    json_path = "garmin_data.json"
    briefing_path = "briefing.md"
    
    # Read Data
    data = {}
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
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
        <div class="glass-panel" style="margin-bottom: 3rem;">
            <div class="activities-header">
                <h2>Previsões de Prova</h2>
            </div>
            <div class="metrics-grid" style="margin-bottom: 0;">
                <div class="metric-card">
                    <div class="metric-label"><h3>5K</h3></div>
                    <div class="metric-value">{pred_5k}</div>
                    <div class="pace-badge">🏃 Pace: {pace_5k}/km</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label"><h3>10K</h3></div>
                    <div class="metric-value">{pred_10k}</div>
                    <div class="pace-badge">🏃 Pace: {pace_10k}/km</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label"><h3>Meia Maratona</h3></div>
                    <div class="metric-value">{pred_half}</div>
                    <div class="pace-badge">🏃 Pace: {pace_half}/km</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label"><h3>Maratona</h3></div>
                    <div class="metric-value">{pred_mara}</div>
                    <div class="pace-badge">🏃 Pace: {pace_mara}/km</div>
                </div>
            </div>
        </div>
        """

    raw_date = data.get("metadata", {}).get("date", date.today().isoformat())
    header_date = raw_date
    if "-" in raw_date:
        y, m, d = raw_date.split("-")
        header_date = f"{d}/{m}/{y}"

    # Inject into HTML
    html = HTML_TEMPLATE.format(
        date=header_date,
        acwr_val=f"{acwr_val:.2f}" if isinstance(acwr_val, float) else (acwr_val or "n/a"),
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
        briefing_json=json.dumps(briefing_text),
        activities_json=json.dumps(activities),
        race_predictions_html=race_preds_html
    )
    
    out_file = "dashboard.html"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html)
        
    print(f"  Dashboard gerado com sucesso em {os.path.abspath(out_file)}")

if __name__ == "__main__":
    main()
