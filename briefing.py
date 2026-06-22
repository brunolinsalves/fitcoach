#!/usr/bin/env python3
"""
briefing.py

Orchestrator script for the Garmin Daily Briefing.
Sequentially runs:
  1. fetch_garmin.py   — pull health/physiological data from Garmin Connect
  2. fetch_strava.py   — pull activities from Strava (incl. MyWhoosh cycling)
  3. calc_training_load.py — merge, deduplicate, calculate TRIMP + ACWR
  4. interpret_briefing.py — generate AI-powered daily briefing
"""

import argparse
import sys
import subprocess
import os
import webbrowser
from pathlib import Path
from dotenv import load_dotenv
import datetime

# Store the original print function to avoid recursion
_print = print

def print(*args, **kwargs):
    now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    prefix = f"[{now_str}] "
    
    if not args:
        _print(*args, **kwargs)
        return
        
    first = args[0]
    if isinstance(first, str):
        leading_newlines = ""
        while first.startswith('\n'):
            leading_newlines += '\n'
            first = first[1:]
        new_first = f"{leading_newlines}{prefix}{first}"
    else:
        new_first = f"{prefix}{first}"
        
    _print(new_first, *args[1:], **kwargs)

# Load environment variables
load_dotenv()

def parse_arguments():
    parser = argparse.ArgumentParser(description="Orchestrator for Garmin Daily Briefing.")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date to fetch in YYYY-MM-DD format (default: today)"
    )
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Skip ALL API fetching and generate briefing using local cached data"
    )
    parser.add_argument(
        "--no-strava",
        action="store_true",
        help="Skip Strava data fetching (use only Garmin data)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="garmin_data.json",
        help="Path to the JSON cache file (default: garmin_data.json)"
    )
    return parser.parse_args()

def run_step(label: str, cmd: list[str], cwd: Path) -> bool:
    """Run a subprocess step and return True if successful."""
    print(f">>> {label}")
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        print(f"\n    Warning: {label} failed (exit code {result.returncode}).", file=sys.stderr)
        return False
    return True

def send_email_if_enabled(project_dir: Path, date_arg: str | None, output_path: str):
    send_email = os.getenv("SEND_EMAIL", "false").lower() in ("true", "1", "yes")
    if not send_email:
        return

    print(">>> Enviando Dashboard por e-mail...")
    html_path = project_dir / "dashboard.html"
    if not html_path.exists():
        print("    Erro: dashboard.html não encontrado. Não foi possível enviar o e-mail.", file=sys.stderr)
        return

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    except Exception as e:
        print(f"    Erro ao ler dashboard.html: {e}", file=sys.stderr)
        return

    # Determine date for the subject
    date_str = date_arg
    if not date_str:
        if os.path.exists(output_path):
            try:
                import json
                with open(output_path, "r", encoding="utf-8") as f_json:
                    data = json.load(f_json)
                    date_str = data.get("metadata", {}).get("date")
            except Exception:
                pass

    if not date_str:
        from datetime import date
        date_str = date.today().isoformat()

    if "-" in date_str:
        y, m, d = date_str.split("-")
        date_str = f"{d}/{m}/{y}"

    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        smtp_port = 587
        
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    email_to = os.getenv("EMAIL_TO", "brunolinsalves@gmail.com")
    email_from = os.getenv("EMAIL_FROM", "brunolinsalves@gmail.com")

    if not smtp_username or not smtp_password:
        print("    Aviso: SMTP_USERNAME ou SMTP_PASSWORD não configurados no arquivo .env. Envio de e-mail cancelado.", file=sys.stderr)
        return

    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"FitCoach: Treino Dashboard | {date_str}"
    msg['From'] = email_from
    msg['To'] = email_to

    part = MIMEText(html_content, 'html', 'utf-8')
    msg.attach(part)

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()

        server.login(smtp_username, smtp_password)
        server.sendmail(email_from, email_to, msg.as_string())
        server.quit()
        print(f"    E-mail enviado com sucesso para {email_to}!")
    except Exception as e:
        print(f"    Erro ao enviar e-mail: {e}", file=sys.stderr)

def main():
    args = parse_arguments()
    project_dir = Path(__file__).parent.resolve()
    
    # Locate the python interpreter in the virtual environment
    venv_python = project_dir / ".venv" / "bin" / "python3"
    python_exe = str(venv_python) if venv_python.exists() else sys.executable

    output_path = os.path.abspath(args.output)
    strava_path = os.path.join(project_dir, "strava_activities.json")
    
    if not args.cached:
        # Step 1: Garmin data collection
        fetch_cmd = [python_exe, str(project_dir / "fetch_garmin.py"), "--output", output_path]
        if args.date:
            fetch_cmd.extend(["--date", args.date])
        
        print()
        if not run_step("[Layer 1a] Collecting data from Garmin Connect...", fetch_cmd, project_dir):
            print("Error: Garmin data collection failed. Cannot continue.", file=sys.stderr)
            sys.exit(1)
        print()

        # Step 2: Strava data collection (optional)
        has_strava_config = os.getenv("STRAVA_CLIENT_ID") and os.getenv("STRAVA_CLIENT_SECRET")
        
        if not args.no_strava and has_strava_config:
            strava_cmd = [python_exe, str(project_dir / "fetch_strava.py"), "--output", strava_path]
            run_step("[Layer 1b] Collecting activities from Strava...", strava_cmd, project_dir)
            print()
        elif not args.no_strava and not has_strava_config:
            print(">>> [Layer 1b] Strava skipped (STRAVA_CLIENT_ID/SECRET not configured in .env)\n")

        # Step 3: Calculate combined training load
        has_strava_data = os.path.exists(strava_path)
        load_cmd = [
            python_exe, str(project_dir / "calc_training_load.py"),
            "--garmin-data", output_path,
            "--strava-data", strava_path,
        ]
        if args.date:
            load_cmd.extend(["--date", args.date])
        
        run_step("[Layer 1c] Calculating combined training load (TRIMP + ACWR)...", load_cmd, project_dir)
        print()
    else:
        print(f"\n>>> [Layers 1a-1c] Skipping all API calls. Using cached files.\n")

    # Check if garmin_data.json exists
    if not os.path.exists(output_path):
        print(f"Error: '{output_path}' does not exist. Run without --cached first.", file=sys.stderr)
        sys.exit(1)

    # Step 4: Interpretation
    interpret_cmd = [python_exe, str(project_dir / "interpret_briefing.py"), output_path]
    run_step("[Layer 2] Generating daily briefing...", interpret_cmd, project_dir)

    # Step 5: Generate Dashboard
    dashboard_cmd = [python_exe, str(project_dir / "generate_dashboard.py")]
    run_step("[Layer 3] Generating HTML Dashboard...", dashboard_cmd, project_dir)
    
    # Send email if configured
    send_email_if_enabled(project_dir, args.date, output_path)
    
    # Open browser
    html_path = os.path.abspath(os.path.join(project_dir, "dashboard.html"))
    if os.path.exists(html_path):
        print(f"\nOpening dashboard in your default browser...")
        webbrowser.open('file://' + html_path)

if __name__ == "__main__":
    main()
