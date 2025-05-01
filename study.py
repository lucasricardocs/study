import streamlit as st
import time
import datetime
import pandas as pd

# Configuração inicial
if 'estudo_iniciado' not in st.session_state:
    st.session_state.estudo_iniciado = False
if 'inicio_tempo' not in st.session_state:
    st.session_state.inicio_tempo = None
if 'historico' not in st.session_state:
    st.session_state.historico = []

# Função para formatar o tempo
def formatar_tempo(segundos):
    horas = int(segundos // 3600)
    minutos = int((segundos % 3600) // 60)
    segundos = int(segundos % 60)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

# Interface do aplicativo
st.title("📚 Cronômetro de Estudo")
st.markdown("Acompanhe suas horas líquidas de estudo por assunto")

# Seleção do assunto
assunto = st.text_input("Qual assunto você está estudando?", "")

col1, col2 = st.columns(2)

with col1:
    if st.button("▶️ Iniciar Estudo") and assunto and not st.session_state.estudo_iniciado:
        st.session_state.estudo_iniciado = True
        st.session_state.inicio_tempo = time.time()
        st.session_state.assunto_atual = assunto
        st.success(f"Estudo de '{assunto}' iniciado!")

with col2:
    if st.button("⏹️ Parar Estudo") and st.session_state.estudo_iniciado:
        tempo_decorrido = time.time() - st.session_state.inicio_tempo
        registro = {
            "Assunto": st.session_state.assunto_atual,
            "Data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Duração (segundos)": tempo_decorrido,
            "Duração Formatada": formatar_tempo(tempo_decorrido)
        }
        st.session_state.historico.append(registro)
        st.session_state.estudo_iniciado = False
        st.session_state.inicio_tempo = None
        st.success(f"Estudo de '{st.session_state.assunto_atual}' concluído! Tempo: {formatar_tempo(tempo_decorrido)}")

# Mostrar cronômetro em tempo real
if st.session_state.estudo_iniciado:
    st.markdown("---")
    placeholder = st.empty()
    while st.session_state.estudo_iniciado:
        tempo_decorrido = time.time() - st.session_state.inicio_tempo
        with placeholder.container():
            st.metric("Tempo de estudo", formatar_tempo(tempo_decorrido))
            st.write(f"Assunto: **{st.session_state.assunto_atual}**")
            if st.button("⏹️ Parar Estudo (alternativo)"):
                tempo_decorrido = time.time() - st.session_state.inicio_tempo
                registro = {
                    "Assunto": st.session_state.assunto_atual,
                    "Data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Duração (segundos)": tempo_decorrido,
                    "Duração Formatada": formatar_tempo(tempo_decorrido)
                }
                st.session_state.historico.append(registro)
                st.session_state.estudo_iniciado = False
                st.session_state.inicio_tempo = None
                st.experimental_rerun()
        time.sleep(1)
    placeholder.empty()

# Mostrar histórico
if st.session_state.historico:
    st.markdown("---")
    st.subheader("📊 Histórico de Estudos")
    
    # Converter para DataFrame
    df = pd.DataFrame(st.session_state.historico)
    
    # Mostrar tabela completa
    st.write("Registros completos:")
    st.dataframe(df)
    
    # Mostrar resumo por assunto
    st.write("Tempo total por assunto:")
    if not df.empty:
        resumo = df.groupby('Assunto')['Duração (segundos)'].sum().reset_index()
        resumo['Tempo Total'] = resumo['Duração (segundos)'].apply(formatar_tempo)
        st.dataframe(resumo[['Assunto', 'Tempo Total']])
    
    # Opção para exportar dados
    st.download_button(
        label="📥 Exportar histórico como CSV",
        data=df.to_csv(index=False).encode('utf-8'),
        file_name='historico_estudos.csv',
        mime='text/csv'
    )

# Instruções
st.markdown("---")
st.subheader("ℹ️ Como usar")
st.markdown("""
1. Digite o assunto que você vai estudar
2. Clique em **Iniciar Estudo** para começar o cronômetro
3. Quando terminar, clique em **Parar Estudo**
4. Veja seu histórico e tempo total por assunto abaixo
""")
