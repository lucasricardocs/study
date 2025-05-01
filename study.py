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
NOME_PLANILHA = "study"
ID_PLANILHA = "1EyllfZ69b5H-n47iB-_Zau6nf3rcBEoG8qYNbYv5uGs"
DURACAO_MINIMA_SEGUNDOS = 10
TENTATIVAS_MAXIMAS = 5
TEMPO_VIDA_CACHE = 600

# CSS personalizado
st.markdown("""
<style>
    /* Cronômetro grande com fonte quadrada */
    .cronometro {
        font-family: 'Courier New', monospace;
        font-size: 5rem !important;
        font-weight: bold;
        letter-spacing: 2px;
        text-align: center;
        margin: 20px 0;
        color: #2e86c1;
        text-shadow: 1px 1px 3px rgba(0,0,0,0.2);
    }
    
    /* Botões estilizados */
    .stButton>button {
        border-radius: 8px;
        border: 2px solid #2e86c1;
        padding: 12px 28px;
        font-weight: bold;
        font-size: 1.1rem;
        transition: all 0.3s;
    }
    
    .stButton>button:hover {
        background-color: #2e86c1 !important;
        color: white !important;
        transform: scale(1.02);
    }
    
    /* Contêiner de botões */
    .controle-botoes {
        display: flex;
        justify-content: center;
        gap: 20px;
        margin: 30px 0;
    }
    
    /* Cartões de informação */
    .cartao-info {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 20px;
        border-left: 5px solid #2e86c1;
        margin-bottom: 25px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    
    /* Cabeçalhos de seção */
    .cabecalho-secao {
        color: #2e86c1;
        border-bottom: 2px solid #2e86c1;
        padding-bottom: 5px;
        margin-bottom: 15px;
    }
</style>
""", unsafe_allow_html=True)

# Estado da sessão
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
        },
        'abas': None
    })

def conectar_google_sheets():
    """Conecta ao Google Sheets"""
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

def carregar_planilha(cliente_gs):
    """Carrega a planilha especificada"""
    try:
        return cliente_gs.open_by_key(ID_PLANILHA)
    except SpreadsheetNotFound:
        try:
            return cliente_gs.open(NOME_PLANILHA)
        except Exception as erro:
            st.error(f"📂 Erro ao acessar planilha: {erro}", icon="❌")
            st.stop()

def inicializar_abas(planilha):
    """Carrega as abas necessárias"""
    st.session_state.abas = {
        'registros': planilha.worksheet("Registros"),
        'materias': planilha.worksheet("Materias"),
        'resumo': planilha.worksheet("Resumo")
    }

def formatar_duracao(segundos):
    """Formata segundos em HH:MM:SS"""
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{int(horas):02d}:{int(minutos):02d}:{int(segundos):02d}"

def obter_materias():
    """Obtém a lista de matérias"""
    try:
        return st.session_state.abas['materias'].col_values(1)[1:]
    except Exception:
        return ["Matemática", "Português", "Direito"]

def exibir_cronometro():
    """Exibe o cronômetro principal"""
    if st.session_state.estudo_ativo:
        st.markdown("---")
        placeholder = st.empty()
        
        # Botão de parar (fora do loop para evitar duplicação)
        st.markdown("<div class='controle-botoes'>", unsafe_allow_html=True)
        parar = st.button("⏹️ PARAR ESTUDO", type="primary")
        st.markdown("</div>", unsafe_allow_html=True)
        
        while st.session_state.estudo_ativo and not parar:
            tempo_decorrido = (datetime.now() - st.session_state.inicio_estudo).total_seconds()
            
            with placeholder.container():
                st.markdown(f"<div class='cronometro'>{formatar_duracao(tempo_decorrido)}</div>", unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"""
                    <div class='cartao-info'>
                        <h4>⏱️ EM ANDAMENTO</h4>
                        <p><b>Matéria:</b> {st.session_state.materia_atual}</p>
                        <p><b>Início:</b> {st.session_state.inicio_estudo.strftime('%H:%M:%S')}</p>
                    </div>
                    """, unsafe_allow_html=True)
            
            time.sleep(0.1)
        
        if parar:
            st.session_state.estudo_ativo = False
            st.rerun()

def iniciar_estudo(materia):
    """Inicia uma sessão de estudo"""
    st.session_state.estudo_ativo = True
    st.session_state.inicio_estudo = datetime.now()
    st.session_state.materia_atual = materia
    st.toast(f"Iniciando estudo de {materia}!", icon="📚")
    st.rerun()

def parar_estudo():
    """Finaliza a sessão de estudo"""
    fim_estudo = datetime.now()
    duracao = (fim_estudo - st.session_state.inicio_estudo).total_seconds()
    
    if duracao < DURACAO_MINIMA_SEGUNDOS:
        st.warning("Tempo mínimo não atingido. Registro não salvo.")
        return
    
    novo_registro = [
        st.session_state.inicio_estudo.strftime("%d/%m/%Y"),
        st.session_state.inicio_estudo.strftime("%H:%M"),
        fim_estudo.strftime("%H:%M"),
        round(duracao/60, 2),
        st.session_state.materia_atual
    ]
    
    try:
        st.session_state.abas['registros'].append_row(novo_registro)
        st.toast("✅ Estudo registrado com sucesso!", icon="✅")
    except Exception as erro:
        st.error(f"Erro ao salvar: {erro}")

def exibir_historico():
    """Exibe o histórico e gráficos"""
    st.markdown("<h3 class='cabecalho-secao'>HISTÓRICO E ANÁLISE</h3>", unsafe_allow_html=True)
    
    try:
        registros = st.session_state.abas['registros'].get_all_records()
        df = pd.DataFrame(registros)
        
        if df.empty:
            st.warning("Nenhum registro encontrado")
            return
            
        df['Data'] = pd.to_datetime(df['Data'], dayfirst=True)
        df['Duração (min)'] = pd.to_numeric(df['Duração (min)'])
        
        # Métricas principais
        total_min = df['Duração (min)'].sum()
        total_hrs = total_min / 60
        media_min = df['Duração (min)'].mean()
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Minutos", f"{total_min:.0f} min")
        col2.metric("Total Horas", f"{total_hrs:.1f} h")
        col3.metric("Duração Média", f"{media_min:.1f} min")
        
        # Gráfico por matéria
        st.subheader("Tempo por Matéria")
        resumo = df.groupby('Matéria')['Duração (min)'].sum().reset_index()
        chart = alt.Chart(resumo).mark_bar().encode(
            x='Matéria',
            y='Duração (min)',
            color=alt.Color('Matéria', legend=None),
            tooltip=['Matéria', 'Duraçãot; (min)']
        ).properties(height=300)
        st.altair_chart(chart, use_container_width=True)
        
        # Gráfico semanal
        st.subheader("Distribuição Semanal")
        df['Dia'] = df['Data'].dt.day_name()
        dias_ordem = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        df['Dia'] = pd.Categorical(df['Dia'], categories=dias_ordem, ordered=True)
        weekly = df.groupby('Dia')['Duração (min)'].sum().reset_index()
        
        weekly_chart = alt.Chart(weekly).mark_bar().encode(
            x=alt.X('Dia', title='Dia da Semana'),
            y=alt.Y('Duração (min)', title='Minutos Estudados'),
            color=alt.value('#2e86c1'),
            tooltip=['Dia', 'Duraçãot; (min)']
        ).properties(height=300)
        st.altair_chart(weekly_chart, use_container_width=True)
        
    except Exception as erro:
        st.error(f"Erro ao cargar dados: {erro}")

def main():
    """Função principal"""
    # Conexão com Google Sheets
    if st.session_state.abas is None:
        try:
            cliente = conectar_google_sheets()
            planilha = carregar_planilha(cliente)
            inicializar_abas(planilha)
        except Exception:
            st.error("Falha ao conectar com o Google Sheets")
            return
    
    # Interface principal
    st.title("⏱️ CRONÔMETRO DE ESTUDOS")
    st.markdown("---")
    
    # Controle de estudo
    st.markdown("<h3 class='cabecalho-secao'>CONTROLE</h3>", unsafe_allow_html=True)
    col1, col2 = st.columns([3, 1])
    
    with col1:
        materia = st.selectbox(
            "SELECIONE A MATÉRIA:",
            obter_materias(),
            disabled=st.session_state.estudo_ativo
        )
    
    with col2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if not st.session_state.estudo_ativo:
            if st.button("▶️ INICIAR", use_container_width=True):
                iniciar_estudo(materia)
    
    # Exibe cronômetro
    exibir_cronometro()
    
    # Exibe histórico e gráficos
    exibir_historico()
    
    # Rodapé
    st.markdown("---")
    st.caption(f"© {datetime.now().year} Cronômetro de Estudos - GCM Caldas Novas")

if __name__ == "__main__":
    main()
