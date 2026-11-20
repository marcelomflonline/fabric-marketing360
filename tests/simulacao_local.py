"""
Simulação local ponta-a-ponta da camada Lakehouse (sem Fabric):
carga inicial → 2 dias incrementais → reexecução (idempotência).
Usa Parquet em vez de Delta (o MERGE é emulado em NB_Utils quando não há Delta).

    python tests/simulacao_local.py
"""
import os
import re
import sys
import shutil
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
NB = RAIZ / "src" / "notebooks"
os.environ.setdefault("FABRIC_LOCAL_ROOT", "/tmp/fabric_local")
shutil.rmtree(os.environ["FABRIC_LOCAL_ROOT"], ignore_errors=True)

from pyspark.sql import SparkSession, functions as F  # noqa: E402

spark = (SparkSession.builder.master("local[4]").config("spark.sql.shuffle.partitions", "4")
         .config("spark.ui.enabled", "false").getOrCreate())
spark.sparkContext.setLogLevel("ERROR")


def correr(nome: str, **params):
    """Executa um notebook resolvendo %run e sobrepondo a célula de parâmetros."""
    ns = {"spark": spark, "display": lambda df: df.show(50, truncate=60)}
    codigo = (NB / f"{nome}.py").read_text(encoding="utf-8")

    def incluir(m):
        return (NB / f"{m.group(1)}.py").read_text(encoding="utf-8")
    codigo = re.sub(r"^# MAGIC %run (\w+)\s*$", incluir, codigo, flags=re.M)
    codigo = re.sub(r"^# MAGIC %.*$", "", codigo, flags=re.M)
    # injeta parâmetros logo a seguir à célula de parâmetros
    atrib = "\n".join(f"{k} = {v!r}" for k, v in params.items())
    codigo = re.sub(r'(# %% tags=\["parameters"\]\n(?:.*\n)*?)(\n# %%)', lambda m: m.group(1) + atrib + "\n" + m.group(2),
                    codigo, count=1)
    print(f"\n────────── {nome} {params}")
    exec(compile(codigo, nome, "exec"), ns)
    return ns


u = {"spark": spark}
exec((NB / "NB_Config.py").read_text(), u)
exec((NB / "NB_Utils.py").read_text(), u)
u["inicializar_tabelas_ops"]()

# 1) Carga inicial
correr("NB_01_Gerar_Dados_Sinteticos", p_modo="inicial")
correr("NB_10_Bronze_Ingestao", p_id_lote="L1")
correr("NB_20_Silver_Transformacao", p_id_lote="L1")

# 2) Dois dias incrementais
for i, d in enumerate(["2025-12-01", "2025-12-02"], start=2):
    correr("NB_01_Gerar_Dados_Sinteticos", p_modo="incremental", p_data_carga=d)
    correr("NB_10_Bronze_Ingestao", p_id_lote=f"L{i}")
    correr("NB_20_Silver_Transformacao", p_id_lote=f"L{i}")

# 3) Reexecução sem ficheiros novos → nada deve mudar
correr("NB_10_Bronze_Ingestao", p_id_lote="L4")
correr("NB_20_Silver_Transformacao", p_id_lote="L4")

# Verificações
ler = lambda lh, t: u["ler_tabela"](lh, t)  # noqa: E731
print("\n══════════ RESULTADOS")
for t in ["produtos", "campanhas", "clientes", "contactos", "conversoes", "custos_campanha", "calendario"]:
    print(f"silver.{t:16s} {ler('LH_Silver', t).count():>8,}")
log = ler("LH_Silver", "ops_log_execucao")
log.groupBy("id_lote", "camada", "estado").count().orderBy("id_lote", "camada").show()
ler("LH_Silver", "ops_quarentena").groupBy("entidade", "regras_falhadas", "id_lote").count().orderBy("id_lote").show(truncate=False)
q = ler("LH_Silver", "ops_resultado_qualidade").filter("falhas > 0")
q.select("id_lote", "entidade", "regra", "acao", "falhas").orderBy("id_lote", "entidade").show(40, truncate=False)

erros = log.filter("estado = 'ERRO'").count()
dup = ler("LH_Silver", "contactos").groupBy("id_contacto").count().filter("count > 1").count()
l4 = log.filter("id_lote = 'L4' AND camada = 'silver'").select("metricas").collect()
print("erros:", erros, "| contactos duplicados na silver:", dup)
print("métricas L4 (devem indicar 0 linhas lidas):", [r[0] for r in l4][:3])
assert erros == 0 and dup == 0
assert ler("LH_Silver", "contactos").filter(F.col("id_campanha") == "CMP-9999-999").count() == 0
print("✔ simulação OK")
