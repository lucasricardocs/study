import streamlit as st
import gspread
import pandas as pd
import altair as alt
from datetime import datetime
from google.oauth2.service_account import Credentials
import time

# Configuração da página
st.set_page_config(
    page_title="Study Timer - GCM Caldas Novas",
    page_icon="⏱️",
    layout="wide"
)

# Verificação inicial das credenciais
if 'google_credentials' not in st.secrets:
    st.error("""
    🔐 Credenciais não encontradas. Por favor verifique:
    1. O arquivo secrets.toml existe na pasta .streamlit/
    2. As credenciais estão na seção [google_credentials]
    3. No Streamlit Cloud, as credências estão nas configurações
    """, icon="⚠️")
    st.stop()

# Inicialização do estado da sessão
if 'estudo_iniciado' not in st.session_state:
    st.session_state.update({
        'estudo_iniciado': False,
        'inicio': None,
        'materia_selecionada': None,
        'ultimo_registro': None
    })

# Constantes
SPREADSHEET_NAME = "study"
SPREADSHEET_ID = "1EyllfZ69b5H-n47iB-_Zau6nf3rcBEoG8qYNbYv5uGs"

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
        st.error(f"⚠️ Abas faltando. Necessárias: {abas_requeridas}. Disponíveis: {abas_disponiveis}")
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
            
        df['Duração (min)'] = pd.to_numeric(df['Duração (min)'])
        totais = df.groupby('Matéria')['Duração (min)'].sum().reset_index()
        totais['Total (horas)'] = (totais['Duração (min)'] / 60).round(2)
        
        resumo.clear()
        resumo.update([totais.columns.values.tolist()] + totais.values.tolist())
        return totais
    except Exception as e:
        st.error(f"📊 Erro ao atualizar resumo: {str(e)}", icon="❌")
        return pd.DataFrame()

# Interface principal
def main():
    st.title("⏱️ Cronômetro de Estudos - GCM Caldas Novas")
    st.caption("Acompanhe seu tempo de estudo para o concurso")

    # Conexão com Google Sheets
    gc = conectar_google_sheets()
    planilha = carregar_planilha(gc)
    abas = carregar_abas(planilha)

    # Carregar matérias
    lista_materias = abas['materias'].col_values(1)[1:]  # Ignora cabeçalho

    # Controles do cronômetro
    col1, col2 = st.columns(2)
    
    with col1:
        materia = st.selectbox(
            "Selecione a matéria:",
            lista_materias,
            index=0,
            key='materia_select'
        )
        
        if st.button("▶️ Iniciar Estudo", type="primary", use_container_width=True):
            st.session_state.estudo_iniciado = True
            st.session_state.inicio = datetime.now()
            st.session_state.materia_selecionada = materia
            st.toast(f"Estudo de {materia} iniciado!", icon="📚")

    with col2:
        if st.button("⏹️ Parar Estudo", type="secondary", use_container_width=True, disabled=not st.session_state.estudo_iniciado):
            fim = datetime.now()
            duracao_min = round((fim - st.session_state.inicio).total_seconds() / 60, 2)
            
            novo_registro = [
                st.session_state.inicio.strftime("%d/%m/%Y"),
                st.session_state.inicio.strftime("%H:%M"),
                fim.strftime("%H:%M"),
                duracao_min,
                st.session_state.materia_selecionada
            ]
            
            abas['registros'].append_row(novo_registro)
            st.session_state.ultimo_registro = {
                'materia': st.session_state.materia_selecionada,
                'duracao': duracao_min,
                'inicio': st.session_state.inicio.strftime("%H:%M"),
                'fim': fim.strftime("%H:%M")
            }
            atualizar_resumo(abas['registros'], abas['resumo'])
            
            st.session_state.estudo_iniciado = False
            st.toast(f"✅ {st.session_state.materia_selecionada}: {duracao_min} minutos registrados!", icon="✅")

    # Mostrar cronômetro
    if st.session_state.estudo_iniciado:
        st.markdown("---")
        placeholder = st.empty()
        
        while st.session_state.estudo_iniciado:
            tempo_decorrido = (datetime.now() - st.session_state.inicio).total_seconds()
            
            with placeholder.container():
                st.metric(
                    label="Tempo de estudo",
                    value=formatar_tempo(tempo_decorrido),
                    help=f"Estudando: {st.session_state.materia_selecionada}"
                )
                
                cols = st.columns(3)
                cols[0].metric("Início", st.session_state.inicio.strftime("%H:%M:%S"))
                cols[1].metric("Matéria", st.session_state.materia_selecionada)
                
                if cols[2].button("⏹️ Parar agora", key="stop_floating"):
                    st.session_state.estudo_iniciado = False
                    st.rerun()
            
            time.sleep(1)
        
        placeholder.empty()

    # Último registro
    if st.session_state.ultimo_registro:
        st.info(
            f"Último registro: {st.session_state.ultimo_registro['materia']} "
            f"({st.session_state.ultimo_registro['duracao']} min) "
            f"das {st.session_state.ultimo_registro['inicio']} às {st.session_state.ultimo_registro['fim']}"
        )

    # Visualização de dados
    st.markdown("---")
    tab1, tab2 = st.tabs(["📋 Histórico Completo", "📊 Resumo por Matéria"])
    
    with tab1:
        st.subheader("Histórico de Estudos")
        df_registros = pd.DataFrame(abas['registros'].get_all_records())
        
        if not df_registros.empty:
            df_registros['Data'] = pd.to_datetime(df_registros['Data'], dayfirst=True)
            df_registros = df_registros.sort_values('Data', ascending=False)
            st.dataframe(
                df_registros,
                column_config={
                    "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "Duração (min)": st.column_config.NumberColumn("Minutos", format="%.1f")
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.warning("Nenhum registro encontrado", icon="⚠️")

    with tab2:
        st.subheader("Progresso por Matéria")
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
                        )
                    },
                    hide_index=True,
                    use_container_width=True
                )
            
            with col2:
                chart = alt.Chart(df_resumo).mark_bar().encode(
                    x=alt.X('Matéria:N', sort='-y'),
                    y=alt.Y('Duração (min):Q', title='Minutos Estudados'),
                    color=alt.Color('Matéria:N', legend=None),
                    tooltip=['Matéria', 'Duração (min)', 'Total (horas)']
                ).properties(height=400)
                st.altair_chart(chart, use_container_width=True)
        else:
            st.warning("Dados de resumo não disponíveis", icon="⚠️")

if __name__ == "__main__":
    main()
