# %% [markdown]
# # NB_01 — Simulador das fontes (dados 100% sintéticos)
# Substitui, neste projeto de demonstração, as extrações dos sistemas reais (CRM, plataforma de envios,
# originação, faturação de media). Escreve CSV em `LH_Bronze/Files/landing/<entidade>/`.
#
# | Modo | O que gera |
# |---|---|
# | `inicial` | Histórico completo até `p_data_corte` (carga inicial) |
# | `incremental` | Só o dia `p_data_carga`: novos contactos, conversões, custos, campanhas que arrancam e **alterações de clientes** (para exercitar o SCD tipo 2) |
#
# Os dados incluem **erros propositados** (duplicados, maiúsculas, espaços, datas em 2 formatos,
# vírgula decimal, registos órfãos e valores negativos) para demonstrar a limpeza e a quarentena.
# ⚠️ Nunca usar dados reais de clientes numa conta trial.

# %%
# MAGIC %run NB_Config

# %%
# MAGIC %run NB_Utils

# %% tags=["parameters"]
p_modo = "inicial"            # "inicial" | "incremental"
p_data_corte = "2025-11-30"   # modo inicial: gera tudo até esta data
p_data_carga = "2025-12-01"   # modo incremental: dia a gerar
p_semente = 42

# %%
import io
import numpy as np
import pandas as pd
from datetime import date, timedelta

ANO_INICIO, ANO_FIM = date(2025, 1, 1), date(2025, 12, 31)
N_CLIENTES = 20_000
rng = np.random.default_rng(p_semente)


def gravar_csv(pdf: pd.DataFrame, entidade: str, data_ficheiro: str) -> None:
    buf = io.StringIO()
    pdf.to_csv(buf, index=False, sep=";")
    destino = caminho_ficheiros(LH_BRONZE, f"{PASTA_LANDING}/{entidade}/{entidade}_{data_ficheiro.replace('-', '')}.csv")
    escrever_texto(destino, buf.getvalue())
    print(f"  {entidade:16s} {len(pdf):>8,} linhas → {destino.split('/Files/')[-1]}")

# %% [markdown]
# ## 1. Gerar o universo completo (determinístico pela semente)

# %%
produtos = pd.DataFrame([
    (1, "Conta à Ordem Digital", "Contas", 0.000, 0),
    (2, "Cartão de Crédito Classic", "Cartões", 0.120, 1500),
    (3, "Cartão de Crédito Gold", "Cartões", 0.110, 4000),
    (4, "Crédito Pessoal", "Crédito ao Consumo", 0.060, 12000),
    (5, "Crédito Automóvel", "Crédito ao Consumo", 0.045, 18000),
    (6, "Crédito Habitação", "Crédito Habitação", 0.012, 165000),
    (7, "Depósito a Prazo 12M", "Poupança", 0.008, 15000),
    (8, "PPR", "Poupança", 0.015, 8000),
    (9, "Fundo de Investimento", "Investimento", 0.018, 10000),
    (10, "Seguro Vida Crédito", "Seguros", 0.250, 600),
    (11, "Seguro Multirriscos Casa", "Seguros", 0.220, 350),
    (12, "Conta Jovem", "Contas", 0.000, 0),
], columns=["id_produto", "nome_produto", "categoria", "margem_estimada", "valor_medio"])

distritos = ["Lisboa", "Porto", "Setúbal", "Braga", "Aveiro", "Leiria", "Coimbra", "Faro", "Santarém", "Viseu",
             "Madeira", "Açores", "Viana do Castelo", "Évora", "Castelo Branco", "Vila Real", "Guarda", "Beja",
             "Bragança", "Portalegre"]
p_dist = np.array([22, 17, 8, 8, 7, 5, 4, 4, 4, 3, 2.5, 2.5, 2, 1.5, 1.5, 1.5, 1.5, 1, 1, 1]); p_dist /= p_dist.sum()

idade = rng.integers(18, 86, N_CLIENTES)
segmento = rng.choice(["Massa", "Afluente", "Premium", "Jovem", "ENI"], N_CLIENTES, p=[0.52, 0.20, 0.08, 0.12, 0.08])
segmento = np.where(idade <= 25, np.where(rng.random(N_CLIENTES) < 0.7, "Jovem", segmento), segmento)
segmento = np.where((segmento == "Jovem") & (idade > 30), "Massa", segmento)
clientes = pd.DataFrame({
    "id_cliente": np.arange(100001, 100001 + N_CLIENTES),
    "data_nascimento": [date(2024 - int(a), int(rng.integers(1, 13)), int(rng.integers(1, 29))).isoformat() for a in idade],  # ≥ 18 anos em 2025
    "genero": rng.choice(["F", "M", "N/D"], N_CLIENTES, p=[0.50, 0.48, 0.02]),
    "distrito": rng.choice(distritos, N_CLIENTES, p=p_dist),
    "segmento": segmento,
    "canal_preferido": rng.choice(["App", "Homebanking", "Balcão", "Telefone"], N_CLIENTES, p=[0.45, 0.25, 0.22, 0.08]),
    "data_adesao": [(ANO_INICIO - timedelta(days=int(d))).isoformat() for d in rng.integers(30, 365 * 20, N_CLIENTES)],
    "escalao_rendimento": rng.choice(["<1000", "1000-2000", "2000-3500", "3500-5000", ">5000"], N_CLIENTES,
                                     p=[0.25, 0.38, 0.22, 0.10, 0.05]),
    "consentimento_marketing": rng.choice(["S", "N"], N_CLIENTES, p=[0.78, 0.22]),
    "tem_email": rng.choice([1, 0], N_CLIENTES, p=[0.88, 0.12]),
    "tem_app": rng.choice([1, 0], N_CLIENTES, p=[0.66, 0.34]),
})
premium = clientes.segmento == "Premium"
clientes.loc[premium, "escalao_rendimento"] = rng.choice(["3500-5000", ">5000"], premium.sum(), p=[0.4, 0.6])

# Campanhas
canais = ["Email", "SMS", "Push App", "Redes Sociais", "Display", "Balcão"]
perfil = {  # custo/contacto, entrega, abertura, clique, custo fixo, volume
    "Email": (0.004, 0.97, 0.24, 0.035, 3000, 7000), "SMS": (0.045, 0.98, 0.90, 0.060, 2500, 4000),
    "Push App": (0.001, 0.92, 0.38, 0.080, 2000, 6000), "Redes Sociais": (0.180, 1.00, 0.55, 0.022, 15000, 3000),
    "Display": (0.090, 1.00, 0.45, 0.009, 12000, 3000), "Balcão": (2.500, 1.00, 1.00, 0.300, 8000, 600)}
temas = {1: "Abre a tua conta em 5 min", 2: "Cashback de Verão", 3: "Viaja com Gold", 4: "Realiza o teu projeto",
         5: "Muda de carro", 6: "A tua casa, o teu banco", 7: "Poupança com taxa garantida", 8: "Reforma tranquila",
         9: "Investir sem complicar", 10: "Proteção do crédito", 11: "Casa protegida", 12: "Conta Jovem sem custos"}
objetivo_cat = {"Cartões": "Aquisição", "Crédito ao Consumo": "Cross-sell", "Crédito Habitação": "Aquisição",
                "Poupança": "Retenção", "Investimento": "Cross-sell", "Seguros": "Cross-sell", "Contas": "Aquisição"}
alvo_prod = {1: "Massa", 2: "Massa", 3: "Afluente", 4: "Massa", 5: "Afluente", 6: "Afluente", 7: "Todos",
             8: "Afluente", 9: "Premium", 10: "Todos", 11: "Todos", 12: "Jovem"}
cat = produtos.set_index("id_produto").categoria
camp_rows = []
for i in range(40):
    idp = int(rng.integers(1, 13)); canal = canais[i % 6]
    ini = ANO_INICIO + timedelta(days=int(rng.integers(0, 345)))
    fim = min(ini + timedelta(days=int(rng.integers(14, 46))), ANO_FIM)
    camp_rows.append({"id_campanha": f"CMP-2025-{i+1:03d}", "nome_campanha": f"{temas[idp]} | {canal}",
                      "id_produto": idp, "canal": canal, "objetivo": objetivo_cat[cat[idp]],
                      "segmento_alvo": alvo_prod[idp], "data_inicio": ini, "data_fim": fim, "orcamento": 0.0})
campanhas = pd.DataFrame(camp_rows)

# Contactos (funil)
elegiveis = clientes[clientes.consentimento_marketing == "S"]
blocos, cid = [], 1
for _, c in campanhas.iterrows():
    alvo = elegiveis if c.segmento_alvo == "Todos" else elegiveis[elegiveis.segmento.isin({c.segmento_alvo, "Massa"})]
    if c.canal == "Email": alvo = alvo[alvo.tem_email == 1]
    if c.canal == "Push App": alvo = alvo[alvo.tem_app == 1]
    cu, pe, pa, pc, fixo, vol = perfil[c.canal]
    amostra = alvo.sample(min(vol, len(alvo)), random_state=int(rng.integers(0, 1e6)))
    n, span = len(amostra), max((c.data_fim - c.data_inicio).days, 1)
    ent = rng.random(n) < pe
    abr = ent & (rng.random(n) < pa * rng.uniform(0.8, 1.2))
    clq = abr & (rng.random(n) < (pc / pa) * np.where(amostra.segmento.values == "Jovem", 1.3, 1.0))
    ts = (pd.Timestamp(c.data_inicio) + pd.to_timedelta(rng.integers(0, span, n), unit="D")
          + pd.to_timedelta(rng.integers(8, 22, n), unit="h") + pd.to_timedelta(rng.integers(0, 60, n), unit="m"))
    blocos.append(pd.DataFrame({"id_contacto": [f"CT{x:08d}" for x in range(cid, cid + n)], "id_campanha": c.id_campanha,
                                "id_cliente": amostra.id_cliente.values, "data_hora_envio": ts,
                                "flag_entregue": ent.astype(int), "flag_aberto": abr.astype(int), "flag_clicado": clq.astype(int)}))
    cid += n
    campanhas.loc[campanhas.id_campanha == c.id_campanha, "orcamento"] = round((fixo + n * cu) * rng.uniform(0.9, 1.3), 2)
contactos = pd.concat(blocos, ignore_index=True)

# Conversões
p_conv = {"Email": 0.10, "SMS": 0.09, "Push App": 0.12, "Redes Sociais": 0.06, "Display": 0.05, "Balcão": 0.35}
base = contactos.merge(campanhas[["id_campanha", "id_produto", "canal"]], on="id_campanha")
cliq = base[base.flag_clicado == 1]
conv = pd.concat([cliq[rng.random(len(cliq)) < cliq.canal.map(p_conv)],
                  base[(base.flag_entregue == 1) & (base.flag_clicado == 0)].sample(1200, random_state=p_semente)])
vm = produtos.set_index("id_produto").valor_medio
conv = conv.assign(
    valor_contratado=[round(float(max(0, rng.normal(vm[p], vm[p] * 0.35))), 2) for p in conv.id_produto],
    data_conversao=(conv.data_hora_envio.dt.normalize() + pd.to_timedelta(rng.integers(0, 30, len(conv)), unit="D")).dt.date,
    canal_conversao=rng.choice(["App", "Homebanking", "Balcão"], len(conv), p=[0.5, 0.3, 0.2]),
).sort_values("data_conversao").reset_index(drop=True)
conv["id_conversao"] = [f"CV{i+1:07d}" for i in range(len(conv))]
conversoes = conv[["id_conversao", "id_contacto", "id_cliente", "id_campanha", "id_produto",
                   "data_conversao", "valor_contratado", "canal_conversao"]]

# Custos diários
custos_rows = []
for _, c in campanhas.iterrows():
    dias = (c.data_fim - c.data_inicio).days + 1
    pesos = rng.dirichlet(np.ones(dias) * 3); total = c.orcamento * rng.uniform(0.85, 1.05)
    for d in range(dias):
        custo = round(float(total * pesos[d]), 2)
        custos_rows.append((c.id_campanha, c.data_inicio + timedelta(days=d), custo,
                            int(custo / 0.004) if c.canal in ("Redes Sociais", "Display") else None))
custos = pd.DataFrame(custos_rows, columns=["id_campanha", "data", "custo", "impressoes"])
custos["impressoes"] = custos["impressoes"].astype("Int64")

print(f"Universo: {len(clientes):,} clientes | {len(campanhas)} campanhas | {len(contactos):,} contactos | "
      f"{len(conversoes):,} conversões | {len(custos):,} custos diários")

# %% [markdown]
# ## 2. Recortar e gravar conforme o modo

# %%
def sujar_texto(pdf, col, frac, fn, seed):
    idx = pdf.sample(frac=frac, random_state=seed).index
    pdf.loc[idx, col] = pdf.loc[idx, col].map(fn)
    return pdf

if p_modo == "inicial":
    corte = date.fromisoformat(p_data_corte)
    print(f"Modo INICIAL até {corte}")
    gravar_csv(produtos.drop(columns="valor_medio"), "produtos", p_data_corte)

    cli = clientes.copy()
    cli = sujar_texto(cli, "distrito", 0.01, str.upper, 1)
    cli = sujar_texto(cli, "distrito", 0.01, lambda s: f"  {s} ", 2)
    cli.loc[cli.sample(100, random_state=3).index, "segmento"] = None
    idx = cli.sample(100, random_state=4).index
    cli.loc[idx, "data_adesao"] = pd.to_datetime(cli.loc[idx, "data_adesao"]).dt.strftime("%d/%m/%Y")
    cli = pd.concat([cli, cli.sample(150, random_state=5)]).sample(frac=1, random_state=6)       # duplicados
    gravar_csv(cli, "clientes", p_data_corte)

    camp = campanhas[campanhas.data_inicio <= corte].copy()
    camp.loc[camp.index % 7 == 0, "canal"] = camp.loc[camp.index % 7 == 0, "canal"].str.lower()
    gravar_csv(camp, "campanhas", p_data_corte)

    ct = contactos[contactos.data_hora_envio.dt.date <= corte].copy()
    ct["data_hora_envio"] = ct.data_hora_envio.dt.strftime("%Y-%m-%d %H:%M:%S")
    gravar_csv(pd.concat([ct, ct.sample(800, random_state=7)]), "contactos", p_data_corte)

    cv = conversoes[conversoes.data_conversao <= corte].copy()
    cv["valor_contratado"] = cv.valor_contratado.astype(str)
    lote = cv.sample(300, random_state=8).index
    cv.loc[lote, "valor_contratado"] = cv.loc[lote, "valor_contratado"].str.replace(".", ",", regex=False)
    gravar_csv(cv, "conversoes", p_data_corte)

    gravar_csv(custos[custos.data <= corte], "custos_campanha", p_data_corte)

elif p_modo == "incremental":
    dia = date.fromisoformat(p_data_carga)
    r = np.random.default_rng(int(dia.strftime("%Y%m%d")))
    print(f"Modo INCREMENTAL para {dia}")

    # Alterações de clientes: mudança de segmento, rendimento, morada ou consentimento (SCD2)
    alt = clientes.sample(40, random_state=int(dia.strftime("%Y%m%d")) % 2**31).copy()
    q = len(alt) // 4
    alt.iloc[:q, alt.columns.get_loc("segmento")] = "Afluente"
    alt.iloc[q:2*q, alt.columns.get_loc("escalao_rendimento")] = "3500-5000"
    alt.iloc[2*q:3*q, alt.columns.get_loc("distrito")] = r.choice(distritos, q)
    alt.iloc[3*q:, alt.columns.get_loc("consentimento_marketing")] = "N"
    gravar_csv(alt, "clientes", p_data_carga)

    camp = campanhas[campanhas.data_inicio == dia]
    if len(camp):
        gravar_csv(camp, "campanhas", p_data_carga)

    ct = contactos[contactos.data_hora_envio.dt.date == dia].copy()
    ct["data_hora_envio"] = ct.data_hora_envio.dt.strftime("%Y-%m-%d %H:%M:%S")
    orfaos = ct.head(2).assign(id_contacto=lambda d: d.id_contacto + "X", id_campanha="CMP-9999-999")  # → quarentena
    gravar_csv(pd.concat([ct, orfaos]), "contactos", p_data_carga)

    cv = conversoes[conversoes.data_conversao == dia].copy()
    if len(cv):
        cv = pd.concat([cv, cv.head(1).assign(id_conversao="CV-ERRO-" + dia.strftime("%Y%m%d"), valor_contratado=-100.0)])
        gravar_csv(cv, "conversoes", p_data_carga)

    cs = custos[custos.data == dia]
    if len(cs):
        gravar_csv(cs, "custos_campanha", p_data_carga)
else:
    raise ValueError(f"p_modo inválido: {p_modo}")
