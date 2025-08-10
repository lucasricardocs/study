# -*- coding: utf-8 -*-
import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound

# --- Configurações da Planilha ---
# Cole aqui o ID da sua planilha e o nome da aba
SPREADSHEET_ID = '1EyllfZ69b5H-n47iB-_Zau6nf3rcBEoG8qYNbYv5uGs'
WORKSHEET_NAME = 'Registro'

# --- Funções de Conexão com Google Sheets ---
@st.cache_resource(ttl=600)
def get_gspread_client():
    """
    Autoriza o acesso ao Google Sheets usando as credenciais do Streamlit secrets.
    """
    try:
        # AQUI ESTÁ A ALTERAÇÃO: o código agora busca pela seção que você definiu.
        credentials_dict = st.secrets["gcp_service_account"]
        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.readonly'
        ]
        creds = Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except KeyError:
        st.error("Credenciais do Google não encontradas. Verifique o arquivo secrets.toml.")
        return None
    except Exception as e:
        st.error(f"Erro de autenticação com Google: {e}")
        return None

@st.cache_data(ttl=600)
def read_data_from_gsheet():
    """
    Lê os dados da planilha e retorna como um DataFrame do pandas.
    """
    client = get_gspread_client()
    if not client:
        return pd.DataFrame()
    
    try:
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        # Usamos get_all_records() porque ele retorna uma lista de dicionários,
        # facilitando a criação do DataFrame.
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        return df
    except SpreadsheetNotFound:
        st.error(f"A planilha com o ID '{SPREADSHEET_ID}' não foi encontrada.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao ler a aba '{WORKSHEET_NAME}': {e}")
        return pd.DataFrame()

# --- Estrutura da Aplicação Streamlit ---
def main():
    st.set_page_config(page_title="Dashboard de Teste", page_icon="✅")
    st.title("✅ Teste de Conexão com Google Sheets")

    st.markdown("---")
    
    st.info("Tentando ler os dados da planilha...")
    df = read_data_from_gsheet()
    
    if not df.empty:
        st.success("🎉 Conexão bem-sucedida! Dados carregados da planilha:")
        st.dataframe(df, use_container_width=True)
        st.write("Linhas lidas:", len(df))
    else:
        st.warning("⚠️ Não foi possível carregar os dados. Verifique os erros acima.")

if __name__ == "__main__":
    main()
