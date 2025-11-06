# Recomendações de Melhoria

## 1. Empacotamento e importação
- Transformar o diretório `src/` em um pacote instalável (ex.: `pyproject.toml` com `package-dir = {"" = "src"}`) eliminaria a necessidade de ajustar `sys.path` manualmente no CLI e nos testes.
- Essa mudança melhora a experiência de desenvolvimento e permite executar os módulos com `python -m srag_health_monitor...` sem hacks específicos do repositório.
- Locais impactados: `main.py` e `tests/test_suite.py` fazem `sys.path.insert` para alcançar os módulos internos.

## 2. Evolução dos artefatos de gráfico
- A geração de gráficos passou a exportar arquivos SVG compatíveis com o relatório, mas ainda não há legenda ou destaque visual para marcos importantes.
- Considerar adicionar linhas de tendência, média móvel ou faixas de confiança para enriquecer a análise visual — especialmente quando os dados apresentam alta variação.
- Locais impactados: `ChartGenerationTool` pode oferecer parâmetros opcionais (ex.: `show_trendline`) que o orquestrador ativa conforme o tipo de relatório.

## 3. Robustez das operações de banco de dados
- Métodos como `create_tables` assumem que `self.conn` já foi inicializada; se alguém chamar a API sem usar o context manager, ocorre `AttributeError`.
- Invocar `self.connect()` no início de cada método público que acessa o banco reduz o risco de mau uso e facilita scripts de inicialização.
- Essa proteção é especialmente útil para utilidades como `load_data_from_csv` ou `get_all_metrics` em pipelines externos.

## 4. Aplicação prática dos guardrails
- Há um limitador de taxa (`RateLimiter`) e validadores de entrada/saída definidos, porém o orquestrador nunca os consulta antes de chamar as ferramentas.
- Integrar essas verificações no fluxo (por exemplo, checando o limiter em `collect_news` e validando métricas após `collect_metrics`) fortalece a governança prometida pela camada de guardrails.
- Também valeria registrar as métricas de uso no `execution_tracker` sempre que uma ferramenta for chamada para aproveitar o logging estruturado existente.
