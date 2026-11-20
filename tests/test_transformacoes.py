"""Testes unitários das regras de negócio da camada Silver (NB_Transformacoes)."""
import datetime as dt
from decimal import Decimal

from conftest import bronze

CLIENTE_BASE = {
    "id_cliente": "100001", "data_nascimento": "1990-05-10", "genero": "F", "distrito": "Lisboa",
    "segmento": "Massa", "canal_preferido": "App", "data_adesao": "2015-01-01",
    "escalao_rendimento": "1000-2000", "consentimento_marketing": "S", "tem_email": "1", "tem_app": "1",
}


def test_para_data_aceita_dois_formatos(spark, nb):
    df = spark.createDataFrame([("2025-03-01",), ("01/03/2025",), ("lixo",)], "d string")
    r = [x[0] for x in df.select(nb["para_data"]("d")).collect()]
    assert r == [dt.date(2025, 3, 1), dt.date(2025, 3, 1), None]


def test_para_decimal_aceita_virgula(spark, nb):
    df = spark.createDataFrame([("1234,56",), ("10.5",)], "v string")
    assert [x[0] for x in df.select(nb["para_decimal"]("v")).collect()] == [Decimal("1234.56"), Decimal("10.50")]


def test_clientes_normaliza_distrito_e_regiao(spark, nb):
    linhas = [dict(CLIENTE_BASE, id_cliente="1", distrito="  LISBOA "),
              dict(CLIENTE_BASE, id_cliente="2", distrito="viana do castelo"),
              dict(CLIENTE_BASE, id_cliente="3", distrito="Atlântida")]
    r = {x.id_cliente: (x.distrito, x.regiao) for x in nb["transformar_clientes"](bronze(spark, linhas)).collect()}
    assert r[1] == ("Lisboa", "Grande Lisboa")
    assert r[2] == ("Viana do Castelo", "Norte")
    assert r[3] == ("Desconhecido", "Desconhecida")


def test_clientes_deduplica_mantendo_extracao_mais_recente(spark, nb):
    antigo = bronze(spark, [dict(CLIENTE_BASE, segmento="Massa")], "2025-11-30")
    novo = bronze(spark, [dict(CLIENTE_BASE, segmento="Premium")], "2025-12-01")
    r = nb["transformar_clientes"](antigo.unionByName(novo)).collect()
    assert len(r) == 1 and r[0].segmento == "Premium"


def test_clientes_segmento_nulo_e_idade(spark, nb):
    r = nb["transformar_clientes"](bronze(spark, [dict(CLIENTE_BASE, segmento=None)], "2025-12-31")).collect()[0]
    assert r.segmento == "Desconhecido"
    assert r.idade == 35 and r.faixa_etaria == "35-44"
    assert r.consentimento_marketing is True


def test_hash_scd2_so_muda_com_atributos_tipo2(spark, nb):
    f = nb["transformar_clientes"]
    base = f(bronze(spark, [CLIENTE_BASE])).collect()[0]
    tipo1 = f(bronze(spark, [dict(CLIENTE_BASE, canal_preferido="Balcão")])).collect()[0]
    tipo2 = f(bronze(spark, [dict(CLIENTE_BASE, segmento="Premium")])).collect()[0]
    assert base.hash_scd2 == tipo1.hash_scd2 and base.hash_scd1 != tipo1.hash_scd1
    assert base.hash_scd2 != tipo2.hash_scd2


def test_campanhas_normaliza_canal(spark, nb):
    linha = {"id_campanha": "C1", "nome_campanha": "x", "id_produto": "1", "canal": "sms", "objetivo": "A",
             "segmento_alvo": "Todos", "data_inicio": "2025-01-01", "data_fim": "2025-01-10", "orcamento": "100,5"}
    r = nb["transformar_campanhas"](bronze(spark, [linha])).collect()[0]
    assert (r.canal, r.tipo_canal, r.duracao_dias, r.orcamento) == ("SMS", "Digital próprio", 10, Decimal("100.50"))


def test_contactos_marca_orfaos(spark, nb):
    campanhas = spark.createDataFrame([("C1",)], "id_campanha string")
    clientes = spark.createDataFrame([(1, True)], "id_cliente int, consentimento_marketing boolean")
    base = {"id_cliente": "1", "data_hora_envio": "2025-01-01 10:00:00",
            "flag_entregue": "1", "flag_aberto": "1", "flag_clicado": "0"}
    df = bronze(spark, [dict(base, id_contacto="A", id_campanha="C1"),
                        dict(base, id_contacto="B", id_campanha="NAO-EXISTE")])
    r = {x.id_contacto: x._campanha_existe for x in
         nb["transformar_contactos"](df, {"campanhas": campanhas, "clientes": clientes}).collect()}
    assert r == {"A": True, "B": False}


def test_regras_qualidade_separam_validos_e_rejeitados(spark, nb):
    df = spark.createDataFrame([(1, 10.0), (2, -5.0), (None, 3.0)], "id int, valor double")
    regras = [{"nome": "id_ok", "expressao": "id IS NOT NULL", "acao": "rejeitar"},
              {"nome": "valor_ok", "expressao": "valor >= 0", "acao": "rejeitar"},
              {"nome": "valor_alto", "expressao": "valor < 5", "acao": "alertar"}]
    validos, rejeitados, resumo = nb["aplicar_regras_qualidade"](df, regras)
    assert [r.id for r in validos.collect()] == [1]
    falhas = {r.id: r._regras_falhadas for r in rejeitados.collect()}
    assert falhas == {2: "valor_ok", None: "id_ok"}
    assert {r["regra"]: r["falhas"] for r in resumo} == {"id_ok": 1, "valor_ok": 1, "valor_alto": 1}
    assert "_regras_falhadas" not in validos.columns


def test_regra_com_resultado_nulo_conta_como_falha(spark, nb):
    df = spark.createDataFrame([(None,)], "valor double")
    validos, rejeitados, _ = nb["aplicar_regras_qualidade"](df, [{"nome": "v", "expressao": "valor >= 0", "acao": "rejeitar"}])
    assert validos.count() == 0 and rejeitados.count() == 1


def test_calendario_em_portugues(spark, nb):
    cal = {r.data: r for r in nb["gerar_calendario"](spark, "2025-03-01", "2025-03-03").collect()}
    sab, seg = cal[dt.date(2025, 3, 1)], cal[dt.date(2025, 3, 3)]
    assert (sab.mes, sab.dia_semana, sab.fim_de_semana, sab.num_dia_semana) == ("Março", "Sábado", True, 6)
    assert (seg.dia_semana, seg.num_dia_semana, seg.id_data) == ("Segunda", 1, 20250303)


def test_config_tem_transformacao_para_cada_entidade(nb):
    assert set(nb["ENTIDADES"]) == set(nb["TRANSFORMACOES"])
    assert set(nb["DEPENDENCIAS_SILVER"]) == set(nb["ENTIDADES"])
