# %% [markdown]
# # NB_Utils — funções de plataforma (OneLake, Delta, controlo e logging)
# Incluído com `%run NB_Utils` **depois** de `%run NB_Config`.
#
# Boas práticas aplicadas:
# - **Sem default lakehouse**: tudo por caminhos OneLake `abfss://` resolvidos por nome → os mesmos
#   notebooks funcionam em DEV e PRD sem alterações (só muda o workspace).
# - **Idempotência**: ficheiros já processados são ignorados; MERGE por chave; watermarks.
# - **Observabilidade**: cada passo escreve em `ops_log_execucao`.
# - **Modo local**: sem `notebookutils` (ex.: testes/CI), usa uma pasta local e Parquet.

# %%
import os
import json
import time
import uuid
import traceback
from datetime import datetime, timezone
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

try:
    import notebookutils  # disponível nos notebooks Fabric
    MODO_LOCAL = False
except ImportError:
    notebookutils = None
    MODO_LOCAL = True

try:
    from delta.tables import DeltaTable
    TEM_DELTA = True
except ImportError:
    TEM_DELTA = False

# No Fabric: sempre Delta. Localmente: Parquet (ou Delta se FABRIC_LOCAL_DELTA=1 e houver os JARs).
FORMATO = "delta" if not MODO_LOCAL else ("delta" if TEM_DELTA and os.environ.get("FABRIC_LOCAL_DELTA") == "1" else "parquet")
RAIZ_LOCAL = os.environ.get("FABRIC_LOCAL_ROOT", "/tmp/fabric_local")

# %% [markdown]
# ## Caminhos OneLake

# %%
_cache_ids: dict = {}

def _id_workspace() -> str:
    return notebookutils.runtime.context["currentWorkspaceId"]


def _id_item(nome: str) -> str:
    if nome not in _cache_ids:
        item = notebookutils.lakehouse.get(nome)
        _cache_ids[nome] = item["id"] if isinstance(item, dict) else item.id
    return _cache_ids[nome]


def caminho_lakehouse(lakehouse: str) -> str:
    if MODO_LOCAL:
        return f"{RAIZ_LOCAL}/{lakehouse}"
    return f"abfss://{_id_workspace()}@onelake.dfs.fabric.microsoft.com/{_id_item(lakehouse)}"


def caminho_tabela(lakehouse: str, tabela: str) -> str:
    base = caminho_lakehouse(lakehouse)
    return f"{base}/Tables/{ESQUEMA}/{tabela}" if USA_ESQUEMAS else f"{base}/Tables/{tabela}"


def caminho_ficheiros(lakehouse: str, relativo: str = "") -> str:
    return f"{caminho_lakehouse(lakehouse)}/Files/{relativo}".rstrip("/")

# %% [markdown]
# ## Leitura e escrita de tabelas

# %%
def tabela_existe(caminho: str) -> bool:
    if FORMATO == "delta":
        return DeltaTable.isDeltaTable(spark, caminho)
    return os.path.exists(caminho.replace("file:", ""))


def ler_tabela(lakehouse: str, tabela: str) -> DataFrame | None:
    c = caminho_tabela(lakehouse, tabela)
    return spark.read.format(FORMATO).load(c) if tabela_existe(c) else None


def acrescentar(df: DataFrame, lakehouse: str, tabela: str) -> None:
    (df.write.format(FORMATO).mode("append").option("mergeSchema", "true")
       .save(caminho_tabela(lakehouse, tabela)))


def substituir(df: DataFrame, lakehouse: str, tabela: str) -> None:
    (df.write.format(FORMATO).mode("overwrite").option("overwriteSchema", "true")
       .save(caminho_tabela(lakehouse, tabela)))


def upsert(df: DataFrame, lakehouse: str, tabela: str, chaves: list[str], ignorar_no_hash=()) -> dict:
    """
    MERGE por chave de negócio. Só atualiza linhas cujo conteúdo mudou (hash), para que
    `_data_processamento` reflita alterações reais e a Gold carregue apenas o necessário.
    Devolve métricas {inseridas, atualizadas}.
    """
    colunas_negocio = [c for c in df.columns if not c.startswith("_") and c not in ignorar_no_hash]
    df = (df.withColumn("_hash_linha", F.sha2(F.concat_ws("||", *[F.coalesce(F.col(c).cast("string"), F.lit("<null>"))
                                                                  for c in colunas_negocio]), 256))
            .withColumn("_data_processamento", F.current_timestamp()))
    caminho = caminho_tabela(lakehouse, tabela)

    if not tabela_existe(caminho):
        df.write.format(FORMATO).save(caminho)
        return {"inseridas": df.count(), "atualizadas": 0}

    if FORMATO == "delta":
        alvo = DeltaTable.forPath(spark, caminho)
        cond = " AND ".join(f"t.`{k}` <=> s.`{k}`" for k in chaves)
        (alvo.alias("t").merge(df.alias("s"), cond)
             .whenMatchedUpdateAll(condition="t._hash_linha <> s._hash_linha")
             .whenNotMatchedInsertAll()
             .execute())
        m = alvo.history(1).select("operationMetrics").collect()[0][0]
        return {"inseridas": int(m.get("numTargetRowsInserted", 0)), "atualizadas": int(m.get("numTargetRowsUpdated", 0))}

    # Modo local sem Delta: emula o MERGE (só para testes)
    atual = spark.read.parquet(caminho).cache()
    atual.count()
    j = df.alias("s").join(atual.select(*chaves, "_hash_linha").alias("t"), chaves, "left")
    novos = j.filter(F.col("t._hash_linha").isNull()).select("s.*")
    alterados = j.filter(F.col("t._hash_linha").isNotNull() & (F.col("t._hash_linha") != F.col("s._hash_linha"))).select("s.*")
    mudancas = novos.unionByName(alterados)
    resultado = atual.join(mudancas.select(*chaves), chaves, "left_anti").unionByName(mudancas, allowMissingColumns=True)
    n_ins, n_upd = novos.count(), alterados.count()
    resultado.write.mode("overwrite").parquet(caminho + "_tmp")
    spark.read.parquet(caminho + "_tmp").write.mode("overwrite").parquet(caminho)
    return {"inseridas": n_ins, "atualizadas": n_upd}

# %% [markdown]
# ## Ficheiros (landing → arquivo)

# %%
def listar_ficheiros(pasta: str) -> list[tuple[str, str]]:
    """Lista (nome, caminho) dos ficheiros de uma pasta; pasta inexistente → lista vazia."""
    if MODO_LOCAL:
        p = pasta
        if not os.path.isdir(p):
            return []
        return sorted((f, f"{p}/{f}") for f in os.listdir(p) if os.path.isfile(f"{p}/{f}"))
    try:
        return sorted((f.name, f.path) for f in notebookutils.fs.ls(pasta) if f.isFile)
    except Exception:
        return []


def mover_ficheiro(origem: str, destino: str) -> None:
    if MODO_LOCAL:
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        os.replace(origem, destino)
    else:
        notebookutils.fs.mv(origem, destino, True)


def escrever_texto(caminho: str, conteudo: str) -> None:
    if MODO_LOCAL:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(conteudo)
    else:
        notebookutils.fs.put(caminho, conteudo, True)

# %% [markdown]
# ## Controlo: watermarks e logging

# %%
def obter_watermark(entidade: str, camada: str):
    """Último valor processado. A tabela é só de *append* (histórico completo e sem conflitos de
    concorrência quando várias entidades correm em paralelo); o watermark é o máximo."""
    wm = ler_tabela(LH_SILVER, OPS_WATERMARK)
    if wm is None:
        return None
    r = (wm.filter((F.col("entidade") == entidade) & (F.col("camada") == camada))
           .agg(F.max("valor")).collect())
    return r[0][0] if r else None


def definir_watermark(entidade: str, camada: str, valor, id_lote: str = None) -> None:
    if valor is None:
        return
    df = spark.createDataFrame([(entidade, camada, valor, id_lote)],
                               "entidade string, camada string, valor timestamp, id_lote string")
    acrescentar(df.withColumn("data_registo", F.current_timestamp()), LH_SILVER, OPS_WATERMARK)


class Execucao:
    """Context manager que regista início/fim/erro de um passo em ops_log_execucao."""

    def __init__(self, id_lote: str, camada: str, entidade: str):
        self.id_lote, self.camada, self.entidade = id_lote, camada, entidade
        self.metricas: dict = {}

    def __enter__(self):
        self.inicio = datetime.now(timezone.utc).replace(tzinfo=None)
        self.t0 = time.time()
        return self

    def __exit__(self, tipo, erro, tb):
        estado = "OK" if erro is None else "ERRO"
        msg = None if erro is None else "".join(traceback.format_exception_only(tipo, erro))[:4000]
        linha = [(str(uuid.uuid4()), self.id_lote, self.camada, self.entidade, estado,
                  self.inicio, datetime.now(timezone.utc).replace(tzinfo=None), round(time.time() - self.t0, 1),
                  json.dumps(self.metricas, default=str), msg)]
        esquema = ("id_execucao string, id_lote string, camada string, entidade string, estado string, "
                   "inicio timestamp, fim timestamp, duracao_seg double, metricas string, erro string")
        try:
            acrescentar(spark.createDataFrame(linha, esquema), LH_SILVER, OPS_LOG)
        except Exception as e:  # o logging nunca deve esconder o erro original
            print("⚠ Falha a escrever log:", e)
        icone = "✔" if estado == "OK" else "✖"
        print(f"{icone} [{self.camada}] {self.entidade}: {estado} em {time.time() - self.t0:.1f}s {self.metricas}")
        return False  # propaga a exceção → o pipeline falha e alerta

# %% [markdown]
# ## SQL analytics endpoint
# A Gold (Warehouse) lê a Silver pelo SQL analytics endpoint, cuja sincronização de metadados é
# assíncrona. Forçamos a sincronização antes de chamar o procedimento de carga.

# %%
def sincronizar_sql_endpoint(lakehouse: str = None) -> None:
    lakehouse = lakehouse or LH_SILVER
    if MODO_LOCAL:
        return
    try:
        import sempy.fabric as fabric
        ws = fabric.get_workspace_id()
        lh_id = fabric.resolve_item_id(lakehouse, "Lakehouse")
        cli = fabric.FabricRestClient()
        props = cli.get(f"v1/workspaces/{ws}/lakehouses/{lh_id}").json()["properties"]
        sql_id = props["sqlEndpointProperties"]["id"]
        r = cli.post(f"v1/workspaces/{ws}/sqlEndpoints/{sql_id}/refreshMetadata", json={})
        print(f"SQL endpoint de {lakehouse}: pedido de sincronização HTTP {r.status_code}")
        if r.status_code == 202:   # operação longa: aguardar
            time.sleep(20)
    except Exception as e:
        print("⚠ Sincronização não forçada (o endpoint sincroniza sozinho em ~1-2 min):", e)

# %% [markdown]
# ## Tabelas operacionais
# Criadas vazias antes de qualquer execução paralela (evita conflitos de criação simultânea).

# %%
ESQUEMAS_OPS = {
    OPS_FICHEIROS: "entidade string, nome_ficheiro string, linhas long, id_lote string, data_processamento timestamp",
    OPS_WATERMARK: "entidade string, camada string, valor timestamp, id_lote string, data_registo timestamp",
    OPS_QUARENTENA: ("entidade string, chave string, registo string, regras_falhadas string, ficheiro_origem string, "
                     "id_lote string, data_quarentena timestamp, resolvido boolean"),
    OPS_QUALIDADE: ("entidade string, regra string, acao string, falhas long, linhas_avaliadas long, "
                    "id_lote string, data_avaliacao timestamp"),
    OPS_LOG: ("id_execucao string, id_lote string, camada string, entidade string, estado string, "
              "inicio timestamp, fim timestamp, duracao_seg double, metricas string, erro string"),
}


def inicializar_tabelas_ops() -> None:
    for tabela, esquema in ESQUEMAS_OPS.items():
        if not tabela_existe(caminho_tabela(LH_SILVER, tabela)):
            spark.createDataFrame([], esquema).write.format(FORMATO).save(caminho_tabela(LH_SILVER, tabela))
            print("criada:", tabela)
