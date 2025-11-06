# SRAG Health Monitor 🏥

Sistema de monitoramento de surtos de SRAG (Síndrome Respiratória Aguda Grave) que automatiza a coleta de dados, geração de gráficos e produção de relatórios epidemiológicos.

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 📋 Sobre o Projeto

O projeto foi desenvolvido para consolidar diferentes fontes de informação sobre SRAG em um fluxo único e reprodutível. O objetivo é oferecer uma visão atualizada do cenário epidemiológico, reunindo métricas calculadas a partir do banco de dados, notícias de apoio e artefatos prontos para visualização.

### Características Principais

- **Orquestrador Automatizado**: Coordena consultas ao banco, busca notícias e gera o relatório final sem dependências de IA generativa.
- **Consulta Automatizada de Dados**: Acessa banco de dados com ~265 mil registros do DATASUS.
- **Busca de Notícias Contextuais**: Consulta feeds RSS em tempo real (com fallback offline opcional).
- **Geração de Visualizações**: Cria gráficos SVG prontos para incorporar nos relatórios.
- **Relatórios Automatizados**: Compila análises completas em formato Markdown.
- **Governança e Auditoria**: Sistema completo de logging e rastreabilidade.
- **Guardrails de Segurança**: Validações em múltiplas camadas e proteção de dados (LGPD).

## 🏗️ Arquitetura

![Arquitetura do Sistema](docs/architecture_diagram.png)

A solução é composta por 6 camadas principais:

1. **Camada de Apresentação**: Interface com usuários/profissionais de saúde
2. **Camada de Orquestração**: Orquestrador principal, auditoria e guardrails
3. **Camada de Ferramentas**: Database Query, News Search e Chart Generation
4. **Camada de Dados**: SQLite, APIs de notícias e gráficos
5. **Camada de Processamento**: ETL de dados do DATASUS
6. **Camada de Saída**: Relatórios e logs de auditoria

### Diagrama Conceitual

O diagrama conceitual completo está disponível em:
- **PNG**: [docs/architecture_diagram.png](docs/architecture_diagram.png)
- **PDF**: [docs/architecture_diagram.pdf](docs/architecture_diagram.pdf)
- **Mermaid**: [docs/architecture_diagram.mmd](docs/architecture_diagram.mmd)

## 📊 Métricas Geradas

O sistema calcula e analisa automaticamente:

1. **Taxa de Aumento de Casos**: Crescimento percentual nos últimos 30 dias
2. **Taxa de Mortalidade**: Percentual de óbitos em relação ao total de casos
3. **Taxa de Ocupação de UTI**: Percentual de casos que necessitaram UTI
4. **Taxa de Vacinação**: Percentual de pacientes com vacinação prévia

Além disso, gera:
- Gráfico de casos diários (últimos 30 dias)
- Gráfico de casos mensais (últimos 12 meses)

## 🚀 Instalação e Configuração

### Pré-requisitos

- Python 3.11+
- pip3

### Instalação

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/srag-health-monitor.git
cd srag-health-monitor

# Instale as dependências
pip3 install -r requirements.txt

```

### Configuração Opcional de Notícias em Tempo Real

- Por padrão, a ferramenta de notícias consulta o feed RSS do Google News filtrado para SRAG em português.
- Para utilizar outra fonte, defina a variável de ambiente `SRAG_NEWS_RSS_URL` com uma URL que aceite o placeholder `{query}`.
- Ajuste o tempo máximo de espera (timeout) configurando `SRAG_NEWS_TIMEOUT` (em segundos), se necessário.

### Estrutura do Projeto

```
srag-health-monitor/
├── src/
│   ├── agents/
│   │   └── orchestrator.py          # Orquestrador principal do relatório
│   ├── tools/
│   │   ├── database_tool.py         # Ferramenta de consulta ao BD
│   │   ├── news_tool.py             # Ferramenta de busca de notícias
│   │   └── chart_tool.py            # Ferramenta de geração de gráficos
│   ├── database/
│   │   └── db_manager.py            # Gerenciador do banco SQLite
│   ├── utils/
│   │   └── data_processor.py        # Processador de dados DATASUS
│   └── guardrails/
│       ├── validators.py            # Validadores e guardrails
│       └── audit_logger.py          # Sistema de auditoria
├── data/
│   ├── raw/                         # Dados brutos do DATASUS
│   ├── processed/                   # Dados processados
│   └── srag.db                      # Banco de dados SQLite
├── outputs/
│   ├── reports/                     # Relatórios gerados
│   └── logs/                        # Logs de auditoria
├── docs/
│   ├── architecture_diagram.png     # Diagrama da arquitetura
│   ├── architecture_diagram.pdf     # Diagrama em PDF
│   └── datasus_info.md             # Informações sobre os dados
└── README.md
```

## 💻 Uso

### 1. Preparar Banco de Dados com o CSV do DATASUS

1. Faça o download do arquivo CSV bruto (SIVEP-Gripe/SRAG 2024) no [Open DATASUS](https://datasus.saude.gov.br/).
2. Salve o arquivo em `data/raw/srag2024.csv` (ou informe outro caminho via `--raw-csv`).
3. Execute o script de preparação:

```bash
python3.11 scripts/prepare_database.py --raw-csv data/raw/srag2024.csv
```

O comando processa o CSV, gera `data/processed/srag_2024_processed.csv` e popula o banco `data/srag.db`.

### 2. Gerar Relatório

```bash
python3.11 main.py --output-dir outputs/reports
```

O relatório será gerado em `outputs/reports/relatorio_YYYYMMDD_HHMMSS.md`

### Exemplo de Uso Programático

```python
from src.agents.orchestrator import SRAGReportOrchestrator

# Criar orquestrador
orchestrator = SRAGReportOrchestrator()

# Gerar relatório
report = orchestrator.run()

print(report)
```

## 🔒 Governança e Transparência

### Sistema de Auditoria

Todas as decisões do orquestrador são registradas em logs estruturados (JSONL):

```json
{
  "event_id": "uuid",
  "timestamp": "2025-11-06T07:31:01",
  "event_type": "agent_decision",
  "execution_id": "20251106_073101",
  "data": {
    "decision": "Gerar relatório de SRAG",
    "reasoning": "Solicitação do usuário",
    "metadata": {}
  }
}
```

### Guardrails Implementados

1. **Validação de Entrada**
   - Sanitização de parâmetros
   - Validação de tipos e ranges
   - Rate limiting

2. **Validação de Saída**
   - Verificação de métricas calculadas
   - Validação de estrutura de relatórios
   - Detecção de anomalias

3. **Proteção de Dados (LGPD)**
   - Detecção automática de PII (CPF, RG, telefone, email)
   - Anonimização de dados sensíveis
   - Dados já anonimizados na fonte (DATASUS)

## 📈 Resultados

### Métricas Atuais (2024)

- **Total de Casos**: 265.087
- **Taxa de Mortalidade**: 7,67%
- **Taxa de Ocupação de UTI**: 27,89%
- **Taxa de Vacinação**: 52,90%
- **Tendência**: -3,67% (redução nos últimos 30 dias)

### Exemplo de Relatório Gerado

Os relatórios incluem:
- Métricas principais com análise contextual
- Notícias recentes sobre SRAG
- Gráficos de visualização temporal
- Conclusões e recomendações baseadas em dados

## 🛠️ Tecnologias Utilizadas

- **Python 3.11**: Linguagem principal
- **SQLite**: Banco de dados
- **Pandas**: Processamento de dados
- **NumPy**: Cálculos auxiliares
- **unittest**: Testes automatizados
- **Logging**: Auditoria e rastreabilidade

## 📝 Critérios de Avaliação Atendidos

### ✅ Arquitetura
- Arquitetura modular e escalável
- Separação clara de responsabilidades
- Uso de design patterns (Factory, Strategy)

### ✅ Governança e Transparência
- Sistema completo de auditoria
- Logging estruturado em JSONL
- Rastreabilidade de todas as decisões
- Métricas de performance

### ✅ Guardrails
- Validação em múltiplas camadas
- Rate limiting
- Sanitização de inputs
- Validação de outputs

### ✅ Tratamento de Dados Sensíveis
- Conformidade com LGPD
- Detecção e anonimização de PII
- Dados já anonimizados na fonte
- Sem armazenamento de dados pessoais

### ✅ Clean Code
- PEP 8 compliance
- Type hints em todas as funções
- Docstrings completas
- Código modular e testável
- Logging apropriado

## 📚 Fonte de Dados

Os dados utilizados são provenientes do **OpenDATASUS**, especificamente do sistema **SIVEP-Gripe** (Sistema de Informação da Vigilância Epidemiológica da Gripe):

- **URL**: https://opendatasus.saude.gov.br/dataset/srag-2021-a-2024
- **Atualização**: Semanal
- **Cobertura**: Nacional (Brasil)
- **Granularidade**: Municipal, diária
- **Licença**: Creative Commons Atribuição

## 🔮 Melhorias Futuras

- [ ] Integração com APIs reais de notícias (Google News API, NewsAPI)
- [ ] Dashboard interativo com Streamlit/Dash
- [ ] Alertas automáticos por email/SMS
- [ ] Análise preditiva com Machine Learning
- [ ] Integração com outros sistemas de vigilância epidemiológica
- [ ] API REST para integração externa
- [ ] Suporte a múltiplas doenças respiratórias

## 👨‍💻 Autor

Desenvolvido como projeto de certificação focado em monitoramento epidemiológico.

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

## 🙏 Agradecimentos

- **Ministério da Saúde** - Pela disponibilização dos dados do DATASUS
- **Indicium HealthCare Inc.** - Pela oportunidade de certificação
- **Comunidade Open Source** - Pelas ferramentas e bibliotecas utilizadas

---

**Nota**: Este é um projeto de demonstração para fins educacionais e de certificação. Para uso em produção, recomenda-se validação adicional por profissionais de saúde e epidemiologistas.
