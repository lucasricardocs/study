import streamlit as st
import gspread
import pandas as pd
import altair as alt
import time
import random
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound, APIError

# Configuração da página
st.set_page_config(
    page_title="Cronômetro de Estudos",
    page_icon="⏱️",
    layout="centered"
)

# Constantes
PLANILHA_NOME = "study"
PLANILHA_ID = "1EyllfZ69b5H-n47iB-_Zau6nf3rcBEoG8qYNbYv5uGs"
DURACAO_MINIMA_SEGUNDOS = 10  # Duração mínima para registrar
MAX_RETRIES = 5  # Número máximo de tentativas para chamadas à API
CACHE_TTL = 600  # Tempo de vida do cache em segundos (10 minutos)

# Inicialização do estado da sessão
if 'estudo_ativo' not in st.session_state:
    st.session_state.update({
        'estudo_ativo': False,
        'inicio_estudo': None,
        'materia_atual': None,
        'ultimo_registro': None,
        'tema': 'light',  # Tema padrão
        'registros_cache': None,  # Cache para registros
        'materias_cache': None,   # Cache para matérias
        'resumo_cache': None,     # Cache para resumo
        'ultima_atualizacao_cache': {  # Timestamps para controle de cache
            'registros': None,
            'materias': None,
            'resumo': None
        }
    })

def exponential_backoff(retry_count):
    """Implementa uma espera exponencial para retentativa."""
    wait_time = min(2 ** retry_count + random.random(), 60)  # Máximo de 60 segundos
    time.sleep(wait_time)

@st.cache_resource(ttl=CACHE_TTL)
def conectar_google_sheets():
    """Conecta ao Google Sheets com tratamento de erros."""
    try:
        credenciais = Credentials.from_service_account_info(
            st.secrets["google_credentials"],
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
        return gspread.authorize(credenciais)
    except Exception as erro:
        st.error(f"🔌 Falha na conexão: {erro}", icon="❌")
        st.stop()

def api_request_with_retry(func, *args, **kwargs):
    """Executa chamadas de API com retentativa e backoff exponencial."""
    for tentativa in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except APIError as erro:
            if erro.response.status_code == 429:
                if tentativa < MAX_RETRIES - 1:
                    st.warning(f"Limite de quota atingido, aguardando... (tentativa {tentativa+1}/{MAX_RETRIES})")
                    exponential_backoff(tentativa)
                else:
                    st.error("Limite de quota persistente. Tente novamente mais tarde.")
                    raise
            else:
                st.error(f"Erro de API: {erro}")
                raise
        except Exception as erro:
            st.error(f"Erro inesperado: {erro}")
            raise

def carregar_planilha(cliente_gs):
    """Carrega a planilha especificada, tentando por ID e depois por nome."""
    try:
        try:
            return api_request_with_retry(cliente_gs.open_by_key, PLANILHA_ID)
        except SpreadsheetNotFound:
            return api_request_with_retry(cliente_gs.open, PLANILHA_NOME)
    except SpreadsheetNotFound:
        st.error(f"📄 Planilha '{PLANILHA_NOME}' (ID: {PLANILHA_ID}) não encontrada", icon="🔍")
        st.stop()
    except Exception as erro:
        st.error(f"📂 Erro ao acessar planilha: {erro}", icon="❌")
        st.stop()

def carregar_abas(planilha):
    """Carrega as abas necessárias e verifica sua existência."""
    abas_requeridas = {"Registros", "Materias", "Resumo"}
    abas_disponiveis = {aba.title for aba in api_request_with_retry(planilha.worksheets)}

    if not abas_requeridas.issubset(abas_disponiveis):
        faltantes = abas_requeridas - abas_disponiveis
        st.error(f"⚠️ Abas faltando: {', '.join(faltantes)}")
        st.info("Crie as abas necessárias na planilha e tente novamente.")
        st.stop()

    return {
        'registros': planilha.worksheet("Registros"),
        'materias': planilha.worksheet("Materias"),
        'resumo': planilha.worksheet("Resumo")
    }

def formatar_duracao(segundos):
    """Converte segundos para o formato HH:MM:SS."""
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{int(horas):02d}:{int(minutos):02d}:{int(segundos):02d}"

def cache_expirado(tipo_cache):
    """Verifica se um determinado cache expirou."""
    ultima_att = st.session_state.ultima_atualizacao_cache.get(tipo_cache)
    if ultima_att is None:
        return True
    return (datetime.now() - ultima_att).total_seconds() > CACHE_TTL

def obter_registros(aba_registros, forcar_atualizacao=False):
    """Obtém registros da aba 'Registros' com suporte a cache."""
    if not forcar_atualizacao and st.session_state.registros_cache is not None and not cache_expirado('registros'):
        return st.session_state.registros_cache

    try:
        registros = api_request_with_retry(aba_registros.get_all_records)
        df_registros = pd.DataFrame(registros)
        
        st.session_state.registros_cache = df_registros
        st.session_state.ultima_atualizacao_cache['registros'] = datetime.now()
        
        return df_registros
    except Exception as erro:
        st.error(f"Erro ao carregar registros: {erro}")
        return st.session_state.registros_cache if st.session_state.registros_cache is not None else pd.DataFrame()

def obter_materias(aba_materias):
    """Obtém a lista de matérias com suporte a cache."""
    if st.session_state.materias_cache is not None and not cache_expirado('materias'):
        return st.session_state.materias_cache

    try:
        materias = api_request_with_retry(aba_materias.col_values, 1)[1:]  # Ignora cabeçalho
        
        st.session_state.materias_cache = materias
        st.session_state.ultima_atualizacao_cache['materias'] = datetime.now()
        
        return materias
    except Exception as erro:
        st.error(f"Erro ao carregar matérias: {erro}")
        return st.session_state.materias_cache if st.session_state.materias_cache is not None else ["Matéria Padrão"]

def atualizar_resumo(aba_registros, aba_resumo):
    """Atualiza a aba de resumo com os totais de tempo de estudo por matéria."""
    df_registros = obter_registros(aba_registros)

    if df_registros.empty:
        try:
            api_request_with_retry(aba_resumo.clear)
        except Exception as erro:
            st.error(f"Erro ao limpar aba de resumo: {erro}")
        return pd.DataFrame()

    df_registros['Duração (min)'] = pd.to_numeric(df_registros['Duração (min)'], errors='coerce')
    totais_por_materia = df_registros.groupby('Matéria')['Duração (min)'].sum().reset_index()
    totais_por_materia['Total (horas)'] = (totais_por_materia['Duração (min)'] / 60).round(2)

    try:
        valores = [totais_por_materia.columns.values.tolist()] + totais_por_materia.values.tolist()
        api_request_with_retry(aba_resumo.clear)
        api_request_with_retry(aba_resumo.update, valores)
        
        st.session_state.resumo_cache = totais_por_materia
        st.session_state.ultima_atualizacao_cache['resumo'] = datetime.now()
        
        return totais_por_materia
    except Exception as erro:
        st.error(f"📊 Erro ao atualizar resumo: {erro}", icon="❌")
        return pd.DataFrame()

def obter_resumo(aba_resumo):
    """Obtém os dados da aba de resumo com suporte a cache."""
    if st.session_state.resumo_cache is not None and not cache_expirado('resumo'):
        return st.session_state.resumo_cache

    try:
        dados_resumo = api_request_with_retry(aba_resumo.get_all_records)
        df_resumo = pd.DataFrame(dados_resumo)
        
        st.session_state.resumo_cache = df_resumo
        st.session_state.ultima_atualizacao_cache['resumo'] = datetime.now()
        
        return df_resumo
    except Exception as erro:
        st.error(f"Erro ao carregar resumo: {erro}")
        return st.session_state.resumo_cache if st.session_state.resumo_cache is not None else pd.DataFrame()

def gerar_grafico_semanal(df_registros):
    """Gera um gráfico de barras mostrando as horas estudadas por dia da semana nos últimos 30 dias."""
    if df_registros.empty:
        return None

    df_registros['Data'] = pd.to_datetime(df_registros['Data'], errors='coerce', dayfirst=True)
    data_limite = datetime.now() - timedelta(days=30)
    df_recentes = df_registros[df_registros['Data'] >= data_limite].copy()

    if df_recentes.empty:
        return None

    df_recentes['Dia Semana'] = df_recentes['Data'].dt.day_name()
    mapeamento_dias = {
        'Monday': 'Segunda',
        'Tuesday': 'Terça',
        'Wednesday': 'Quarta',
        'Thursday': 'Quinta',
        'Friday': 'Sexta',
        'Saturday': 'Sábado',
        'Sunday': 'Domingo'
    }
    df_recentes['Dia Semana'] = df_recentes['Dia Semana'].map(mapeamento_dias)
    ordem_dias_portugues = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']

    df_agrupado = df_recentes.groupby('Dia Semana')['Duração (min)'].sum().reset_index()
    df_agrupado['Horas'] = df_agrupado['Duração (min)'] / 60

    df_agrupado['Ordem'] = df_agrupado['Dia Semana'].apply(lambda dia: ordem_dias_portugues.index(dia))
    df_agrupado = df_agrupado.sort_values('Ordem').drop('Ordem', axis=1)

    return alt.Chart(df_agrupado).mark_bar().encode(
        x=alt.X('Dia Semana:N', title='Dia da Semana', sort=ordem_dias_portugues),
        y=alt.Y('Horas:Q', title='Horas Estudadas'),
        color=alt.Color('Dia Semana:N', legend=None),
        tooltip=['Dia Semana', alt.Tooltip('Horas:Q', format=".2f")]
    ).properties(
        height=300,
        title='Horas de Estudo por Dia da Semana (Últimos 30 dias)'
    )

def display_ultimo_registro():
    """Exibe o último registro de estudo."""
    if st.session_state.ultimo_registro:
        st.markdown("<div class='highlight'>", unsafe_allow_html=True)
        st.info(
            f"Último registro: **{st.session_state.ultimo_registro['materia']}** "
            f"({st.session_state.ultimo_registro['duracao']:.2f} min) "
            f"das {st.session_state.ultimo_registro['inicio']} às {st.session_state.ultimo_registro['fim']}"
        )
        st.markdown("</div>", unsafe_allow_html=True)

def handle_iniciar_estudo(materia_selecionada):
    """Inicia a sessão de estudo."""
    st.session_state.estudo_ativo = True
    st.session_state.inicio_estudo = datetime.now()
    st.session_state.materia_atual = materia_selecionada
    st.toast(f"Estudo de {materia_selecionada} iniciado!", icon="📚")
    st.experimental_rerun()

def handle_parar_estudo(abas):
    """Para a sessão de estudo e salva o registro."""
    fim_estudo = datetime.now()
    duracao_segundos = (fim_estudo - st.session_state.inicio_estudo).total_seconds()

    if duracao_segundos < DURACAO_MINIMA_SEGUNDOS:
        st.warning(f"⚠️ Tempo mínimo não atingido ({DURACAO_MINIMA_SEGUNDOS} segundos). Registro não salvo.")
        st.session_state.estudo_ativo = False
        st.experimental_rerun()
        return

    duracao_minutos = round(duracao_segundos / 60, 2)
    novo_registro = [
        st.session_state.inicio_estudo.strftime("%d/%m/%Y"),
        st.session_state.inicio_estudo.strftime("%H:%M"),
        fim_estudo.strftime("%H:%M"),
        duracao_minutos,
        st.session_state.materia_atual
    ]

    try:
        api_request_with_retry(abas['registros'].append_row, novo_registro)
        
        st.session_state.ultimo_registro = {
            'materia': st.session_state.materia_atual,
            'duracao': duracao_minutos,
            'inicio': st.session_state.inicio_estudo.strftime("%H:%M"),
            'fim': fim_estudo.strftime("%H:%M")
        }
        
        st.session_state.ultima_atualizacao_cache['registros'] = None
        
        atualizar_resumo(abas['registros'], abas['resumo'])
        
        st.toast(f"✅ {st.session_state.materia_atual}: {duracao_minutos} minutos registrados!", icon="✅")
    except Exception as erro:
        st.error(f"Erro ao salvar registro: {erro}")

    st.session_state.estudo_ativo = False
    st.experimental_rerun()

def display_cronometro():
    """Exibe o cronômetro em tempo real durante o estudo."""
    if st.session_state.estudo_ativo:
        st.markdown("---")
        placeholder_cronometro = st.empty()

        while st.session_state.estudo_ativo:
            tempo_decorrido = (datetime.now() - st.session_state.inicio_estudo).total_seconds()

            with placeholder_cronometro.container():
                st.markdown(f"<p class='timer-display'>{formatar_duracao(tempo_decorrido)}</p>", unsafe_allow_html=True)
                col_info1, col_info2, col_botao = st.columns(3)
                col_info1.metric("Início", st.session_state.inicio_estudo.strftime("%H:%M:%S"))
                col_info2.metric("Matéria", st.session_state.materia_atual)
                if col_botao.button("⏹️ Parar agora", key="stop_floating"):
                    st.session_state.estudo_ativo = False
                    st.experimental_rerun()

        placeholder_cronometro.empty()

def display_historico(abas):
    """Exibe o histórico de estudos com filtros."""
    st.subheader("Histórico de Estudos")
    df_registros = obter_registros(abas['registros'])

    if df_registros.empty:
        st.warning("Nenhum registro encontrado", icon="⚠️")
        return

    col_filtro1, col_filtro2 = st.columns(2)
    with col_filtro1:
        materias_unicas = ["Todas"] + sorted(df_registros['Matéria'].unique().tolist())
        filtro_materia = st.selectbox("Filtrar por matéria:", materias_unicas)

    with col_filtro2:
        df_registros['Data'] = pd.to_datetime(df_registros['Data'], dayfirst=True, errors='coerce')
        min_data = df_registros['Data'].min().date()
        max_data = df_registros['Data'].max().date()
        intervalo_datas = st.date_input("Período:", value=(min_data, max_data), min_value=min_data, max_value=datetime.now().date())

    df_filtrado = df_registros.copy()
    if filtro_materia != "Todas":
        df_filtrado = df_filtrado[df_filtrado['Matéria'] == filtro_materia]

    if isinstance(intervalo_datas, tuple) and len(intervalo_datas) == 2:
        data_inicio, data_fim = intervalo_datas
        df_filtrado = df_filtrado[(df_filtrado['Data'].dt.date >= data_inicio) & (df_filtrado['Data'].dt.date <= data_fim)]

    df_filtrado = df_filtrado.sort_values('Data', ascending=False)
    total_minutos_periodo = df_filtrado['Duração (min)'].sum()
    st.metric("Total de horas estudadas no período", f"{(total_minutos_periodo / 60):.2f}h")

    st.dataframe(
        df_filtrado,
        column_config={
            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "Duração (min)": st.column_config.NumberColumn("Minutos", format="%.1f")
        },
        hide_index=True,
        use_container_width=True
    )

def display_resumo_materias(abas):
    """Exibe o resumo do tempo de estudo por matéria."""
    st.subheader("Progresso por Matéria")
    df_resumo = obter_resumo(abas['resumo'])

    if df_resumo.empty:
        st.warning("Dados de resumo não disponíveis", icon="⚠️")
        return

    df_resumo = df_resumo.sort_values('Duração (min)', ascending=False)
    col_tabela, col_grafico = st.columns([1, 2])

    with col_tabela:
        st.dataframe(
            df_resumo,
            column_config={
                "Duração (min)": st.column_config.ProgressColumn(
                    "Progresso",
                    help="Tempo estudado em minutos",
                    format="%.1f",
                    min_value=0,
                    max_value=df_resumo['Duração (min)'].max() * 1.1 if not df_resumo.empty else 1
                ),
                "Total (horas)": st.column_config.NumberColumn("Horas", format="%.2f h")
            },
            hide_index=True,
            use_container_width=True
        )

    with col_grafico:
        grafico = alt.Chart(df_resumo).mark_bar().encode(
            x=alt.X('Matéria:N', sort='-y', title=None),
            y=alt.Y('Duração (min):Q', title='Minutos Estudados'),
            color=alt.Color('Matéria:N', legend=None),
            tooltip=['Matéria', 'Duração (min)', alt.Tooltip('Total (horas)', format=".2f")]
        ).properties(height=400)
        st.altair_chart(grafico, use_container_width=True)

def display_analise_padroes(abas):
    """Exibe a análise de padrões de estudo semanais e estatísticas."""
    st.subheader("Análise de Padrões")
    df_registros = obter_registros(abas['registros'])

    if df_registros.empty:
        st.warning("Sem dados suficientes para análise de padrões", icon="⚠️")
        return

    df_registros['Duração (min)'] = pd.to_numeric(df_registros['Duração (min)'], errors='coerce')
    grafico_semanal = gerar_grafico_semanal(df_registros)
    if grafico_semanal:
        st.altair_chart(grafico_semanal, use_container_width=True)
    else:
        st.info("Dados insuficientes para gerar visualização semanal.")

    total_horas = df_registros['Duração (min)'].sum() / 60
    total_sessoes = len(df_registros)
    duracao_media = df_registros['Duração (min)'].mean() if not df_registros.empty else 0

    col_metricas = st.columns(3)
    col_metricas[0].metric("Total de Horas", f"{total_horas:.2f}h")
    col_metricas[1].metric("Total de Sessões", f"{total_sessoes}")
    col_metricas[2].metric("Duração Média", f"{duracao_media:.1f} min")

    st.subheader("Dicas Personalizadas")
    if duracao_media < 25 and total_sessoes > 0:
        st.info("📌 Suas sessões têm duração média curta. Experimente a técnica Pomodoro (25 minutos de estudo focado).")
    elif duracao_media > 90:
        st.info("📌 Sessões de estudo muito longas podem diminuir a retenção. Considere fazer pausas a cada 50-60 minutos.")

    if total_sessoes > 0:
        df_registros['Data'] = pd.to_datetime(df_registros['Data'], dayfirst=True, errors='coerce')
        dias_unicos = df_registros['Data'].dt.date.nunique()
        frequencia = total_sessoes / dias_unicos if dias_unicos > 0 else 0
        if frequencia < 1:
            st.info("🗓️ Parece que você não estuda todos os dias. Tentar estudar um pouco diariamente pode ajudar na consistência.")
        elif frequencia > 2:
            st.info("🚀 Você está com um ritmo intenso de estudos! Certifique-se de incluir descanso para evitar o esgotamento.")
    else:
        st.info("📊 Comece a registrar seus estudos para receber dicas personalizadas!")

def main():
    """Função principal para executar a aplicação Streamlit."""
    # Estilização CSS personalizada
    st.markdown("""
    <style>
        div.stButton > button:first-child {
            height: 3em;
            font-weight: bold;
        }
        .highlight {
            background-color: #f0f8ff;
            padding: 15px;
            border-radius: 8px;
            border-left: 5px solid #4682b4;
            margin: 10px 0;
        }
        .timer-display {
            font-size: 3rem !important;
            font-weight: bold !important;
            text-align: center !important;
        }
    </style>
    """, unsafe_allow_html=True)

    st.title("⏱️ Cronômetro de Estudos - GCM Caldas Novas")
    st.caption("Acompanhe seu tempo de estudo para o concurso")

    # Conexão com Google Sheets e carregamento de dados
    cliente_gs = conectar_google_sheets()
    planilha = carregar_planilha(cliente_gs)
    abas = carregar_abas(planilha)

    # MOSTRAR TABELA DE REGISTROS IMEDIATAMENTE (NOVO)
    st.subheader("📋 Verificação de Dados")
    st.write("Aqui estão os registros atuais para verificação:")
    df_registros = obter_registros(abas['registros'], forcar_atualizacao=True)
    st.dataframe(df_registros)
    
    # Verificação adicional das abas (OPCIONAL)
    st.subheader("🔍 Verificação de Abas")
    abas_disponiveis = [aba.title for aba in planilha.worksheets()]
    st.write(f"Abas disponíveis na planilha: {', '.join(abas_disponiveis)}")
    st.markdown("---")

    # Carregar matérias
    try:
        lista_materias = obter_materias(abas['materias'])
        if not lista_materias:
            st.warning("Nenhuma matéria cadastrada. Adicione matérias na aba 'Materias' da planilha.")
            lista_materias = ["Matéria Padrão"]
    except Exception as erro:
        st.error(f"Erro ao carregar matérias: {erro}")
        lista_materias = ["Matéria Padrão"]

    # Controles do cronômetro
    col_materia, col_botoes = st.columns([2, 2])

    with col_materia:
        materia_selecionada = st.selectbox(
            "Selecione a matéria:",
            lista_materias,
            index=0,
            key='materia_select',
            disabled=st.session_state.estudo_ativo
        )

    with col_botoes:
        if not st.session_state.estudo_ativo:
            if st.button("▶️ Iniciar Estudo", type="primary", use_container_width=True):
                handle_iniciar_estudo(materia_selecionada)
        else:
            if st.button("⏹️ Parar Estudo", type="secondary", use_container_width=True):
                handle_parar_estudo(abas)

    # Mostrar cronômetro quando ativo
    display_cronometro()

    # Último registro
    display_ultimo_registro()

    # Visualização de dados em tabs
    st.markdown("---")
    tab_historico, tab_resumo, tab_padroes = st.tabs(["📋 Histórico", "📊 Resumo por Matéria", "📅 Padrões Semanais"])

    with tab_historico:
        display_historico(abas)

    with tab_resumo:
        display_resumo_materias(abas)

    with tab_padroes:
        display_analise_padroes(abas)

    # Rodapé
    st.markdown("---")
    st.caption(f"Desenvolvido para GCM Caldas Novas | {datetime.now().year}")

if __name__ == "__main__":
    main()
