import streamlit as st
import gspread
import pandas as pd
import altair as alt
import time
import random
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound, APIError

# Page configuration
st.set_page_config(
    page_title="Study Timer",
    page_icon="⏱️",
    layout="centered"
)

# Constants
SPREADSHEET_NAME = "study"
SPREADSHEET_ID = "1EyllfZ69b5H-n47iB-_Zau6nf3rcBEoG8qYNbYv5uGs"
MIN_DURATION_SECONDS = 10
MAX_RETRIES = 5
CACHE_TTL = 600

# Custom CSS
st.markdown("""
<style>
    /* Square font timer */
    .big-timer {
        font-family: 'Courier New', monospace;
        font-size: 5rem !important;
        font-weight: bold;
        letter-spacing: 2px;
        text-align: center;
        margin: 20px 0;
        color: #2e86c1;
        text-shadow: 1px 1px 3px rgba(0,0,0,0.2);
    }
    
    /* Beautiful buttons */
    .stButton>button {
        border-radius: 8px;
        border: 2px solid #2e86c1;
        padding: 12px 28px;
        font-weight: bold;
        font-size: 1.1rem;
        transition: all 0.3s;
        background-color: white;
        color: #2e86c1;
    }
    
    .stButton>button:hover {
        background-color: #2e86c1 !important;
        color: white !important;
        transform: scale(1.02);
    }
    
    .primary-button {
        background-color: #2e86c1 !important;
        color: white !important;
    }
    
    /* Button container */
    .button-container {
        display: flex;
        justify-content: center;
        gap: 20px;
        margin: 30px 0;
    }
    
    /* Info cards */
    .info-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 20px;
        border-left: 5px solid #2e86c1;
        margin-bottom: 25px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    
    /* Section headers */
    .section-header {
        color: #2e86c1;
        border-bottom: 2px solid #2e86c1;
        padding-bottom: 5px;
        margin-bottom: 15px;
    }
</style>
""", unsafe_allow_html=True)

# Session state initialization
if 'estudo_ativo' not in st.session_state:
    st.session_state.update({
        'estudo_ativo': False,
        'inicio_estudo': None,
        'materia_atual': None,
        'ultimo_registro': None,
        'registros_cache': None,
        'materias_cache': None,
        'resumo_cache': None,
        'ultima_atualizacao_cache': {
            'registros': None,
            'materias': None,
            'resumo': None
        }
    })

def exponential_backoff(retry_count):
    """Implements exponential backoff for retries"""
    wait_time = min(2 ** retry_count + random.random(), 60)
    time.sleep(wait_time)

@st.cache_resource(ttl=CACHE_TTL)
def conectar_google_sheets():
    """Connects to Google Sheets with error handling"""
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
        st.error(f"🔌 Connection failed: {erro}", icon="❌")
        st.stop()

def api_request_with_retry(func, *args, **kwargs):
    """Makes API calls with retry and exponential backoff"""
    for tentativa in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except APIError as erro:
            if erro.response.status_code == 429:
                if tentativa < MAX_RETRIES - 1:
                    st.warning(f"Rate limit reached, waiting... (attempt {tentativa+1}/{MAX_RETRIES})")
                    exponential_backoff(tentativa)
                else:
                    st.error("Persistent rate limit. Please try again later.")
                    raise
            else:
                st.error(f"API error: {erro}")
                raise
        except Exception as erro:
            st.error(f"Unexpected error: {erro}")
            raise

def carregar_planilha(cliente_gs):
    """Loads the specified spreadsheet, trying by ID then by name"""
    try:
        try:
            return api_request_with_retry(cliente_gs.open_by_key, SPREADSHEET_ID)
        except SpreadsheetNotFound:
            return api_request_with_retry(cliente_gs.open, SPREADSHEET_NAME)
    except SpreadsheetNotFound:
        st.error(f"📄 Spreadsheet '{SPREADSHEET_NAME}' (ID: {SPREADSHEET_ID}) not found", icon="🔍")
        st.stop()
    except Exception as erro:
        st.error(f"📂 Error accessing spreadsheet: {erro}", icon="❌")
        st.stop()

def verificar_estrutura_planilha(planilha):
    """Verifies if the spreadsheet has the required structure"""
    try:
        abas = api_request_with_retry(planilha.worksheets)
        abas_disponiveis = {aba.title for aba in abas}
        abas_requeridas = {"Registros", "Materias", "Resumo"}
        
        if not abas_requeridas.issubset(abas_disponiveis):
            faltantes = abas_requeridas - abas_disponiveis
            st.error(f"Missing sheets: {', '.join(faltantes)}")
            return False
            
        return True
    except Exception as erro:
        st.error(f"Structure verification failed: {str(erro)[:200]}")
        return False

def carregar_abas(planilha):
    """Loads the required worksheets"""
    return {
        'registros': planilha.worksheet("Registros"),
        'materias': planilha.worksheet("Materias"),
        'resumo': planilha.worksheet("Resumo")
    }

def formatar_duracao(segundos):
    """Formats seconds as HH:MM:SS"""
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{int(horas):02d}:{int(minutos):02d}:{int(segundos):02d}"

def cache_expirado(tipo_cache):
    """Checks if cache has expired"""
    ultima_att = st.session_state.ultima_atualizacao_cache.get(tipo_cache)
    if ultima_att is None:
        return True
    return (datetime.now() - ultima_att).total_seconds() > CACHE_TTL

def obter_registros(aba_registros, forcar_atualizacao=False):
    """Gets records with robust error handling"""
    try:
        # Safe cache verification
        cache_valido = (
            not forcar_atualizacao and
            st.session_state.get('registros_cache') is not None and
            not cache_expirado('registros')
        )
        
        if cache_valido:
            return st.session_state.registros_cache
            
        # Data retrieval
        registros = api_request_with_retry(aba_registros.get_all_records)
        df_registros = pd.DataFrame(registros) if registros else pd.DataFrame()
        
        # Cache update
        st.session_state.registros_cache = df_registros
        st.session_state.ultima_atualizacao_cache['registros'] = datetime.now()
        
        return df_registros
        
    except Exception as erro:
        st.error(f"⚠️ Error loading records. Using local cache... Details: {str(erro)[:200]}")
        return st.session_state.get('registros_cache', pd.DataFrame())

def obter_materias(aba_materias):
    """Gets subjects list with robust error handling"""
    try:
        # Cache verification
        if (st.session_state.get('materias_cache') is not None and 
            not cache_expirado('materias')):
            return st.session_state.materias_cache
            
        materias = api_request_with_retry(aba_materias.col_values, 1)[1:]  # Skip header
        materias = [m for m in materias if m.strip()]  # Remove empty values
        
        # Cache update
        st.session_state.materias_cache = materias if materias else ["Default Subject"]
        st.session_state.ultima_atualizacao_cache['materias'] = datetime.now()
        
        return st.session_state.materias_cache
        
    except Exception as erro:
        st.error(f"⚠️ Error loading subjects. Using cache... Details: {str(erro)[:200]}")
        return st.session_state.get('materias_cache', ["Default Subject"])

def atualizar_resumo(aba_registros, aba_resumo):
    """Updates summary sheet with error handling"""
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
        st.error(f"⚠️ Error updating summary. Details: {str(erro)[:200]}")
        return st.session_state.get('resumo_cache', pd.DataFrame())

def display_cronometro():
    """Displays large square-font timer"""
    if st.session_state.estudo_ativo:
        st.markdown("---")
        placeholder = st.empty()
        
        while st.session_state.estudo_ativo:
            tempo_decorrido = (datetime.now() - st.session_state.inicio_estudo).total_seconds()
            
            with placeholder.container():
                # Main timer
                st.markdown(f"<div class='big-timer'>{formatar_duracao(tempo_decorrido)}</div>", 
                           unsafe_allow_html=True)
                
                # Info cards
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"""
                    <div class='info-card'>
                        <h4>⏱️ IN PROGRESS</h4>
                        <p><b>Subject:</b> {st.session_state.materia_atual}</p>
                        <p><b>Started:</b> {st.session_state.inicio_estudo.strftime('%H:%M:%S')}</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Centered stop button
                st.markdown("<div class='button-container'>", unsafe_allow_html=True)
                if st.button("⏹️ STOP STUDY", type="primary", key="stop_button"):
                    st.session_state.estudo_ativo = False
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
                
            time.sleep(0.1)
        
        placeholder.empty()

def handle_iniciar_estudo(materia_selecionada):
    """Starts study session"""
    st.session_state.estudo_ativo = True
    st.session_state.inicio_estudo = datetime.now()
    st.session_state.materia_atual = materia_selecionada
    st.toast(f"Started studying {materia_selecionada}!", icon="📚")
    st.rerun()

def handle_parar_estudo(abas):
    """Stops study session and saves record"""
    fim_estudo = datetime.now()
    duracao_segundos = (fim_estudo - st.session_state.inicio_estudo).total_seconds()

    if duracao_segundos < MIN_DURATION_SECONDS:
        st.warning(f"⚠️ Minimum time not reached ({MIN_DURATION_SECONDS} seconds). Record not saved.")
        st.session_state.estudo_ativo = False
        st.rerun()
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
        
        st.toast(f"✅ {st.session_state.materia_atual}: {duracao_minutos} minutes recorded!", icon="✅")
    except Exception as erro:
        st.error(f"Error saving record: {erro}")

    st.session_state.estudo_ativo = False
    st.rerun()

def display_historico():
    """Displays simplified study history"""
    st.markdown("<h3 class='section-header'>STUDY HISTORY</h3>", unsafe_allow_html=True)
    
    with st.spinner("Loading data..."):
        df_registros = obter_registros(st.session_state.abas['registros'])
    
    if not df_registros.empty:
        # Calculate totals
        total_min = df_registros['Duração (min)'].sum()
        total_hrs = total_min / 60
        
        # Display metrics
        col1, col2 = st.columns(2)
        col1.metric("Total Minutes", f"{total_min:.0f} min")
        col2.metric("Total Hours", f"{total_hrs:.1f} h")
        
        # Simplified table
        st.dataframe(
            df_registros[['Data', 'Matéria', 'Duração (min)']].sort_values('Data', ascending=False),
            column_config={
                "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Duração (min)": st.column_config.NumberColumn(format="%.1f")
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.warning("No records found", icon="⚠️")

def main():
    # Connect to Google Sheets
    try:
        cliente_gs = conectar_google_sheets()
        planilha = carregar_planilha(cliente_gs)
        
        if not verificar_estrutura_planilha(planilha):
            st.stop()
            
        st.session_state.abas = carregar_abas(planilha)
    except Exception as e:
        st.error("Failed to connect to Google Sheets")
        st.stop()
    
    # App header
    st.title("⏱️ STUDY TIMER")
    st.markdown("---")
    
    # Control section
    st.markdown("<h3 class='section-header'>CONTROL PANEL</h3>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        materia_selecionada = st.selectbox(
            "SELECT SUBJECT:",
            obter_materias(st.session_state.abas['materias']),
            key='materia_select',
            disabled=st.session_state.estudo_ativo
        )
    
    with col2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if not st.session_state.estudo_ativo:
            if st.button("▶️ START", type="primary", use_container_width=True):
                handle_iniciar_estudo(materia_selecionada)
    
    # Display timer
    display_cronometro()
    
    # Display history
    st.markdown("---")
    display_historico()
    
    # Footer
    st.markdown("---")
    st.caption(f"© {datetime.now().year} Study Timer App | GCM Caldas Novas")

if __name__ == "__main__":
    main()
