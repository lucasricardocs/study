import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime, timedelta, date
import time
import gspread
from google.oauth2.service_account import Credentials

# Inicialização de variáveis de estado
if 'estudo_ativo' not in st.session_state:
    st.session_state.estudo_ativo = False
if 'hora_inicio' not in st.session_state:
    st.session_state.hora_inicio = None
if 'materia_atual' not in st.session_state:
    st.session_state.materia_atual = None
if 'ultimo_registro' not in st.session_state:
    st.session_state.ultimo_registro = None

def conectar_google_sheets():
    """Conecta à API do Google Sheets usando credenciais."""
    try:
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive',
                 'https://www.googleapis.com/auth/spreadsheets']  # Adicione a scope do spreadsheets aqui
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
    """Carrega a planilha específica."""
    try:
        # Usa o nome correto da planilha
        planilha = cliente_gs.open("study")
        return planilha
    except Exception as e:
        st.error(f"Erro ao carregar planilha: {e}")
        return None

def carregar_abas(planilha):
    """Carrega as abas da planilha."""
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
    """Obtém a lista de matérias da aba correspondente."""
    try:
        if not aba_materias:
            return []
        materias = aba_materias.col_values(1)
        # Remove o cabeçalho se existir
        if materias and materias[0].lower() == 'matéria':
            materias = materias[1:]
        return materias
    except Exception as e:
        st.error(f"Erro ao obter lista de matérias: {e}")
        return []

def obter_registros_df(aba_registros):
    """Obtém os registros de estudo como DataFrame."""
    try:
        if not aba_registros:
            return pd.DataFrame()

        # Obtém todos os dados da planilha
        dados = aba_registros.get_all_values()
        if not dados:
            return pd.DataFrame()

        # Converte para DataFrame
        cabecalho = dados[0]
        registros = dados[1:]
        df = pd.DataFrame(registros, columns=cabecalho)

        return df
    except Exception as e:
        st.error(f"Erro ao obter registros: {e}")
        return pd.DataFrame()

def handle_iniciar_estudo(materia_selecionada):
    """Inicia uma nova sessão de estudo."""
    st.session_state.estudo_ativo = True
    st.session_state.hora_inicio = datetime.now()
    st.session_state.materia_atual = materia_selecionada
    st.success(f"Estudo iniciado: {materia_selecionada}")
    st.rerun() # Adiciona para atualizar a interface imediatamente

def handle_parar_estudo(abas):
    """Finaliza a sessão de estudo atual e registra na planilha."""
    if st.session_state.estudo_ativo and st.session_state.hora_inicio:
        duracao = datetime.now() - st.session_state.hora_inicio
        duracao_minutos = round(duracao.total_seconds() / 60, 1)

        # Registra o estudo na planilha
        try:
            data_hoje = datetime.now().strftime("%d/%m/%Y")
            hora_atual = datetime.now().strftime("%H:%M")

            novo_registro = [data_hoje, hora_atual, st.session_state.materia_atual, str(duracao_minutos)]
            abas['registros'].append_row(novo_registro)

            # Atualiza o último registro na sessão
            st.session_state.ultimo_registro = {
                'data': data_hoje,
                'hora': hora_atual,
                'materia': st.session_state.materia_atual,
                'duracao': duracao_minutos
            }

            st.success(f"Estudo finalizado: {duracao_minutos} minutos")
        except Exception as e:
            st.error(f"Erro ao registrar estudo: {e}")

    # Reseta o estado
    st.session_state.estudo_ativo = False
    st.session_state.hora_inicio = None
    st.session_state.materia_atual = None
    st.rerun() # Adiciona para atualizar a interface imediatamente

def display_cronometro():
    """Exibe o cronômetro de estudo."""
    st.subheader("⏱️ Cronômetro")

    if st.session_state.estudo_ativo and st.session_state.hora_inicio:
        # Calcula o tempo decorrido
        tempo_atual = datetime.now()
        duracao = tempo_atual - st.session_state.hora_inicio
        horas, resto = divmod(duracao.total_seconds(), 3600)
        minutos, segundos = divmod(resto, 60)

        # Exibe o tempo formatado
        tempo_formatado = f"{int(horas):02d}:{int(minutos):02d}:{int(segundos):02d}"

        # Destaque para o cronômetro ativo
        st.markdown(f"""
        <div class="highlight">
            <p>Estudando <b>{st.session_state.materia_atual}</b> há:</p>
            <p class="timer-display">{tempo_formatado}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("Nenhum estudo em andamento. Inicie um novo estudo no painel lateral.")

def display_ultimo_registro():
    """Exibe informações sobre o último registro de estudo."""
    if st.session_state.ultimo_registro:
        st.subheader("Último Registro")
        registro = st.session_state.ultimo_registro
        st.write(f"**Matéria:** {registro['materia']}")
        st.write(f"**Duração:** {registro['duracao']} min")
        st.write(f"**Data:** {registro['data']} às {registro['hora']}")
    else:
        st.subheader("Sem registros recentes")

def display_historico(abas):
    """Exibe o histórico de estudos."""
    st.subheader("Histórico de Estudos")

    df_registros = obter_registros_df(abas['registros'])

    if df_registros.empty:
        st.info("Nenhum registro de estudo encontrado.")
        return

    # Configurações de exibição da tabela
    st.dataframe(
        df_registros,
        hide_index=True,
        use_container_width=True
    )

def display_resumo_materias(abas):
    """Exibe resumo por matéria."""
    st.subheader("Resumo por Matéria")

    df_registros = obter_registros_df(abas['registros'])

    if df_registros.empty:
        st.info("Sem dados para mostrar no resumo.")
        return

    # Converte duração para número
    df_registros['Duração (min)'] = pd.to_numeric(df_registros['Duração (min)'], errors='coerce')

    # Agrupa por matéria
    df_resumo = df_registros.groupby('Matéria').agg({
        'Duração (min)': 'sum'
    }).reset_index()

    # Adiciona coluna de horas
    df_resumo['Total (horas)'] = df_resumo['Duração (min)'] / 60

    # Ordena por duração
    df_resumo = df_resumo.sort_values('Duração (min)', ascending=False)

    # Exibe a tabela
    st.dataframe(
        df_resumo,
        column_config={
            "Duração (min)": st.column_config.ProgressColumn(
                "Progresso",
                help="Tempo estudado em minutos",
                format="%.1f",
                min_value=0,
                max_value=df_resumo['Duração (min)'].max() * 1.1 if not df_resumo.empty and df_resumo['Duração (min)'].max() > 0 else 1
            ),
            "Total (horas)": st.column_config.NumberColumn("Horas", format="%.2f h")
        },
        hide_index=True,
        use_container_width=True
    )

    # Exibe o gráfico abaixo da tabela
    if not df_resumo.empty:
        grafico = alt.Chart(df_resumo).mark_bar().encode(
            x=alt.X('Matéria:N', sort='-y', title=None),
            y=alt.Y('Duração (min):Q', title='Minutos Estudados'),
            color=alt.Color('Matéria:N', legend=None),
            tooltip=['Matéria', 'Duração (min)', alt.Tooltip('Total (horas)', format=".2f")]
        ).properties(height=400)
        st.altair_chart(grafico, use_container_width=True)
    else:
        st.info("Nenhum dado de resumo para exibir no gráfico.")

def gerar_grafico_semanal(df_registros):
    """Gera gráfico semanal de estudos."""
    try:
        # Verifica se há dados suficientes
        if df_registros.empty:
            return None

        # Certifica-se que a data está no formato correto
        df_registros['Data'] = pd.to_datetime(df_registros['Data'], dayfirst=True, errors='coerce')

        # Filtra para os últimos 30 dias
        data_limite = datetime.now() - timedelta(days=30)
        df_recente = df_registros[df_registros['Data'] >= data_limite]

        if df_recente.empty:
            return None

        # Adiciona dia da semana
        df_recente['DiaSemana'] = df_recente['Data'].dt.day_name()

        # Ordem dos dias da semana
        ordem_dias = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        nomes_dias = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
        mapa_dias = dict(zip(ordem_dias, nomes_dias))

        # Traduz os nomes dos dias
        df_recente['DiaSemana'] = df_recente['DiaSemana'].map(mapa_dias)

        # Agrupamento por dia da semana
        df_semanal = df_recente.groupby('DiaSemana').agg({
            'Duração (min)': 'sum'
        }).reset_index()

        # Certifica que todos os dias da semana estão representados
        dias_faltantes = [dia for dia in nomes_dias if dia not in df_semanal['DiaSemana'].values]
        df_complemento = pd.DataFrame({'DiaSemana': dias_faltantes, 'Duração (min)': [0] * len(dias_faltantes)})
        df_semanal = pd.concat([df_semanal, df_complemento], ignore_index=True)

        # Reordena os dias da semana
        ordem_dias_pt = dict(zip(nomes_dias, range(len(nomes_dias))))
        df_semanal['ordem'] = df_semanal['DiaSemana'].map(ordem_dias_pt)
        df_semanal = df_semanal.sort_values('ordem')

        # Cria o gráfico
        grafico = alt.Chart(df_semanal).mark_bar().encode(
            x=alt.X('DiaSemana:N', sort=list(mapa_dias.values()), title='Dia da Semana'),
            y=alt.Y('Duração (min):Q', title='Minutos Estudados'),
            color=alt.Color('DiaSemana:N', legend=None),
            tooltip=['DiaSemana', alt.Tooltip('Duração (min)', format=".1f")]
        ).properties(
            title='Distribuição de Estudos por Dia da Semana',
            height=300
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
    col_metricas[2].metric("Duração Média", f"{duracao_media:.1f} min")

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
        elif frequencia:
            st.info("🚀 Você está com um ritmo intenso de estudos! Certifique-se de incluir descanso para evitar o esgotamento.")
    else:
        st.info("📊 Comece a registrar seus estudos para receber dicas personalizadas!")

def main():
    """Função principal para executar a aplicação Streamlit."""
    # Estilização CSS personalizada
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
            font-size: 5rem !important; /* Aumenta significativamente o tamanho da fonte */
            font-weight: bold !important;
            text-align: center !important;
        }
    </style>
    """, unsafe_allow_html=True)

    st.title("Cronômetro de Estudos para GCM Caldas Novas") # Adiciona o título no topo
    st.caption("Acompanhe seu tempo de estudo para o concurso")

    # Conexão com Google Sheets e carregamento de dados
    cliente_gs = conectar_google_sheets()
    if cliente_gs:
        planilha = carregar_planilha(cliente_gs)
        if planilha:
            abas = carregar_abas(planilha)

            # Carregar matérias
            lista_materias = obter_materias_lista(abas['materias'])
            if not lista_materias:
                st.warning("Nenhuma matéria cadastrada. Adicione matérias na aba 'Materias' da planilha.")
                lista_materias = ["Matéria Padrão"]

            # Sidebar para iniciar nova sessão
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

            # Layout principal
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

    # Rodapé
    st.markdown("---")
    st.caption(f"Desenvolvido para GCM Caldas Novas | {datetime.now().year}")

if __name__ == "__main__":
    main()
