# Arquitetura da Solução - SRAG Health Monitor

## Visão Geral

Sistema de monitoramento automatizado de surtos de SRAG (Síndrome Respiratória Aguda Grave) que integra coleta de dados, geração de artefatos e produção de relatórios.

## Componentes Principais

### 1. Orquestrador
- **Função**: Coordenar o fluxo de execução entre ferramentas
- **Tecnologia**: Python puro
- **Responsabilidades**:
  - Receber requisições de geração de relatório
  - Orquestrar chamadas às ferramentas
  - Agregar resultados e gerar relatório final
  - Registrar decisões para auditoria

### 2. Ferramentas (Tools)

#### 2.1 Database Query Tool
- Consultar métricas no banco de dados SQLite
- Calcular: taxa de aumento de casos, taxa de mortalidade, taxa de ocupação UTI, taxa de vacinação
- Retornar dados para gráficos (30 dias e 12 meses)

#### 2.2 News Search Tool
- Buscar notícias em tempo real sobre SRAG
- Fontes: feeds RSS públicos (ex.: Google News) com fallback offline
- Processar e extrair informações relevantes

#### 2.3 Chart Generation Tool
- Gerar gráfico de casos diários (últimos 30 dias)
- Gerar gráfico de casos mensais (últimos 12 meses)
- Formato: PNG/SVG para inclusão no relatório

#### 2.4 Report Generator Tool
- Compilar métricas, notícias e gráficos
- Gerar relatório em formato Markdown/PDF
- Incluir explicações contextualizadas

### 3. Banco de Dados
- **Tecnologia**: SQLite (simplicidade e portabilidade)
- **Esquema**:
  - Tabela principal: casos_srag
  - Índices otimizados para consultas temporais
  - Colunas relevantes: data, UF, município, idade, evolução, UTI, vacinação

### 4. Sistema de Governança e Auditoria
- **Logging estruturado**: Todas as decisões do orquestrador
- **Rastreabilidade**: ID de execução único por relatório
- **Métricas**: Tempo de execução, tokens utilizados, fontes consultadas

### 5. Guardrails
- **Validação de entrada**: Sanitização de parâmetros
- **Validação de saída**: Verificação de métricas calculadas
- **Rate limiting**: Controle de chamadas à API
- **Tratamento de dados sensíveis**: Anonimização de informações pessoais

### 6. Pipeline de Dados
- **Extração**: Download de dados do DATASUS
- **Transformação**: Limpeza, tratamento de valores ausentes, seleção de colunas
- **Carga**: Inserção no banco SQLite com validações

## Fluxo de Execução

```
Usuário → Orquestrador → [
    ├─ Database Query Tool → Métricas + Dados para gráficos
    ├─ News Search Tool → Notícias contextuais
    ├─ Chart Generation Tool → Artefatos visuais
    └─ Report Generator Tool → Relatório final
] → Auditoria/Logging → Saída (Markdown)
```

## Tecnologias Utilizadas

- **Python 3.11**: Linguagem principal
- **SQLite**: Banco de dados
- **Pandas**: Processamento de dados
- **NumPy**: Cálculos auxiliares
- **Logging**: Auditoria e rastreamento
- **unittest**: Testes automatizados

## Critérios de Avaliação Atendidos

1. **Arquitetura**: Modular, escalável, orientada a serviços
2. **Governança**: Sistema completo de logging e auditoria
3. **Guardrails**: Validações em múltiplas camadas
4. **Dados Sensíveis**: Anonimização e conformidade com LGPD
5. **Clean Code**: PEP 8, type hints, documentação, testes
