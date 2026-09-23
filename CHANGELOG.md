# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui. O formato segue
o espírito do [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); as
versões seguem [SemVer](https://semver.org/lang/pt-BR/).

## Unreleased

### Adicionado
- `CONTRIBUTING.md` e Dependabot para `uv` e GitHub Actions (mensal, minor/patch agrupados).
- `HEALTHCHECK` na imagem Docker, para `docker run` avulso; o compose já tinha o probe.
- README: seção de limitações epidemiológicas (sem nowcasting, denominadores,
  limiares heurísticos).

### Alterado
- Builds reproduzíveis: `pyproject.toml` + `uv.lock` substituem `requirements.txt`,
  `mypy.ini`, `ruff.toml` e `pytest.ini`. CI instala com `uv sync --locked` e a imagem
  Docker usa o mesmo lockfile. `Makefile` e READMEs migram para `uv`.
- Imagem Docker deixa de instalar `build-essential`: as dependências têm wheels para 3.11.
- CI: `actions/checkout` v4 para v7 e `actions/setup-python` v5 para v7.
- CI passa a bloquear em `ruff`, `mypy` e `pytest`, não apenas nos testes (#11).
- README: seções de execução agrupadas e tabela de evidências levada para o inglês.
- README em português volta a ser o principal; a versão em inglês fica em `README.en.md`.
- Documentação expõe evidências operacionais e um relatório de exemplo em `docs/exemplo/`.

### Corrigido
- O indicador "taxa de ocupação de UTI" media, na verdade, a proporção de casos
  notificados com internação em UTI. Renomeado para `proporcao_casos_uti`
  ("Proporção de Casos com Internação em UTI") em métricas, relatório, validadores
  e documentação; as recomendações passam a citar o limiar heurístico de 30%.
- `claim_next` do store SQLite passa a ser atômico entre processos
  (`BEGIN IMMEDIATE` + checagem de `rowcount`); antes, dois workers podiam
  executar o mesmo job.

### Removido
- `src/agents/orchestrator.py`: orquestrador legado (LangGraph) sem nenhum import,
  com ano 2024 fixo e manipulação de `sys.path`. O pipeline em uso é `agents/report_pipeline.py`.

### Segurança
- API: `db_path` e `output_dir` deixam de aceitar caminhos arbitrários do cliente.
  Passam a ser relativos a `SRAG_DATA_DIR` / `SRAG_OUTPUT_DIR`; absolutos, `..` e
  symlinks para fora da base são rejeitados na API e de novo no worker.
- Política de reporte de vulnerabilidades em `SECURITY.md`.
- Atualização de dependências mantida dentro dos runtimes suportados.
- Atualização automática de versões pelo Dependabot desativada; bumps passam por revisão manual.

## 0.1.0 — 2026-07-24

Primeira versão marcada. Consolida a produtização do monitor de SRAG.

### Adicionado
- Pipeline de ingestão, API HTTP, worker e configuração Docker (`Dockerfile` e `docker-compose.yml`).
- Geração de narrativa por LLM integrada ao pipeline de relatório.
- Feeds RSS reais de fontes de saúde no lugar de notícias simuladas; URLs configuráveis via `SRAG_NEWS_FEEDS`.
- Pipeline de relatório coordenado por blackboard de etapas (estigmergia) (#4).
- `POST /reports/{job_id}/retry` com retomada a partir do ponto da falha (#5).
- Suíte de testes dividida em módulos temáticos, cobrindo casos de borda da API, falhas do blackboard e guardrails de auditoria.
- Relatório de exemplo com gráficos no README.
- Workflow de testes em Python no GitHub Actions.

### Corrigido
- Conexões SQLite e handlers do log de auditoria fechados de forma determinística.
- Nomes de arquivo dos gráficos recebem timestamp, evitando sobrescrita entre execuções.
- Testes e caminhos tornados reprodutíveis entre ambientes.
- Parsing de datas e tratamento de tabelas vazias no banco.

### Removido
- Notas de entrega da certificação, sem relação com o produto (#3).

## Origem — 2025-11-06

- Implementação inicial do SRAG Health Monitor: indicadores determinísticos, analytics e relatórios automatizados.
