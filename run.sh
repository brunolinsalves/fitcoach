#!/bin/bash

# Acessa a pasta do projeto
cd /home/bruno/Documentos/projetos/pessoal/fitcoach || exit

# Ativa o ambiente virtual
source .venv/bin/activate

pip install -r requirements.txt --break-system-packages

# Executa o script do STF
python3 briefing.py

# Desativa o ambiente virtual
deactivate