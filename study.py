import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import time
import pytz

# --- Initialization ---
if 'estudo_ativo' not in st.session_state:
    st.session_state.estudo_ativo = False
if 'hora_inicio' not in st.session_state:
    st.session_state.hora_inicio = None
if 'materia_atual' not in st.session_state:
    st.session_state.materia_atual = None
if 'ultimo_registro' not in st.session_state:
    st.session_state.ultimo_registro = None
if 'cronometro_container' not in st.session_state:
    st.session_state.cronometro_container = None

# --- Google Sheets Functions ---
def conectar_google_sheets():
    try:
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive',
                 'https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_info(
            st.secrets["google_credentials"],
            scopes=scope
        )
        cliente = gspread.authorize(creds)
        return cliente
    except Exception as e:
        st.error(f"Erro ao conectar ao Google Sheets: {e}")
        return None

def carregar_planilha(cliente_gs):
    try:
        planilha = cliente_gs.open("study")
        return planilha
    except Exception as e:
        st.error(f"Erro ao carregar planilha: {e}")
        return None

def carregar_abas(planilha):
    if not planilha:
        return {}
    try:
        return {
            'registros': planilha.worksheet("Registros"),
            'materias': planilha.worksheet("Materias")
        }
    except Exception as e:
        st.error(f"Erro ao carregar abas da planilha: {e}")
        return {}

def obter_materias_lista(aba_materias):
    try:
        if not aba_materias:
            return []
        materias = aba_materias.col_values(1)
        if materias and materias[0].lower() == 'matéria':
            materias = materias[1:]
        return materias
    except Exception as e:
        st.error(f"Erro ao obter lista de matérias: {e}")
        return []

def obter_registros_df(aba_registros):
    try:
        if not aba_registros:
            return pd.DataFrame()
        dados = aba_registros.get_all_values()
        if not dados:
            return pd.DataFrame()
        cabecalho = dados[0]
        registros = dados[1:]
        df = pd.DataFrame(registros, columns=cabecalho)
        return df
    except Exception as e:
        st.error(f"Erro ao obter registros: {e}")
        return pd.DataFrame()

def registrar_estudo(abas, materia, inicio_brasilia, fim_brasilia, duracao):
    """Registra o estudo na planilha."""
    try:
        data_hoje = inicio_brasilia.strftime("%d/%m/%Y")
        hora_inicio_str = inicio_brasilia.strftime("%H:%M:%S")
        hora_fim_str = fim_brasilia.strftime("%H:%M:%S")
        duracao_minutos = round(duracao.total_seconds() / 60, 2)  # More precise duration

        novo_registro = [data_hoje, hora_inicio_str, hora_fim_str, str(duracao_minutos), materia]
        abas['registros'].append_row(novo_registro)
        st.success(f"Estudo de {duracao_minutos} minutos em {materia} registrado.")
    except Exception as e:
        st.error(f"Erro ao registrar estudo: {e}")

# --- Session Management ---
def handle_iniciar_estudo(materia_selecionada):
    st.session_state.estudo_ativo = True
    brasilia_tz = pytz.timezone('America/Sao_Paulo')
    st.session_state.hora_inicio = datetime.now(brasilia_tz)
    st.session_state.materia_atual = materia_selecionada
    st.info(f"Estudo iniciado em {materia_selecionada} às {st.session_state.hora_inicio.strftime('%H:%M:%S')} (Brasília)")
    st.rerun()

def handle_parar_estudo(abas):
    if st.session_state.estudo_ativo and st.session_state.hora_inicio:
        brasilia_tz = pytz.timezone('America/Sao_Paulo')
        hora_fim = datetime.now(brasilia_tz)
        duracao = hora_fim - st.session_state.hora_inicio
        registrar_estudo(abas, st.session_state.materia_atual, st.session_state.hora_inicio, hora_fim, duracao)

        st.session_state.ultimo_registro = {
            'data': hora_fim.strftime("%d/%m/%Y"),
            'hora_inicio': st.session_state.hora_inicio.strftime("%H:%M:%S"),
            'hora_fim': hora_fim.strftime("%H:%M:%S"),
            'materia': st.session_state.materia_atual,
            'duracao': round(duracao.total_seconds() / 60, 2)
        }

    st.session_state.estudo_ativo = False
    st.session_state.hora_inicio = None
    st.session_state.materia_atual = None
    st.rerun()

# --- Display Functions ---
def display_cronometro():
    st.subheader("⏱️ Cronômetro")
    cronometro_placeholder = st.empty()
    brasilia_tz = pytz.timezone('America/Sao_Paulo')

    if st.session_state.estudo_ativo and st.session_state.hora_inicio:
        while st.session_state.estudo_ativo:
            tempo_atual_brasilia = datetime.now(brasilia_tz)
            duracao = tempo_atual_brasilia - st.session_state.hora_inicio
            horas = int(duracao.total_seconds() // 3600)
            minutos = int((duracao.total_seconds() % 3600) // 60)
            segundos = int(duracao.total_seconds() % 60)
            tempo_formatado = f"{horas:02d}:{minutos:02d}:{segundos:02d}"
            cronometro_placeholder.markdown(f"""
                <div style="background-color: black; color: green; padding: 20px; border-radius: 3px; font-size: 7em; text-align: center; font-family: 'Courier New', monospace; font-weight: bold;">
                    {tempo_formatado}
                </div>
            """, unsafe_allow_html=True)
            time.sleep(1)
        else:
            cronometro_placeholder.markdown(f"""
                <div style="background-color: black; color: green; padding: 20px; border-radius: 3px; font-size: 7em; text-align: center; font-family: 'Courier New', monospace; font-weight: bold;">
                    00:00:00
                </div>
            """, unsafe_allow_html=True)
    else:
        cronometro_placeholder.markdown(f"""
            <div style="background-color: black; color: green; padding: 20px; border-radius: 3px; font-size: 7em; text-align: center; font-family: 'Courier New', monospace; font-weight: bold;">
                00:00:00
            </div>
        """, unsafe_allow_html=True)

def display_ultimo_registro():
    if st.session_state.ultimo_registro:
        registro = st.session_state.ultimo_registro
        if 'hora_inicio' in registro:
            st.subheader("Último Registro")
            st.write(f"**Matéria:** {registro['materia']}")
            st.write(f"**Início (Brasília):** {registro['hora_inicio']}")
            st.write(f"**Fim (Brasília):** {registro['hora_fim']}")
            st.write(f"**Duração:** {registro['duracao']} min")
        else:
            st.subheader("Sem registros recentes")
            st.warning("O último registro parece incompleto.", icon="⚠️")
    else:
        st.subheader("Sem registros recentes")

def display_historico(abas):
    st.subheader("Histórico de Estudos")
    df_registros = obter_registros_df(abas['registros'])
    if not df_registros.empty:
        st.dataframe(
            df_registros,
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("Nenhum registro de estudo encontrado.")
def display_resumo_materias(abas):
    st.markdown("<h2 style='font-family: \"Digital-7\", sans-serif;'>Resumo por Matéria</h2>", unsafe_allow_html=True)
    df_registros = obter_registros_df(abas['registros'])
    if df_registros.empty:
        st.info("Sem dados para mostrar no resumo.")
        return

    df_registros['Duração (min)'] = pd.to_numeric(df_registros['Duração (min)'], errors='coerce')
    df_resumo = df_registros.groupby('Matéria').agg({'Duração (min)': 'sum'}).reset_index()
    df_resumo['Total (horas)'] = df_resumo['Duração (min)'] / 60
    df_resumo = df_resumo.sort_values('Duração (min)', ascending=False)

    st.dataframe(
        df_resumo,
        column_config={
            "Duração (min)": st.column_config.ProgressColumn(
                "Progresso",
                help="Tempo estudado em minutos",
                format="%.2f",
                min_value=0,
                max_value=df_resumo['Duração (min)'].max() * 1.1 if not df_resumo.empty and df_resumo['Duração (min)'].max() > 0 else 1
            ),
            "Total (horas)": st.column_config.NumberColumn("Horas", format="%.2f h")
        },
        hide_index=True,
        use_container_width=True
    )

    if not df_resumo.empty:
        grafico = alt.Chart(df_resumo).mark_bar().encode(
            x=alt.X('Matéria:N', sort='-y', title=None),
            y=alt.Y('Duração (min):Q', title='Minutos Estudados'),
            color=alt.Color('Matéria:N', legend=None),
            tooltip=['Matéria', alt.Tooltip('Duração (min)', format=".2f"), alt.Tooltip('Total (horas)', format=".2f")]
        ).properties(height=500)  # Aumentei a altura para 500 pixels
        st.altair_chart(grafico, use_container_width=True)
    else:
        st.info("Nenhum dado de resumo para exibir no gráfico.")

def gerar_grafico_semanal(df_registros):
    try:
        if df_registros.empty:
            return None
        df_registros['Data'] = pd.to_datetime(df_registros['Data'], dayfirst=True, errors='coerce')
        data_limite = datetime.now() - timedelta(days=30)
        df_recente = df_registros[df_registros['Data'] >= data_limite]
        if df_recente.empty:
            return None
        df_recente['DiaSemana'] = df_recente['Data'].dt.day_name()
        ordem_dias = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        nomes_dias = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
        mapa_dias = dict(zip(ordem_dias, nomes_dias))
        df_recente['DiaSemana'] = df_recente['DiaSemana'].map(mapa_dias)
        df_semanal = df_recente.groupby('DiaSemana').agg({'Duração (min)': 'sum'}).reset_index()
        dias_faltantes = [dia for dia in nomes_dias if dia not in df_semanal['DiaSemana'].values]
        df_complemento = pd.DataFrame({'DiaSemana': dias_faltantes, 'Duração (min)': [0] * len(dias_faltantes)})
        df_semanal = pd.concat([df_semanal, df_complemento], ignore_index=True)
        ordem_dias_pt = dict(zip(nomes_dias, range(len(nomes_dias))))
        df_semanal['ordem'] = df_semanal['DiaSemana'].map(ordem_dias_pt)
        df_semanal = df_semanal.sort_values('ordem')
        grafico = alt.Chart(df_semanal).mark_bar().encode(
            x=alt.X('DiaSemana:N', sort=list(mapa_dias.values()), title='Dia da Semana'),
            y=alt.Y('Duração (min):Q', title='Minutos Estudados'),
            color=alt.Color('DiaSemana:N', legend=None),
            tooltip=['DiaSemana', alt.Tooltip('Duração (min)', format=".1f")]
        ).properties(
            title='Distribuição de Estudos por Dia da Semana',
            height=400  # Aumentei a altura para 400 pixels
        )
        return grafico
    except Exception as e:
        st.error(f"Erro ao gerar gráfico semanal: {e}")
        return None
        
def display_analise_padroes(abas):
    st.subheader("Análise de Padrões")
    df_registros = obter_registros_df(abas['registros'])
    if df_registros.empty:
        st.warning("Sem dados suficientes para análise de padrões", icon="⚠️")
        st.info("Registre mais sessões de estudo para ver seus padrões.")
        return
    df_registros['Duração (min)'] = pd.to_numeric(df_registros['Duração (min)'], errors='coerce')
    grafico_semanal = gerar_grafico_semanal(df_registros)
    if grafico_semanal:
        st.altair_chart(grafico_semanal, use_container_width=True)
    else:
        st.info("Dados insuficientes para gerar visualização semanal (requer dados dos últimos 30 dias).")
    total_horas = df_registros['Duração (min)'].sum() / 60
    total_sessoes = len(df_registros)
    duracao_media = df_registros['Duração (min)'].mean() if not df_registros.empty else 0
    col_metricas = st.columns(3)
    col_metricas[0].metric("Total de Horas", f"{total_horas:.2f}h")
    col_metricas[1].metric("Total de Sessões", f"{total_sessoes}")
    col_metricas[2].metric("Duração Média", f"{duracao_media:.2f} min")
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
    st.markdown("""
    <style>
        div.stButton > button:first-child {
            height: 3em;
            font-weight: bold;
        }
    </style>
    """, unsafe_allow_html=True)

    st.title("Cronômetro de Estudos para GCM Caldas Novas")
    st.caption("Acompanhe seu tempo de estudo para o concurso")

    cliente_gs = conectar_google_sheets()
    if cliente_gs:
        planilha = carregar_planilha(cliente_gs)
        if planilha:
            abas = carregar_abas(planilha)

            lista_materias = obter_materias_lista(abas['materias'])
            if not lista_materias:
                st.warning("Nenhuma matéria cadastrada. Adicione matérias na aba 'Materias' da planilha.")
                lista_materias = ["Matéria Padrão"]

            with st.sidebar:
                st.subheader("Iniciar Nova Sessão")
                materia_selecionada = st.selectbox(
                    "Selecione a matéria:",
                    lista_materias,
                    index=0,
                    key='materia_select',
                    disabled=st.session_state.estudo_ativo
                )
                if not st.session_state.estudo_ativo:
                    if st.button("▶️ Iniciar Estudo", type="primary", use_container_width=True):
                        handle_iniciar_estudo(materia_selecionada)
                else:
                    if st.button("⏹️ Parar Estudo", type="secondary", use_container_width=True):
                        handle_parar_estudo(abas)

                st.markdown("---")
                display_ultimo_registro()

            col_direita = st.container()
            with col_direita:
                display_cronometro()

                st.markdown("---")
                tab_historico, tab_resumo, tab_padroes = st.tabs(["📋 Histórico", "📊 Resumo por Matéria", "📅 Padrões Semanais"])

                with tab_historico:
                    display_historico(abas)

                with tab_resumo:
                    display_resumo_materias(abas)

                with tab_padroes:
                    display_analise_padroes(abas)

    st.markdown("---")
    st.caption(f"Desenvolvido para GCM Caldas Novas | {datetime.now().year}")

if __name__ == "__main__":
    main()
