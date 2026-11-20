# %% [markdown]
# # NB_30 — Manutenção das tabelas Delta (agendar semanalmente)
# - **OPTIMIZE**: compacta ficheiros pequenos (cargas incrementais diárias criam muitos) → leituras
#   mais rápidas no Spark, no SQL endpoint e no Direct Lake.
# - **VACUUM**: remove ficheiros antigos já não referenciados (poupa armazenamento OneLake).
#   Retenção de 7 dias → permite *time travel* para recuperar de erros da última semana.
# - Estatísticas por tabela em `ops_log_execucao`.

# %%
# MAGIC %run NB_Config

# %%
# MAGIC %run NB_Utils

# %% tags=["parameters"]
p_id_lote = "manutencao"
p_retencao_horas = RETENCAO_VACUUM_HORAS

# %%
alvos = ([(LH_BRONZE, e) for e in ENTIDADES]
         + [(LH_SILVER, e) for e in ENTIDADES] + [(LH_SILVER, "calendario")]
         + [(LH_SILVER, t) for t in ESQUEMAS_OPS])

for lakehouse, tabela in alvos:
    caminho = caminho_tabela(lakehouse, tabela)
    if not tabela_existe(caminho):
        continue
    with Execucao(p_id_lote, "manutencao", f"{lakehouse}.{tabela}") as ex:
        dt = DeltaTable.forPath(spark, caminho)
        antes = dt.detail().select("numFiles", "sizeInBytes").collect()[0]
        dt.optimize().executeCompaction()
        dt.vacuum(p_retencao_horas)
        depois = dt.detail().select("numFiles", "sizeInBytes").collect()[0]
        ex.metricas.update(ficheiros_antes=antes[0], ficheiros_depois=depois[0],
                           mb=round(depois[1] / 1024 / 1024, 2))
