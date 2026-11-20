# Marketing 360 — solução end-to-end em Microsoft Fabric (v2, boas práticas)

Plataforma de dados para a **equipa de Marketing de um banco de retalho** (cenário "Novo Banco"),
construída numa **conta trial do Fabric** com **licença Power BI Free**, seguindo os padrões usados em
projetos de produção: arquitetura medalhão, cargas incrementais e idempotentes, qualidade de dados
com quarentena, SCD tipo 2, modelo semântico como código, testes automáticos e CI/CD.

> **Dados 100% sintéticos.** Nenhum dado real de clientes, nenhum nome, NIF, IBAN ou contacto.
> Não usar a marca ou o logótipo do banco sem autorização da instituição.

---

## 1. Caso de uso

| Pergunta do Marketing | Resposta na solução |
|---|---|
| Que campanhas e canais dão retorno? | ROI, ROAS, CPA por campanha, canal e produto |
| Onde se perde o cliente no funil? | Entrega → abertura → clique → conversão |
| Estamos a cumprir o orçamento? | Execução do orçamento, custo acumulado (YTD) |
| Que segmentos e regiões respondem melhor? | Conversão por segmento, faixa etária e região, **com o segmento que o cliente tinha à data** (SCD2) |
| Quem contactar a seguir? | Score de envolvimento 0–100 e lista "Alto envolvimento sem conversão" |
| Cumprimos o RGPD? | Contactos a clientes sem consentimento (deve ser 0), testado em cada carga |

## 2. Arquitetura

```
 FONTES (simuladas)            LH_Bronze                 LH_Silver                       WH_Gold                    POWER BI
 ──────────────────            ─────────                 ─────────                       ───────                    ────────
 CRM, envios,      ──CSV──▶  Files/landing/<ent>/      <entidade> (Delta, MERGE)      gold.dim_* (SCD1/SCD2)     SM_Marketing360
 originação,                   │ NB_10 (incremental,     ▲ NB_20 (watermark,           gold.fact_*  (MERGE)      (Direct Lake, RLS,
 faturas media                 │ idempotente)            │ regras DQ, quarentena)      gold.cliente_envolvimento  41 medidas)
                               ▼                         │                              ctl.* (watermarks, logs,        │
                             <entidade> (Delta, texto) ──┘                               testes)                         ▼
                             Files/arquivo/               ops_* (log, watermarks,      ▲                           RPT_Marketing360
                                                          quarentena, qualidade)        │ ctl.usp_carregar_gold     (4 páginas + App)
                                                                │ SQL analytics endpoint ┘ (nome em 3 partes)

 Orquestração  PL_Marketing360_Diario:  NB_00 (DAG runMultiple: Bronze ∥ → Silver por dependências)
                                        → ctl.usp_carregar_gold (dims → factos → testes) → refresh do modelo
                                        → em falha: alerta (Teams/Outlook) + atividade Fail
```

Decisões e alternativas consideradas: [`docs/01_Arquitetura_e_Decisoes.md`](docs/01_Arquitetura_e_Decisoes.md).

## 3. Boas práticas aplicadas

| Prática | Onde |
|---|---|
| Medalhão com **um item por camada** (LH_Bronze, LH_Silver, WH_Gold) | Arquitetura |
| **Metadata-driven**: nova fonte = nova entrada de configuração | `NB_Config` |
| Notebooks **sem default lakehouse** (caminhos OneLake resolvidos por nome) → iguais em DEV/PRD | `NB_Utils` |
| Bronze **imutável e idempotente** (controlo de ficheiros, arquivo, linhagem) | `NB_10` |
| Silver **incremental** por watermark + **MERGE** com deteção de alterações por hash | `NB_20`, `NB_Utils.upsert` |
| **Qualidade de dados** declarativa (rejeitar/alertar), **quarentena** com motivo | `NB_Config`, `NB_20` |
| Lógica de negócio em **funções puras testadas** (pytest + Spark local) | `NB_Transformacoes`, `tests/` |
| Orquestração em **DAG numa só sessão Spark** (`runMultiple`, retries) | `NB_00` |
| Gold dimensional: **chaves substitutas** (IDENTITY), **SCD2**, membro desconhecido, *point-in-time lookup* | `WH_01`–`WH_03` |
| Carga Gold **incremental** (watermarks) com **MERGE**, transação por passo | `WH_02`, `WH_03` |
| **Testes de qualidade bloqueantes** na Gold (unicidade, RI, reconciliação, RGPD) | `WH_04` |
| **Observabilidade** ponta-a-ponta (logs Lakehouse + Warehouse numa vista) | `ops_log_execucao`, `ctl.vw_monitorizacao` |
| Manutenção Delta (OPTIMIZE, VACUUM, V-Order) | `NB_30`, `NB_20` |
| **Modelo semântico como código**, Direct Lake, RLS, Best Practice Analyzer | `NB_40` |
| Segurança em camadas: roles, máscara dinâmica, CLS, RLS, privilégio mínimo | `WH_00`, `WH_06`, `NB_40` |
| **Git + CI/CD** (lint, testes, deploy com `fabric-cicd`) e ambientes DEV/PRD | `.github/`, `cicd/`, `docs/05` |
| Documentação de operação (runbook) e dicionário de dados | `docs/` |

## 4. Licenças: o que a conta trial e a licença Free permitem

| | Trial Fabric (60 dias) | Só licença Free |
|---|---|---|
| Lakehouse, Warehouse, Notebooks, Pipelines | ✅ | ❌ |
| Modelo semântico e relatório (o trial inclui o Power BI Individual Trial) | ✅ | Só em *O meu workspace* |
| Power BI Desktop | ✅ gratuito | ✅ gratuito |
| Partilhar o relatório com colegas que só têm licença Free | ❌ exige capacidade F64+ **paga** | ❌ |
| Partilhar com colegas que tenham o seu próprio trial ou Pro | ✅ | ❌ |
| Integração Git e pipelines de implementação | ✅ | ❌ |
| Copilot | ❌ | ❌ |

- O trial dura **60 dias**. Depois, os itens Fabric ficam inacessíveis e os dados ficam 7 dias no
  OneLake. **Este repositório é a cópia de segurança do projeto.**
- É preciso uma **conta de trabalho ou escola**. Num tenant empresarial, o administrador pode ter os
  trials desativados.
- Para mostrar o relatório a quem não tem licença: apresentar a partir da sua conta ou exportar para PDF/PowerPoint.

## 5. Estrutura do repositório

```
├── README.md                         ← este guia
├── docs/                             arquitetura, convenções, runbook, dicionário, CI/CD, relatório
├── src/
│   ├── notebooks/                    código-fonte (.py, formato percent) — revisto em PR
│   │   ├── NB_Config                 metadados: entidades, chaves, regras de qualidade
│   │   ├── NB_Utils                  OneLake, MERGE, watermarks, logging, sincronização SQL endpoint
│   │   ├── NB_Transformacoes         regras de negócio Silver (funções puras, testadas)
│   │   ├── NB_00_Orquestrador        DAG Bronze → Silver
│   │   ├── NB_01_Gerar_Dados_Sinteticos   simulador das fontes (inicial / incremental)
│   │   ├── NB_10_Bronze_Ingestao
│   │   ├── NB_20_Silver_Transformacao
│   │   ├── NB_30_Manutencao_Delta
│   │   └── NB_40_Modelo_Semantico    modelo como código (medidas, relações, RLS, BPA)
│   ├── notebooks_ipynb/              os mesmos notebooks prontos a importar no Fabric
│   ├── warehouse/                    WH_00 … WH_06 (T-SQL, reexecutáveis)
│   └── powerbi/                      tema JSON + referência DAX gerada
├── tests/                            pytest + simulação ponta-a-ponta local
├── cicd/ · fabric/ · .github/        deploy (fabric-cicd), pasta da integração Git, workflows
└── pyproject.toml · requirements-dev.txt
```

## 6. Implementação passo a passo

### Passo 1 — Ativar o trial
1. Em <https://app.fabric.microsoft.com>: **foto de perfil → Gestor de contas → Iniciar avaliação**.
   Escolher a região *West Europe* ou *North Europe*.
2. Sem o trial ativo, as opções **Fabric** e **Avaliação do Fabric** aparecem a cinzento ao criar o workspace.
   Se o botão não aparecer: criar um Lakehouse em *O meu workspace* costuma propor o trial. Se mesmo
   assim não aparecer, o administrador desativou os trials (definição *Users can try Microsoft Fabric paid features*).

### Passo 2 — Workspace(s)
1. **Novo workspace** → `WS_Marketing360_DEV` → em **Tipo de workspace** escolher **Avaliação do Fabric**.
2. (Recomendado) Repetir para `WS_Marketing360_PRD`. O fluxo DEV → PRD está em `docs/05`.
3. Criar pastas no workspace: `01 Ingestão`, `02 Transformação`, `03 Consumo`, `99 Utilitários`.

### Passo 3 — Itens de dados (nomes exatos, usados pelo código)
| Item | Nome | Nota |
|---|---|---|
| Lakehouse | `LH_Bronze` | manter **Lakehouse schemas** ativo (predefinição) |
| Lakehouse | `LH_Silver` | idem |
| Warehouse | `WH_Gold` | mesmo workspace (consultas entre bases de dados) |

Se criar os Lakehouses **sem** esquemas, mudar `USA_ESQUEMAS = False` em `NB_Config`.

### Passo 4 — Notebooks
1. **Importar → Notebook → Deste computador** → todos os `.ipynb` de `src/notebooks_ipynb/`.
2. Não é preciso anexar Lakehouse: os notebooks usam caminhos OneLake.
3. Confirmar que a célula de parâmetros de cada notebook está marcada (menu `…` da célula → *Toggle parameter cell*).
4. (Recomendado) Criar um **Ambiente** `ENV_Marketing360` com `semantic-link-labs` como biblioteca
   pública e associá-lo ao NB_40 (evita o `%pip install` em cada execução).

### Passo 5 — Warehouse
No `WH_Gold` → **Nova consulta SQL** → executar por ordem `WH_00` … `WH_06`.
As tabelas, procedimentos, testes, vistas e segurança ficam criados.

### Passo 6 — Primeira carga (manual, para validar)
1. Abrir `NB_00_Orquestrador` → parâmetro `p_gerar_dados = "inicial"` → **Executar tudo**.
   O DAG mostra Bronze e Silver por entidade. Esperado: 0 erros e 0 linhas em quarentena na carga inicial.
2. No `WH_Gold`: `EXEC ctl.usp_carregar_gold;` Os testes de qualidade são mostrados no fim e todos os bloqueantes devem dar 0.
3. Verificar: `SELECT * FROM ctl.vw_monitorizacao ORDER BY inicio DESC;`

### Passo 7 — Pipeline `PL_Marketing360_Diario`
Parâmetros do pipeline: `p_gerar_dados` (String, `nao`) e `p_data_carga` (String, `2025-12-01`).

| # | Atividade | Configuração | Ligação |
|---|---|---|---|
| 1 | **Notebook** `Lakehouse` | `NB_00_Orquestrador`; parâmetros: `p_id_lote` = `@pipeline().RunId`, `p_gerar_dados` = `@pipeline().parameters.p_gerar_dados`, `p_data_carga` = `@pipeline().parameters.p_data_carga`; tentativas 1; tempo limite 02:00:00 | — |
| 2 | **Procedimento armazenado** `Gold` | `WH_Gold` → `ctl.usp_carregar_gold`; `id_lote` = `@pipeline().RunId` | êxito de 1 |
| 3 | **Atualização do modelo semântico** | `SM_Marketing360` | êxito de 2 |
| 4 | **Teams** ou **Office 365 Outlook** `Alerta` | mensagem com `@pipeline().RunId` e `@pipeline().Pipeline` | **falha** *e* **ignorado** de 3 (as duas condições na mesma atividade funcionam como "OU") |
| 5 | **Falha** (*Fail*) | mensagem "Carga Marketing360 falhou" | êxito de 4 (o pipeline fica marcado como falhado) |

- **Agendamento:** diário às 06:00 (Europe/Lisbon). No trial, desativá-lo quando não estiver a ser usado.
- **Pipeline `PL_Marketing360_Manutencao`:** uma atividade Notebook `NB_30_Manutencao_Delta`, agendada ao domingo.

### Passo 8 — Modelo semântico e relatório
1. `WH_Gold` → **Novo modelo semântico** → `SM_Marketing360` → selecionar as 9 tabelas do esquema `gold`:
   `dim_data`, `dim_cliente`, `dim_produto`, `dim_campanha`, `fact_contactos`, `fact_conversoes`,
   `fact_custos_campanha`, `cliente_envolvimento` e `rls_acesso_regiao`.
2. Executar `NB_40_Modelo_Semantico`. Aplica os nomes amigáveis, as relações, a tabela de datas, as 41
   medidas, a RLS e corre o Best Practice Analyzer.
3. **Novo relatório** a partir do modelo → **Ver → Temas → Procurar temas** → `src/powerbi/Tema_Marketing360.json`.
   O desenho das 4 páginas está em [`docs/06_Especificacao_Relatorio.md`](docs/06_Especificacao_Relatorio.md).
4. Distribuir através de uma **App** do workspace (os consumidores não entram no workspace).

### Passo 9 — Simular o dia a dia
Executar o pipeline com `p_gerar_dados = incremental` e `p_data_carga` = `2025-12-01`, depois `2025-12-02`, e assim por diante. Em cada dia:
- chegam novos contactos, conversões e custos, e campanhas que arrancam;
- 40 clientes mudam de segmento, rendimento, distrito ou consentimento, gerando **novas versões SCD2**
  (ver `SELECT * FROM gold.vw_historico_cliente`);
- 2 contactos órfãos e 1 conversão com valor negativo vão para a **quarentena**
  (ver `SELECT * FROM ctl.vw_quarentena_pendente`).

Uma revogação de consentimento seguida de novo envio aparece como **aviso RGPD** em `ctl.resultado_testes`.
É o comportamento esperado para a demonstração.

### Passo 10 — Git e CI/CD (opcional, recomendado)
Ligar o workspace DEV a um repositório GitHub ou Azure DevOps (**Definições do workspace → Integração Git**,
pasta `fabric/`). Configurar os *workflows* em `.github/` e seguir [`docs/05_CICD_e_Ambientes.md`](docs/05_CICD_e_Ambientes.md).

## 7. Desenvolvimento local

```bash
pip install -r requirements-dev.txt     # requer Java 17 para o Spark local
ruff check src tests                    # estilo
pytest -q                               # 12 testes unitários das regras de negócio
python tests/simulacao_local.py         # Bronze+Silver: inicial + 2 incrementais + reexecução
```

## 8. Documentação

| Documento | Conteúdo |
|---|---|
| [01 Arquitetura e decisões](docs/01_Arquitetura_e_Decisoes.md) | Porquê cada escolha (ADR) e alternativas |
| [02 Convenções](docs/02_Convencoes.md) | Nomes, código, Git, revisão |
| [03 Runbook](docs/03_Runbook_Operacao.md) | Monitorizar, falhas, reprocessar, quarentena, recuperar |
| [04 Dicionário de dados](docs/04_Dicionario_de_Dados.md) | Tabelas Gold, colunas e KPIs |
| [05 CI/CD e ambientes](docs/05_CICD_e_Ambientes.md) | Git, DEV/PRD, fabric-cicd |
| [06 Especificação do relatório](docs/06_Especificacao_Relatorio.md) | Páginas, visuais, acessibilidade |
