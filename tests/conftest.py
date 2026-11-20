"""Fixtures partilhadas: Spark local e carregamento das funções dos notebooks."""
import os
import re
import pathlib
import pytest
from pyspark.sql import SparkSession

RAIZ = pathlib.Path(__file__).resolve().parents[1]
NOTEBOOKS = RAIZ / "src" / "notebooks"


def carregar_notebook(nome: str, contexto: dict) -> dict:
    """Executa um notebook .py (formato percent) ignorando magics (%run, %pip) e devolve o namespace."""
    codigo = (NOTEBOOKS / f"{nome}.py").read_text(encoding="utf-8")
    codigo = re.sub(r"^# MAGIC %.*$", "", codigo, flags=re.M)
    exec(compile(codigo, f"{nome}.py", "exec"), contexto)
    return contexto


@pytest.fixture(scope="session")
def spark():
    os.environ.setdefault("PYSPARK_PYTHON", "python3")
    s = (SparkSession.builder.master("local[2]").appName("testes-marketing360")
         .config("spark.sql.shuffle.partitions", "2")
         .config("spark.ui.enabled", "false")
         .config("spark.sql.session.timeZone", "UTC")
         .getOrCreate())
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()


@pytest.fixture(scope="session")
def nb(spark):
    """Namespace com NB_Config + NB_Transformacoes carregados."""
    ns = {"spark": spark}
    carregar_notebook("NB_Config", ns)
    carregar_notebook("NB_Transformacoes", ns)
    return ns


def bronze(spark, linhas: list[dict], data_extracao="2025-11-30", ficheiro="f_20251130.csv"):
    """Cria um DataFrame no formato Bronze (tudo string + colunas de linhagem)."""
    from pyspark.sql import functions as F
    cols = list(linhas[0].keys())
    df = spark.createDataFrame([[None if r.get(c) is None else str(r.get(c)) for c in cols] for r in linhas],
                               ", ".join(f"`{c}` string" for c in cols))
    return (df.withColumn("_id_lote", F.lit("teste"))
              .withColumn("_ficheiro_origem", F.lit(ficheiro))
              .withColumn("_data_extracao", F.to_date(F.lit(data_extracao)))
              .withColumn("_data_ingestao", F.current_timestamp())
              .withColumn("_linha", F.monotonically_increasing_id()))
