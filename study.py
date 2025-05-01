import streamlit as st
import gspread
import pandas as pd
import altair as alt
import time
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
DURACAO_MINIMA_SEGUNDOS = 10

# Inicialização do estado da sessão
if 'estudo_ativo' not in st.session_state:
    st.session_state.update({
        'estudo_ativo': False,
        'inicio_estudo': None,
        'materia_atual': None,
        'ultimo_registro': None,
        'planilha_conectada': False,
        'aba_registros': None
    })

# Função para conectar ao Google Sheets
def conectar_google_sheets():
    try:
        credenciais = Credentials.from_service_account_info(
            st.secrets["google_credentials"],
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
        cliente = gspread.authorize(credenciais)
        planilha = cliente.open("Registro de Estudos")
        aba_registros = planilha.worksheet("Registros")
        st.session_state.planilha_conectada = True
        st.session_state.aba_registros = aba_registros
        return True
    except Exception as e:
        st.error(f"Erro ao conectar ao Google Sheets: {e}")
        return False

# Função para formatar a duração
def formatar_duracao(segundos):
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{int(horas):02d}:{int(minutos):02d}:{int(segundos):02d}"

# Função para iniciar o estudo
def iniciar_estudo(materia_selecionada):
    if not st.session_state.planilha_conectada:
        if not conectar_google_sheets():
            return
    
    st.session_state.estudo_ativo = True
    st.session_state.inicio_estudo = datetime.now()
    st.session_state.materia_atual = materia_selecionada
    st.toast(f"Estudo de {materia_selecionada} iniciado!", icon="📚")
    st.rerun()

# Função para parar o estudo e registrar
def parar_estudo():
    fim_estudo = datetime.now()
    duracao_segundos = (fim_estudo - st.session_state.inicio_estudo).total_seconds()
    
    if duracao_segundos < DURACAO_MINIMA_SEGUNDOS:
        st.warning(f"Tempo mínimo não atingido ({DURACAO_MINIMA_SEGUNDOS} segundos). Registro não salvo.")
    else:
        duracao_minutos = round(duracao_segundos / 60, 2)
        registro = [
            st.session_state.inicio_estudo.strftime("%d/%m/%Y"),
            st.session_state.inicio_estudo.strftime("%H:%M"),
            fim_estudo.strftime("%H:%M"),
            duracao_minutos,
            st.session_state.materia_atual
        ]
        
        try:
            st.session_state.aba_registros.append_row(registro)
            st.session_state.ultimo_registro = {
                'materia': st.session_state.materia_atual,
                'duracao': duracao_minutos,
                'inicio': st.session_state.inicio_estudo.strftime("%H:%M"),
                'fim': fim_estudo.strftime("%H:%M")
            }
            st.toast(f"✅ {st.session_state.materia_atual}: {duracao_minutos} minutos registrados!", icon="✅")
        except Exception as e:
            st.error(f"Erro ao salvar registro: {e}")
    
    st.session_state.estudo_ativo = False
    st.rerun()

# Função para exibir o cronômetro
def exibir_cronometro():
    if st.session_state.estudo_ativo:
        st.markdown("---")
        placeholder = st.empty()
        stop_button_pressed = False
        
        while st.session_state.estudo_ativo and not stop_button_pressed:
            tempo_decorrido = (datetime.now() - st.session_state.inicio_estudo).total_seconds()
            
            with placeholder.container():
                st.markdown(f"""
                <div style="font-family: 'Courier New', monospace; 
                            font-size: 5rem; 
                            font-weight: bold;
                            text-align: center;
                            color: #2e86c1;
                            margin: 20px 0;">
                    {formatar_duracao(tempo_decorrido)}
                </div>
                """, unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                col1.metric("Matéria", st.session_state.materia_atual)
                col2.metric("Início", st.session_state.inicio_estudo.strftime("%H:%M:%S"))
                
                if st.button("⏹️ Parar Estudo", type="primary", key="botao_parar"):
                    stop_button_pressed = True
                    parar_estudo()
            
            time.sleep(1)

# Função principal
def main():
    st.title("⏱️ Cronômetro de Estudos")
    
    # Controles
    col1, col2 = st.columns([3, 1])
    
    with col1:
        materia = st.selectbox(
            "Selecione a matéria:",
            ["Matemática", "Português", "Direito", "Outros"],
            disabled=st.session_state.estudo_ativo,
            key="seletor_materia"
        )
    
    with col2:
        if not st.session_state.estudo_ativo:
            if st.button("▶️ Iniciar Estudo", type="primary", use_container_width=True, key="botao_iniciar"):
                iniciar_estudo(materia)
    
    # Exibir cronômetro
    exibir_cronometro()
    
    # Exibir último registro
    if st.session_state.get('ultimo_registro'):
        st.markdown("---")
        st.subheader("Último Registro")
        st.write(f"Matéria: {st.session_state.ultimo_registro['materia']}")
        st.write(f"Duração: {st.session_state.ultimo_registro['duracao']} minutos")
        st.write(f"Horário: {st.session_state.ultimo_registro['inicio']} às {st.session_state.ultimo_registro['fim']}")
    
    # Tentar conectar ao Google Sheets se ainda não conectado
    if not st.session_state.planilha_conectada:
        conectar_google_sheets()

if __name__ == "__main__":
    main()
