import streamlit as st
import gspread
import pandas as pd
import altair as alt
from datetime import datetime
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound
import time

# Configuração da página
st.set_page_config(page_title="Cronômetro de Estudos GCM", layout="wide")

# Função para conectar ao Google Sheets
def conectar_google_sheets():
    """Conecta ao Google Sheets usando as credenciais do Streamlit secrets"""
    try:
        # Definir os escopos necessários
        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # Obter credenciais do secrets.toml
        credentials_dict = st.secrets["google_credentials"]
        creds = Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)
        gc = gspread.authorize(creds)
        
        return gc
    except Exception as e:
        st.error(f"Erro ao conectar ao Google Sheets: {e}")
        return None

# Função para carregar dados da planilha
def carregar_dados(gc):
    """Carrega todas as abas necessárias da planilha"""
    try:
        spreadsheet_id = st.secrets["1EyllfZ69b5H-n47iB-_Zau6nf3rcBEoG8qYNbYv5uGs"]
        spreadsheet = gc.open_by_key(spreadsheet_id)
        
        # Carregar cada aba
        registros = spreadsheet.worksheet("Registros")
        materias = spreadsheet.worksheet("Materias")
        resumo = spreadsheet.worksheet("Resumo")
        
        return registros, materias, resumo
    except SpreadsheetNotFound:
        st.error("Planilha não encontrada. Verifique o ID da planilha.")
        return None, None, None
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return None, None, None

# Função para formatar tempo
def formatar_tempo(minutos):
    """Converte minutos para formato HH:MM"""
    horas = int(minutos // 60)
    mins = int(minutos % 60)
    return f"{horas:02d}:{mins:02d}"

# Função para atualizar resumo
def atualizar_resumo(registros, resumo):
    """Atualiza a aba Resumo com os totais por matéria"""
    try:
        # Obter dados como DataFrame
        df_registros = pd.DataFrame(registros.get_all_records())
        
        # Verificar se há dados
        if df_registros.empty:
            return None
            
        # Calcular totais por matéria (convertendo para numérico)
        df_registros['Duração (min)'] = pd.to_numeric(df_registros['Duração (min)'], errors='coerce')
        totais = df_registros.groupby('Matéria')['Duração (min)'].sum().reset_index()
        totais['Total (horas)'] = totais['Duração (min)'].apply(formatar_tempo)
        
        # Atualizar aba Resumo
        resumo.clear()
        resumo.update([totais.columns.values.tolist()] + totais.values.tolist())
        
        return totais
    except Exception as e:
        st.error(f"Erro ao atualizar resumo: {e}")
        return None

# Interface principal
def main():
    # Inicializar estado da sessão
    if 'estudo_iniciado' not in st.session_state:
        st.session_state.estudo_iniciado = False
    if 'inicio' not in st.session_state:
        st.session_state.inicio = None
    if 'materia_selecionada' not in st.session_state:
        st.session_state.materia_selecionada = None

    # Conectar ao Google Sheets
    gc = conectar_google_sheets()
    if not gc:
        st.stop()
    
    # Carregar dados
    registros, materias, resumo = carregar_dados(gc)
    if not registros or not materias or not resumo:
        st.stop()

    # Obter lista de matérias (ignorando cabeçalho se existir)
    lista_materias = materias.col_values(1)
    if lista_materias[0] == "Matéria":  # Se tiver cabeçalho
        lista_materias = lista_materias[1:]

    # Layout do cronômetro
    st.title("⏱ Cronômetro de Estudos - GCM Caldas Novas")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Controle de Estudo")
        materia = st.selectbox("Selecione a matéria:", lista_materias, key='select_materia')
        
        if st.button("▶️ Iniciar Estudo", type="primary") and not st.session_state.estudo_iniciado:
            st.session_state.estudo_iniciado = True
            st.session_state.inicio = datetime.now()
            st.session_state.materia_selecionada = materia
            st.success(f"Estudo de {materia} iniciado!")
    
    with col2:
        st.subheader("Ações")
        if st.button("⏹️ Parar Estudo", type="secondary") and st.session_state.estudo_iniciado:
            fim = datetime.now()
            duracao = round((fim - st.session_state.inicio).total_seconds() / 60, 1)  # Em minutos
            
            # Registrar na aba Registros
            novo_registro = [
                st.session_state.inicio.strftime("%d/%m/%Y"),
                st.session_state.inicio.strftime("%H:%M"),
                fim.strftime("%H:%M"),
                str(duracao),
                st.session_state.materia_selecionada
            ]
            registros.append_row(novo_registro)
            
            # Atualizar resumo
            atualizar_resumo(registros, resumo)
            
            st.success(f"Estudo de {st.session_state.materia_selecionada} registrado! Duração: {formatar_tempo(duracao)}")
            st.session_state.estudo_iniciado = False

    # Mostrar cronômetro em tempo real
    if st.session_state.estudo_iniciado:
        st.markdown("---")
        placeholder = st.empty()
        
        while st.session_state.estudo_iniciado:
            tempo_decorrido = datetime.now() - st.session_state.inicio
            horas, resto = divmod(tempo_decorrido.seconds, 3600)
            minutos, segundos = divmod(resto, 60)
            
            with placeholder.container():
                st.metric("Tempo de estudo", f"{horas:02d}:{minutos:02d}:{segundos:02d}")
                st.write(f"Matéria: **{st.session_state.materia_selecionada}**")
                st.write(f"Iniciado às: {st.session_state.inicio.strftime('%H:%M:%S')}")
                
                if st.button("⏹️ Parar Estudo (alternativo)", key="stop_alternativo"):
                    # Mesma lógica do botão principal
                    fim = datetime.now()
                    duracao = round((fim - st.session_state.inicio).total_seconds() / 60, 1)
                    
                    novo_registro = [
                        st.session_state.inicio.strftime("%d/%m/%Y"),
                        st.session_state.inicio.strftime("%H:%M"),
                        fim.strftime("%H:%M"),
                        str(duracao),
                        st.session_state.materia_selecionada
                    ]
                    registros.append_row(novo_registro)
                    atualizar_resumo(registros, resumo)
                    
                    st.session_state.estudo_iniciado = False
                    st.experimental_rerun()
            
            time.sleep(1)
        
        placeholder.empty()

    # Visualização de dados
    st.markdown("---")
    tab1, tab2 = st.tabs(["📋 Histórico", "📊 Resumo"])
    
    with tab1:
        st.subheader("Histórico de Estudos")
        df_registros = pd.DataFrame(registros.get_all_records())
        
        if not df_registros.empty:
            # Converter durações para numérico para ordenação
            df_registros['Duração (min)'] = pd.to_numeric(df_registros['Duração (min)'], errors='coerce')
            df_registros['Data'] = pd.to_datetime(df_registros['Data'], format='%d/%m/%Y')
            df_ordenado = df_registros.sort_values("Data", ascending=False)
            
            # Formatando a data para exibição
            df_ordenado['Data'] = df_ordenado['Data'].dt.strftime('%d/%m/%Y')
            
            st.dataframe(df_ordenado, hide_index=True)
        else:
            st.info("Nenhum registro de estudo encontrado.")

    with tab2:
        st.subheader("Resumo por Matéria")
        df_resumo = pd.DataFrame(resumo.get_all_records())
        
        if not df_resumo.empty:
            # Converter para numérico para ordenação
            df_resumo['Total (min)'] = pd.to_numeric(df_resumo['Total (min)'], errors='coerce')
            df_ordenado = df_resumo.sort_values("Total (min)", ascending=False)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.dataframe(df_ordenado, hide_index=True)
            
            with col2:
                # Gráfico de barras
                chart = alt.Chart(df_ordenado).mark_bar().encode(
                    x='Matéria',
                    y='Total (min)',
                    color=alt.Color('Matéria', legend=None)
                ).properties(
                    width=600,
                    height=400
                )
                st.altair_chart(chart, use_container_width=True)
        else:
            st.info("Nenhum dado de resumo disponível.")

if __name__ == "__main__":
    main()
