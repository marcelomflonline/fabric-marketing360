# %% [markdown]
# # NB_Transformacoes — regras de negócio da camada Silver (funções puras)
# Incluído com `%run NB_Transformacoes`. Só depende de PySpark (sem `notebookutils`, sem caminhos),
# por isso é **testado automaticamente** em `tests/` com pytest e um Spark local.
#
# Convenção: `transformar_<entidade>(df_bronze, ctx) -> DataFrame` recebe as linhas Bronze novas
# (texto em bruto) e devolve-as tipadas, normalizadas e deduplicadas, ANTES das regras de qualidade.
# `ctx` é um dicionário com dados de referência (ex.: campanhas e clientes Silver atuais).

# %%
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType

# ----------------------------------------------------------------------------------
# Funções utilitárias
# ----------------------------------------------------------------------------------

def para_data(col_name: str):
    """Converte texto em data aceitando yyyy-MM-dd e dd/MM/yyyy."""
    c = F.trim(F.col(col_name))
    return F.coalesce(F.to_date(c, "yyyy-MM-dd"), F.to_date(c, "dd/MM/yyyy"))


def para_decimal(col_name: str, precisao: int = 18, escala: int = 2):
    """Aceita vírgula ou ponto como separador decimal."""
    return F.regexp_replace(F.trim(F.col(col_name)), ",", ".").cast(DecimalType(precisao, escala))


def mapear(col_name: str, dicionario: dict, por_omissao: str | None = None):
    """Normaliza valores com {chave_em_minúsculas: valor_canónico}."""
    mapa = F.create_map(*[F.lit(x) for kv in dicionario.items() for x in kv])
    chave = F.lower(F.trim(F.col(col_name)))
    fallback = F.lit(por_omissao) if por_omissao is not None else F.trim(F.col(col_name))
    return F.coalesce(mapa[chave], fallback)


def texto_ou_nulo(col_name: str):
    """Trim; string vazia passa a NULL."""
    return F.nullif(F.trim(F.col(col_name)), F.lit(""))


def hash_colunas(colunas: list[str]):
    """SHA-256 estável de um conjunto de colunas (deteção de alterações)."""
    return F.sha2(F.concat_ws("||", *[F.coalesce(F.col(c).cast("string"), F.lit("<null>")) for c in colunas]), 256)


def deduplicar_ultimo(df: DataFrame, chaves: list[str]) -> DataFrame:
    """Mantém a versão mais recente de cada chave (último ficheiro, última linha)."""
    ordem = [F.col("_data_extracao").desc_nulls_last(), F.col("_data_ingestao").desc(), F.col("_linha").desc()]
    w = Window.partitionBy(*chaves).orderBy(*ordem)
    return df.withColumn("_rn", F.row_number().over(w)).filter("_rn = 1").drop("_rn")


COLUNAS_LINHAGEM = ["_id_lote", "_ficheiro_origem", "_data_extracao"]

# ----------------------------------------------------------------------------------
# Qualidade de dados
# ----------------------------------------------------------------------------------

def aplicar_regras_qualidade(df: DataFrame, regras: list[dict]):
    """
    Avalia as regras (expressões SQL booleanas). Uma regra com resultado NULL conta como falha.
    Devolve (validos, rejeitados, resumo):
      - validos: linhas que passam todas as regras 'rejeitar' (colunas auxiliares removidas)
      - rejeitados: linhas que falham pelo menos uma regra 'rejeitar', com a coluna `_regras_falhadas`
      - resumo: lista de dicts {regra, acao, falhas}
    """
    if not regras:
        return df, df.limit(0).withColumn("_regras_falhadas", F.lit(None).cast("string")), []

    aux = df
    nomes = []
    for i, r in enumerate(regras):
        nome_col = f"_dq_{i}"
        aux = aux.withColumn(nome_col, F.coalesce(F.expr(r["expressao"]).cast("boolean"), F.lit(False)))
        nomes.append(nome_col)

    rej_cols = [f"_dq_{i}" for i, r in enumerate(regras) if r["acao"] == "rejeitar"]
    falhadas = F.concat_ws(",", *[F.when(~F.col(f"_dq_{i}"), F.lit(r["nome"])) for i, r in enumerate(regras)
                                  if r["acao"] == "rejeitar"])
    passa = F.lit(True)
    for c in rej_cols:
        passa = passa & F.col(c)
    aux = aux.withColumn("_passa", passa).withColumn("_regras_falhadas", falhadas)

    contagens = aux.agg(*[F.sum(F.when(~F.col(f"_dq_{i}"), 1).otherwise(0)).alias(f"_dq_{i}")
                          for i in range(len(regras))]).collect()[0]
    resumo = [{"regra": r["nome"], "acao": r["acao"], "falhas": int(contagens[f"_dq_{i}"] or 0)}
              for i, r in enumerate(regras)]

    remover = nomes + ["_passa", "_regras_falhadas"]
    validos = aux.filter("_passa").drop(*remover)
    rejeitados = aux.filter("NOT _passa").drop(*nomes, "_passa")
    return validos, rejeitados, resumo

# ----------------------------------------------------------------------------------
# Dados de referência
# ----------------------------------------------------------------------------------

DISTRITOS = ["Lisboa", "Porto", "Setúbal", "Braga", "Aveiro", "Leiria", "Coimbra", "Faro", "Santarém", "Viseu",
             "Madeira", "Açores", "Viana do Castelo", "Évora", "Castelo Branco", "Vila Real", "Guarda", "Beja",
             "Bragança", "Portalegre"]
REGIAO = {"Lisboa": "Grande Lisboa", "Setúbal": "Grande Lisboa", "Porto": "Norte", "Braga": "Norte",
          "Viana do Castelo": "Norte", "Vila Real": "Norte", "Bragança": "Norte", "Aveiro": "Centro",
          "Leiria": "Centro", "Coimbra": "Centro", "Viseu": "Centro", "Guarda": "Centro",
          "Castelo Branco": "Centro", "Santarém": "Centro", "Évora": "Alentejo", "Beja": "Alentejo",
          "Portalegre": "Alentejo", "Faro": "Algarve", "Madeira": "Ilhas", "Açores": "Ilhas"}
CANAIS = {"email": "Email", "e-mail": "Email", "sms": "SMS", "push app": "Push App", "push": "Push App",
          "redes sociais": "Redes Sociais", "display": "Display", "balcão": "Balcão", "balcao": "Balcão"}
TIPO_CANAL = {"Email": "Digital próprio", "SMS": "Digital próprio", "Push App": "Digital próprio",
              "Redes Sociais": "Media paga", "Display": "Media paga", "Balcão": "Presencial"}

# ----------------------------------------------------------------------------------
# Transformações por entidade
# ----------------------------------------------------------------------------------

def transformar_produtos(df: DataFrame, ctx: dict | None = None) -> DataFrame:
    df = deduplicar_ultimo(df.withColumn("id_produto", F.col("id_produto").cast("int")), ["id_produto"])
    return df.select(
        "id_produto",
        texto_ou_nulo("nome_produto").alias("nome_produto"),
        texto_ou_nulo("categoria").alias("categoria"),
        para_decimal("margem_estimada", 9, 4).alias("margem_estimada"),
        *COLUNAS_LINHAGEM)


def transformar_campanhas(df: DataFrame, ctx: dict | None = None) -> DataFrame:
    df = deduplicar_ultimo(df.withColumn("id_campanha", texto_ou_nulo("id_campanha")), ["id_campanha"])
    df = (df.withColumn("canal", mapear("canal", CANAIS))
            .withColumn("tipo_canal", mapear("canal", {k.lower(): v for k, v in TIPO_CANAL.items()}, "Outro")))
    return (df.select(
                "id_campanha",
                texto_ou_nulo("nome_campanha").alias("nome_campanha"),
                F.col("id_produto").cast("int").alias("id_produto"),
                "canal", "tipo_canal",
                texto_ou_nulo("objetivo").alias("objetivo"),
                texto_ou_nulo("segmento_alvo").alias("segmento_alvo"),
                para_data("data_inicio").alias("data_inicio"),
                para_data("data_fim").alias("data_fim"),
                para_decimal("orcamento").alias("orcamento"),
                *COLUNAS_LINHAGEM)
            .withColumn("duracao_dias", F.datediff("data_fim", "data_inicio") + 1))


def transformar_clientes(df: DataFrame, ctx: dict | None = None) -> DataFrame:
    data_ref = (ctx or {}).get("data_referencia")
    ref = F.to_date(F.lit(data_ref)) if data_ref else F.coalesce(F.col("_data_extracao"), F.current_date())
    df = deduplicar_ultimo(df.withColumn("id_cliente", F.col("id_cliente").cast("int")), ["id_cliente"])
    df = (df
        .withColumn("distrito", mapear("distrito", {d.lower(): d for d in DISTRITOS}, "Desconhecido"))
        .withColumn("regiao", mapear("distrito", {k.lower(): v for k, v in REGIAO.items()}, "Desconhecida"))
        .withColumn("segmento", F.coalesce(texto_ou_nulo("segmento"), F.lit("Desconhecido")))
        .withColumn("genero", F.coalesce(texto_ou_nulo("genero"), F.lit("N/D")))
        .withColumn("canal_preferido", F.coalesce(texto_ou_nulo("canal_preferido"), F.lit("Desconhecido")))
        .withColumn("escalao_rendimento", F.coalesce(texto_ou_nulo("escalao_rendimento"), F.lit("Desconhecido")))
        .withColumn("data_nascimento", para_data("data_nascimento"))
        .withColumn("data_adesao", para_data("data_adesao"))
        .withColumn("idade", F.floor(F.months_between(ref, "data_nascimento") / 12).cast("int"))
        .withColumn("faixa_etaria", F.when(F.col("idade") < 25, "18-24").when(F.col("idade") < 35, "25-34")
                                     .when(F.col("idade") < 45, "35-44").when(F.col("idade") < 55, "45-54")
                                     .when(F.col("idade") < 65, "55-64").otherwise("65+"))
        .withColumn("antiguidade_anos", F.floor(F.months_between(ref, "data_adesao") / 12).cast("int"))
        .withColumn("consentimento_marketing", F.upper(F.trim("consentimento_marketing")) == "S")
        .withColumn("tem_email", F.col("tem_email").cast("int") == 1)
        .withColumn("tem_app", F.col("tem_app").cast("int") == 1))
    # Atributos que geram nova versão na dimensão (SCD tipo 2) vs. que são só sobrepostos (tipo 1)
    scd2 = ["segmento", "escalao_rendimento", "distrito", "consentimento_marketing"]
    scd1 = ["genero", "canal_preferido", "tem_email", "tem_app", "data_nascimento", "data_adesao"]
    return (df
        .withColumn("hash_scd2", hash_colunas(scd2))
        .withColumn("hash_scd1", hash_colunas(scd1))
        .select("id_cliente", "data_nascimento", "idade", "faixa_etaria", "genero", "distrito", "regiao",
                "segmento", "canal_preferido", "escalao_rendimento", "data_adesao", "antiguidade_anos",
                "consentimento_marketing", "tem_email", "tem_app", "hash_scd2", "hash_scd1",
                *COLUNAS_LINHAGEM))


def _marcar_existencia(df: DataFrame, ref: DataFrame | None, chave: str, nome_flag: str,
                       extra: str | None = None, nome_extra: str | None = None) -> DataFrame:
    """Acrescenta flag booleana: a chave existe na tabela de referência? (integridade referencial)"""
    if ref is None:
        df = df.withColumn(nome_flag, F.lit(True))
        return df.withColumn(nome_extra, F.lit(True)) if nome_extra else df
    cols = [F.col(chave).alias(f"_ref_{chave}"), F.lit(True).alias(nome_flag)]
    if extra:
        cols.append(F.col(extra).cast("boolean").alias(nome_extra))
    r = ref.select(*cols).dropDuplicates([f"_ref_{chave}"])
    out = df.join(r, df[chave] == r[f"_ref_{chave}"], "left").drop(f"_ref_{chave}")
    out = out.withColumn(nome_flag, F.coalesce(F.col(nome_flag), F.lit(False)))
    if nome_extra:
        out = out.withColumn(nome_extra, F.coalesce(F.col(nome_extra), F.lit(False)))
    return out


def transformar_contactos(df: DataFrame, ctx: dict | None = None) -> DataFrame:
    ctx = ctx or {}
    df = deduplicar_ultimo(df.withColumn("id_contacto", texto_ou_nulo("id_contacto")), ["id_contacto"])
    df = df.select(
        "id_contacto",
        texto_ou_nulo("id_campanha").alias("id_campanha"),
        F.col("id_cliente").cast("int").alias("id_cliente"),
        F.to_timestamp(F.trim("data_hora_envio"), "yyyy-MM-dd HH:mm:ss").alias("data_hora_envio"),
        F.col("flag_entregue").cast("int").alias("flag_entregue"),
        F.col("flag_aberto").cast("int").alias("flag_aberto"),
        F.col("flag_clicado").cast("int").alias("flag_clicado"),
        *COLUNAS_LINHAGEM)
    df = (df.withColumn("data_envio", F.to_date("data_hora_envio"))
            .withColumn("hora_envio", F.hour("data_hora_envio")))
    df = _marcar_existencia(df, ctx.get("campanhas"), "id_campanha", "_campanha_existe")
    df = _marcar_existencia(df, ctx.get("clientes"), "id_cliente", "_cliente_existe",
                            "consentimento_marketing", "_cliente_consentiu")
    return df


def transformar_conversoes(df: DataFrame, ctx: dict | None = None) -> DataFrame:
    ctx = ctx or {}
    df = deduplicar_ultimo(df.withColumn("id_conversao", texto_ou_nulo("id_conversao")), ["id_conversao"])
    df = df.select(
        "id_conversao",
        texto_ou_nulo("id_contacto").alias("id_contacto"),
        F.col("id_cliente").cast("int").alias("id_cliente"),
        texto_ou_nulo("id_campanha").alias("id_campanha"),
        F.col("id_produto").cast("int").alias("id_produto"),
        para_data("data_conversao").alias("data_conversao"),
        para_decimal("valor_contratado").alias("valor_contratado"),
        texto_ou_nulo("canal_conversao").alias("canal_conversao"),
        *COLUNAS_LINHAGEM)
    return _marcar_existencia(df, ctx.get("campanhas"), "id_campanha", "_campanha_existe")


def transformar_custos_campanha(df: DataFrame, ctx: dict | None = None) -> DataFrame:
    ctx = ctx or {}
    df = (df.withColumn("id_campanha", texto_ou_nulo("id_campanha"))
            .withColumn("data", para_data("data")))
    df = deduplicar_ultimo(df, ["id_campanha", "data"])
    df = df.select("id_campanha", "data",
                   para_decimal("custo").alias("custo"),
                   F.col("impressoes").cast("long").alias("impressoes"),
                   *COLUNAS_LINHAGEM)
    return _marcar_existencia(df, ctx.get("campanhas"), "id_campanha", "_campanha_existe")


def gerar_calendario(spark, inicio: str = "2024-01-01", fim: str = "2027-12-31") -> DataFrame:
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
             "Setembro", "Outubro", "Novembro", "Dezembro"]
    dias = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]  # dayofweek: 1 = domingo
    return (spark.sql(f"SELECT explode(sequence(to_date('{inicio}'), to_date('{fim}'), interval 1 day)) AS data")
        .withColumn("id_data", F.date_format("data", "yyyyMMdd").cast("int"))
        .withColumn("ano", F.year("data"))
        .withColumn("trimestre", F.concat(F.lit("T"), F.quarter("data")))
        .withColumn("ano_trimestre", F.concat(F.year("data"), F.lit(" T"), F.quarter("data")))
        .withColumn("num_mes", F.month("data"))
        .withColumn("mes", F.element_at(F.array(*[F.lit(m) for m in meses]), F.month("data")))
        .withColumn("mes_abrev", F.substring("mes", 1, 3))
        .withColumn("ano_mes", F.date_format("data", "yyyy-MM"))
        .withColumn("semana_iso", F.weekofyear("data"))
        .withColumn("dia_semana", F.element_at(F.array(*[F.lit(d) for d in dias]), F.dayofweek("data")))
        .withColumn("num_dia_semana", ((F.dayofweek("data") + 5) % 7) + 1)   # 1 = segunda … 7 = domingo
        .withColumn("fim_de_semana", F.dayofweek("data").isin(1, 7)))


TRANSFORMACOES = {
    "produtos": transformar_produtos,
    "campanhas": transformar_campanhas,
    "clientes": transformar_clientes,
    "contactos": transformar_contactos,
    "conversoes": transformar_conversoes,
    "custos_campanha": transformar_custos_campanha,
}
