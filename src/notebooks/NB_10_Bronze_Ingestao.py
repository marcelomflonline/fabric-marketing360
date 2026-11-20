# %% [markdown]
# # NB_10 — Bronze: ingestão incremental e idempotente
# Para cada entidade (ou só `p_entidade`):
# 1. lista os ficheiros em `LH_Bronze/Files/landing/<entidade>/`;
# 2. ignora os já registados em `ops_ficheiros_processados` (**idempotência**: reexecutar não duplica);
# 3. lê-os **como texto** (a Bronze não interpreta nem corrige) e acrescenta colunas de linhagem;
# 4. faz *append* na tabela Delta `LH_Bronze.<entidade>`;
# 5. regista os ficheiros e move-os para `Files/arquivo/<entidade>/AAAA/MM/`.

# %%
# MAGIC %run NB_Config

# %%
# MAGIC %run NB_Utils

# %% tags=["parameters"]
p_entidade = "todas"
p_id_lote = "manual"

# %%
import fnmatch
from pyspark.sql import functions as F

entidades = list(ENTIDADES) if p_entidade == "todas" else [p_entidade]


def ficheiros_ja_processados(entidade: str) -> set:
    t = ler_tabela(LH_SILVER, OPS_FICHEIROS)
    if t is None:
        return set()
    return {r[0] for r in t.filter(F.col("entidade") == entidade).select("nome_ficheiro").collect()}


for entidade in entidades:
    cfg = ENTIDADES[entidade]
    with Execucao(p_id_lote, "bronze", entidade) as ex:
        pasta = caminho_ficheiros(LH_BRONZE, f"{PASTA_LANDING}/{entidade}")
        todos = [(n, p) for n, p in listar_ficheiros(pasta) if fnmatch.fnmatch(n, cfg["padrao_ficheiro"])]
        feitos = ficheiros_ja_processados(entidade)
        novos = [(n, p) for n, p in todos if n not in feitos]
        ex.metricas.update(ficheiros_encontrados=len(todos), ficheiros_novos=len(novos))

        # ficheiros repetidos (já processados) saem da landing para não se acumularem
        for n, p in todos:
            if n in feitos:
                mover_ficheiro(p, caminho_ficheiros(LH_BRONZE, f"{PASTA_ARQUIVO}/{entidade}/duplicados/{n}"))

        if not novos:
            continue

        df = (spark.read
              .option("header", True).option("sep", ";").option("encoding", "UTF-8")
              .option("inferSchema", False)          # tudo como string
              .csv([p for _, p in novos]))
        df = (df
              .withColumn("_ficheiro_origem", F.col("_metadata.file_name"))
              .withColumn("_data_extracao", F.to_date(F.regexp_extract("_ficheiro_origem", r"_(\d{8})\.csv$", 1), "yyyyMMdd"))
              .withColumn("_linha", F.monotonically_increasing_id())
              .withColumn("_id_lote", F.lit(p_id_lote))
              .withColumn("_data_ingestao", F.current_timestamp()))

        contagem = {r["_ficheiro_origem"]: r["count"] for r in df.groupBy("_ficheiro_origem").count().collect()}
        acrescentar(df, LH_BRONZE, entidade)

        registo = spark.createDataFrame(
            [(entidade, n, int(contagem.get(n, 0)), p_id_lote) for n, _ in novos],
            "entidade string, nome_ficheiro string, linhas long, id_lote string"
        ).withColumn("data_processamento", F.current_timestamp())
        acrescentar(registo, LH_SILVER, OPS_FICHEIROS)

        for n, p in novos:
            data = n.rsplit("_", 1)[-1][:8]
            mover_ficheiro(p, caminho_ficheiros(LH_BRONZE, f"{PASTA_ARQUIVO}/{entidade}/{data[:4]}/{data[4:6]}/{n}"))

        ex.metricas["linhas"] = int(sum(contagem.values()))
