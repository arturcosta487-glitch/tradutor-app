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
import json
import uuid
import hashlib
import platform
import threading
import tkinter as tk
from tkinter import font as tkfont

import requests

# Troque pela URL do seu servidor depois de subir no Render
BASE_URL = "https://tradutor-gamer-key.onrender.com"

APP_NAME = "TradutorPT"
SUPPORT_URL = "https://discord.gg/SEU-SERVIDOR-AQUI"

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
    """ID 'único' do computador, sem precisar de admin nem libs extras."""
    raw = f"{platform.node()}-{uuid.getnode()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ---------------------------- cores / estilo ----------------------------
BG_0 = "#0b0e14"
CARD = "#141925"
LINE = "#222838"
CYAN = "#3ee0e8"
CYAN_DIM = "#1d8e95"
TEXT = "#e7ecf5"
TEXT_DIM = "#8a93a6"
ERROR = "#ff7575"


def round_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class KeyGateApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg=BG_0)
        self.root.resizable(False, False)

        w, h = 380, 430
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.remember_var = tk.BooleanVar(value=False)
        self.validating = False

        self._build_ui(w, h)

        saved = load_saved_key()
        if saved:
            self.key_entry.insert(0, saved)
            self.remember_var.set(True)
            self._draw_toggle()

        self.root.mainloop()

    # ------------------------------------------------------------------
    def _build_ui(self, w, h):
        title_font = tkfont.Font(family="Segoe UI Semibold", size=15)
        sub_font = tkfont.Font(family="Segoe UI", size=9)
        label_font = tkfont.Font(family="Segoe UI", size=9)
        btn_font = tkfont.Font(family="Segoe UI Semibold", size=11)
        link_font = tkfont.Font(family="Segoe UI", size=8, underline=False)

        tk.Label(self.root, text="TRADUTOR PT-BR", fg=CYAN, bg=BG_0,
                  font=("Segoe UI", 9), justify="center").pack(pady=(28, 2))
        tk.Label(self.root, text="Cole sua key para liberar o app", fg=TEXT_DIM,
                  bg=BG_0, font=sub_font).pack(pady=(0, 18))

        # ---- card ----
        card_w, card_h = w - 48, 250
        self.card = tk.Canvas(self.root, width=card_w, height=card_h,
                               bg=BG_0, highlightthickness=0)
        self.card.pack()
        round_rect(self.card, 1, 1, card_w - 1, card_h - 1, 16,
                    fill=CARD, outline=LINE)

        tk.Label(self.card, text="Key", fg=TEXT_DIM, bg=CARD,
                  font=label_font).place(x=22, y=18)

        # entrada da key
        entry_frame = tk.Frame(self.card, bg="#0e1320", highlightthickness=1,
                                highlightbackground=LINE, highlightcolor=CYAN_DIM)
        entry_frame.place(x=20, y=40, width=card_w - 40, height=38)
        self.key_entry = tk.Entry(entry_frame, bg="#0e1320", fg=TEXT,
                                    insertbackground=CYAN, relief="flat",
                                    font=("Consolas", 11), justify="center")
        self.key_entry.pack(fill="both", expand=True, padx=8, pady=8)

        # remember me
        rem_y = 96
        tk.Label(self.card, text="Lembrar minha key", fg=TEXT_DIM, bg=CARD,
                  font=label_font).place(x=22, y=rem_y)
        self.toggle_canvas = tk.Canvas(self.card, width=40, height=20, bg=CARD,
                                         highlightthickness=0, cursor="hand2")
        self.toggle_canvas.place(x=card_w - 62, y=rem_y - 2)
        self.toggle_canvas.bind("<Button-1>", self._toggle_remember)
        self._draw_toggle()

        # botão LAUNCH
        self.launch_canvas = tk.Canvas(self.card, width=card_w - 40, height=44,
                                         bg=CARD, highlightthickness=0, cursor="hand2")
        self.launch_canvas.place(x=20, y=132)
        self._draw_launch_button("LAUNCH")
        self.launch_canvas.bind("<Button-1>", lambda e: self.on_launch())

        # status
        self.status_var = tk.StringVar(value="")
        self.status_label = tk.Label(self.card, textvariable=self.status_var,
                                       fg=TEXT_DIM, bg=CARD, font=("Segoe UI", 9 ),
                                       wraplength=card_w - 40, justify="center")
        self.status_label.place(x=20, y=188)

        # link de suporte
        support = tk.Label(self.root, text="Problemas? entra no nosso Discord",
                             fg=CYAN_DIM, bg=BG_0, font=link_font, cursor="hand2")
        support.pack(pady=(16, 0))
        support.bind("<Button-1>", lambda e: self._open_support())

    def _open_support(self):
        import webbrowser
        webbrowser.open(SUPPORT_URL)

    # ------------------------------------------------------------------
    def _draw_toggle(self):
        self.toggle_canvas.delete("all")
        on = self.remember_var.get()
        bg = CYAN_DIM if on else "#2a3142"
        round_rect(self.toggle_canvas, 0, 0, 40, 20, 10, fill=bg, outline="")
        knob_x = 28 if on else 12
        self.toggle_canvas.create_oval(knob_x - 8, 2, knob_x + 8, 18,
                                         fill="#ffffff" if on else "#9aa3b5", outline="")

    def _toggle_remember(self, event=None):
        self.remember_var.set(not self.remember_var.get())
        self._draw_toggle()

    def _draw_launch_button(self, text, enabled=True):
        self.launch_canvas.delete("all")
        w = int(self.launch_canvas["width"])
        h = int(self.launch_canvas["height"])
        fill = CYAN if enabled else "#2a3142"
        round_rect(self.launch_canvas, 0, 0, w, h, 10, fill=fill, outline="")
        self.launch_canvas.create_text(w // 2, h // 2, text=text,
                                         fill="#06181a" if enabled else TEXT_DIM,
                                         font=("Segoe UI Semibold", 11))

    # ------------------------------------------------------------------
    def set_status(self, text, kind="info"):
        color = {"info": TEXT_DIM, "ok": CYAN, "error": ERROR}.get(kind, TEXT_DIM)
        self.status_label.configure(fg=color)
        self.status_var.set(text)

    def on_launch(self):
        if self.validating:
            return
        key = self.key_entry.get().strip()
        if not key:
            self.set_status("Cole sua key antes de continuar.", "error")
            return

        self.validating = True
        self._draw_launch_button("VALIDANDO...", enabled=False)
        self.set_status("Verificando sua key...", "info")

        threading.Thread(target=self._validate_key, args=(key,), daemon=True).start()

    def _validate_key(self, key):
        try:
            resp = requests.post(
                f"{BASE_URL}/api/keys/validate",
                json={"key": key, "hwid": get_hwid()},
                timeout=15,
            )
            data = resp.json()
        except Exception:
            self.root.after(0, self._on_validate_result, False,
                              "Não consegui falar com o servidor. Confere sua internet e tenta de novo.")
            return

        if data.get("valid"):
            self.root.after(0, self._on_validate_result, True, key)
        else:
            reason = data.get("reason", "Key inválida.")
            self.root.after(0, self._on_validate_result, False, reason)

    def _on_validate_result(self, ok, payload):
        self.validating = False
        if not ok:
            self._draw_launch_button("LAUNCH", enabled=True)
            self.set_status(payload, "error")
            return

        key = payload
        if self.remember_var.get():
            save_key(key)
        else:
            clear_saved_key()

        self.set_status("Key válida! Abrindo o tradutor...", "ok")
        self.root.after(600, self._open_translator)

    def _open_translator(self):
        self.root.destroy()
        # abre o tradutor de verdade na mesma janela de processo
        import tradutor_overlay
        tradutor_overlay.main()


if __name__ == "__main__":
    KeyGateApp()
