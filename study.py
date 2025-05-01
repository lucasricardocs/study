import streamlit as st
import gspread
import pandas as pd
import altair as alt
import time
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound

# Configuração da página
st.set_page_config(
    page_title="Cronômetro de Estudos", 
    page_icon="⏱️",
    layout="centered"
)

# Constantes
SPREADSHEET_NAME = "study"
SPREADSHEET_ID = "1EyllfZ69b5H-n47iB-_Zau6nf3rcBEoG8qYNbYv5uGs"
MIN_DURATION_SECONDS = 10  # Duração mínima para registrar (10 segundos)

# Inicialização do estado da sessão
if 'estudo_iniciado' not in st.session_state:
    st.session_state.update({
        'estudo_iniciado': False,
        'inicio': None,
        'materia_selecionada': None,
        'ultimo_registro': None,
        'tema': 'light'  # Tema padrão
    })

@st.cache_resource(ttl=300)
def conectar_google_sheets():
    """Conecta ao Google Sheets com tratamento de erros"""
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["google_credentials"],
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"🔌 Falha na conexão: {str(e)}", icon="❌")
        st.stop()

def carregar_planilha(gc):
    """Carrega a planilha especificada com tratamento de erros"""
    try:
        # Tenta abrir pelo ID primeiro
        try:
            return gc.open_by_key(SPREADSHEET_ID)
        except:
            # Fallback para busca por nome
            return gc.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        st.error(f"📄 Planilha '{SPREADSHEET_NAME}' (ID: {SPREADSHEET_ID}) não encontrada", icon="🔍")
        st.stop()
    except Exception as e:
        st.error(f"📂 Erro ao acessar planilha: {str(e)}", icon="❌")
        st.stop()

def carregar_abas(planilha):
    """Carrega as abas necessárias com verificação"""
    abas_requeridas = {"Registros", "Materias", "Resumo"}
    abas_disponiveis = {ws.title for ws in planilha.worksheets()}
    
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

# Funções auxiliares
def formatar_tempo(segundos):
    """Converte segundos para HH:MM:SS"""
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{int(horas):02d}:{int(minutos):02d}:{int(segundos):02d}"

def atualizar_resumo(registros, resumo):
    """Atualiza a aba de resumo com os totais"""
    try:
        df = pd.DataFrame(registros.get_all_records())
        
        if df.empty:
            return pd.DataFrame()
            
        # Garantir que a coluna seja numérica
        df['Duração (min)'] = pd.to_numeric(df['Duração (min)'], errors='coerce')
        
        # Agrupar por matéria
        totais = df.groupby('Matéria')['Duração (min)'].sum().reset_index()
        totais['Total (horas)'] = (totais['Duração (min)'] / 60).round(2)
        
        # Atualizar a planilha de resumo
        resumo.clear()
        resumo.update([totais.columns.values.tolist()] + totais.values.tolist())
        return totais
    except Exception as e:
        st.error(f"📊 Erro ao atualizar resumo: {str(e)}", icon="❌")
        return pd.DataFrame()

def gerar_visualizacao_semanal(df_registros):
    """Gera visualização de horas estudadas por dia da semana"""
    if df_registros.empty:
        return None
    
    # Garantir que a data está no formato correto
    df_registros['Data'] = pd.to_datetime(df_registros['Data'], errors='coerce', dayfirst=True)
    
    # Filtrar apenas últimos 30 dias
    data_limite = datetime.now() - timedelta(days=30)
    df_ultimos_30dias = df_registros[df_registros['Data'] >= data_limite]
    
    if df_ultimos_30dias.empty:
        return None
    
    # Adicionar dia da semana
    df_ultimos_30dias['Dia Semana'] = df_ultimos_30dias['Data'].dt.day_name()
    
    # Agrupar por dia da semana
    ordem_dias = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    nomes_dias = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
    
    # Mapeamento de inglês para português
    mapa_dias = dict(zip(ordem_dias, nomes_dias))
    df_ultimos_30dias['Dia Semana'] = df_ultimos_30dias['Dia Semana'].map(mapa_dias)
    
    # Agrupar
    df_por_dia = df_ultimos_30dias.groupby('Dia Semana')['Duração (min)'].sum().reset_index()
    
    # Reordenar dias
    df_por_dia['Ordem'] = df_por_dia['Dia Semana'].map(dict(zip(nomes_dias, range(7))))
    df_por_dia = df_por_dia.sort_values('Ordem').drop('Ordem', axis=1)
    
    # Converter para horas
    df_por_dia['Horas'] = df_por_dia['Duração (min)'] / 60
    
    return alt.Chart(df_por_dia).mark_bar().encode(
        x=alt.X('Dia Semana:N', title='Dia da Semana', sort=nomes_dias),
        y=alt.Y('Horas:Q', title='Horas Estudadas'),
        color=alt.Color('Dia Semana:N', legend=None),
        tooltip=['Dia Semana', 'Horas:Q']
    ).properties(height=300, title='Horas de Estudo por Dia da Semana (Últimos 30 dias)')

# Interface principal
def main():
    # Estilização CSS personalizada
    st.markdown("""
    <style>
        div.stButton > button:first-child {
            height: 3em;
            font-weight: bold;
        }
        .highlight {
            background-color: #f0f8ff;
            padding: 20px;
            border-radius: 10px;
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

    # Conexão com Google Sheets
    gc = conectar_google_sheets()
    planilha = carregar_planilha(gc)
    abas = carregar_abas(planilha)

    # Carregar matérias
    try:
        lista_materias = abas['materias'].col_values(1)[1:]  # Ignora cabeçalho
        if not lista_materias:
            st.warning("Nenhuma matéria cadastrada. Adicione matérias na aba 'Materias' da planilha.")
            lista_materias = ["Matéria Padrão"]
    except Exception as e:
        st.error(f"Erro ao carregar matérias: {e}")
        lista_materias = ["Matéria Padrão"]

    # Controles do cronômetro
    col1, col2 = st.columns(2)
    
    with col1:
        materia = st.selectbox(
            "Selecione a matéria:",
            lista_materias,
            index=0,
            key='materia_select'
        )
        
        if st.button("▶️ Iniciar Estudo", type="primary", use_container_width=True, disabled=st.session_state.estudo_iniciado):
            st.session_state.estudo_iniciado = True
            st.session_state.inicio = datetime.now()
            st.session_state.materia_selecionada = materia
            st.toast(f"Estudo de {materia} iniciado!", icon="📚")
            st.experimental_rerun()

    with col2:
        if st.button("⏹️ Parar Estudo", type="secondary", use_container_width=True, disabled=not st.session_state.estudo_iniciado):
            fim = datetime.now()
            segundos_decorridos = (fim - st.session_state.inicio).total_seconds()
            
            # Verificar duração mínima
            if segundos_decorridos < MIN_DURATION_SECONDS:
                st.warning(f"⚠️ Tempo mínimo não atingido ({MIN_DURATION_SECONDS} segundos). Registro não salvo.")
                st.session_state.estudo_iniciado = False
                st.experimental_rerun()
            
            duracao_min = round(segundos_decorridos / 60, 2)
            
            novo_registro = [
                st.session_state.inicio.strftime("%d/%m/%Y"),
                st.session_state.inicio.strftime("%H:%M"),
                fim.strftime("%H:%M"),
                duracao_min,
                st.session_state.materia_selecionada
            ]
            
            try:
                abas['registros'].append_row(novo_registro)
                st.session_state.ultimo_registro = {
                    'materia': st.session_state.materia_selecionada,
                    'duracao': duracao_min,
                    'inicio': st.session_state.inicio.strftime("%H:%M"),
                    'fim': fim.strftime("%H:%M")
                }
                atualizar_resumo(abas['registros'], abas['resumo'])
                st.toast(f"✅ {st.session_state.materia_selecionada}: {duracao_min} minutos registrados!", icon="✅")
            except Exception as e:
                st.error(f"Erro ao salvar registro: {e}")
            
            st.session_state.estudo_iniciado = False
            st.experimental_rerun()

    # Mostrar cronômetro quando ativo
    if st.session_state.estudo_iniciado:
        st.markdown("---")
        placeholder = st.empty()
        
        while st.session_state.estudo_iniciado:
            tempo_decorrido = (datetime.now() - st.session_state.inicio).total_seconds()
            
            with placeholder.container():
                st.markdown(f"<p class='timer-display'>{formatar_tempo(tempo_decorrido)}</p>", unsafe_allow_html=True)
                
                cols = st.columns(3)
                cols[0].metric("Início", st.session_state.inicio.strftime("%H:%M:%S"))
                cols[1].metric("Matéria", st.session_state.materia_selecionada)
                
                if cols[2].button("⏹️ Parar agora", key="stop_floating"):
                    st.session_state.estudo_iniciado = False
                    st.experimental_rerun()
            
            time.sleep(1)
        
        placeholder.empty()

    # Último registro
    if st.session_state.ultimo_registro:
        st.markdown("<div class='highlight'>", unsafe_allow_html=True)
        st.info(
            f"Último registro: **{st.session_state.ultimo_registro['materia']}** "
            f"({st.session_state.ultimo_registro['duracao']} min) "
            f"das {st.session_state.ultimo_registro['inicio']} às {st.session_state.ultimo_registro['fim']}"
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # Visualização de dados
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["📋 Histórico", "📊 Resumo por Matéria", "📅 Padrões Semanais"])
    
    # Tab 1: Histórico completo
    with tab1:
        st.subheader("Histórico de Estudos")
        
        try:
            df_registros = pd.DataFrame(abas['registros'].get_all_records())
            
            # Filtros
            col1, col2 = st.columns(2)
            with col1:
                if not df_registros.empty and 'Matéria' in df_registros.columns:
                    materias_unicas = ["Todas"] + sorted(df_registros['Matéria'].unique().tolist())
                    filtro_materia = st.selectbox("Filtrar por matéria:", materias_unicas)
            
            with col2:
                if not df_registros.empty and 'Data' in df_registros.columns:
                    df_registros['Data'] = pd.to_datetime(df_registros['Data'], dayfirst=True, errors='coerce')
                    min_date = df_registros['Data'].min().date()
                    max_date = df_registros['Data'].max().date()
                    intervalo_datas = st.date_input(
                        "Período:",
                        value=(min_date, max_date),
                        min_value=min_date,
                        max_value=datetime.now().date()
                    )
            
            if not df_registros.empty:
                # Aplicar filtros
                df_filtrado = df_registros.copy()
                
                if filtro_materia != "Todas":
                    df_filtrado = df_filtrado[df_filtrado['Matéria'] == filtro_materia]
                
                if isinstance(intervalo_datas, tuple) and len(intervalo_datas) == 2:
                    data_inicio, data_fim = intervalo_datas
                    df_filtrado = df_filtrado[
                        (df_filtrado['Data'].dt.date >= data_inicio) & 
                        (df_filtrado['Data'].dt.date <= data_fim)
                    ]
                
                # Ordenar por data decrescente
                df_filtrado = df_filtrado.sort_values('Data', ascending=False)
                
                # Adicionar totais
                total_minutos = df_filtrado['Duração (min)'].sum()
                st.metric(
                    "Total de horas estudadas no período", 
                    f"{(total_minutos / 60):.2f}h", 
                    help="Total de horas no período selecionado"
                )
                
                # Exibir tabela
                st.dataframe(
                    df_filtrado,
                    column_config={
                        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                        "Duração (min)": st.column_config.NumberColumn("Minutos", format="%.1f")
                    },
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.warning("Nenhum registro encontrado", icon="⚠️")
        except Exception as e:
            st.error(f"Erro ao carregar histórico: {e}")

    # Tab 2: Resumo por matéria
    with tab2:
        st.subheader("Progresso por Matéria")
        try:
            df_resumo = pd.DataFrame(abas['resumo'].get_all_records())
            
            if not df_resumo.empty:
                df_resumo = df_resumo.sort_values('Duração (min)', ascending=False)
                
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    st.dataframe(
                        df_resumo,
                        column_config={
                            "Duração (min)": st.column_config.ProgressColumn(
                                "Progresso",
                                help="Tempo estudado em minutos",
                                format="%.1f",
                                min_value=0,
                                max_value=df_resumo['Duração (min)'].max() * 1.1
                            ),
                            "Total (horas)": st.column_config.NumberColumn(
                                "Horas",
                                format="%.2f h"
                            )
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                
                with col2:
                    chart = alt.Chart(df_resumo).mark_bar().encode(
                        x=alt.X('Matéria:N', sort='-y', title=None),
                        y=alt.Y('Duração (min):Q', title='Minutos Estudados'),
                        color=alt.Color('Matéria:N', legend=None),
                        tooltip=['Matéria', 'Duração (min)', 'Total (horas)']
                    ).properties(height=400)
                    st.altair_chart(chart, use_container_width=True)
            else:
                st.warning("Dados de resumo não disponíveis", icon="⚠️")
        except Exception as e:
            st.error(f"Erro ao carregar resumo: {e}")
    
    # Tab 3: Padrões semanais
    with tab3:
        st.subheader("Análise de Padrões")
        try:
            df_registros = pd.DataFrame(abas['registros'].get_all_records())
            
            if not df_registros.empty:
                df_registros['Duração (min)'] = pd.to_numeric(df_registros['Duração (min)'], errors='coerce')
                
                # Gráfico por dia da semana
                grafico_semanal = gerar_visualizacao_semanal(df_registros)
                if grafico_semanal:
                    st.altair_chart(grafico_semanal, use_container_width=True)
                else:
                    st.info("Dados insuficientes para gerar visualização semanal.")
                
                # Calcular estatísticas
                total_horas = df_registros['Duração (min)'].sum() / 60
                total_sessoes = len(df_registros)
                duracao_media = df_registros['Duração (min)'].mean()
                
                # Exibir estatísticas
                cols = st.columns(3)
                cols[0].metric("Total de Horas", f"{total_horas:.2f}h")
                cols[1].metric("Total de Sessões", f"{total_sessoes}")
                cols[2].metric("Duração Média", f"{duracao_media:.1f} min")
                
                # Dicas baseadas nos dados
                st.subheader("Dicas Personalizadas")
                
                if duracao_media < 30:
                    st.info("📌 Suas sessões têm duração média curta. Considere aumentar para 25-30 minutos (técnica pomodoro).")
                elif duracao_media > 90:
                    st.info("📌 Suas sessões são longas. Considere fazer pausas mais frequentes para melhorar a retenção.")
                
                if total_sessoes > 0:
                    # Verificar frequência de estudos
                    df_registros['Data'] = pd.to_datetime(df_registros['Data'], dayfirst=True, errors='coerce')
                    dias_unicos = df_registros['Data'].dt.date.nunique()
                    
                    if dias_unicos > 0:
                        frequencia = total_sessoes / dias_unicos
                        if frequencia < 1.5:
                            st.info("📌 Você tende a fazer poucas sessões por dia. Estudar com mais frequência e em sessões menores pode melhorar o aprendizado.")
            else:
                st.warning("Sem dados suficientes para análise de padrões", icon="⚠️")
        except Exception as e:
            st.error(f"Erro na análise de padrões: {e}")
    
    # Rodapé
    st.markdown("---")
    st.caption("Desenvolvido para GCM Caldas Novas | 2025")

if __name__ == "__main__":
    main()
