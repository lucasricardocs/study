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
DURACAO_MINIMA_SEGUNDOS = 10
MAX_RETRIES = 5
CACHE_TTL = 600

def inicializar_session_state():
    """Garante que todos os estados necessários estão inicializados"""
    defaults = {
        'estudo_ativo': False,
        'inicio_estudo': None,
        'materia_atual': None,
        'ultimo_registro': None,
        'tema': 'light',
        'registros_cache': None,
        'materias_cache': None,
        'resumo_cache': None,
        'ultima_atualizacao_cache': {
            'registros': None,
            'materias': None,
            'resumo': None
        }
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def exponential_backoff(retry_count):
    """Implementa uma espera exponencial para retentativa."""
    wait_time = min(2 ** retry_count + random.random(), 60)
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

def verificar_estrutura_planilha(planilha):
    """Verifica se a planilha tem a estrutura mínima necessária"""
    try:
        abas = api_request_with_retry(planilha.worksheets)
        abas_disponiveis = {aba.title for aba in abas}
        abas_requeridas = {"Registros", "Materias", "Resumo"}
        
        if not abas_requeridas.issubset(abas_disponiveis):
            faltantes = abas_requeridas - abas_disponiveis
            st.error(f"Estrutura incompleta. Faltam abas: {', '.join(faltantes)}")
            return False
            
        return True
    except Exception as erro:
        st.error(f"Falha na verificação da estrutura: {str(erro)[:200]}")
        return False

def carregar_abas(planilha):
    """Carrega as abas necessárias."""
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
    """Obtém registros com tratamento robusto de erros."""
    try:
        # Verificação segura do cache
        cache_valido = (
            not forcar_atualizacao and
            st.session_state.get('registros_cache') is not None and
            not cache_expirado('registros')
        )
        
        if cache_valido:
            return st.session_state.registros_cache
            
        # Busca dos dados
        registros = api_request_with_retry(aba_registros.get_all_records)
        df_registros = pd.DataFrame(registros) if registros else pd.DataFrame()
        
        # Atualização segura do cache
        st.session_state.registros_cache = df_registros
        st.session_state.ultima_atualizacao_cache['registros'] = datetime.now()
        
        return df_registros
        
    except Exception as erro:
        st.error(f"⚠️ Erro ao carregar registros. Usando cache local... Detalhes: {str(erro)[:200]}")
        return st.session_state.get('registros_cache', pd.DataFrame())

def obter_materias(aba_materias):
    """Obtém a lista de matérias com tratamento robusto."""
    try:
        # Verificação de cache
        if (st.session_state.get('materias_cache') is not None and 
            not cache_expirado('materias')):
            return st.session_state.materias_cache
            
        materias = api_request_with_retry(aba_materias.col_values, 1)[1:]  # Ignora cabeçalho
        materias = [m for m in materias if m.strip()]  # Remove valores vazios
        
        # Atualização do cache
        st.session_state.materias_cache = materias if materias else ["Matéria Padrão"]
        st.session_state.ultima_atualizacao_cache['materias'] = datetime.now()
        
        return st.session_state.materias_cache
        
    except Exception as erro:
        st.error(f"⚠️ Erro ao carregar matérias. Usando cache... Detalhes: {str(erro)[:200]}")
        return st.session_state.get('materias_cache', ["Matéria Padrão"])

def atualizar_resumo(aba_registros, aba_resumo):
    """Atualiza a aba de resumo com tratamento de erros."""
    try:
        df_registros = obter_registros(aba_registros)
        
        if df_registros.empty:
            api_request_with_retry(aba_resumo.clear)
            return pd.DataFrame()

        df_registros['Duração (min)'] = pd.to_numeric(df_registros['Duração (min)'], errors='coerce')
        totais_por_materia = df_registros.groupby('Matéria')['Duração (min)'].sum().reset_index()
        totais_por_materia['Total (horas)'] = (totais_por_materia['Duração (min)'] / 60).round(2)

        valores = [totais_por_materia.columns.values.tolist()] + totais_por_materia.values.tolist()
        api_request_with_retry(aba_resumo.clear)
        api_request_with_retry(aba_resumo.update, valores)
        
        st.session_state.resumo_cache = totais_por_materia
        st.session_state.ultima_atualizacao_cache['resumo'] = datetime.now()
        
        return totais_por_materia
    except Exception as erro:
        st.error(f"⚠️ Erro ao atualizar resumo. Detalhes: {str(erro)[:200]}")
        return st.session_state.get('resumo_cache', pd.DataFrame())

def gerar_grafico_semanal(df_registros):
    """Gera gráfico de horas estudadas por dia da semana."""
    if df_registros.empty:
        return None

    try:
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
    except Exception:
        return None

def display_ultimo_registro():
    """Exibe o último registro de estudo."""
    if st.session_state.get('ultimo_registro'):
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
    """Exibe o cronômetro em tempo real."""
    if st.session_state.get('estudo_ativo'):
        st.markdown("---")
        placeholder = st.empty()

        while st.session_state.estudo_ativo:
            tempo_decorrido = (datetime.now() - st.session_state.inicio_estudo).total_seconds()

            with placeholder.container():
                st.markdown(f"<p class='timer-display'>{formatar_duracao(tempo_decorrido)}</p>", unsafe_allow_html=True)
                col1, col2, col3 = st.columns(3)
                col1.metric("Início", st.session_state.inicio_estudo.strftime("%H:%M:%S"))
                col2.metric("Matéria", st.session_state.materia_atual)
                if col3.button("⏹️ Parar agora", key="stop_floating"):
                    st.session_state.estudo_ativo = False
                    st.experimental_rerun()

            time.sleep(1)
        
        placeholder.empty()

def display_historico(abas):
    """Exibe o histórico de estudos com filtros."""
    st.subheader("Histórico de Estudos")
    df_registros = obter_registros(abas['registros'])

    if df_registros.empty:
        st.warning("Nenhum registro encontrado", icon="⚠️")
        return

    with st.expander("🔍 Filtros", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            materias_unicas = ["Todas"] + sorted(df_registros['Matéria'].unique().tolist())
            filtro_materia = st.selectbox("Filtrar por matéria:", materias_unicas)

        with col2:
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
    total_minutos = df_filtrado['Duraçãot; (min)'].sum()
    
    st.metric("Total no período", f"{(total_minutos / 60):.2f} horas")
    st.dataframe(
        df_filtrado,
        column_config={
            "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Duraçãot; (min)": st.column_config.NumberColumn(format="%.1f")
        },
        hide_index=True,
        use_container_width=True
    )

def display_resumo_materias(abas):
    """Exibe o resumo por matéria."""
    st.subheader("Progresso por Matéria")
    df_resumo = obter_resumo(abas['resumo'])

    if df_resumo.empty:
        st.warning("Dados de resumo não disponíveis", icon="⚠️")
        return

    df_resumo = df_resumo.sort_values('Duraçãot; (min)', ascending=False)
    
    tab1, tab2 = st.tabs(["📊 Gráfico", "📋 Tabela"])
    
    with tab1:
        try:
            chart = alt.Chart(df_resumo).mark_bar().encode(
                x=alt.X('Matéria:N', sort='-y', title=None),
                y=alt.Y('Duraçãot; (min):Q', title='Minutos Estudados'),
                color=alt.Color('Matéria:N', legend=None),
                tooltip=['Matéria', 'Duraçãot; (min)', alt.Tooltip('Total (horas)', format=".2f")]
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)
        except Exception:
            st.error("Erro ao gerar gráfico")

    with tab2:
        st.dataframe(
            df_resumo,
            column_config={
                "Duraçãot; (min)": st.column_config.ProgressColumn(
                    format="%.1f",
                    min_value=0,
                    max_value=df_resumo['Duraçãot; (min)'].max() * 1.1
                ),
                "Total (horas)": st.column_config.NumberColumn(format="%.2f h")
            },
            hide_index=True,
            use_container_width=True
        )

def display_analise_padroes(abas):
    """Exibe análise de padrões de estudo."""
    st.subheader("Análise de Padrões")
    df_registros = obter_registros(abas['registros'])

    if df_registros.empty:
        st.warning("Sem dados suficientes para análise", icon="⚠️")
        return

    tab1, tab2 = st.tabs(["📅 Semanal", "📈 Estatísticas"])

    with tab1:
        grafico = gerar_grafico_semanal(df_registros)
        if grafico:
            st.altair_chart(grafico, use_container_width=True)
        else:
            st.info("Dados insuficientes para análise semanal")

    with tab2:
        df = df_registros.copy()
        df['Duraçãot; (min)'] = pd.to_numeric(df['Duraçãot; (min)'], errors='coerce')
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Horas", f"{(df['Duraçãot; (min)'].sum() / 60):.2f}h")
        col2.metric("Total de Sessões", len(df))
        col3.metric("Duração Média", f"{df['Duraçãot; (min)'].mean():.1f} min")

        st.subheader("Dicas Personalizadas")
        if len(df) > 0:
            if df['Duraçãot; (min)'].mean() < 25:
                st.info("📌 Experimente a técnica Pomodoro (25 minutos focados)")
            elif df['Duraçãot; (min)'].mean() > 90:
                st.info("📌 Considere pausas a cada 50-60 minutos para melhor retenção")
            
            freq = len(df) / df['Data'].nunique()
            if freq < 1:
                st.info("🗓️ Estude um pouco todos os dias para melhor consistência")
            elif freq > 2:
                st.info("🚀 Bom ritmo! Não esqueça dos descansos")

def modo_emergencia():
    """Interface mínima quando há falhas críticas"""
    st.error("🚨 Modo emergência ativado (sem conexão)")
    
    st.warning("Funcionalidades limitadas disponíveis:")
    
    if st.session_state.get('registros_cache') is not None:
        with st.expander("📋 Dados locais disponíveis"):
            st.dataframe(st.session_state.registros_cache)
    
    st.subheader("Simulação de Estudo")
    materia = st.selectbox("Matéria", ["Matemática", "Português", "Direito", "Outra"])
    
    if st.button("Simular sessão de estudo"):
        st.warning("Dados não serão salvos permanentemente")
        st.session_state.ultimo_registro = {
            'materia': materia,
            'duracao': random.randint(15, 120),
            'inicio': datetime.now().strftime("%H:%M"),
            'fim': (datetime.now() + timedelta(minutes=30)).strftime("%H:%M")
        }
        st.rerun()

def main():
    """Função principal da aplicação."""
    # CSS customizado
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
        .st-emotion-cache-16txtl3 {
            padding: 2rem 1rem;
        }
    </style>
    """, unsafe_allow_html=True)

    # Inicialização segura
    inicializar_session_state()

    try:
        # Conexão e verificação inicial
        st.title("⏱️ Cronômetro de Estudos - GCM Caldas Novas")
        
        cliente_gs = conectar_google_sheets()
        planilha = carregar_planilha(cliente_gs)
        
        if not verificar_estrutura_planilha(planilha):
            st.stop()
            
        abas = carregar_abas(planilha)
        
        # Seção de status
        with st.expander("🔍 Status do Sistema", expanded=True):
            cols = st.columns(3)
            cols[0].success("✅ Conexão estabelecida")
            cols[1].info(f"📊 Registros: {len(obter_registros(abas['registros']))}")
            cols[2].info(f"📚 Matérias: {len(obter_materias(abas['materias']))}")

        # Controles principais
        st.subheader("Controle de Estudo")
        col1, col2 = st.columns([2, 1])
        
        with col1:
            materia = st.selectbox(
                "Matéria",
                obter_materias(abas['materias']),
                disabled=st.session_state.get('estudo_ativo', False)
            )
        
        with col2:
            if not st.session_state.get('estudo_ativo', False):
                if st.button("▶️ Iniciar Estudo", type="primary", use_container_width=True):
                    handle_iniciar_estudo(materia)
            else:
                if st.button("⏹️ Parar Estudo", type="secondary", use_container_width=True):
                    handle_parar_estudo(abas)

        display_cronometro()
        display_ultimo_registro()

        # Visualizações
        st.markdown("---")
        tab1, tab2, tab3 = st.tabs(["📋 Histórico", "📊 Progresso", "📅 Análise"])
        
        with tab1:
            display_historico(abas)
        
        with tab2:
            display_resumo_materias(abas)
        
        with tab3:
            display_analise_padroes(abas)

    except Exception as e:
        st.error("Ocorreu um erro crítico na aplicação")
        modo_emergencia()

    # Rodapé
    st.markdown("---")
    st.caption(f"Desenvolvido para GCM Caldas Novas | {datetime.now().year}")

if __name__ == "__main__":
    main()
