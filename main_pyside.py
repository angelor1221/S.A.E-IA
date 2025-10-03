import sys
import threading
import re
import os
from functools import partial

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QTabWidget, QFormLayout, QLineEdit, QComboBox,
                               QPushButton, QLabel, QScrollArea, QFrame,
                               QHBoxLayout, QTextEdit, QProgressDialog, QMessageBox)
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QIcon

import database
import chatbot
from datetime import datetime, timedelta

STYLESHEET = """
    QWidget { background-color: #2E3440; color: #ECEFF4; font-family: "Segoe UI"; font-size: 14px; }
    QTabWidget::pane { border: 1px solid #4C566A; }
    QTabBar::tab { background-color: #434C5E; color: #D8DEE9; padding: 10px; border-top-left-radius: 5px; border-top-right-radius: 5px; }
    QTabBar::tab:selected { background-color: #5E81AC; color: #ECEFF4; }
    QPushButton { background-color: #5E81AC; color: white; font-weight: bold; border-radius: 5px; padding: 8px 15px; border: none; }
    QPushButton:hover { background-color: #81A1C1; }
    QLineEdit, QComboBox, QTextEdit { background-color: #4C566A; border: 1px solid #2E3440; border-radius: 5px; padding: 5px; }
    QScrollArea { border: none; }
    QFrame#itemFrame { border: 1px solid #4C566A; border-radius: 5px; }
    QLabel#titleLabel { font-size: 22px; font-weight: bold; }
    QLabel#chatBubble, QLabel#userBubble { border-radius: 15px; padding: 10px; }
    QLabel#chatBubble { background-color: #434C5E; border: 1px solid #4C566A; }
    QLabel#userBubble { background-color: #5E81AC; border: 1px solid #81A1C1; }
"""


# --- CORREÇÃO: Usando um comunicador para threading seguro ---
class Communicate(QObject):
    result_ready = Signal(object)


class HospitalApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CliniCare IA - Sistema de Gestão Hospitalar")
        self.setWindowIcon(QIcon())
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet(STYLESHEET)

        self.chat_history = [];
        self.paciente_chat_id = None;
        self.typing_indicator_layout = None
        self.pending_ai_responses = set()

        self.tabs = QTabWidget();
        self.setCentralWidget(self.tabs)
        self.tabs.addTab(self.create_add_patient_tab(), "Adicionar Paciente")
        self.tabs.addTab(self.create_patient_list_tab(), "Lista de Pacientes")
        self.tabs.addTab(self.create_medication_schedule_tab(), "Próximas Medicações")
        self.tabs.addTab(self.create_chatbot_tab(), "Chatbot IA")

        self.details_frame = QFrame(self);
        self.details_frame.setObjectName("detailsFrame")
        self.details_frame.setStyleSheet(
            "#detailsFrame { border: 2px solid #5E81AC; border-radius: 10px; background-color: #2E3440; }")
        details_layout, top_bar_layout = QVBoxLayout(self.details_frame), QHBoxLayout()
        self.details_title = QLabel("Detalhes");
        self.details_title.setObjectName("titleLabel")
        close_button = QPushButton("Fechar");
        close_button.clicked.connect(self.details_frame.hide)
        top_bar_layout.addWidget(self.details_title);
        top_bar_layout.addStretch();
        top_bar_layout.addWidget(close_button)
        self.details_content = QTextEdit();
        self.details_content.setReadOnly(True)
        details_layout.addLayout(top_bar_layout);
        details_layout.addWidget(self.details_content);
        self.details_frame.hide()

        database.criar_tabelas()
        if not database.get_todos_pacientes(): self.adicionar_dados_iniciais()
        self.refresh_all()

    def refresh_all(self):
        self.refresh_patient_list(); self.refresh_chatbot_patient_list(); self.refresh_medication_schedule(); self.refresh_add_patient_tab()

    def resizeEvent(self, event):
        super().resizeEvent(event); self.details_frame.setGeometry(int(self.width() * 0.15), int(self.height() * 0.15),
                                                                   int(self.width() * 0.7), int(self.height() * 0.7))

    def create_add_patient_tab(self):
        widget = QWidget();
        main_layout = QVBoxLayout(widget);
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        title = QLabel("Admissão de Novo Paciente");
        title.setObjectName("titleLabel");
        title.setAlignment(Qt.AlignmentFlag.AlignCenter);
        main_layout.addWidget(title)
        form_frame = QFrame();
        form_layout = QFormLayout(form_frame)
        self.entry_nome = QLineEdit();
        self.entry_idade = QLineEdit();
        self.entry_condicao = QLineEdit();
        self.quarto_menu = QComboBox()
        form_layout.addRow("Nome Completo:", self.entry_nome);
        form_layout.addRow("Idade:", self.entry_idade);
        form_layout.addRow("Condição de Admissão:", self.entry_condicao);
        form_layout.addRow("Quarto:", self.quarto_menu)
        main_layout.addWidget(form_frame)
        admit_button = QPushButton("Admitir Paciente ➕");
        admit_button.clicked.connect(self.salvar_paciente);
        main_layout.addWidget(admit_button)
        return widget

    def refresh_add_patient_tab(self):
        todos_quartos = [f"{a}º Andar - {a}{q:02d}" for a in range(1, 6) for q in range(1, 21)]
        quartos_ocupados = database.get_quartos_ocupados()
        quartos_disponiveis = [q for q in todos_quartos if q.split(" - ")[1] not in quartos_ocupados]
        current_selection = self.quarto_menu.currentText()
        self.quarto_menu.clear();
        self.quarto_menu.addItems(quartos_disponiveis if quartos_disponiveis else ["Todos os quartos estão ocupados"])
        if current_selection in quartos_disponiveis: self.quarto_menu.setCurrentText(current_selection)

    def salvar_paciente_thread(self, callback_signal):
        nome = self.entry_nome.text();
        idade = self.entry_idade.text();
        condicao = self.entry_condicao.text();
        sala = self.quarto_menu.currentText().split(" - ")[1]
        try:
            paciente_id = database.adicionar_paciente_simples(nome, int(idade), condicao, sala,
                                                              datetime.now().isoformat())
            success, plano = chatbot.gerar_plano_tratamento_ia(nome, int(idade), condicao)
            if success:
                padrao_med = re.compile(r"Medicamento: (.*), Dosagem: (.*), Frequência: (\d+) horas")
                for med in padrao_med.findall(plano): database.adicionar_medicamento(paciente_id, med[0].strip(),
                                                                                     med[1].strip(),
                                                                                     int(med[2].strip()))
            callback_signal.emit((success, plano))
        except Exception as e:
            print(f"ERRO na thread salvar_paciente: {e}");
            callback_signal.emit((False, str(e)))

    def on_plano_gerado(self, result):
        self.progress.close()
        success, data = result
        if success:
            plano = data;
            self.entry_nome.clear();
            self.entry_idade.clear();
            self.entry_condicao.clear();
            self.refresh_all()
            self.details_title.setText("Plano de Tratamento Sugerido")
            plano_html = plano.replace("**", "").replace("\n", "<br>")
            plano_html = plano_html.replace("Crítica",
                                            "<span style='color: #BF616A; font-weight: bold;'>Crítica 🔴</span>").replace(
                "Grave", "<span style='color: #BF616A; font-weight: bold;'>Grave 🔴</span>").replace("Moderada",
                                                                                                    "<span style='color: #D08770; font-weight: bold;'>Moderada 🟡</span>").replace(
                "Leve", "<span style='color: #A3BE8C; font-weight: bold;'>Leve 🟢</span>")
            self.details_content.setHtml(plano_html);
            self.details_frame.show();
            self.details_frame.raise_()
        else:
            QMessageBox.critical(self, "Erro de IA", f"Não foi possível gerar o plano de tratamento:\n{data}")

    def salvar_paciente(self):
        if "Todos os quartos" in self.quarto_menu.currentText(): QMessageBox.critical(self, "Erro",
                                                                                      "Não há quartos disponíveis."); return
        if not (
                self.entry_nome.text() and self.entry_idade.text().isdigit() and self.entry_condicao.text()): QMessageBox.critical(
            self, "Erro", "Preencha todos os dados."); return
        self.progress = QProgressDialog("Gerando plano...", "Cancelar", 0, 0, self);
        self.progress.setWindowModality(Qt.WindowModality.WindowModal);
        self.progress.show()

        self.comm = Communicate();
        self.comm.result_ready.connect(self.on_plano_gerado)
        threading.Thread(target=self.salvar_paciente_thread, args=(self.comm.result_ready,), daemon=True).start()

    def create_patient_list_tab(self):
        widget = QWidget();
        layout = QVBoxLayout(widget);
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll = QScrollArea();
        scroll.setWidgetResizable(True);
        scroll_content = QWidget()
        self.patient_scroll_layout = QVBoxLayout(scroll_content);
        self.patient_scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(scroll_content);
        layout.addWidget(scroll)
        return widget

    def refresh_patient_list(self):
        self.clear_layout(self.patient_scroll_layout)
        for p in database.get_todos_pacientes():
            frame = QFrame();
            frame.setObjectName("itemFrame");
            layout = QHBoxLayout(frame)
            label = QLabel(f"{p['nome']} - (Quarto: {p['sala']})");
            view = QPushButton("Ficha 📄");
            delete = QPushButton("Deletar 🗑️")
            delete.setStyleSheet("background-color: #BF616A;")
            view.clicked.connect(partial(self.mostrar_detalhes_paciente, p['id']))
            delete.clicked.connect(partial(self.confirmar_delecao, p['id']))
            layout.addWidget(label);
            layout.addStretch();
            layout.addWidget(view);
            layout.addWidget(delete)
            self.patient_scroll_layout.addWidget(frame)

    def confirmar_delecao(self, pid, checked=False):
        if QMessageBox.question(self, "Confirmar Deleção", "Tem certeza?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            database.deletar_paciente(pid);
            self.refresh_all()

    def mostrar_detalhes_paciente(self, pid, checked=False):
        paciente, medicamentos, historico = database.get_detalhes_paciente(pid)
        if not paciente: return
        self.details_title.setText(f"Ficha de {paciente['nome']}")
        html = f"<h3>Informações</h3><p><b>Nome:</b> {paciente['nome']}<br><b>Idade:</b> {paciente['idade']} anos<br><b>Admissão:</b> {datetime.fromisoformat(paciente['data_admissao']).strftime('%d/%m/%Y')}<br><b>Condição:</b> {paciente['condicao']}<br><b>Quarto:</b> {paciente['sala']}</p><hr><h3>Medicação Atual</h3>"
        meds_atuais = [m for m in medicamentos if m['frequencia_horas'] is not None]
        if meds_atuais:
            html += "<ul>"; html += "".join(
                [f"<li><b>{m['nome_medicamento']}</b> ({m['dosagem']}) - A cada {m['frequencia_horas']} horas</li>" for
                 m in meds_atuais]); html += "</ul>"
        else:
            html += "<p>Nenhum medicamento atual.</p>"
        html += "<hr><h3>Histórico de Evolução</h3>"
        if historico:
            html += "<ul>"; html += "".join([
                                                f"<li><b>{datetime.fromisoformat(n['data_registro']).strftime('%d/%m/%Y')}:</b> {n['nota_evolucao']}</li>"
                                                for n in historico]); html += "</ul>"
        else:
            html += "<p>Nenhuma nota de evolução.</p>"
        self.details_content.setHtml(html);
        self.details_frame.show();
        self.details_frame.raise_()

    def create_medication_schedule_tab(self):
        widget = QWidget();
        layout = QVBoxLayout(widget);
        top_layout = QHBoxLayout();
        title = QLabel("Próximas Medicações (24h)");
        title.setObjectName("titleLabel")
        refresh_button = QPushButton("Atualizar ↻");
        refresh_button.clicked.connect(self.refresh_medication_schedule)
        top_layout.addWidget(title);
        top_layout.addStretch();
        top_layout.addWidget(refresh_button)
        scroll = QScrollArea();
        scroll.setWidgetResizable(True);
        scroll_content = QWidget()
        self.medication_scroll_layout = QVBoxLayout(scroll_content);
        self.medication_scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(scroll_content);
        layout.addLayout(top_layout);
        layout.addWidget(scroll)
        return widget

    def refresh_medication_schedule(self):
        self.clear_layout(self.medication_scroll_layout)
        agenda = database.get_proximas_medicacoes()
        if not agenda: self.medication_scroll_layout.addWidget(QLabel("Nenhuma medicação agendada."))
        for item in agenda:
            texto = f"<p><b>{item['horario'].strftime('%H:%M')}</b> - <b>Paciente:</b> {item['paciente']} (Quarto {item['sala']})<br><b>Medicamento:</b> {item['medicamento']} - {item['dosagem']}</p>"
            frame = QFrame();
            frame.setObjectName("itemFrame");
            frame.setLayout(QVBoxLayout());
            frame.layout().addWidget(QLabel(texto))
            self.medication_scroll_layout.addWidget(frame)

    def create_chatbot_tab(self):
        widget = QWidget();
        layout = QVBoxLayout(widget);
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Paciente:"));
        self.chatbot_patient_combo = QComboBox();
        self.chatbot_patient_combo.currentTextChanged.connect(self.carregar_paciente_chat)
        selector_layout.addWidget(self.chatbot_patient_combo, 1);
        self.chat_scroll = QScrollArea();
        self.chat_scroll.setWidgetResizable(True)
        chat_content = QWidget();
        self.chat_log_layout = QVBoxLayout(chat_content);
        self.chat_log_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_scroll.setWidget(chat_content);
        input_layout = QHBoxLayout();
        self.chat_entry = QLineEdit();
        self.chat_entry.setPlaceholderText("Digite sua pergunta...");
        self.chat_entry.returnPressed.connect(self.enviar_pergunta_chatbot)
        send_button = QPushButton("Enviar ➤");
        send_button.clicked.connect(self.enviar_pergunta_chatbot)
        input_layout.addWidget(self.chat_entry);
        input_layout.addWidget(send_button)
        layout.addLayout(selector_layout);
        layout.addWidget(self.chat_scroll, 1);
        layout.addLayout(input_layout)
        return widget

    def refresh_chatbot_patient_list(self):
        current_data = self.chatbot_patient_combo.currentData();
        self.chatbot_patient_combo.blockSignals(True);
        self.chatbot_patient_combo.clear()
        pacientes = database.get_todos_pacientes()
        if pacientes:
            for p in pacientes: self.chatbot_patient_combo.addItem(f"{p['nome']} (ID: {p['id']})", p['id'])
            if current_data in [p['id'] for p in pacientes]: self.chatbot_patient_combo.setCurrentIndex(
                [p['id'] for p in pacientes].index(current_data))
        self.chatbot_patient_combo.blockSignals(False)
        if self.chatbot_patient_combo.count() > 0 and self.chatbot_patient_combo.currentData() != self.paciente_chat_id:
            self.carregar_paciente_chat()
        elif self.chatbot_patient_combo.count() == 0:
            self.carregar_paciente_chat()

    def carregar_paciente_chat(self):
        if self.typing_indicator_layout: self.hide_typing_indicator()
        self.clear_layout(self.chat_log_layout);
        paciente_id = self.chatbot_patient_combo.currentData()
        if not paciente_id: self.chat_history = []; self.paciente_chat_id = None; return
        self.paciente_chat_id = paciente_id;
        paciente, meds, hist_trat = database.get_detalhes_paciente(paciente_id)
        self.chat_history = chatbot.construir_historico_inicial(paciente, meds, hist_trat)
        for msg in database.get_chat_historico(paciente_id):
            self.formatar_e_inserir_chat(msg['remetente'], msg['mensagem'])
            self.chat_history.append(
                {'role': 'user' if msg['remetente'] == 'Enfermeira' else 'model', 'parts': [msg['mensagem']]})
        if paciente_id in self.pending_ai_responses: self.show_typing_indicator()

    def enviar_pergunta_chatbot(self):
        pergunta = self.chat_entry.text().strip()
        if not (pergunta and self.paciente_chat_id): return
        originating_patient_id = self.paciente_chat_id
        self.chat_entry.clear();
        self.formatar_e_inserir_chat("Enfermeira", pergunta)
        database.salvar_mensagem_chat(originating_patient_id, "Enfermeira", pergunta)
        self.show_typing_indicator();
        self.pending_ai_responses.add(originating_patient_id)

        self.comm = Communicate();
        self.comm.result_ready.connect(lambda result: self.on_ia_response(result, originating_patient_id))
        threading.Thread(target=self.run_chat_thread, args=(self.chat_history, pergunta, self.comm.result_ready),
                         daemon=True).start()

    def run_chat_thread(self, history, question, callback_signal):
        success, data = chatbot.continuar_chat(history, question)
        callback_signal.emit((success, data))

    def on_ia_response(self, result, originating_patient_id):
        self.pending_ai_responses.discard(originating_patient_id);
        success, data = result
        if self.paciente_chat_id == originating_patient_id:
            self.hide_typing_indicator()
            if success:
                resposta = data;
                database.salvar_mensagem_chat(originating_patient_id, "IA", resposta)
                self.formatar_e_inserir_chat("IA", resposta)
            else:
                error_message = f"Desculpe, ocorreu um erro na IA.\nDetalhe: {data}"
                self.formatar_e_inserir_chat("IA", error_message)
        elif success:
            database.salvar_mensagem_chat(originating_patient_id, "IA", data)

    def formatar_e_inserir_chat(self, remetente, texto):
        texto_html = f"<b>{'Você' if remetente == 'Enfermeira' else 'Assistente'}:</b><br>{texto.replace('**', '').replace('\n', '<br>')}"
        bubble = QLabel(texto_html);
        bubble.setWordWrap(True);
        bubble.setTextFormat(Qt.TextFormat.RichText)
        bubble_layout = QHBoxLayout()
        if remetente == 'Enfermeira':
            bubble.setObjectName("userBubble"); bubble_layout.addStretch(); bubble_layout.addWidget(bubble)
        else:
            bubble.setObjectName("chatBubble"); bubble_layout.addWidget(bubble); bubble_layout.addStretch()
        self.chat_log_layout.addLayout(bubble_layout)
        QApplication.processEvents()  # --- CORREÇÃO: Força a atualização da UI ---
        self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

    def show_typing_indicator(self):
        if self.typing_indicator_layout: return
        self.typing_indicator_label = QLabel("Digitando...");
        self.typing_indicator_label.setObjectName("chatBubble")
        self.typing_indicator_layout = QHBoxLayout();
        self.typing_indicator_layout.addWidget(self.typing_indicator_label);
        self.typing_indicator_layout.addStretch()
        self.chat_log_layout.addLayout(self.typing_indicator_layout)
        self.typing_dots = 0;
        self.typing_timer = QTimer(self);
        self.typing_timer.timeout.connect(self.update_typing_animation);
        self.typing_timer.start(400)

    def update_typing_animation(self):
        self.typing_dots = (self.typing_dots + 1) % 4;
        self.typing_indicator_label.setText(f"Digitando{'.' * self.typing_dots}")

    def hide_typing_indicator(self):
        if self.typing_indicator_layout:
            self.typing_timer.stop();
            self.clear_layout(self.typing_indicator_layout);
            self.typing_indicator_layout = None

    def clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                if item is None: continue
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                elif item.layout() is not None:
                    self.clear_layout(item.layout())

    def adicionar_dados_iniciais(self):
        hoje = datetime.now()
        pacientes = [
            {"nome": "João da Silva", "idade": 68, "condicao": "Pneumonia Grave", "sala": "101",
             "data_admissao": (hoje - timedelta(days=3)).isoformat(),
             "medicamentos_atuais": [
                 {"nome": "Ceftriaxona 1g IV", "dosagem": "1g", "inicio": (hoje - timedelta(days=3)).isoformat(),
                  "frequencia": 12},
                 {"nome": "Dipirona 1g", "dosagem": "1g", "inicio": (hoje - timedelta(days=3)).isoformat(),
                  "frequencia": 6}],
             "historico": [{"data": (hoje - timedelta(days=1)).isoformat(),
                            "nota": "Apresenta melhora no padrão respiratório."}]},
            {"nome": "Maria Oliveira", "idade": 75, "condicao": "Fratura de fêmur", "sala": "205",
             "data_admissao": (hoje - timedelta(days=2)).isoformat(),
             "medicamentos_atuais": [
                 {"nome": "Morfina 10mg", "dosagem": "10mg", "inicio": (hoje - timedelta(days=2)).isoformat(),
                  "frequencia": 4},
                 {"nome": "Clexane 40mg", "dosagem": "40mg", "inicio": (hoje - timedelta(days=2)).isoformat(),
                  "frequencia": 24}],
             "historico": [{"data": (hoje - timedelta(days=1)).isoformat(),
                            "nota": "Dor controlada, iniciou fisioterapia no leito."}]},
            {"nome": "Carlos Pereira", "idade": 55, "condicao": "Infarto Agudo do Miocárdio", "sala": "310",
             "data_admissao": (hoje - timedelta(days=1)).isoformat(),
             "medicamentos_atuais": [
                 {"nome": "AAS 100mg", "dosagem": "100mg", "inicio": (hoje - timedelta(days=1)).isoformat(),
                  "frequencia": 24},
                 {"nome": "Clopidogrel 75mg", "dosagem": "75mg", "inicio": (hoje - timedelta(days=1)).isoformat(),
                  "frequencia": 24}],
             "historico": [{"data": (hoje - timedelta(days=1)).isoformat(),
                            "nota": "Estável hemodinamicamente após angioplastia. Ansioso."}]},
            {"nome": "Ana Costa", "idade": 42, "condicao": "Crise Asmática Moderada", "sala": "415",
             "data_admissao": hoje.isoformat(),
             "medicamentos_atuais": [
                 {"nome": "Prednisona 40mg", "dosagem": "40mg", "inicio": hoje.isoformat(), "frequencia": 12},
                 {"nome": "Salbutamol Inalatório", "dosagem": "2 jatos", "inicio": hoje.isoformat(), "frequencia": 4}],
             "historico": [
                 {"data": hoje.isoformat(), "nota": "Respondeu bem à medicação inicial. Sibilância diminuída."}]},
            {"nome": "José Santos", "idade": 81, "condicao": "Infecção do Trato Urinário", "sala": "520",
             "data_admissao": (hoje - timedelta(days=4)).isoformat(),
             "medicamentos_atuais": [
                 {"nome": "Ciprofloxacino 500mg", "dosagem": "500mg", "inicio": (hoje - timedelta(days=4)).isoformat(),
                  "frequencia": 12}],
             "historico": [{"data": (hoje - timedelta(days=2)).isoformat(),
                            "nota": "Melhora do estado de orientação após início do antibiótico."}]}
        ]
        for p in pacientes: database.adicionar_paciente_completo(p)
        print("5 perfis iniciais foram criados.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HospitalApp()
    window.show()
    sys.exit(app.exec())