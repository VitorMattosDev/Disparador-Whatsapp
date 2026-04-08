"""
Disparador de Mensagens — WhatsApp Web
Estratégias anti-bloqueio:
  • Sessão do Chrome salva (sem QR toda vez)
  • Múltiplas mensagens — sorteia uma diferente para cada contato
  • Variação invisível por mensagem (zero-width space)
  • Delay aleatório entre mensagens
  • Pausa longa a cada N mensagens

Dependências:
    pip install customtkinter selenium
"""

import os
import re
import time
import random
import threading
import queue

import customtkinter as ctk
from tkinter import messagebox

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

# Pasta onde o executável está rodando.
# sys.executable aponta para o .exe quando empacotado pelo PyInstaller,
# e para o interpretador Python quando rodando como script normal.
import sys
BASE_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
CHROME_PROFILE_DIR = os.path.join(os.path.expanduser("~"), ".wpp_disparador_profile")
BLACKLIST_FILE     = os.path.join(BASE_DIR, "numeros_bloqueados.txt")
RECENTES_FILE      = os.path.join(BASE_DIR, "numeros_recentes.txt")
NUM_MENSAGENS = 5

MENSAGENS_PADRAO = [
    "Olá, {nome}! 👋\n\nAqui é da Genesys Fibra. Vimos que você se cadastrou na nossa rede mas ainda não conhece nossos planos.\n\nPosso te apresentar nossas opções? 😊",
    "Oi, {nome}! Tudo bem? 😊\n\nSou da Genesys Fibra. Você passou pela nossa rede de Wi-Fi e gostaríamos de te apresentar nossos planos de internet.\n\nTem um minutinho pra conversar?",
    "Olá, {nome}! 🙂\n\nAqui é a equipe da Genesys Fibra. Notamos que você usou nossa rede e achamos que nossas opções de plano podem te interessar.\n\nPosso te mandar os detalhes?",
    "",
    "",
]

# ── Blacklist ─────────────────────────────────────────────────────────────────

def carregar_blacklist() -> set:
    if not os.path.exists(BLACKLIST_FILE):
        return set()
    with open(BLACKLIST_FILE, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip()}

def salvar_blacklist(bl: set):
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(bl)))

def adicionar_blacklist(numero: str):
    bl = carregar_blacklist()
    bl.add(numero)
    salvar_blacklist(bl)

def remover_blacklist(numero: str):
    bl = carregar_blacklist()
    bl.discard(numero)
    salvar_blacklist(bl)

# ── Recentes ──────────────────────────────────────────────────────────────────

def carregar_recentes() -> set:
    if not os.path.exists(RECENTES_FILE):
        return set()
    with open(RECENTES_FILE, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip()}

def salvar_recentes(numeros: set):
    with open(RECENTES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(numeros)))

# ── Helpers ────────────────────────────────────────────────────────────────────

def limpar_numero(numero: str) -> str:
    n = re.sub(r"\D", "", numero.strip())
    if not n:
        return ""
    if not n.startswith("55"):
        n = "55" + n
    return n


def variar_mensagem(texto: str) -> str:
    """Insere zero-width space em posição aleatória — imperceptível ao leitor."""
    INVISIVEL = "\u200b"
    pos = random.randint(1, max(1, len(texto) - 1))
    return texto[:pos] + INVISIVEL + texto[pos:]


def iniciar_driver():
    erro_chrome = None
    try:
        opts = webdriver.ChromeOptions()
        opts.add_argument("--start-maximized")
        opts.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        driver = webdriver.Chrome(options=opts)
        return driver, "Chrome"
    except Exception as e:
        erro_chrome = str(e)

    try:
        opts = webdriver.EdgeOptions()
        opts.add_argument("--start-maximized")
        opts.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        driver = webdriver.Edge(options=opts)
        return driver, "Edge"
    except Exception as e:
        raise RuntimeError(
            f"Não foi possível iniciar Chrome ou Edge.\n\n"
            f"Erro Chrome: {erro_chrome}\n"
            f"Erro Edge: {e}\n\n"
            "Verifique se o Selenium está atualizado: pip install --upgrade selenium"
        ) from e


def aguardar_login(driver, log_q, stop_event, timeout=120):
    SELETORES = [
        "#side",
        '[data-testid="chat-list"]',
        '[aria-label="Lista de conversas"]',
        '[data-testid="search"]',
        'div[role="navigation"]',
    ]

    def ja_logado():
        for s in SELETORES:
            try:
                if driver.find_element(By.CSS_SELECTOR, s).is_displayed():
                    return True
            except Exception:
                pass
        return False

    time.sleep(2)
    if ja_logado():
        log_q.put(("success", "✅ Sessão restaurada — sem necessidade de QR Code!\n"))
        return True

    log_q.put(("warn",
        "📱 Escaneie o QR Code no navegador que abriu.\n"
        "   (Nas próximas vezes não será necessário)\n"
        "   Aguardando login..."))

    deadline = time.time() + timeout
    while time.time() < deadline:
        if stop_event.is_set():
            return False
        if ja_logado():
            log_q.put(("success", "✅ WhatsApp Web conectado!\n"))
            return True
        time.sleep(1)

    log_q.put(("error",
        "❌ Timeout aguardando login.\n"
        "   Certifique-se de escanear o QR Code dentro de 2 minutos."))
    return False


def encontrar_caixa(driver):
    SELETORES_CAIXA = [
        '[data-testid="conversation-compose-box-input"]',
        '[aria-label="Digite uma mensagem"]',
        '[aria-label="Type a message"]',
        'div[contenteditable="true"][role="textbox"]',
        'footer div[contenteditable="true"]',
    ]
    deadline = time.time() + 25
    while time.time() < deadline:
        for s in SELETORES_CAIXA:
            try:
                el = driver.find_element(By.CSS_SELECTOR, s)
                if el.is_displayed():
                    return el
            except Exception:
                pass
        time.sleep(0.5)
    return None


def enviar_mensagem(driver, numero: str, mensagem: str, stop_event) -> bool:
    driver.get(f"https://web.whatsapp.com/send?phone={numero}")

    try:
        caixa = encontrar_caixa(driver)
        if caixa is None:
            raise Exception("Caixa de texto não encontrada")

        if stop_event.is_set():
            return False

        time.sleep(random.uniform(1.2, 2.5))
        caixa.click()
        time.sleep(random.uniform(0.3, 0.7))

        linhas = mensagem.split("\n")
        for idx, linha in enumerate(linhas):
            if stop_event.is_set():
                return False
            driver.execute_script(
                "arguments[0].focus(); "
                "document.execCommand('insertText', false, arguments[1]);",
                caixa, linha
            )
            time.sleep(random.uniform(0.15, 0.4))
            if idx < len(linhas) - 1:
                caixa.send_keys(Keys.SHIFT, Keys.ENTER)
                time.sleep(random.uniform(0.1, 0.25))

        caixa = encontrar_caixa(driver)
        if caixa is None:
            raise Exception("Caixa perdida antes do envio")

        time.sleep(random.uniform(0.5, 1.2))
        caixa.send_keys(Keys.ENTER)
        time.sleep(random.uniform(0.8, 1.5))
        return True

    except Exception:
        try:
            driver.find_element(
                By.XPATH, '//div[@data-animate-modal-backdrop="true"]//button'
            ).click()
        except Exception:
            pass
        return False


# ── Thread principal ───────────────────────────────────────────────────────────

def disparar(numeros, templates, delay_min, delay_max,
             pausa_a_cada, duracao_pausa, log_q, prog_q, stop_event):
    driver = None
    try:
        log_q.put(("info", "🌐 Iniciando navegador..."))
        driver, browser = iniciar_driver()
        log_q.put(("info", f"   Usando {browser}."))
        log_q.put(("info", f"   {len(templates)} variação(ões) de mensagem ativas.\n"))

        driver.get("https://web.whatsapp.com")
        if not aguardar_login(driver, log_q, stop_event):
            return

        total = len(numeros)
        enviados = falhas = 0

        for i, (numero_raw, nome) in enumerate(numeros):
            if stop_event.is_set():
                log_q.put(("warn", "\n⛔ Disparo cancelado pelo usuário."))
                break

            prog_q.put(("progress", (i + 1, total)))
            numero = limpar_numero(numero_raw)

            if not numero or len(numero) < 12:
                log_q.put(("warn", f"  {i+1:>4}. ⚠️  Número inválido: '{numero_raw}', pulando."))
                falhas += 1
                continue

            if numero in carregar_blacklist():
                log_q.put(("warn", f"  {i+1:>4}. 🚫 +{numero} está na lista negra, pulando."))
                falhas += 1
                continue

            if numero in carregar_recentes():
                log_q.put(("warn", f"  {i+1:>4}. ⏭️  +{numero} já foi chamado recentemente, pulando."))
                falhas += 1
                continue

            # Sorteia uma das mensagens disponíveis para este contato
            template = random.choice(templates)
            mensagem = template.replace("{nome}", nome) if nome else template
            mensagem = variar_mensagem(mensagem)

            log_q.put(("info",
                f"  {i+1:>4}. 📤 Enviando para +{numero}" +
                (f" ({nome})" if nome else "") + "..."))

            ok = enviar_mensagem(driver, numero, mensagem, stop_event)

            if ok:
                log_q.put(("success", "        ✅ Enviado!"))
                enviados += 1
            else:
                log_q.put(("error", "        ❌ Número não encontrado no WhatsApp."))
                falhas += 1

            if stop_event.is_set():
                break

            eh_ultimo = (i == total - 1)

            if pausa_a_cada > 0 and enviados > 0 and enviados % pausa_a_cada == 0 and not eh_ultimo:
                log_q.put(("warn",
                    f"\n☕ Pausa de {duracao_pausa // 60}min após {enviados} envios..."))
                for _ in range(duracao_pausa * 10):
                    if stop_event.is_set():
                        break
                    time.sleep(0.1)
                log_q.put(("info", "   Retomando...\n"))
                continue

            if not eh_ultimo:
                espera = random.uniform(delay_min, delay_max)
                log_q.put(("info", f"        ⏳ Aguardando {espera:.0f}s..."))
                for _ in range(int(espera * 10)):
                    if stop_event.is_set():
                        break
                    time.sleep(0.1)

        log_q.put(("success",
            f"\n✅ Concluído!  Enviados: {enviados}  |  Falhas/inválidos: {falhas}"))
        prog_q.put(("done", enviados))

    except RuntimeError as e:
        log_q.put(("error", f"❌ {e}"))
        prog_q.put(("done", 0))
    except Exception as e:
        log_q.put(("error", f"❌ Erro inesperado: {e}"))
        prog_q.put(("done", 0))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


# ── Interface ──────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Disparador de Mensagens • WhatsApp Web")
        self.geometry("920x700")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._thread     = None
        self._stop_event = threading.Event()
        self._log_q      = queue.Queue()
        self._prog_q     = queue.Queue()

        self._build_ui()
        self._build_blacklist_panel()
        self._build_recentes_panel()
        self._poll()

    def _build_ui(self):
        # Frame com scroll para caber tudo na janela
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=0, pady=0)
        root = self._scroll  # todos os widgets vão dentro do scroll

        ctk.CTkLabel(root, text="Disparador de Mensagens",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(20, 2))
        ctk.CTkLabel(root, text="WhatsApp Web  •  Envio com delay anti-bloqueio",
                     font=ctk.CTkFont(size=12), text_color="gray60").pack(pady=(0, 14))

        # ── Painel superior: números + mensagens ──────────────────────────────
        main = ctk.CTkFrame(root, fg_color="transparent")
        main.pack(padx=20, fill="x")
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=2)

        # Números
        esq = ctk.CTkFrame(main, corner_radius=12)
        esq.grid(row=0, column=0, padx=(0, 8), sticky="nsew")

        ctk.CTkLabel(esq, text="📋  Lista de Números",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(esq,
                     text="Um por linha. Formatos aceitos:\n"
                          "11999998888  •  (11) 99999-8888\n"
                          "Para personalizar: 11999998888;Nome\n"
                          "Para ignorar um número: # 11999998888",
                     font=ctk.CTkFont(size=11), text_color="gray55",
                     justify="left").pack(anchor="w", padx=14, pady=(0, 6))
        self.txt_numeros = ctk.CTkTextbox(
            esq, height=180, font=ctk.CTkFont(family="Courier New", size=12))
        self.txt_numeros.pack(padx=10, pady=(0, 12), fill="both", expand=True)

        # Mensagens com abas
        dir_ = ctk.CTkFrame(main, corner_radius=12)
        dir_.grid(row=0, column=1, padx=(8, 0), sticky="nsew")

        ctk.CTkLabel(dir_, text="✉️  Variações de Mensagem",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(dir_,
                     text="Uma variação é sorteada aleatoriamente para cada contato. "
                          "Abas vazias são ignoradas. Use {nome} para personalizar.",
                     font=ctk.CTkFont(size=11), text_color="gray55",
                     wraplength=420, justify="left").pack(anchor="w", padx=14, pady=(0, 6))

        self.tabs = ctk.CTkTabview(dir_, height=180)
        self.tabs.pack(padx=10, pady=(0, 12), fill="both", expand=True)

        self.txt_mensagens = []
        for i in range(NUM_MENSAGENS):
            nome_aba = f"  Msg {i + 1}  "
            self.tabs.add(nome_aba)
            txt = ctk.CTkTextbox(
                self.tabs.tab(nome_aba),
                font=ctk.CTkFont(size=12), wrap="word")
            txt.pack(fill="both", expand=True)
            if i < len(MENSAGENS_PADRAO) and MENSAGENS_PADRAO[i]:
                txt.insert("1.0", MENSAGENS_PADRAO[i])
            self.txt_mensagens.append(txt)

        # ── Configurações anti-bloqueio ────────────────────────────────────────
        cfg = ctk.CTkFrame(root, corner_radius=12)
        cfg.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(cfg, text="🛡️  Configurações anti-bloqueio",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=8, sticky="w", padx=14, pady=(10, 8))

        ctk.CTkLabel(cfg, text="Intervalo entre mensagens:").grid(
            row=1, column=0, sticky="w", padx=14)
        ctk.CTkLabel(cfg, text="mín").grid(row=1, column=1, padx=(8, 2))
        self.delay_min = ctk.CTkEntry(cfg, width=55)
        self.delay_min.insert(0, "35")
        self.delay_min.grid(row=1, column=2, padx=2)
        ctk.CTkLabel(cfg, text="máx").grid(row=1, column=3, padx=(8, 2))
        self.delay_max = ctk.CTkEntry(cfg, width=55)
        self.delay_max.insert(0, "100")
        self.delay_max.grid(row=1, column=4, padx=2)
        ctk.CTkLabel(cfg, text="seg").grid(row=1, column=5, padx=(2, 30))

        ctk.CTkLabel(cfg, text="Pausa longa a cada").grid(
            row=1, column=6, sticky="w", padx=(0, 4))
        self.pausa_a_cada = ctk.CTkEntry(cfg, width=55)
        self.pausa_a_cada.insert(0, "15")
        self.pausa_a_cada.grid(row=1, column=7, padx=2)
        ctk.CTkLabel(cfg, text="envios, parar").grid(row=1, column=8, padx=4)
        self.duracao_pausa = ctk.CTkEntry(cfg, width=55)
        self.duracao_pausa.insert(0, "5")
        self.duracao_pausa.grid(row=1, column=9, padx=2)
        ctk.CTkLabel(cfg, text="min").grid(row=1, column=10, padx=(2, 14))

        ctk.CTkLabel(cfg,
                     text="💡  Valores pré-definidos com as configurações recomendadas  •  "
                          "Use 0 no campo de pausa para desativá-la",
                     font=ctk.CTkFont(size=11), text_color="#f39c12").grid(
            row=2, column=0, columnspan=11, sticky="w", padx=14, pady=(4, 10))

        # ── Botões ─────────────────────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(root, fg_color="transparent")
        btn_frame.pack(padx=20, pady=(0, 6), fill="x")

        self.btn_start = ctk.CTkButton(
            btn_frame, text="▶  Iniciar Disparo",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42, width=200, command=self._start,
        )
        self.btn_start.pack(side="left")

        self.btn_stop = ctk.CTkButton(
            btn_frame, text="⏹  Parar",
            font=ctk.CTkFont(size=14), height=42, width=130,
            fg_color="#c0392b", hover_color="#922b21",
            state="disabled", command=self._stop,
        )
        self.btn_stop.pack(side="left", padx=10)

        self.btn_limpar = ctk.CTkButton(
            btn_frame, text="🗑  Limpar Log",
            font=ctk.CTkFont(size=12), height=42, width=130,
            fg_color="gray30", hover_color="gray20",
            command=self._limpar_log,
        )
        self.btn_limpar.pack(side="right")

        # ── Progresso ──────────────────────────────────────────────────────────
        prog_frame = ctk.CTkFrame(root, fg_color="transparent")
        prog_frame.pack(padx=20, fill="x")
        self.progress = ctk.CTkProgressBar(prog_frame, height=14, corner_radius=6)
        self.progress.pack(fill="x", pady=(0, 2))
        self.progress.set(0)
        self.lbl_prog = ctk.CTkLabel(
            prog_frame, text="Aguardando...",
            font=ctk.CTkFont(size=11), text_color="gray55")
        self.lbl_prog.pack(anchor="e")

        # ── Log ────────────────────────────────────────────────────────────────
        self.log_box = ctk.CTkTextbox(
            root, font=ctk.CTkFont(family="Courier New", size=12),
            corner_radius=10, state="disabled", height=150,
        )
        self.log_box.pack(padx=20, pady=(4, 16), fill="x")
        self.log_box._textbox.tag_configure("info",    foreground="#e0e0e0")
        self.log_box._textbox.tag_configure("warn",    foreground="#f39c12")
        self.log_box._textbox.tag_configure("error",   foreground="#e74c3c")
        self.log_box._textbox.tag_configure("success", foreground="#2ecc71")

    # ── Lista Negra ────────────────────────────────────────────────────────────

    def _build_blacklist_panel(self):
        """Painel recolhível da lista negra, abaixo do log."""
        root = self._scroll
        bl_outer = ctk.CTkFrame(root, corner_radius=12)
        bl_outer.pack(padx=20, pady=(0, 16), fill="x")

        # Header clicável para recolher/expandir
        header = ctk.CTkFrame(bl_outer, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(10, 0))

        ctk.CTkLabel(header, text="🚫  Lista Negra  —  números que nunca receberão mensagens",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")

        self.btn_toggle_bl = ctk.CTkButton(
            header, text="▼  Mostrar", width=110, height=26,
            fg_color="gray30", hover_color="gray20",
            font=ctk.CTkFont(size=11),
            command=self._toggle_blacklist,
        )
        self.btn_toggle_bl.pack(side="right")

        # Conteúdo (começa recolhido)
        self._bl_visible = False
        self._bl_frame = ctk.CTkFrame(bl_outer, fg_color="transparent")
        # não pack ainda — recolhido

        hint = ctk.CTkLabel(self._bl_frame,
                     text="Digite ou cole um número e clique em Bloquear.  "
                          "Clique em ✕ para remover da lista negra.",
                     font=ctk.CTkFont(size=11), text_color="gray55")
        hint.pack(anchor="w", padx=4, pady=(6, 4))

        add_row = ctk.CTkFrame(self._bl_frame, fg_color="transparent")
        add_row.pack(fill="x", pady=(0, 6))

        self.entry_bl = ctk.CTkEntry(add_row, width=220,
                                     placeholder_text="Ex: 17999998888")
        self.entry_bl.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            add_row, text="🚫  Bloquear número",
            height=32, width=160,
            fg_color="#c0392b", hover_color="#922b21",
            command=self._bloquear_numero,
        ).pack(side="left")

        # Lista dos bloqueados
        self.bl_scrollframe = ctk.CTkScrollableFrame(
            self._bl_frame, height=120, corner_radius=8)
        self.bl_scrollframe.pack(fill="x", pady=(0, 10))

        self._refresh_blacklist_ui()

    def _toggle_blacklist(self):
        if self._bl_visible:
            self._bl_frame.pack_forget()
            self.btn_toggle_bl.configure(text="▼  Mostrar")
            self._bl_visible = False
        else:
            self._bl_frame.pack(fill="x", padx=14, pady=(6, 0))
            self.btn_toggle_bl.configure(text="▲  Recolher")
            self._bl_visible = True

    def _refresh_blacklist_ui(self):
        for w in self.bl_scrollframe.winfo_children():
            w.destroy()
        bl = sorted(carregar_blacklist())
        if not bl:
            ctk.CTkLabel(self.bl_scrollframe,
                         text="Nenhum número bloqueado.",
                         text_color="gray55",
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=8, pady=4)
            return
        for numero in bl:
            row = ctk.CTkFrame(self.bl_scrollframe, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=f"+{numero}",
                         font=ctk.CTkFont(family="Courier New", size=12)).pack(
                side="left", padx=(6, 0))
            ctk.CTkButton(
                row, text="✕  Desbloquear", width=120, height=24,
                fg_color="gray30", hover_color="gray20",
                font=ctk.CTkFont(size=11),
                command=lambda n=numero: self._desbloquear(n),
            ).pack(side="right", padx=6)

    def _bloquear_numero(self):
        raw = self.entry_bl.get().strip()
        numero = limpar_numero(raw)
        if not numero or len(numero) < 12:
            messagebox.showerror("Número inválido",
                "Digite um número válido com DDD (ex: 17999998888).")
            return
        adicionar_blacklist(numero)
        self.entry_bl.delete(0, "end")
        self._refresh_blacklist_ui()

    def _desbloquear(self, numero: str):
        remover_blacklist(numero)
        self._refresh_blacklist_ui()

    # ── Lista de Recentes ──────────────────────────────────────────────────────

    def _build_recentes_panel(self):
        root = self._scroll
        rec_outer = ctk.CTkFrame(root, corner_radius=12)
        rec_outer.pack(padx=20, pady=(0, 10), fill="x")

        # Header
        header = ctk.CTkFrame(rec_outer, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(10, 0))

        self._lbl_rec_titulo = ctk.CTkLabel(
            header, text="⏭️  Números Recentes  —  carregando...",
            font=ctk.CTkFont(weight="bold"))
        self._lbl_rec_titulo.pack(side="left")

        self.btn_toggle_rec = ctk.CTkButton(
            header, text="▼  Mostrar", width=110, height=26,
            fg_color="gray30", hover_color="gray20",
            font=ctk.CTkFont(size=11),
            command=self._toggle_recentes,
        )
        self.btn_toggle_rec.pack(side="right")

        self._rec_visible = False
        self._rec_frame = ctk.CTkFrame(rec_outer, fg_color="transparent")

        # Instrução
        ctk.CTkLabel(self._rec_frame,
            text=("Cole aqui os números do mês ANTERIOR (um por linha).\n"
                  "O programa vai pular qualquer número dessa lista durante o disparo.\n"
                  "Na virada do mês: clique em 'Substituir pela lista abaixo' para atualizar."),
            font=ctk.CTkFont(size=11), text_color="gray55",
            justify="left").pack(anchor="w", padx=4, pady=(8, 6))

        # Área de texto para colar nova lista
        self.txt_recentes = ctk.CTkTextbox(
            self._rec_frame, height=100,
            font=ctk.CTkFont(family="Courier New", size=11))
        self.txt_recentes.pack(fill="x", padx=4, pady=(0, 8))

        # Botões
        btn_row = ctk.CTkFrame(self._rec_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=4, pady=(0, 10))

        ctk.CTkButton(
            btn_row,
            text="💾  Substituir pela lista abaixo",
            height=32, width=220,
            fg_color="#1a6b3c", hover_color="#145530",
            font=ctk.CTkFont(size=12),
            command=self._substituir_recentes,
        ).pack(side="left")

        ctk.CTkButton(
            btn_row,
            text="🗑  Limpar tudo",
            height=32, width=130,
            fg_color="gray30", hover_color="gray20",
            font=ctk.CTkFont(size=12),
            command=self._limpar_recentes,
        ).pack(side="left", padx=10)

        self._lbl_rec_count = ctk.CTkLabel(
            btn_row, text="",
            font=ctk.CTkFont(size=11), text_color="gray55")
        self._lbl_rec_count.pack(side="right")

        self._refresh_recentes_ui()

    def _toggle_recentes(self):
        if self._rec_visible:
            self._rec_frame.pack_forget()
            self.btn_toggle_rec.configure(text="▼  Mostrar")
            self._rec_visible = False
        else:
            self._rec_frame.pack(fill="x", padx=14, pady=(6, 0))
            self.btn_toggle_rec.configure(text="▲  Recolher")
            self._rec_visible = True

    def _refresh_recentes_ui(self):
        recentes = carregar_recentes()
        n = len(recentes)
        if n == 0:
            self._lbl_rec_titulo.configure(
                text="⏭️  Números Recentes  —  nenhum número cadastrado")
            self._lbl_rec_count.configure(text="")
        else:
            self._lbl_rec_titulo.configure(
                text=f"⏭️  Números Recentes  —  {n} número(s) serão pulados")
            self._lbl_rec_count.configure(
                text=f"{n} número(s) na lista")

    def _substituir_recentes(self):
        raw = self.txt_recentes.get("1.0", "end").strip().splitlines()
        novos = set()
        invalidos = 0
        for linha in raw:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            # Suporta formato número;nome — descarta o nome
            numero = limpar_numero(linha.split(";")[0])
            if numero and len(numero) >= 12:
                novos.add(numero)
            else:
                invalidos += 1

        if not novos:
            messagebox.showerror("Lista vazia",
                "Não foi encontrado nenhum número válido para salvar.")
            return

        msg = f"Serão salvos {len(novos)} número(s) como recentes.\n"
        if invalidos:
            msg += f"({invalidos} linha(s) inválidas serão ignoradas)\n"
        msg += "\nIsso substituirá a lista atual. Confirma?"

        if not messagebox.askyesno("Confirmar substituição", msg):
            return

        salvar_recentes(novos)
        self.txt_recentes.delete("1.0", "end")
        self._refresh_recentes_ui()
        messagebox.showinfo("Salvo",
            f"{len(novos)} número(s) salvos na lista de recentes.\nEles serão pulados automaticamente no próximo disparo.")

    def _limpar_recentes(self):
        if not carregar_recentes():
            return
        if not messagebox.askyesno("Limpar lista de recentes",
                "Isso vai remover todos os números da lista de recentes.\n"
                "Eles voltarão a ser disparados normalmente. Confirma?"):
            return
        salvar_recentes(set())
        self._refresh_recentes_ui()

    def _get_templates(self):
        """Retorna apenas as abas com conteúdo preenchido."""
        templates = []
        for txt in self.txt_mensagens:
            conteudo = txt.get("1.0", "end").strip()
            if conteudo:
                templates.append(conteudo)
        return templates

    def _parse_numeros(self):
        linhas = self.txt_numeros.get("1.0", "end").strip().splitlines()
        resultado = []
        for linha in linhas:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue  # linha vazia ou comentada com # é ignorada
            if ";" in linha:
                partes = linha.split(";", 1)
                resultado.append((partes[0].strip(), partes[1].strip()))
            else:
                resultado.append((linha, ""))
        return resultado

    def _start(self):
        numeros   = self._parse_numeros()
        templates = self._get_templates()

        if not numeros:
            messagebox.showerror("Lista vazia", "Cole pelo menos um número na lista.")
            return
        if not templates:
            messagebox.showerror("Sem mensagem",
                "Preencha pelo menos uma variação de mensagem.")
            return

        try:
            d_min = float(self.delay_min.get())
            d_max = float(self.delay_max.get())
            if d_min < 5 or d_max < d_min:
                raise ValueError
        except ValueError:
            messagebox.showerror("Delay inválido",
                "O mínimo deve ser ≥ 5s e o máximo deve ser maior que o mínimo.")
            return

        try:
            pausa_a_cada  = int(self.pausa_a_cada.get())
            duracao_pausa = int(float(self.duracao_pausa.get()) * 60)
        except ValueError:
            messagebox.showerror("Pausa inválida", "Verifique os campos de pausa longa.")
            return

        pausa_txt = (f"Pausa de {duracao_pausa // 60}min a cada {pausa_a_cada} envios."
                     if pausa_a_cada > 0 else "Sem pausa longa.")

        if not messagebox.askyesno(
            "Confirmar disparo",
            f"Serão enviadas mensagens para {len(numeros)} número(s).\n"
            f"{len(templates)} variação(ões) de mensagem ativa(s).\n\n"
            f"Intervalo: {d_min:.0f}s – {d_max:.0f}s entre cada envio.\n"
            f"{pausa_txt}\n\n"
            "O navegador vai abrir (ou restaurar a sessão salva).\n\n"
            "Deseja continuar?"
        ):
            return

        self._limpar_log()
        self.progress.set(0)
        self.lbl_prog.configure(text="Iniciando...")
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=disparar,
            args=(numeros, templates, d_min, d_max,
                  pausa_a_cada, duracao_pausa,
                  self._log_q, self._prog_q, self._stop_event),
            daemon=True,
        )
        self._thread.start()

    def _stop(self):
        self._stop_event.set()
        self.btn_stop.configure(state="disabled")
        self.lbl_prog.configure(text="Cancelando...")

    def _limpar_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _log(self, level, msg):
        self.log_box.configure(state="normal")
        self.log_box._textbox.insert("end", msg + "\n", level)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _poll(self):
        try:
            while True:
                level, msg = self._log_q.get_nowait()
                self._log(level, msg)
        except queue.Empty:
            pass

        try:
            while True:
                kind, val = self._prog_q.get_nowait()
                if kind == "progress":
                    atual, total = val
                    self.progress.set(atual / total)
                    self.lbl_prog.configure(text=f"{atual} / {total} números")
                elif kind == "done":
                    self.btn_start.configure(state="normal")
                    self.btn_stop.configure(state="disabled")
                    if val:
                        self.progress.set(1)
                        self.lbl_prog.configure(text="Concluído ✓")
        except queue.Empty:
            pass

        self.after(120, self._poll)

    def _on_close(self):
        self._stop_event.set()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
