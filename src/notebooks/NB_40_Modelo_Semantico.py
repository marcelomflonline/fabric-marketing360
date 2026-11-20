# %% [markdown]
# # NB_40 — Modelo semântico como código (semantic-link-labs)
# Aplica de forma **repetível e versionada** toda a lógica do modelo Direct Lake `SM_Marketing360`:
# nomes amigáveis, colunas ocultas, relações, tabela de datas, ordenações, **medidas DAX com pastas e
# formatos**, **RLS por região** e, no fim, corre o **Best Practice Analyzer**.
#
# Pré-requisito (1 minuto, no portal): `WH_Gold` → *Novo modelo semântico* → nome `SM_Marketing360` →
# selecionar as tabelas do esquema `gold` listadas em `TABELAS` abaixo. O resto é feito aqui.
#
# O notebook é **idempotente**: pode ser executado sempre que uma medida mudar.

# %%
# MAGIC %pip install -q semantic-link-labs

# %% tags=["parameters"]
p_modelo = "SM_Marketing360"
p_workspace = None          # None = workspace atual
p_executar_bpa = True

# %%
import sempy.fabric as fabric
from sempy_labs.tom import connect_semantic_model

# nome da tabela no Warehouse → nome amigável no modelo
TABELAS = {
    "dim_data": "Data",
    "dim_cliente": "Cliente",
    "dim_produto": "Produto",
    "dim_campanha": "Campanha",
    "fact_contactos": "Contactos",
    "fact_conversoes": "Conversões",
    "fact_custos_campanha": "Custos",
    "cliente_envolvimento": "Envolvimento",
    "rls_acesso_regiao": "Acesso Região",
}

RELACOES = [  # (tabela N, coluna, tabela 1, coluna)
    ("Contactos", "id_data_envio", "Data", "id_data"),
    ("Contactos", "sk_campanha", "Campanha", "sk_campanha"),
    ("Contactos", "sk_cliente", "Cliente", "sk_cliente"),
    ("Conversões", "id_data_conversao", "Data", "id_data"),
    ("Conversões", "sk_campanha", "Campanha", "sk_campanha"),
    ("Conversões", "sk_cliente", "Cliente", "sk_cliente"),
    ("Conversões", "sk_produto", "Produto", "sk_produto"),
    ("Custos", "id_data", "Data", "id_data"),
    ("Custos", "sk_campanha", "Campanha", "sk_campanha"),
    ("Envolvimento", "sk_cliente", "Cliente", "sk_cliente"),
]

OCULTAR_PREFIXOS = ("sk_", "hash_", "id_lote", "data_carga", "data_criacao", "data_atualizacao")
OCULTAR_EM_FACTOS = ("id_data", "id_data_envio", "id_data_conversao", "id_campanha", "id_contacto", "id_cliente")

ORDENAR_POR = [("Data", "mes", "num_mes"), ("Data", "mes_abrev", "num_mes"),
               ("Data", "dia_semana", "num_dia_semana")]

PCT, EUR0, EUR2, INT, DEC2 = "0.0%", "#,0 €", "#,0.00 €", "#,0", "0.00x"

# (tabela, nome, expressão, formato, pasta, descrição)
MEDIDAS = [
    # --- Funil
    ("Contactos", "Contactos Enviados", "SUM ( Contactos[enviado] )", INT, "1. Funil", "Nº de mensagens/contactos enviados."),
    ("Contactos", "Contactos Entregues", "SUM ( Contactos[entregue] )", INT, "1. Funil", ""),
    ("Contactos", "Aberturas", "SUM ( Contactos[aberto] )", INT, "1. Funil", ""),
    ("Contactos", "Cliques", "SUM ( Contactos[clicado] )", INT, "1. Funil", ""),
    ("Contactos", "Clientes Contactados", "CALCULATE ( DISTINCTCOUNT ( Cliente[id_cliente] ), Contactos )", INT, "1. Funil",
     "Clientes distintos (id de negócio, todas as versões SCD2)."),
    ("Contactos", "Taxa de Entrega", "DIVIDE ( [Contactos Entregues], [Contactos Enviados] )", PCT, "1. Funil", ""),
    ("Contactos", "Taxa de Abertura", "DIVIDE ( [Aberturas], [Contactos Entregues] )", PCT, "1. Funil", "Aberturas ÷ entregues."),
    ("Contactos", "CTR", "DIVIDE ( [Cliques], [Contactos Entregues] )", PCT, "1. Funil", "Cliques ÷ entregues."),
    ("Contactos", "Click-to-Open", "DIVIDE ( [Cliques], [Aberturas] )", PCT, "1. Funil", ""),
    # --- Conversão
    ("Conversões", "Conversões", "COUNTROWS ( 'Conversões' )", INT, "2. Conversão", "Contratações atribuídas a campanhas."),
    ("Conversões", "Taxa de Conversão", "DIVIDE ( [Conversões], [Contactos Enviados] )", PCT, "2. Conversão", "Conversões ÷ enviados."),
    ("Conversões", "Conversões por Clique",
     "CALCULATE ( [Conversões], 'Conversões'[tipo_atribuicao] = \"Clique\" )", INT, "2. Conversão", ""),
    ("Conversões", "Valor Contratado", "SUM ( 'Conversões'[valor_contratado] )", EUR0, "2. Conversão", ""),
    ("Conversões", "Ticket Médio", "DIVIDE ( [Valor Contratado], [Conversões] )", EUR0, "2. Conversão", ""),
    ("Conversões", "Receita Estimada", "SUM ( 'Conversões'[receita_estimada] )", EUR0, "2. Conversão",
     "Valor contratado × margem anual estimada do produto."),
    ("Conversões", "Dias até Conversão", "AVERAGE ( 'Conversões'[dias_ate_conversao] )", "0.0", "2. Conversão", ""),
    # --- Custos e retorno
    ("Custos", "Custo", "SUM ( Custos[custo] )", EUR0, "3. Custos e Retorno", "Custo real faturado."),
    ("Custos", "Orçamento", "SUM ( Campanha[orcamento] )", EUR0, "3. Custos e Retorno", ""),
    ("Custos", "Execução do Orçamento", "DIVIDE ( [Custo], [Orçamento] )", PCT, "3. Custos e Retorno", ""),
    ("Custos", "Custo por Contacto", "DIVIDE ( [Custo], [Contactos Enviados] )", "#,0.000 €", "3. Custos e Retorno", ""),
    ("Custos", "CPC", "DIVIDE ( [Custo], [Cliques] )", EUR2, "3. Custos e Retorno", "Custo por clique."),
    ("Custos", "CPA", "DIVIDE ( [Custo], [Conversões] )", EUR2, "3. Custos e Retorno", "Custo por aquisição."),
    ("Custos", "Impressões", "SUM ( Custos[impressoes] )", INT, "3. Custos e Retorno", ""),
    ("Custos", "CPM", "DIVIDE ( [Custo], [Impressões] ) * 1000", EUR2, "3. Custos e Retorno", ""),
    ("Custos", "ROI", "DIVIDE ( [Receita Estimada] - [Custo], [Custo] )", PCT, "3. Custos e Retorno",
     "(Receita estimada − custo) ÷ custo."),
    ("Custos", "ROAS", "DIVIDE ( [Receita Estimada], [Custo] )", DEC2, "3. Custos e Retorno", ""),
    # --- Tempo
    ("Conversões", "Conversões Mês Anterior", "CALCULATE ( [Conversões], DATEADD ( 'Data'[data], -1, MONTH ) )", INT, "4. Tempo", ""),
    ("Conversões", "Conversões Var. % MoM",
     "DIVIDE ( [Conversões] - [Conversões Mês Anterior], [Conversões Mês Anterior] )", PCT, "4. Tempo", ""),
    ("Conversões", "Valor Contratado YTD", "TOTALYTD ( [Valor Contratado], 'Data'[data] )", EUR0, "4. Tempo", ""),
    ("Custos", "Custo YTD", "TOTALYTD ( [Custo], 'Data'[data] )", EUR0, "4. Tempo", ""),
    # --- Clientes
    ("Envolvimento", "Clientes na Base",
     "CALCULATE ( DISTINCTCOUNT ( Cliente[id_cliente] ), Cliente[registo_atual] = TRUE (), Cliente[id_cliente] <> -1 )",
     INT, "5. Clientes", "Clientes atuais (versão corrente)."),
    ("Envolvimento", "Clientes com Consentimento",
     "CALCULATE ( [Clientes na Base], Cliente[consentimento_marketing] = TRUE () )", INT, "5. Clientes", ""),
    ("Envolvimento", "% Consentimento", "DIVIDE ( [Clientes com Consentimento], [Clientes na Base] )", PCT, "5. Clientes", ""),
    ("Envolvimento", "Score Médio de Envolvimento", "AVERAGE ( Envolvimento[score_envolvimento] )", "0.0", "5. Clientes", ""),
    ("Envolvimento", "Clientes Alto Envolvimento",
     "CALCULATE ( COUNTROWS ( Envolvimento ), Envolvimento[nivel_envolvimento] = \"Alto\" )", INT, "5. Clientes", ""),
    ("Envolvimento", "Oportunidades (Alto sem Conversão)",
     "CALCULATE ( COUNTROWS ( Envolvimento ), Envolvimento[nivel_envolvimento] = \"Alto\", Envolvimento[n_conversoes] = 0 )",
     INT, "5. Clientes", "Clientes muito envolvidos que ainda não contrataram: lista para a próxima campanha."),
    ("Contactos", "Contactos sem Consentimento",
     "CALCULATE ( [Contactos Enviados], Cliente[consentimento_marketing] = FALSE (), Cliente[id_cliente] <> -1 )",
     INT, "5. Clientes", "RGPD: deve ser 0. Usa a versão do cliente à data do envio."),
    # --- Apresentação
    ("Custos", "Ranking ROI Campanha",
     "IF ( HASONEVALUE ( Campanha[nome_campanha] ), RANKX ( ALLSELECTED ( Campanha[nome_campanha] ), [ROI],, DESC, DENSE ) )",
     INT, "9. Apresentação", ""),
    ("Custos", "Cor ROI",
     "SWITCH ( TRUE (), ISBLANK ( [ROI] ), \"#9AA0A6\", [ROI] >= 1, \"#1E8E3E\", [ROI] >= 0, \"#F9AB00\", \"#D93025\" )",
     "", "9. Apresentação", "Usar em formatação condicional (valor do campo)."),
    ("Custos", "Título Página",
     "\"Desempenho de campanhas — \" & IF ( HASONEVALUE ( Campanha[canal] ), VALUES ( Campanha[canal] ), \"todos os canais\" )",
     "", "9. Apresentação", ""),
    ("Contactos", "Última Atualização",
     "\"Dados até \" & FORMAT ( MAX ( 'Data'[data] ), \"dd/mm/yyyy\" )", "", "9. Apresentação", ""),
]

RLS_ROLE = "Acesso por Região"
RLS_FILTROS = {
    "Cliente": (
        "VAR _regioes = CALCULATETABLE ( VALUES ( 'Acesso Região'[regiao] ), "
        "'Acesso Região'[utilizador] = USERPRINCIPALNAME () ) "
        "RETURN \"Todas\" IN _regioes || Cliente[regiao] IN _regioes"),
    "Acesso Região": "'Acesso Região'[utilizador] = USERPRINCIPALNAME ()",
}

# %% [markdown]
# ## 1. Nomes amigáveis

# %%
with connect_semantic_model(dataset=p_modelo, readonly=False, workspace=p_workspace) as tom:
    existentes = {t.Name for t in tom.model.Tables}
    for origem, destino in TABELAS.items():
        if origem in existentes and destino not in existentes:
            tom.model.Tables[origem].Name = destino
            print(f"tabela {origem} → {destino}")
    em_falta = [d for d in TABELAS.values() if d not in {t.Name for t in tom.model.Tables}]
    assert not em_falta, f"Tabelas em falta no modelo (adicione-as no portal): {em_falta}"

# %% [markdown]
# ## 2. Estrutura: colunas ocultas, relações, datas, ordenações

# %%
FACTOS = {"Contactos", "Conversões", "Custos", "Envolvimento"}

with connect_semantic_model(dataset=p_modelo, readonly=False, workspace=p_workspace) as tom:
    for t in tom.model.Tables:
        for c in t.Columns:
            if c.Name.startswith(OCULTAR_PREFIXOS) or (t.Name in FACTOS and c.Name in OCULTAR_EM_FACTOS):
                c.IsHidden = True
    tom.model.Tables["Acesso Região"].IsHidden = True

    atuais = {(r.FromTable.Name, r.FromColumn.Name, r.ToTable.Name, r.ToColumn.Name) for r in tom.model.Relationships}
    for de_t, de_c, para_t, para_c in RELACOES:
        if (de_t, de_c, para_t, para_c) not in atuais:
            tom.add_relationship(from_table=de_t, from_column=de_c, to_table=para_t, to_column=para_c,
                                 from_cardinality="Many", to_cardinality="One")
            print(f"relação {de_t}[{de_c}] → {para_t}[{para_c}]")

    tom.mark_as_date_table(table_name="Data", column_name="data")
    for tabela, coluna, por in ORDENAR_POR:
        tom.set_sort_by_column(table_name=tabela, column_name=coluna, sort_by_column=por)

# %% [markdown]
# ## 3. Medidas (criar ou atualizar)

# %%
with connect_semantic_model(dataset=p_modelo, readonly=False, workspace=p_workspace) as tom:
    for tabela, nome, expr, fmt, pasta, desc in MEDIDAS:
        m = tom.model.Tables[tabela].Measures.Find(nome)
        if m is None:
            tom.add_measure(table_name=tabela, measure_name=nome, expression=expr,
                            format_string=fmt or None, display_folder=pasta, description=desc or None)
        else:
            m.Expression, m.DisplayFolder = expr, pasta
            if fmt:
                m.FormatString = fmt
            if desc:
                m.Description = desc
    print(f"{len(MEDIDAS)} medidas aplicadas")

# %% [markdown]
# ## 4. Segurança ao nível da linha (RLS)
# Depois de publicar: *Modelo semântico → Segurança* → adicionar utilizadores/grupos à role.
# Quem não estiver em `gold.rls_acesso_regiao` não vê clientes (por desenho: "negar por omissão").

# %%
with connect_semantic_model(dataset=p_modelo, readonly=False, workspace=p_workspace) as tom:
    if not any(r.Name == RLS_ROLE for r in tom.model.Roles):
        tom.add_role(role_name=RLS_ROLE, model_permission="Read",
                     description="Filtra clientes pela região atribuída em gold.rls_acesso_regiao")
    for tabela, filtro in RLS_FILTROS.items():
        tom.set_rls(role_name=RLS_ROLE, table_name=tabela, filter_expression=filtro)

# %% [markdown]
# ## 5. Atualizar (reframing Direct Lake) e Best Practice Analyzer

# %%
fabric.refresh_dataset(dataset=p_modelo, workspace=p_workspace)
print("Modelo atualizado.")

if p_executar_bpa:
    import sempy_labs as labs
    labs.run_model_bpa(dataset=p_modelo, workspace=p_workspace)
