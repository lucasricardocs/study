# -*- coding: utf-8 -*-
import streamlit as st
import gspread
import pandas as pd
import altair as alt
import numpy as np
from datetime import datetime
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound
import warnings
import time

# Suprimir warnings específicos do pandas
warnings.filterwarnings('ignore', category=FutureWarning, message='.*observed=False.*')

# --- Configurações Globais e Constantes ---

# O ID e o nome da aba agora são fixos no código, como no primeiro exemplo.
# Mantenha os valores corretos para o seu projeto.
SPREADSHEET_ID = '1EyllfZ69b5H-n47iB-_Zau6nf3rcBEoG8qYNbYv5uGs'
WORKSHEET_NAME = 'Registro'

CONCURSO_DATE = datetime(2025, 9, 28) # Data do concurso

# Dados do edital (para calcular o progresso ponderado)
ED_DATA = {
    'Disciplinas': [
        'LÍNGUA PORTUGUESA',
        'RLM',
        'INFORMÁTICA',
        'LEGISLAÇÃO',
        'CONHECIMENTOS ESPECÍFICOS - ASSISTENTE EM ADMINISTRAÇÃO'
    ],
    'Total_Conteudos': [20, 15, 10, 15, 30],
    'Peso': [2, 1, 1, 1, 3]
}

# --- Funções de Cache para Acesso ao Google Sheets ---
@st.cache_resource
def get_google_auth():
    """Autoriza o acesso ao Google Sheets e retorna o cliente gspread."""
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets',
              'https://www.googleapis.com/auth/spreadsheets.readonly',
              'https://www.googleapis.com/auth/drive.readonly']
    try:
        if "google_credentials" not in st.secrets:
            st.error("Credenciais do Google ('google_credentials') não encontradas. Configure o arquivo .streamlit/secrets.toml")
            return None
        
        credentials_dict = st.secrets["google_credentials"]
        if not credentials_dict:
            st.error("As credenciais do Google em st.secrets estão vazias.")
            return None
            
        creds = Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)
        gc = gspread.authorize(creds)
        return gc
    except Exception as e:
        st.error(f"Erro de autenticação com Google: {e}")
        return None

@st.cache_resource
def get_worksheet():
    """Retorna o objeto worksheet da planilha especificada."""
    gc = get_google_auth()
    if gc:
        try:
            spreadsheet = gc.open_by_key(SPREADSHEET_ID)
            worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
            return worksheet
        except SpreadsheetNotFound:
            st.error(f"Planilha com ID '{SPREADSHEET_ID}' não encontrada.")
            return None
        except Exception as e:
            st.error(f"Erro ao acessar a aba '{WORKSHEET_NAME}': {e}")
            return None
    return None

@st.cache_data(ttl=600)
def read_sales_data():
    """Lê todos os registros da planilha e retorna como DataFrame."""
    worksheet = get_worksheet()
    if not worksheet:
        st.info("⚠️ Usando dados de exemplo, pois não foi possível conectar ao Google Sheets.")
        
        # Dados de exemplo agora usam as novas colunas
        sample_data = []
        np.random.seed(42)
        for disciplina in ED_DATA['Disciplinas']:
            for i in range(np.random.randint(5, 15)): # Conteúdo aleatório para cada disciplina
                status = 'Feito' if np.random.rand() < 0.5 else 'Pendente'
                sample_data.append({'Disciplinas': disciplina, 'Conteúdos': f'Tópico {i+1}', 'Status': status})
        
        return pd.DataFrame(sample_data)

    try:
        data = worksheet.get_all_values()
        if not data:
            st.warning("Planilha está vazia. Verifique se há dados na aba especificada.")
            return pd.DataFrame()
            
        headers = data[0]
        records = data[1:]
        
        df = pd.DataFrame(records, columns=headers)
        
        # Colunas obrigatórias
        required_columns = ['Disciplinas', 'Conteúdos', 'Status']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            st.error(f"Colunas obrigatórias não encontradas: {missing_columns}. Verifique o nome das colunas na planilha.")
            return pd.DataFrame()
            
        df['Status'] = df['Status'].astype(str).str.strip()
        df = df[df['Status'].isin(['Feito', 'Pendente'])]
        
        return df
    except Exception as e:
        st.error(f"Erro ao ler dados da planilha: {e}")
        return pd.DataFrame()

# ----------------------------------------------------------------------------------------------------------------------

# --- Funções de Processamento de Dados ---
def calculate_weighted_metrics(df_dados):
    """Calcula métricas de progresso ponderado com base no edital."""
    df_edital = pd.DataFrame(ED_DATA)
    
    if df_dados.empty or 'Disciplinas' not in df_dados.columns or 'Status' not in df_dados.columns:
        st.error("Dados insuficientes para calcular métricas.")
        return pd.DataFrame(), 0.0

    df_dados = df_dados.copy()
    df_dados['Status'] = df_dados['Status'].astype(str).str.strip()
    df_dados['Feito'] = (df_dados['Status'].str.lower() == 'feito').astype(int)
    df_dados['Pendente'] = (df_dados['Status'].str.lower() == 'pendente').astype(int)
    
    df_progresso_summary = df_dados.groupby('Disciplinas', observed=False).agg(
        Conteudos_Feitos=('Feito', 'sum'),
        Conteudos_Pendentes=('Pendente', 'sum')
    ).reset_index()
    
    df_final = pd.merge(df_edital, df_progresso_summary, on='Disciplinas', how='left').fillna(0)
    
    df_final['Total_Conteudos_Real'] = df_final['Conteudos_Feitos'] + df_final['Conteudos_Pendentes']
    df_final['Pontos_por_Conteudo'] = np.where(
        df_final['Total_Conteudos'] > 0,
        df_final['Peso'] / df_final['Total_Conteudos'],
        0
    )
    df_final['Pontos_Concluidos'] = df_final['Conteudos_Feitos'] * df_final['Pontos_por_Conteudo']
    df_final['Pontos_Totais'] = df_final['Total_Conteudos'] * df_final['Pontos_por_Conteudo']
    df_final['Pontos_Pendentes'] = df_final['Pontos_Totais'] - df_final['Pontos_Concluidos']
    
    df_final['Progresso_Ponderado'] = np.where(
        df_final['Peso'] > 0,
        np.round(df_final['Pontos_Concluidos'] / df_final['Peso'] * 100, 1),
        0
    )
    
    total_pontos = df_final['Peso'].sum()
    total_pontos_concluidos = df_final['Pontos_Concluidos'].sum()
    progresso_ponderado_geral = round(
        (total_pontos_concluidos / total_pontos) * 100, 1
    ) if total_pontos > 0 else 0
    
    return df_final, progresso_ponderado_geral

# ----------------------------------------------------------------------------------------------------------------------

# --- Funções de Design e Gráficos ---
def apply_light_theme_css():
    """Aplica CSS para tema limpo e profissional."""
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }
        
        .main-header {
            text-align: center;
            padding: 2rem 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 10px;
            margin-bottom: 2rem;
        }
        
        .section-header {
            font-size: 1.3rem;
            font-weight: 600;
            color: #2c3e50;
            margin: 2rem 0 1rem 0;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 0.5rem;
        }
        
        .footer {
            text-align: center;
            padding: 2rem 0;
            color: #666;
            border-top: 1px solid #eee;
            margin-top: 3rem;
        }
        </style>
    """, unsafe_allow_html=True)

def create_altair_donut_chart(data_row):
    """Cria um gráfico de rosca para o progresso ponderado."""
    df_chart = pd.DataFrame({
        'Status': ['Concluído', 'Pendente'],
        'Pontos': [data_row['Pontos_Concluidos'], data_row['Pontos_Pendentes']]
    })
    
    base = alt.Chart(df_chart).encode(theta=alt.Theta("Pontos:Q", stack=True))
    
    pie = base.mark_arc(outerRadius=85, innerRadius=55, stroke="white", strokeWidth=3).encode(
        color=alt.Color("Status:N", scale=alt.Scale(domain=['Concluído', 'Pendente'], range=['#667eea', '#e74c3c']), legend=None),
        tooltip=["Status:N", alt.Tooltip("Pontos:Q", format=".2f")]
    )
    
    text_progresso = alt.Chart(
        pd.DataFrame({'text': [f"{data_row['Progresso_Ponderado']:.1f}%"]})
    ).mark_text(
        align='center', baseline='middle', fontSize=20, fontWeight='bold', color='#2c3e50'
    ).encode(text=alt.Text('text:N'))
    
    return (pie + text_progresso).properties(
        title=alt.TitleParams(
            text=data_row['Disciplinas'], fontSize=14, fontWeight='bold', anchor='start'
        ),
        width=200, height=200
    ).resolve_scale(color='independent')

def create_altair_bar_chart(df_summary):
    """Cria gráfico de barras horizontal do progresso por disciplina."""
    df_melted = df_summary.melt(
        id_vars=['Disciplinas'],
        value_vars=['Conteudos_Feitos', 'Conteudos_Pendentes'],
        var_name='Status',
        value_name='Conteudos'
    )
    
    df_melted['Status_Display'] = df_melted['Status'].map({'Conteudos_Feitos': 'Concluído', 'Conteudos_Pendentes': 'Pendente'})
    
    chart = alt.Chart(df_melted).mark_bar(
        stroke='white', strokeWidth=1
    ).encode(
        x=alt.X('Conteudos:Q', title='Número de Conteúdos'),
        y=alt.Y('Disciplinas:N', sort='-x', title=''),
        color=alt.Color('Status_Display:N', scale=alt.Scale(domain=['Concluído', 'Pendente'], range=['#667eea', '#e74c3c']), legend=alt.Legend(title="Status", orient="top")),
        tooltip=['Disciplinas:N', 'Status_Display:N', 'Conteudos:Q']
    ).properties(title="Progresso por Disciplina", height=300)
    
    return chart

def create_priority_chart(df_summary):
    """Cria gráfico de prioridade baseado em peso vs progresso."""
    df_priority = df_summary.copy()
    df_priority['Prioridade'] = (100 - df_priority['Progresso_Ponderado']) * df_priority['Peso'] / 100
    
    chart = alt.Chart(df_priority).mark_circle(
        size=200, stroke='white', strokeWidth=2
    ).encode(
        x=alt.X('Progresso_Ponderado:Q', title='Progresso Atual (%)', scale=alt.Scale(domain=[0, 100])),
        y=alt.Y('Peso:Q', title='Peso da Disciplina'),
        size=alt.Size('Prioridade:Q', title='Prioridade', scale=alt.Scale(range=[100, 400])),
        color=alt.Color('Prioridade:Q', scale=alt.Scale(scheme='reds'), legend=None),
        tooltip=['Disciplinas:N', 'Progresso_Ponderado:Q', 'Peso:Q', 'Prioridade:Q']
    ).properties(title="Matriz de Prioridade de Estudo", width=400, height=300)
    
    return chart

# ----------------------------------------------------------------------------------------------------------------------

# --- Configuração da Página e UI Principal ---
st.set_page_config(
    page_title="Dashboard TAE UFG",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

apply_light_theme_css()

# Sidebar
with st.sidebar:
    st.markdown("### 🎯 Dashboard TAE UFG")
    st.markdown("---")
    
    dias_restantes = (CONCURSO_DATE - datetime.now()).days
    if dias_restantes > 0:
        st.success(f"🗓️ **{dias_restantes} dias** para o concurso")
        dias_uteis = int(dias_restantes * 5/7)
        st.info(f"📅 Aproximadamente **{dias_uteis} dias úteis**")
    else:
        st.warning("🎯 Concurso já realizado")
    
    st.markdown("---")
    
    if st.button("🔄 Atualizar Dados", type="primary"):
        st.cache_data.clear()
        st.rerun()
    
    with st.expander("ℹ️ Informações"):
        st.markdown("""
        **Pesos das Disciplinas:**
        - Língua Portuguesa: 2
        - RLM: 1
        - Informática: 1
        - Legislação: 1
        - Conhecimentos Específicos: 3
        """)

# Header Principal
st.markdown("""
<div class="main-header">
    <h1>📊 Dashboard TAE UFG</h1>
    <p>Acompanhamento do Progresso de Estudos</p>
</div>
""", unsafe_allow_html=True)

# Conteúdo Principal
df_dados = read_sales_data()

if not df_dados.empty:
    df_final, progresso_ponderado_geral = calculate_weighted_metrics(df_dados)
    
    st.markdown('<div class="section-header">📈 Resumo Geral</div>', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    
    total_conteudos_feito = df_dados[df_dados['Status'].str.lower() == 'feito'].shape[0]
    total_conteudos_pendente = df_dados[df_dados['Status'].str.lower() == 'pendente'].shape[0]
    total_conteudos = total_conteudos_feito + total_conteudos_pendente
    
    with col1:
        st.metric(label="🎯 Progresso Geral", value=f"{progresso_ponderado_geral:.1f}%")
    with col2:
        st.metric(label="✅ Conteúdos Feitos", value=f"{total_conteudos_feito}")
    with col3:
        st.metric(label="⏳ Conteúdos Pendentes", value=f"{total_conteudos_pendente}")
    with col4:
        taxa_conclusao = (total_conteudos_feito / total_conteudos * 100) if total_conteudos > 0 else 0
        st.metric(label="📊 Taxa de Conclusão", value=f"{taxa_conclusao:.1f}%")
    
    st.markdown("---")
    
    st.markdown('<div class="section-header">🎨 Personalizar Visualização</div>', unsafe_allow_html=True)
    disciplinas_disponiveis = list(df_final['Disciplinas'].unique())
    disciplinas_selecionadas = st.multiselect(
        "Selecione as disciplinas para visualização:", disciplinas_disponiveis, default=disciplinas_disponiveis
    )
    
    if disciplinas_selecionadas:
        df_final_filtered = df_final[df_final['Disciplinas'].isin(disciplinas_selecionadas)]
        
        st.markdown('<div class="section-header">🎯 Progresso por Disciplina</div>', unsafe_allow_html=True)
        num_cols = min(3, len(df_final_filtered))
        for i in range(0, len(df_final_filtered), num_cols):
            cols = st.columns(num_cols)
            for idx, (_, row) in enumerate(df_final_filtered.iloc[i:i+num_cols].iterrows()):
                with cols[idx]:
                    chart = create_altair_donut_chart(row)
                    st.altair_chart(chart, use_container_width=True)
        
        st.markdown("---")
        
        st.markdown('<div class="section-header">📊 Análise Detalhada</div>', unsafe_allow_html=True)
        col_left, col_right = st.columns(2)
        with col_left:
            chart_bar = create_altair_bar_chart(df_final_filtered)
            st.altair_chart(chart_bar, use_container_width=True)
        with col_right:
            chart_priority = create_priority_chart(df_final_filtered)
            st.altair_chart(chart_priority, use_container_width=True)
        
        with st.expander("📋 Dados Detalhados", expanded=False):
            st.markdown("**Resumo por Disciplina:**")
            display_columns = ['Disciplinas', 'Conteudos_Feitos', 'Conteudos_Pendentes', 'Progresso_Ponderado', 'Peso']
            df_display = df_final_filtered[display_columns].copy()
            df_display.columns = ['Disciplina', 'Feitos', 'Pendentes', 'Progresso (%)', 'Peso']
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            st.markdown("**Todos os Conteúdos:**")
            st.dataframe(df_dados[df_dados['Disciplinas'].isin(disciplinas_selecionadas)], use_container_width=True, hide_index=True)
    
    else:
        st.info("Selecione pelo menos uma disciplina para visualizar os dados.")

else:
    st.error("❌ Não foi possível carregar os dados. Verifique sua conexão e configurações.")
    st.markdown("""
    **Possíveis soluções:**
    1. Verifique se o ID da planilha está correto
    2. Confirme se a aba 'Registro' existe
    3. Verifique as permissões de acesso à planilha
    4. Confirme se as credenciais do Google estão configuradas corretamente
    """)

# Rodapé
st.markdown("""
<div class="footer">
    <p>
        🚀 Dashboard desenvolvido com Streamlit |
        📊 Concurso TAE UFG 2025 |
        💡 Acompanhe seu progresso de forma inteligente
    </p>
</div>
""", unsafe_allow_html=True)
