# %% [markdown]
# # NB_00 — Orquestrador do Lakehouse (DAG)
# Chamado pelo pipeline `PL_Marketing360_Diario`. Corre Bronze e Silver de todas as entidades numa
# **única sessão Spark** com `notebookutils.notebook.runMultiple` (DAG com dependências e paralelismo),
# o que é mais rápido e consome menos capacidade do que uma atividade de pipeline por notebook.
#
# ```
#  [gerar dados]* → bronze_<entidade> (×6, em paralelo)
#                       └→ silver_produtos, silver_campanhas, silver_clientes, silver_calendario
#                            └→ silver_contactos (campanhas, clientes)
#                                 └→ silver_conversoes (campanhas, contactos)
#                            └→ silver_custos_campanha (campanhas)
#  → sincronizar SQL endpoint do LH_Silver → (pipeline) procedimento Gold no Warehouse
# ```
# *só se `p_gerar_dados` ≠ "nao" (simulador de fontes, apenas para demonstração)

# %%
# MAGIC %run NB_Config

# %%
# MAGIC %run NB_Utils

# %% tags=["parameters"]
p_id_lote = "manual"
p_gerar_dados = "nao"          # "nao" | "inicial" | "incremental"
p_data_carga = "2025-12-01"    # usado pelo simulador em modo incremental
p_reprocessar = False
p_concorrencia = 4

# %%
import json

inicializar_tabelas_ops()

if p_gerar_dados != "nao":
    notebookutils.notebook.run("NB_01_Gerar_Dados_Sinteticos", 1800,
                               {"p_modo": p_gerar_dados, "p_data_carga": p_data_carga})

# %%
atividades = []
for ent in ENTIDADES:
    atividades.append({
        "name": f"bronze_{ent}",
        "path": "NB_10_Bronze_Ingestao",
        "timeoutPerCellInSeconds": 1200,
        "args": {"p_entidade": ent, "p_id_lote": p_id_lote},
        "retry": 1, "retryIntervalInSeconds": 30,
    })
for ent, deps in DEPENDENCIAS_SILVER.items():
    atividades.append({
        "name": f"silver_{ent}",
        "path": "NB_20_Silver_Transformacao",
        "timeoutPerCellInSeconds": 1800,
        "args": {"p_entidade": ent, "p_id_lote": p_id_lote, "p_reprocessar": p_reprocessar},
        "dependencies": [f"bronze_{ent}"] + [f"silver_{d}" for d in deps],
        "retry": 1, "retryIntervalInSeconds": 60,
    })
atividades.append({
    "name": "silver_calendario",
    "path": "NB_20_Silver_Transformacao",
    "timeoutPerCellInSeconds": 600,
    "args": {"p_entidade": "calendario", "p_id_lote": p_id_lote, "p_reprocessar": p_reprocessar},
})

DAG = {"activities": atividades, "timeoutInSeconds": 5400, "concurrency": p_concorrencia}
assert notebookutils.notebook.validateDAG(DAG), "DAG inválido"

# %%
try:
    resultado = notebookutils.notebook.runMultiple(DAG, {"displayDAGViaGraphviz": True})
finally:
    # resumo do lote a partir do log (mesmo em caso de falha)
    log = ler_tabela(LH_SILVER, OPS_LOG)
    if log is not None:
        display(log.filter(F.col("id_lote") == p_id_lote)
                   .select("camada", "entidade", "estado", "duracao_seg", "metricas", "erro")
                   .orderBy("inicio"))

# %%
sincronizar_sql_endpoint(LH_SILVER)

erros = (ler_tabela(LH_SILVER, OPS_LOG)
         .filter((F.col("id_lote") == p_id_lote) & (F.col("estado") == "ERRO")).count())
quarentena = (ler_tabela(LH_SILVER, OPS_QUARENTENA)
              .filter(F.col("id_lote") == p_id_lote).count())

notebookutils.notebook.exit(json.dumps({"id_lote": p_id_lote, "erros": erros, "linhas_em_quarentena": quarentena}))
