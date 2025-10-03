import google.generativeai as genai
from datetime import datetime

API_KEY = "AIzaSyDcfT-Fl0NiedJwsX0XWvJwt5xMGH6y4gw"  # <-- VERIFIQUE ESTA CHAVE COM MUITA ATENÇÃO

genai.configure(api_key=API_KEY, transport='rest')

generation_config = {"temperature": 0.7, "top_p": 1, "top_k": 1, "max_output_tokens": 8192}
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

model = genai.GenerativeModel(model_name="gemini-2.5-pro",
                              generation_config=generation_config,
                              safety_settings=safety_settings)


def gerar_plano_tratamento_ia(nome, idade, condicao):
    # Esta função já usa generate_content e funciona bem. Nenhuma mudança necessária.
    prompt = f"""
    Aja como a IA médica chefe de um hospital. Crie um plano de tratamento inicial conciso.
    **Dados do Paciente:**
    - Nome: {nome}
    - Idade: {idade} anos
    - Condição de Admissão: {condicao}

    **Sua Resposta Deve Conter Exatamente 2 Seções:**
    1.  **Avaliação de Gravidade:** Classifique a gravidade em: Leve, Moderada, Grave ou Crítica. Justifique.
    2.  **Plano de Medicação Sugerido:** Sugira 2 a 3 medicamentos. **PARA CADA MEDICAMENTO, USE O FORMATO EXATO:** `Medicamento: [Nome], Dosagem: [Dosagem], Frequência: [Número] horas.`
    """
    try:
        response = model.generate_content(prompt)
        return True, response.text
    except Exception as e:
        print(f"ERRO ao gerar plano: {e}")
        return False, str(e)


# --- LÓGICA DE CHAT COMPLETAMENTE REFEITA ---

def construir_historico_inicial(detalhes_paciente, medicamentos, historico):
    """Apenas constrói a lista de histórico inicial para a conversa."""
    paciente_info = (f"- **Nome:** {detalhes_paciente['nome']}\n"
                     f"- **Idade:** {detalhes_paciente['idade']} anos\n"
                     f"- **Data de Admissão:** {datetime.fromisoformat(detalhes_paciente['data_admissao']).strftime('%d/%m/%Y')}\n"
                     f"- **Condição de Admissão:** {detalhes_paciente['condicao']}\n"
                     f"- **Sala:** {detalhes_paciente['sala']}")

    meds_atuais_list = [m for m in medicamentos if m['frequencia_horas'] is not None]
    meds_atuais = "\n".join(
        [f"- {m['nome_medicamento']} ({m['dosagem']}) a cada {m['frequencia_horas']} horas" for m in meds_atuais_list])
    if not meds_atuais: meds_atuais = "Nenhum."

    historico_formatado = "\n".join(
        [f"- Em {datetime.fromisoformat(h['data_registro']).strftime('%d/%m/%Y')}: {h['nota_evolucao']}" for h in
         historico])
    if not historico_formatado: historico_formatado = "Nenhuma nota de evolução registrada."

    prompt_contexto = f"""
    Você é um assistente médico sênior. Responda perguntas sobre o paciente abaixo.
    Use as informações específicas como CONTEXTO PRINCIPAL, mas USE SEU CONHECIMENTO MÉDICO GERAL para dar explicações detalhadas.

    **--- Dados do Paciente ---**
    **Informações Gerais:**\n{paciente_info}
    **Medicamentos Atuais:**\n{meds_atuais}
    **Histórico de Tratamento / Evolução:**\n{historico_formatado}
    **--- Fim dos Dados ---**

    Responda às perguntas da enfermeira.
    """

    # Monta o histórico inicial no formato que a API espera
    history = [
        {'role': 'user', 'parts': [prompt_contexto]},
        {'role': 'model',
         'parts': [f"Entendido. Estou pronto para responder perguntas sobre o paciente {detalhes_paciente['nome']}."]}
    ]
    return history


def continuar_chat(history, nova_pergunta):
    """Continua uma conversa usando o histórico completo (método stateless)."""
    history.append({'role': 'user', 'parts': [nova_pergunta]})
    try:
        response = model.generate_content(history)
        # Adiciona a resposta da IA ao histórico para a próxima chamada
        history.append({'role': 'model', 'parts': [response.text]})
        return True, response.text
    except Exception as e:
        print(f"ERRO no chat: {e}")
        # Remove a última pergunta do usuário em caso de erro, para tentar de novo
        history.pop()
        return False, str(e)