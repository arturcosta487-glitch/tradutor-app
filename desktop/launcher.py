"""
LAUNCHER - Tradutor PT-BR
=========================
Tela de entrada com a key. Valida online no servidor e, se a key for
válida, fecha essa tela e abre o tradutor (tradutor_overlay.py) direto,
sem precisar de .bat nem de abrir nada na mão.
 
----------------------------------------------------------------------
ANTES DE EMPACOTAR EM .EXE:
----------------------------------------------------------------------
1) Troque BASE_URL abaixo pela URL do seu servidor no Render.
2) Deixe este arquivo (launcher.py) na MESMA pasta que tradutor_overlay.py
3) pip install requests pyinstaller
4) No CMD, dentro da pasta:
     pyinstaller --onefile --noconsole --name TradutorPT launcher.py
   Isso gera dist\\TradutorPT.exe — um único executável, sem .bat.
----------------------------------------------------------------------
"""
 
import os
import sys
import uuid
import hashlib
import platform
import threading
import tkinter as tk
from tkinter import font as tkfont
 
import requests
 
BASE_URL    = "https://tradutor-gamer-key.onrender.com"
APP_NAME    = "TradutorPT"
SUPPORT_URL = "https://discord.gg/SEU-SERVIDOR-AQUI"
VERSION     = "V.1.0.0"
 
# ---------- onde guardamos a key "lembrada" no PC do usuário ----------
def _config_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path
 
KEY_FILE = os.path.join(_config_dir(), "key.dat")
 
def load_saved_key():
    try:
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""
 
def save_key(key):
    try:
        with open(KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key)
    except Exception:
        pass
 
def clear_saved_key():
    try:
        os.remove(KEY_FILE)
    except Exception:
        pass
 
def get_hwid():
    raw = f"{platform.node()}-{uuid.getnode()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
 
# ========================== PALETA ==========================
BG        = "#0f111a"   # fundo geral
PANEL_L   = "#161b29"   # painel esquerdo
PANEL_R   = "#13172280" # painel direito (levemente diferente)
CARD_BG   = "#1a1f31"   # fundo dos cards internos
LINE      = "#252d42"   # bordas suaves
ACCENT    = "#7eb8f7"   # azul pastel (destaque principal)
ACCENT2   = "#a78bfa"   # lilás pastel (secundário)
ACCENT3   = "#6ee7b7"   # verde menta (online dot)
TEXT      = "#e8eaf6"   # texto principal
TEXT_2    = "#8b93b0"   # texto secundário
ERROR     = "#f87171"   # erro
SUCCESS   = "#6ee7b7"   # sucesso
 
# arredondamento padrão
R = 22
 
def pill(canvas, x1, y1, x2, y2, r=R, **kw):
    """Retângulo com cantos bem arredondados (pill/squircle style)."""
    pts = [
        x1+r, y1,   x2-r, y1,
        x2,   y1,   x2,   y1+r,
        x2,   y2-r, x2,   y2,
        x2-r, y2,   x1+r, y2,
        x1,   y2,   x1,   y2-r,
        x1,   y1+r, x1,   y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)
 
 
class KeyGateApp:
    W, H = 620, 410
 
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.overrideredirect(True)
 
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - self.W) // 2
        y  = (sh - self.H) // 2
        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")
 
        self.remember_var = tk.BooleanVar(value=False)
        self.validating   = False
        self._drag_x = self._drag_y = 0
 
        self._build()
 
        saved = load_saved_key()
        if saved:
            self.key_entry.insert(0, saved)
            self.remember_var.set(True)
            self._draw_toggle()
 
        self.root.mainloop()
 
    # ------------------------------------------------------------------
    def _build(self):
        W, H = self.W, self.H
 
        # ── base canvas ──────────────────────────────────────────────
        base = tk.Canvas(self.root, width=W, height=H,
                         bg=BG, highlightthickness=0)
        base.pack()
 
        # moldura externa (pill grande)
        pill(base, 6, 6, W-6, H-6, r=28,
             fill=CARD_BG, outline=LINE, width=1)
 
        # divisória vertical suave
        base.create_line(280, 28, 280, H-28, fill=LINE, width=1)
 
        # ── arrastar / fechar ────────────────────────────────────────
        base.bind("<Button-1>",   self._drag_start)
        base.bind("<B1-Motion>",  self._drag_move)
 
        # botão ✕
        x_id = base.create_text(W-26, 24, text="✕", fill=TEXT_2,
                                 font=("Segoe UI", 11), tags="xbtn")
        base.tag_bind("xbtn", "<Button-1>",
                      lambda e: self.root.destroy())
        base.tag_bind("xbtn", "<Enter>",
                      lambda e: base.itemconfig(x_id, fill=ERROR))
        base.tag_bind("xbtn", "<Leave>",
                      lambda e: base.itemconfig(x_id, fill=TEXT_2))
 
        # ── LADO ESQUERDO ────────────────────────────────────────────
        # card do produto
        pill(base, 22, 22, 258, 128, r=20,
             fill="#0f1320", outline=LINE, width=1)
 
        # ícone "T" arredondado
        pill(base, 34, 34, 86, 86, r=16, fill=ACCENT2, outline="")
        base.create_text(60, 60, text="T", fill="#ffffff",
                         font=("Segoe UI", 22, "bold"))
 
        # nome + versão
        base.create_text(100, 50, text="Tradutor PT-BR",
                         fill=TEXT, font=("Segoe UI", 11, "bold"), anchor="w")
        base.create_text(100, 70, text=f"[ {VERSION} ]",
                         fill=TEXT_2, font=("Segoe UI", 9), anchor="w")
 
        # bolinha online
        base.create_oval(242, 26, 254, 38,
                         fill=ACCENT3, outline="")
 
        # tagline fofa embaixo do card
        base.create_text(140, 155, text="🎮  Seu tradutor de jogos", fill=TEXT_2,
                         font=("Segoe UI", 9))
        base.create_text(140, 175, text="em tempo real  ✨",
                         fill=TEXT_2, font=("Segoe UI", 9))
 
        # ── LADO DIREITO ─────────────────────────────────────────────
        rx = 295   # x inicial do painel direito
        cw = W - rx - 18  # largura útil
 
        # título
        base.create_text(rx + cw//2, 44,
                         text="TRADUTOR PT-BR",
                         fill=ACCENT, font=("Segoe UI", 12, "bold"))
        base.create_text(rx + cw//2, 64,
                         text="Insira sua key para continuar",
                         fill=TEXT_2, font=("Segoe UI", 9))
 
        # label Key
        base.create_text(rx + 4, 88, text="Key",
                         fill=TEXT_2, font=("Segoe UI", 9), anchor="w")
 
        # campo de key
        efield = tk.Frame(self.root, bg="#0b0e1a",
                          highlightthickness=1,
                          highlightbackground=LINE,
                          highlightcolor=ACCENT)
        efield.place(x=rx, y=100, width=cw, height=40)
        # arredonda via canvas
        ecv = tk.Canvas(efield, bg="#0b0e1a", highlightthickness=0)
        ecv.pack(fill="both", expand=True)
 
        self.key_entry = tk.Entry(
            self.root, bg="#0b0e1a", fg=TEXT,
            insertbackground=ACCENT, relief="flat",
            font=("Consolas", 11), justify="center",
            bd=0
        )
        self.key_entry.place(x=rx+4, y=104, width=cw-8, height=32)
 
        # fundo pill para o campo
        ef_cv = tk.Canvas(self.root, width=cw, height=40,
                          bg=CARD_BG, highlightthickness=0)
        ef_cv.place(x=rx, y=100)
        pill(ef_cv, 0, 0, cw, 40, r=14,
             fill="#0b0e1a", outline=LINE, width=1)
        ef_cv.lower()   # manda pra trás da entry
 
        # row "Lembrar"
        base.create_text(rx+4, 158, text="Lembrar minha key",
                         fill=TEXT_2, font=("Segoe UI", 9), anchor="w")
        self.toggle_cv = tk.Canvas(self.root, width=44, height=22,
                                   bg=CARD_BG, highlightthickness=0,
                                   cursor="hand2")
        self.toggle_cv.place(x=rx + cw - 46, y=148)
        self.toggle_cv.bind("<Button-1>", self._toggle_remember)
        self._draw_toggle()
 
        # botão LAUNCH
        self.launch_cv = tk.Canvas(self.root, width=cw, height=46,
                                   bg=CARD_BG, highlightthickness=0,
                                   cursor="hand2")
        self.launch_cv.place(x=rx, y=180)
        self._draw_launch("LAUNCH")
        self.launch_cv.bind("<Button-1>", lambda e: self.on_launch())
        self.launch_cv.bind("<Enter>",    lambda e: self._launch_hover(True))
        self.launch_cv.bind("<Leave>",    lambda e: self._launch_hover(False))
 
        # status
        self.status_var = tk.StringVar(value="")
        tk.Label(self.root, textvariable=self.status_var,
                 fg=TEXT_2, bg=CARD_BG,
                 font=("Segoe UI", 8),
                 wraplength=cw, justify="center"
                 ).place(x=rx, y=238, width=cw)
 
        # link discord
        disc = tk.Label(self.root,
                        text="Problemas? Entra no nosso Discord  💬",
                        fg=ACCENT2, bg=CARD_BG,
                        font=("Segoe UI", 8), cursor="hand2")
        disc.place(x=rx + cw//2, y=H-38, anchor="center")
        disc.bind("<Button-1>", lambda e: self._open_discord())
 
    # ------------------------------------------------------------------
    def _drag_start(self, e):
        self._drag_x, self._drag_y = e.x, e.y
 
    def _drag_move(self, e):
        nx = self.root.winfo_x() + e.x - self._drag_x
        ny = self.root.winfo_y() + e.y - self._drag_y
        self.root.geometry(f"+{nx}+{ny}")
 
    # ------------------------------------------------------------------
    def _draw_toggle(self):
        cv = self.toggle_cv
        cv.delete("all")
        on = self.remember_var.get()
        bg = ACCENT if on else "#252d42"
        pill(cv, 0, 0, 44, 22, r=11, fill=bg, outline="")
        kx = 31 if on else 13
        cv.create_oval(kx-9, 2, kx+9, 20,
                       fill="#ffffff" if on else "#555e78", outline="")
 
    def _toggle_remember(self, _=None):
        self.remember_var.set(not self.remember_var.get())
        self._draw_toggle()
 
    # ------------------------------------------------------------------
    _launch_hovered = False
 
    def _draw_launch(self, text, enabled=True):
        cv   = self.launch_cv
        cw   = int(cv["width"])
        ch   = int(cv["height"])
        cv.delete("all")
        if enabled:
            col = ACCENT2 if self._launch_hovered else ACCENT
        else:
            col = "#252d42"
        pill(cv, 0, 0, cw, ch, r=16, fill=col, outline="")
        cv.create_text(cw//2, ch//2, text=text,
                       fill="#060c1a" if enabled else TEXT_2,
                       font=("Segoe UI", 11, "bold"))
 
    def _launch_hover(self, entering):
        self._launch_hovered = entering
        if not self.validating:
            self._draw_launch("LAUNCH")
 
    # ------------------------------------------------------------------
    def set_status(self, text, kind="info"):
        colors = {"info": TEXT_2, "ok": SUCCESS, "error": ERROR}
        lbl = self.root.nametowidget(self.root.winfo_children()[-1])
        # encontra o label de status pelo textvariable
        for w in self.root.winfo_children():
            if isinstance(w, tk.Label) and w.cget("textvariable") == str(self.status_var):
                w.configure(fg=colors.get(kind, TEXT_2))
                break
        self.status_var.set(text)
 
    def on_launch(self):
        if self.validating:
            return
        key = self.key_entry.get().strip()
        if not key:
            self.set_status("Cole sua key antes de continuar.", "error")
            return
 
        self.validating = True
        self._draw_launch("VALIDANDO...", enabled=False)
        self.set_status("Verificando sua key...", "info")
        threading.Thread(target=self._validate_key,
                         args=(key,), daemon=True).start()
 
    def _validate_key(self, key):
        try:
            resp = requests.post(
                f"{BASE_URL}/api/keys/validate",
                json={"key": key, "hwid": get_hwid()},
                timeout=15,
            )
            data = resp.json()
        except Exception:
            self.root.after(0, self._on_result, False,
                            "Não consegui falar com o servidor. Confere sua internet.")
            return
 
        if data.get("valid"):
            self.root.after(0, self._on_result, True, key)
        else:
            reason = data.get("reason", "Key inválida.")
            self.root.after(0, self._on_result, False, reason)
 
    def _on_result(self, ok, payload):
        self.validating = False
        if not ok:
            self._draw_launch("LAUNCH")
            self.set_status(payload, "error")
            return
 
        key = payload
        if self.remember_var.get():
            save_key(key)
        else:
            clear_saved_key()
 
        self.set_status("Key válida! Abrindo o tradutor... ✨", "ok")
        self.root.after(600, self._open_translator)
 
    def _open_translator(self):
        self.root.destroy()
        import tradutor_overlay
        tradutor_overlay.main()
 
    def _open_discord(self):
        import webbrowser
        webbrowser.open(SUPPORT_URL)
 
 
if __name__ == "__main__":
    KeyGateApp()
 
