"""
Configuração central do sistema SRAG Health Monitor.

Este módulo define os diretórios e caminhos utilizados pelo sistema,
permitindo configuração via variável de ambiente SRAG_BASE_DIR.
"""

import os
from pathlib import Path

# Base directory - pode ser configurado via variável de ambiente
# Em ambientes onde /home/ubuntu não é acessível, configure SRAG_BASE_DIR
BASE_DIR = Path(os.getenv('SRAG_BASE_DIR', '/home/ubuntu/srag-health-monitor'))

# Diretórios principais
DATA_DIR = BASE_DIR / 'data'
OUTPUTS_DIR = BASE_DIR / 'outputs'
REPORTS_DIR = OUTPUTS_DIR / 'reports'
LOGS_DIR = OUTPUTS_DIR / 'logs'

# Criar diretórios se não existirem (apenas se o diretório base existir ou puder ser criado)
try:
    for directory in [DATA_DIR, OUTPUTS_DIR, REPORTS_DIR, LOGS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
except (PermissionError, OSError):
    # Em ambientes de teste ou CI, os diretórios podem não ser criáveis
    # Eles serão criados sob demanda quando necessário
    pass
