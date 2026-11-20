# 01 — Arquitetura e decisões (ADR)

Cada decisão segue o formato: **Contexto → Decisão → Consequências**. Alterar uma decisão = novo ADR.

---

### ADR-01 · Medalhão com um item por camada
- **Contexto:** precisamos de separar o dado em bruto (auditoria), o dado limpo (reutilizável) e o modelo de consumo.
- **Decisão:** `LH_Bronze` (ficheiros e Delta em texto), `LH_Silver` (Delta tipado e conformado) e `WH_Gold` (estrela).
- **Consequências:** permissões por camada (ex.: analistas só no `WH_Gold`), ciclos de vida independentes,
  reprocessamento a partir da Bronze. Mais um item a gerir do que num só Lakehouse.

### ADR-02 · Lakehouse para Bronze/Silver, Warehouse para Gold
- **Contexto:** a equipa de engenharia trabalha em Python/Spark; os analistas e o Marketing em SQL.
- **Decisão:** Spark para ingestão e limpeza (ficheiros, regras, escala); T-SQL no Warehouse para o modelo
  dimensional (transações multi-tabela, MERGE, IDENTITY, segurança granular: máscara, CLS, RLS).
- **Consequências:** a ponte faz-se **sem cópia** pelo SQL analytics endpoint (`LH_Silver.dbo.tabela`).
  A sincronização de metadados do endpoint é assíncrona, por isso o orquestrador força-a antes da Gold.
- **Alternativa:** Gold também em Lakehouse (Spark). Mais simples, mas sem transações multi-tabela nem
  segurança T-SQL. Válida se a equipa for só Python.

### ADR-03 · Notebooks sem *default lakehouse*
- **Decisão:** todos os acessos por caminhos `abfss://<workspace>@onelake…/<lakehouse>/Tables/dbo/<tabela>`,
  resolvidos por nome no workspace atual.
- **Consequências:** o mesmo código corre em DEV e PRD sem regras de implementação nem edições, e
  o `runMultiple` funciona sem conflitos de lakehouse.

### ADR-04 · Ingestão metadata-driven e idempotente
- **Decisão:** a configuração (`NB_Config`) define entidades, padrões de ficheiro, chaves e regras. A Bronze
  regista cada ficheiro em `ops_ficheiros_processados` e move-o para `Files/arquivo/`.
- **Consequências:** reexecutar não duplica e nova fonte = configuração + função de transformação.

### ADR-05 · Incremental por watermark + MERGE com hash
- **Decisão:** a Silver lê só a Bronze nova (`_data_ingestao > watermark`), faz MERGE por chave de negócio
  e só atualiza se o `_hash_linha` mudou. A Gold lê só a Silver alterada (`_data_processamento`).
- **Consequências:** custo proporcional ao volume novo. O watermark só avança quando o passo termina
  com sucesso (falha → repete o lote).
- **Watermarks em *append*** (máximo por entidade): sem conflitos de concorrência Delta quando as
  entidades correm em paralelo, e com histórico completo.

### ADR-06 · Qualidade de dados declarativa com quarentena
- **Decisão:** regras SQL por entidade com ação `rejeitar` (vai para `ops_quarentena` com o motivo) ou
  `alertar` (passa e é contada). Na Gold, testes **bloqueantes** fazem falhar o pipeline.
- **Consequências:** dados maus nunca chegam ao relatório e nunca se perdem (podem ser corrigidos e reprocessados).
- **Alternativa:** Great Expectations / Soda. Mais completo, mas mais uma dependência. A abordagem atual cobre o essencial.

### ADR-07 · SCD tipo 2 em `dim_cliente`
- **Contexto:** o Marketing quer saber em que segmento o cliente estava quando foi contactado.
- **Decisão:** atributos tipo 2 = segmento, escalão de rendimento, distrito/região e consentimento. Os factos
  ligam-se à **versão válida na data do evento**. A validade vem da data de extração do ficheiro.
- **Consequências:** análises históricas corretas e auditoria RGPD do consentimento à data do envio. A dimensão cresce com as alterações.

### ADR-08 · Chaves substitutas com IDENTITY e membro desconhecido
- **Decisão:** `sk_*` `BIGINT IDENTITY` nas dimensões. A linha "Desconhecido" (id de negócio -1) é usada quando o lookup falha.
- **Consequências:** os factos nunca ficam órfãos no relatório. Os valores IDENTITY não são sequenciais
  nem previsíveis, por isso o membro desconhecido é procurado pelo id de negócio e nunca por `sk = -1`.

### ADR-09 · Orquestração: pipeline + DAG em notebook
- **Decisão:** o pipeline tem 3 passos (Lakehouse, Gold, modelo) com alertas. Dentro do passo Lakehouse,
  `runMultiple` executa Bronze e Silver por entidade em paralelo, com dependências e *retries*, **numa só sessão Spark**.
- **Consequências:** menos arranques de sessão (mais rápido, menos CU) e paralelismo controlado.

### ADR-10 · Direct Lake e modelo como código
- **Decisão:** modelo semântico Direct Lake sobre `WH_Gold`. A lógica (medidas, relações, RLS, formatos)
  é aplicada por `NB_40` com semantic-link-labs.
- **Consequências:** desempenho de importação sem cópias nem refresh agendado, e lógica versionada e
  reaplicável. A RLS fica no modelo, porque RLS no Warehouse faria o Direct Lake recorrer a DirectQuery.

### ADR-11 · Atribuição de conversões
- **Decisão:** atribuição *last-touch*. Se houve clique → "Clique"; senão, contacto entregue até 30 dias antes → "Janela 30 dias".
- **Consequências:** simples e explicável. Sobrevaloriza canais de fim de funil. A evolução natural é a
  atribuição multi-toque ou os modelos de *uplift* (ver próximos passos).

## Próximos passos (roadmap)
1. Fontes reais: *Copy job* / *Mirroring* do CRM e atalhos OneLake para a plataforma de envios.
2. Modelo de propensão (MLflow no Fabric) → `gold.cliente_propensao`.
3. *Data Activator*: alerta quando o CPA de uma campanha passar o limite.
4. Etiquetas de sensibilidade (Purview) e *endorsement* (Certificado) no modelo.
5. Notebooks Python puros (sem Spark) para entidades pequenas: menos CU.
