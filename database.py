import sqlite3
from datetime import datetime

def conectar_db():
    conn = sqlite3.connect('hospital.db')
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn.cursor(), conn

def criar_tabelas():
    cursor, conn = conectar_db()
    cursor.execute('CREATE TABLE IF NOT EXISTS pacientes (id INTEGER PRIMARY KEY, nome TEXT, idade INTEGER, condicao TEXT, sala TEXT, data_admissao TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS historico_tratamento (id INTEGER PRIMARY KEY, paciente_id INTEGER, data_registro TEXT, nota_evolucao TEXT, FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS chat_historico (id INTEGER PRIMARY KEY, paciente_id INTEGER, remetente TEXT, mensagem TEXT, timestamp TEXT, FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS medicamentos (id INTEGER PRIMARY KEY, paciente_id INTEGER, nome_medicamento TEXT NOT NULL, dosagem TEXT, inicio_tratamento TEXT, frequencia_horas INTEGER, FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE)')
    conn.commit()
    conn.close()

def adicionar_paciente_completo(p):
    cursor, conn = conectar_db()
    cursor.execute('INSERT INTO pacientes (nome, idade, condicao, sala, data_admissao) VALUES (?, ?, ?, ?, ?)',
                   (p['nome'], p['idade'], p['condicao'], p['sala'], p['data_admissao']))
    paciente_id = cursor.lastrowid
    for med in p.get('medicamentos_atuais', []):
        cursor.execute('INSERT INTO medicamentos (paciente_id, nome_medicamento, dosagem, inicio_tratamento, frequencia_horas) VALUES (?, ?, ?, ?, ?)',
                       (paciente_id, med['nome'], med['dosagem'], med['inicio'], med['frequencia']))
    for nota in p.get('historico', []):
        cursor.execute('INSERT INTO historico_tratamento (paciente_id, data_registro, nota_evolucao) VALUES (?, ?, ?)',
                       (paciente_id, nota['data'], nota['nota']))
    conn.commit()
    conn.close()

def adicionar_paciente_simples(nome, idade, condicao, sala, data_admissao):
    cursor, conn = conectar_db()
    cursor.execute('INSERT INTO pacientes (nome, idade, condicao, sala, data_admissao) VALUES (?, ?, ?, ?, ?)',
                   (nome, idade, condicao, sala, data_admissao))
    paciente_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return paciente_id

def adicionar_medicamento(paciente_id, nome, dosagem, frequencia):
    cursor, conn = conectar_db()
    cursor.execute('INSERT INTO medicamentos (paciente_id, nome_medicamento, dosagem, inicio_tratamento, frequencia_horas) VALUES (?, ?, ?, ?, ?)',
                   (paciente_id, nome, dosagem, datetime.now().isoformat(), frequencia))
    conn.commit()
    conn.close()

def get_quartos_ocupados():
    cursor, conn = conectar_db()
    cursor.execute("SELECT sala FROM pacientes")
    quartos = [row['sala'] for row in cursor.fetchall()]
    conn.close()
    return quartos

def get_proximas_medicacoes():
    from datetime import datetime, timedelta
    cursor, conn = conectar_db()
    cursor.execute('SELECT p.nome, p.sala, m.nome_medicamento, m.dosagem, m.inicio_tratamento, m.frequencia_horas FROM pacientes p JOIN medicamentos m ON p.id = m.paciente_id WHERE m.frequencia_horas IS NOT NULL')
    medicamentos_db = cursor.fetchall()
    conn.close()
    agora, proximas_doses = datetime.now(), []
    for med in medicamentos_db:
        inicio_dt, freq_horas = datetime.fromisoformat(med['inicio_tratamento']), med['frequencia_horas']
        if agora < inicio_dt:
            proxima_dose = inicio_dt
        else:
            doses_passadas = int((agora - inicio_dt).total_seconds() / 3600 // freq_horas)
            proxima_dose = inicio_dt + timedelta(hours=(doses_passadas + 1) * freq_horas)
        if agora <= proxima_dose < agora + timedelta(hours=24):
            proximas_doses.append({"paciente": med['nome'], "sala": med['sala'], "medicamento": med['nome_medicamento'], "dosagem": med['dosagem'], "horario": proxima_dose})
    return sorted(proximas_doses, key=lambda x: x['horario'])

def get_todos_pacientes():
    cursor, conn = conectar_db()
    cursor.execute('SELECT id, nome, sala FROM pacientes ORDER BY nome')
    pacientes = cursor.fetchall()
    conn.close()
    return pacientes

def get_detalhes_paciente(paciente_id):
    cursor, conn = conectar_db()
    cursor.execute('SELECT * FROM pacientes WHERE id = ?', (paciente_id,))
    paciente = cursor.fetchone()
    cursor.execute('SELECT * FROM medicamentos WHERE paciente_id = ?', (paciente_id,))
    medicamentos = cursor.fetchall()
    cursor.execute('SELECT * FROM historico_tratamento WHERE paciente_id = ? ORDER BY data_registro DESC', (paciente_id,))
    historico = cursor.fetchall()
    conn.close()
    return paciente, medicamentos, historico

def deletar_paciente(paciente_id):
    cursor, conn = conectar_db()
    cursor.execute('DELETE FROM pacientes WHERE id = ?', (paciente_id,))
    conn.commit()
    conn.close()

def salvar_mensagem_chat(paciente_id, remetente, mensagem):
    cursor, conn = conectar_db()
    cursor.execute('INSERT INTO chat_historico (paciente_id, remetente, mensagem, timestamp) VALUES (?, ?, ?, ?)',
                   (paciente_id, remetente, mensagem, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_chat_historico(paciente_id):
    cursor, conn = conectar_db()
    cursor.execute('SELECT remetente, mensagem FROM chat_historico WHERE paciente_id = ? ORDER BY timestamp ASC', (paciente_id,))
    historico = cursor.fetchall()
    conn.close()
    return historico