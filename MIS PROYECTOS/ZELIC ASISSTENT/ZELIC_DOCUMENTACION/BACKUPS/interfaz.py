"""
interfaz.py — Zelic AI Desktop Assistant
Visual design ported from zelic_frontend.html.
Backend logic preserved from original interfaz.py.
Voice: ModuloVoz runs inline (no separate Toplevel).
"""

import tkinter as tk
from tkinter import filedialog
import threading
import math
import time
import random

from google import genai
from CONFIG.config import API_KEY
from memoria_simple import MemoriaSimple, PerfilUsuario
from orquestador import clasificar_intencion
from core import chat, imagen, documento, sistema
from core import tareas
from core import saludo as saludo_mod
from core import clima as clima_mod
from core import sistema_info as sysinfo_mod
from core import vision_pantalla
from core.voz import ModuloVoz
import database as db

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

# ── Paleta (del HTML) ──────────────────────────────────────────────────────────
BG0        = "#08111f"
BG1        = "#0c1628"
BG2        = "#111d33"
BG3        = "#16233b"
BG4        = "#1b2a44"
BLUE       = "#2d5af0"
BLUE_A     = "#4d78f8"
CYAN       = "#41c8f5"
LIVE_CYAN  = "#18D7FF"
LIVE_BLUE  = "#7DA9FF"
VIO        = "#7b5ea7"
T0         = "#f7faff"
T1         = "#d7e2ff"
T2         = "#91a2c6"
T3         = "#4a5a7a"

# Tkinter-safe border approximations (no alpha support)
BD_DIM     = "#0e1a2e"
BD_MED     = "#1a2a42"
BD_BLUE    = "#2a3f70"
BD_BLUE_LT = "#3a5898"
BG_VIOLET  = "#14213a"
BD_VIO     = "#3a2a60"

# Fonts
F_UI    = ("Segoe UI", 10)
F_SM    = ("Segoe UI", 9)
F_LG    = ("Segoe UI", 12)
F_BOLD  = ("Segoe UI", 10, "bold")
F_MONO  = ("Courier New", 9)
F_MONO8 = ("Courier New", 8)


# ══════════════════════════════════════════════════════════════════════════════
class ZelicApp:
# ══════════════════════════════════════════════════════════════════════════════

    def __init__(self, root):
        self.root = root
        self.root.title("Zelic")
        self.root.geometry("1120x680")
        self.root.configure(bg=BG0)
        self.root.minsize(860, 520)

        # ── Backend init ──
        db.inicializar()
        tareas.inicializar_tablas()
        self.sesion_id       = None
        self.total_msgs      = 0
        self.client          = genai.Client(api_key=API_KEY)
        self.perfil          = PerfilUsuario()
        self.memoria         = None

        # ── State ──
        self.modulo_activo        = tk.StringVar(value="chat")
        self.archivo_adjunto      = None
        self._ultimo_modulo       = ""
        self._en_chat             = False
        self._placeholder_activo  = False
        self._nav_drawer_visible  = False
        self._cargando_sesion     = False

        # ── Voice state ──
        self._voz_modulo             = None
        self._voice_float_visible    = False
        self._transcripciones_voz    = []
        self._vf_anim_running        = False
        self._vf_orb_frame           = 0
        self._vf_voice_estado        = "idle"
        self._vf_bars_current        = []
        self._vf_bars_targets        = []
        self._vf_bars_speeds         = []

        # ── Orb animation ──
        self._orb_frame   = 0
        self._zmark_phase = 0.0

        self._build_ui()
        self._cargar_sidebar_data()
        self._nueva_conversacion()

        self.root.protocol("WM_DELETE_WINDOW", self._cerrar)
        self._iniciar_monitor_recordatorios()
        self.root.bind("<Control-z>", lambda e: self._toggle_voice_float())
        self._tick_clock()
        self._zmark_anim()

    # ══════════════════════════════════════════════════════════════════════════
    #  BUILD UI
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self._build_topbar()

        self.body = tk.Frame(self.root, bg=BG0)
        self.body.pack(fill="both", expand=True)

        self._build_nav_col()

        # main_area holds nav_drawer + center + right_panel
        self.main_area = tk.Frame(self.body, bg=BG0)
        self.main_area.pack(side="left", fill="both", expand=True)

        self._build_right_panel()
        self._build_nav_drawer()

        self.center = tk.Frame(self.main_area, bg=BG0)
        self.center.pack(side="left", fill="both", expand=True)

        # Voice float built after layout is ready
        self.root.after(200, self._build_voice_float)

    # ── Topbar ────────────────────────────────────────────────────────────────

    def _build_topbar(self):
        self.topbar = tk.Frame(self.root, bg=BG1, height=44)
        self.topbar.pack(fill="x", side="top")
        self.topbar.pack_propagate(False)

        # Bottom border line
        tk.Frame(self.topbar, bg=BD_MED, height=1).place(
            relx=0, rely=1.0, relwidth=1, y=-1)

        # ── Left ──
        left = tk.Frame(self.topbar, bg=BG1)
        left.pack(side="left", padx=(16, 0), fill="y")

        self._zmark_canvas = tk.Canvas(
            left, width=26, height=26, bg=BG1, highlightthickness=0, cursor="hand2")
        self._zmark_canvas.pack(side="left", padx=(0, 10))
        # Outer diamond (rotated square)
        self._zmark_canvas.create_rectangle(
            6, 6, 20, 20, outline=BD_BLUE_LT, fill="", width=1, tags="zd_outer")
        # Inner bead
        self._zmark_canvas.create_rectangle(
            10, 10, 16, 16, fill=BLUE_A, outline="", tags="zd_inner")

        tk.Label(left, text="ZELIC", bg=BG1, fg=T0,
                 font=("Segoe UI", 10, "bold")).pack(side="left")

        # Divider
        tk.Frame(self.topbar, bg=BD_DIM, width=1).pack(
            side="left", padx=18, fill="y", pady=12)

        # Tabs
        tabs = tk.Frame(self.topbar, bg=BG1)
        tabs.pack(side="left", fill="y")
        self._tab_btns = []
        for i, name in enumerate(["Sistema", "Workspace", "Memoria"]):
            btn = tk.Label(tabs, text=name, bg=BG1,
                           fg=T1 if i == 0 else T3,
                           font=F_SM, cursor="hand2", padx=12, pady=5)
            btn.pack(side="left")
            if i == 0:
                btn.config(bg=BD_MED)
            btn.bind("<Button-1>", lambda e, b=btn: self._on_tab(b))
            self._tab_btns.append(btn)

        # ── Right ──
        right = tk.Frame(self.topbar, bg=BG1)
        right.pack(side="right", padx=16, fill="y")

        self.lbl_clock = tk.Label(right, text="--:--", bg=BG1, fg=T3,
                                  font=F_MONO)
        self.lbl_clock.pack(side="right", padx=(14, 0))

        # System pill
        pill = tk.Frame(right, bg=BD_DIM,
                        highlightbackground=BD_MED, highlightthickness=1)
        pill.pack(side="right")
        pill_inner = tk.Frame(pill, bg=BD_DIM, padx=8, pady=3)
        pill_inner.pack()
        dot_c = tk.Canvas(pill_inner, width=6, height=6, bg=BD_DIM,
                          highlightthickness=0)
        dot_c.pack(side="left", padx=(0, 5))
        dot_c.create_oval(0, 0, 6, 6, fill=CYAN, outline="", tags="sdot")
        self._sdot_canvas = dot_c
        self._sdot_phase  = 0.0
        self._animate_sdot()
        tk.Label(pill_inner, text="SYSTEM ONLINE", bg=BD_DIM, fg=T2,
                 font=F_MONO8).pack(side="left")

    def _on_tab(self, clicked):
        for b in self._tab_btns:
            b.config(fg=T3, bg=BG1)
        clicked.config(fg=T1, bg=BD_MED)

    # ── Nav column ────────────────────────────────────────────────────────────

    def _build_nav_col(self):
        nav_outer = tk.Frame(self.body, bg=BG0, width=58)
        nav_outer.pack(side="left", fill="y")
        nav_outer.pack_propagate(False)
        tk.Frame(nav_outer, bg=BD_DIM, width=1).pack(side="right", fill="y")

        # Capsule
        self.nav_cap = tk.Frame(nav_outer, bg=BG3, padx=0, pady=8,
                                highlightbackground=BD_MED, highlightthickness=1)
        self.nav_cap.place(relx=0.5, rely=0.5, anchor="center")

        nav_items = [
            ("⌂", "home",    True,  self._nav_home),
            ("✉", "chat",    False, self._nav_chat),
            (None, None,     False, None),
            ("◉", "memory",  False, self._nav_memory),
            ("⊞", "files",   False, self._nav_files),
            ("⚙", "tools",   False, self._nav_tools),
            (None, None,     False, None),
            ("⊟", "config",  False, self._nav_config),
        ]
        self._nav_btns = {}
        for icon, name, active, cmd in nav_items:
            if icon is None:
                tk.Frame(self.nav_cap, bg=BD_DIM, height=1, width=22).pack(pady=3)
                continue
            f = self._make_nav_btn(self.nav_cap, icon, name, active, cmd)
            self._nav_btns[name] = f

    def _make_nav_btn(self, parent, icon, name, active, cmd):
        bg_n = BG2 if active else BG3
        fg_n = BLUE_A if active else T3

        frame = tk.Frame(parent, bg=bg_n, width=38, height=36, cursor="hand2")
        frame.pack(pady=1)
        frame.pack_propagate(False)

        lbl = tk.Label(frame, text=icon, bg=bg_n, fg=fg_n,
                       font=("Segoe UI", 14), cursor="hand2")
        lbl.place(relx=0.5, rely=0.5, anchor="center")

        if active:
            ind = tk.Frame(frame, bg=BLUE_A, width=2, height=12)
            ind.place(x=0, rely=0.5, anchor="w")

        def _enter(e):
            frame.config(bg=BG2); lbl.config(bg=BG2, fg=T2)
        def _leave(e):
            frame.config(bg=bg_n); lbl.config(bg=bg_n, fg=fg_n)
        def _click(e):
            if cmd:
                cmd()

        for w in (frame, lbl):
            w.bind("<Enter>", _enter)
            w.bind("<Leave>", _leave)
            w.bind("<Button-1>", _click)

        return frame

    # ── Nav drawer (conversation history) ─────────────────────────────────────

    def _build_nav_drawer(self):
        self.nav_drawer = tk.Frame(self.main_area, bg=BG1, width=224)
        tk.Frame(self.nav_drawer, bg=BD_MED, width=1).pack(side="right", fill="y")

        hdr = tk.Frame(self.nav_drawer, bg=BG1)
        hdr.pack(fill="x", padx=14, pady=(14, 8))
        tk.Label(hdr, text="CONVERSACIONES", bg=BG1, fg=T3,
                 font=F_MONO8).pack(side="left")
        tk.Button(hdr, text="＋", bg=BG2, fg=BLUE_A, font=("Segoe UI", 11),
                  bd=0, cursor="hand2", padx=6, pady=0,
                  activebackground=BD_BLUE, activeforeground=T1,
                  command=self._nueva_conversacion).pack(side="right")

        scroll_f = tk.Frame(self.nav_drawer, bg=BG1)
        scroll_f.pack(fill="both", expand=True)

        self.hist_canvas = tk.Canvas(scroll_f, bg=BG1, highlightthickness=0)
        hsb = tk.Scrollbar(scroll_f, orient="vertical",
                           command=self.hist_canvas.yview, width=3)
        self.hist_canvas.configure(yscrollcommand=hsb.set)
        hsb.pack(side="right", fill="y")
        self.hist_canvas.pack(side="left", fill="both", expand=True)

        self.frame_historial = tk.Frame(self.hist_canvas, bg=BG1)
        self.hist_canvas.create_window((0, 0), window=self.frame_historial,
                                       anchor="nw")
        self.frame_historial.bind(
            "<Configure>",
            lambda e: self.hist_canvas.configure(
                scrollregion=self.hist_canvas.bbox("all")))
        self.hist_canvas.bind(
            "<MouseWheel>",
            lambda e: self.hist_canvas.yview_scroll(
                int(-1*(e.delta/120)), "units"))

    # ── Right panel ───────────────────────────────────────────────────────────

    def _build_right_panel(self):
        self.rp = tk.Frame(self.main_area, bg=BG1, width=216)
        self.rp.pack(side="right", fill="y")
        self.rp.pack_propagate(False)
        tk.Frame(self.rp, bg=BD_DIM, width=1).pack(side="left", fill="y")

        rp_i = tk.Frame(self.rp, bg=BG1)
        rp_i.pack(side="left", fill="both", expand=True)

        # Head
        rp_head = tk.Frame(rp_i, bg=BG1)
        rp_head.pack(fill="x", pady=(16, 12))

        orb_c = tk.Canvas(rp_head, width=38, height=38, bg=BG1,
                          highlightthickness=0)
        orb_c.pack()
        orb_c.create_oval(1, 1, 37, 37, outline=BLUE_A, fill="", width=1,
                          tags="mo_a")
        orb_c.create_oval(6, 6, 32, 32, outline=BD_BLUE, fill="", width=1,
                          tags="mo_b")
        orb_c.create_rectangle(13, 13, 25, 25, outline=BLUE_A, fill=BG2,
                                width=1, tags="mo_bead")
        self._rp_orb = orb_c
        self._rp_orb_phase = 0.0
        self._animate_rp_orb()

        st_row = tk.Frame(rp_head, bg=BG1)
        st_row.pack(pady=(6, 0))
        tk.Label(st_row, text="◆", bg=BG1, fg=CYAN,
                 font=("Segoe UI", 9)).pack(side="left")
        self.rp_status = tk.Label(st_row, text="online", bg=BG1, fg=T3,
                                  font=F_MONO8)
        self.rp_status.pack(side="left", padx=4)

        tk.Frame(rp_i, bg=BD_DIM, height=1).pack(fill="x")

        # Scrollable content
        sc_outer = tk.Frame(rp_i, bg=BG1)
        sc_outer.pack(fill="both", expand=True)

        rp_cv = tk.Canvas(sc_outer, bg=BG1, highlightthickness=0)
        rp_cv.pack(fill="both", expand=True)

        self.rp_scroll = tk.Frame(rp_cv, bg=BG1)
        rp_cv.create_window((0, 0), window=self.rp_scroll, anchor="nw")
        self.rp_scroll.bind(
            "<Configure>",
            lambda e: rp_cv.configure(scrollregion=rp_cv.bbox("all")))
        rp_cv.bind(
            "<MouseWheel>",
            lambda e: rp_cv.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._build_rp_context()
        self._build_rp_neural()
        self._build_rp_tasks()

    def _rp_section(self, text):
        f = tk.Frame(self.rp_scroll, bg=BG1)
        f.pack(fill="x", padx=14, pady=(14, 8))
        tk.Label(f, text=text, bg=BG1, fg=T3, font=F_MONO8).pack(side="left")
        tk.Frame(f, bg=BD_DIM, height=1).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

    def _ctx_card(self, label, initial, attr):
        card = tk.Frame(self.rp_scroll, bg=BG_VIOLET,
                        highlightbackground=BD_VIO, highlightthickness=1,
                        padx=10, pady=8)
        card.pack(fill="x", padx=14, pady=(0, 6))
        tk.Label(card, text=label.upper(), bg=BG_VIOLET, fg=T3,
                 font=F_MONO8).pack(anchor="w")
        lbl = tk.Label(card, text=initial, bg=BG_VIOLET, fg=T1, font=F_MONO)
        lbl.pack(anchor="w")
        setattr(self, attr, lbl)

    def _build_rp_context(self):
        self._rp_section("Context")
        self._ctx_card("intent",  "design mode", "ctx_intent_lbl")
        self._ctx_card("module",  "chat",         "ctx_module_lbl")

    def _build_rp_neural(self):
        self._rp_section("Neural")

        rows = [
            ("activity", None,       "bars"),
            ("cpu",      "—",        "cyan"),
            ("ram",      "—",        "normal"),
            ("latency",  "36ms",     "cyan"),
            ("memory",   "gemini",   "normal"),
            ("voice",    "ready",    "cyan"),
        ]
        for key, val, style in rows:
            row = tk.Frame(self.rp_scroll, bg=BG1)
            row.pack(fill="x", padx=14, pady=(3, 0))
            tk.Label(row, text=key, bg=BG1, fg=T3, font=F_MONO).pack(side="left")

            if style == "bars":
                bf = tk.Frame(row, bg=BG1)
                bf.pack(side="right")
                self._neural_bars_w = []
                for i in range(6):
                    b = tk.Frame(bf, bg=BLUE_A if i < 4 else BD_MED,
                                 width=7, height=3)
                    b.pack(side="left", padx=1)
                    self._neural_bars_w.append(b)
                self._animate_neural_bars(0)
            else:
                color = CYAN if style == "cyan" else T2
                lbl = tk.Label(row, text=val, bg=BG1, fg=color, font=F_MONO)
                lbl.pack(side="right")
                if key == "cpu":    self.rp_cpu = lbl
                elif key == "ram":  self.rp_ram = lbl
                elif key == "voice": self.rp_voice_lbl = lbl

            tk.Frame(self.rp_scroll, bg=BD_DIM, height=1).pack(
                fill="x", padx=14)

        self._update_metrics()

    def _build_rp_tasks(self):
        self._rp_section("Tareas")
        self.rp_tasks_frame = tk.Frame(self.rp_scroll, bg=BG1)
        self.rp_tasks_frame.pack(fill="x", padx=14, pady=(0, 20))
        self._cargar_tareas_rp()

    def _cargar_tareas_rp(self):
        for w in self.rp_tasks_frame.winfo_children():
            w.destroy()
        pending = tareas.listar_tareas(solo_pendientes=True)
        if not pending:
            tk.Label(self.rp_tasks_frame, text="Sin tareas pendientes",
                     bg=BG1, fg=T3, font=F_MONO8).pack(anchor="w", pady=4)
            return
        for tid, titulo, _, fecha_lim in pending[:6]:
            row = tk.Frame(self.rp_tasks_frame, bg=BG1, cursor="hand2")
            row.pack(fill="x", pady=3)

            chk = tk.Canvas(row, width=14, height=14, bg=BG1,
                            highlightthickness=0, cursor="hand2")
            chk.pack(side="left", padx=(0, 7))
            chk.create_rectangle(1, 1, 13, 13, outline=BD_MED, fill="", width=1)

            txt = titulo[:24] + "…" if len(titulo) > 24 else titulo
            lbl = tk.Label(row, text=txt, bg=BG1, fg=T2, font=F_MONO)
            lbl.pack(side="left")

            def _check(t=tid, c=chk):
                tareas.completar_tarea(t)
                c.create_rectangle(1, 1, 13, 13,
                                   fill=BD_BLUE, outline=BLUE_A, width=1)
                c.create_text(7, 7, text="✓", fill=BLUE_A,
                              font=("Segoe UI", 7))
                self.root.after(500, self._cargar_tareas_rp)

            chk.bind("<Button-1>", lambda e, f=_check: f())
            lbl.bind("<Button-1>",  lambda e, f=_check: f())
            tk.Frame(self.rp_tasks_frame, bg=BD_DIM, height=1).pack(fill="x")

    # ══════════════════════════════════════════════════════════════════════════
    #  CENTER — CHAT PANEL
    # ══════════════════════════════════════════════════════════════════════════

    def _mostrar_chat(self):
        self._en_chat = True
        for w in self.center.winfo_children():
            w.destroy()

        # ── Neural Core header ──
        core_z = tk.Frame(self.center, bg=BG0, pady=20)
        core_z.pack(fill="x")

        orb_c = tk.Canvas(core_z, width=84, height=84, bg=BG0,
                          highlightthickness=0)
        orb_c.pack()
        self._orb_canvas = orb_c
        self._orb_frame  = 0
        self._draw_orb_static(orb_c, 42, 42)
        self._animate_orb()

        tk.Label(core_z, text="ZELIC", bg=BG0, fg=T0,
                 font=("Segoe UI", 9, "bold")).pack(pady=(10, 3))
        sub_row = tk.Frame(core_z, bg=BG0)
        sub_row.pack()
        dot_cv = tk.Canvas(sub_row, width=6, height=6, bg=BG0,
                           highlightthickness=0)
        dot_cv.pack(side="left", padx=(0, 5))
        dot_cv.create_oval(0, 0, 6, 6, fill=CYAN, outline="")
        tk.Label(sub_row, text="Neural Core Online", bg=BG0, fg=T3,
                 font=F_MONO8).pack(side="left")

        # Divider
        tk.Frame(self.center, bg=BD_DIM, height=1).pack(fill="x")

        # ── Message thread ──
        msgs_outer = tk.Frame(self.center, bg=BG0)
        msgs_outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(msgs_outer, bg=BG0, highlightthickness=0)
        vsb = tk.Scrollbar(msgs_outer, orient="vertical",
                           command=self.canvas.yview, width=3)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.mensajes_frame = tk.Frame(self.canvas, bg=BG0)
        self.canvas_window  = self.canvas.create_window(
            (0, 0), window=self.mensajes_frame, anchor="nw")
        self.mensajes_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")))
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(
                self.canvas_window, width=e.width))
        self.canvas.bind(
            "<MouseWheel>",
            lambda e: self.canvas.yview_scroll(
                int(-1*(e.delta/120)), "units"))

        # ── Input bar ──
        self._build_input_bar()

        # Start greeting
        threading.Thread(target=self._cargar_saludo, daemon=True).start()

    def _build_input_bar(self):
        inp_wrap = tk.Frame(self.center, bg=BG0, pady=8)
        inp_wrap.pack(fill="x", padx=24, side="bottom")

        # Input group container
        self._ig = tk.Frame(inp_wrap, bg=BG2,
                            highlightbackground=BD_MED, highlightthickness=1)
        self._ig.pack(fill="x")

        # Focus accent line (top)
        self._ig_line = tk.Frame(self._ig, bg=BLUE, height=1)
        # hidden by default, shown on focus

        # Inner row
        ig_inner = tk.Frame(self._ig, bg=BG2)
        ig_inner.pack(fill="x", padx=12, pady=(10, 6))

        self.entrada = tk.Text(
            ig_inner, height=1, bg=BG2, fg=T0,
            font=("Segoe UI", 12), bd=0,
            insertbackground=T0, wrap="word", padx=0, pady=0)
        self.entrada.pack(side="left", fill="both", expand=True)
        self.entrada.bind("<Return>",     self._on_enter)
        self.entrada.bind("<KeyRelease>", self._ajustar_altura)
        self.entrada.bind("<FocusIn>",    self._on_focus_in)
        self.entrada.bind("<FocusOut>",   self._on_focus_out)

        self._placeholder_activo = True
        self.entrada.insert("1.0", "Ask Zelic…")
        self.entrada.config(fg=T3)

        # Buttons
        i_btns = tk.Frame(ig_inner, bg=BG2)
        i_btns.pack(side="right")

        self._ib_attach = self._make_ib(i_btns, "⊕", self._adjuntar_archivo)
        self._ib_attach.pack(side="left", padx=2)

        self._ib_mic = self._make_ib(i_btns, "🎙", self._toggle_voice_float)
        self._ib_mic.pack(side="left", padx=2)

        self.btn_enviar = self._make_ib(
            i_btns, "↑", self._enviar, send=True)
        self.btn_enviar.pack(side="left", padx=2)

        # Meta row
        meta = tk.Frame(self._ig, bg=BG2)
        meta.pack(fill="x", padx=12, pady=(0, 8))
        for hint in ["↵ send", "⇧↵ newline", "⌃Z voice"]:
            tk.Label(meta, text=hint, bg=BG2, fg=T3,
                     font=F_MONO8, padx=3).pack(side="left")
        self.mdl_lbl = tk.Label(meta, text="gemini-2.5-flash",
                                bg=BG2, fg=T3, font=F_MONO8)
        self.mdl_lbl.pack(side="right")

    def _make_ib(self, parent, icon, cmd, send=False):
        bg_n = BD_BLUE if send else BG2
        fg_n = BLUE_A  if send else T3
        brd  = BD_BLUE_LT if send else BG3

        c = tk.Canvas(parent, width=30, height=30, bg=bg_n,
                      highlightbackground=brd, highlightthickness=1,
                      cursor="hand2")
        c.create_text(15, 15, text=icon, fill=fg_n,
                      font=("Segoe UI", 12), tags="icon")

        def _enter(e):
            c.config(bg=BLUE_A if send else BG3)
            c.itemconfig("icon", fill=T0 if send else T2)
        def _leave(e):
            c.config(bg=bg_n)
            c.itemconfig("icon", fill=fg_n)

        c.bind("<Enter>",    _enter)
        c.bind("<Leave>",    _leave)
        c.bind("<Button-1>", lambda e: cmd())
        return c

    def _on_focus_in(self, e=None):
        self._quitar_placeholder()
        self._ig_line.pack(fill="x")

    def _on_focus_out(self, e=None):
        self._poner_placeholder()
        self._ig_line.pack_forget()

    # ══════════════════════════════════════════════════════════════════════════
    #  VOICE FLOAT
    # ══════════════════════════════════════════════════════════════════════════

    def _build_voice_float(self):
        self.voice_float = tk.Frame(
            self.root, bg=BG3,
            highlightbackground=BD_BLUE_LT, highlightthickness=1)

        inner = tk.Frame(self.voice_float, bg=BG3)
        inner.pack(padx=18, pady=(20, 16))

        # Top accent line
        tk.Frame(self.voice_float, bg=BD_BLUE_LT, height=1).place(
            relx=0.24, y=0, relwidth=0.52)

        # ── Orb ──
        vf_orb = tk.Canvas(inner, width=56, height=56, bg=BG3,
                           highlightthickness=0)
        vf_orb.pack()
        vf_orb.create_oval(1,  1,  55, 55, outline="#1a3060", fill="",
                           width=1, tags="vfr_a")
        vf_orb.create_oval(7,  7,  49, 49, outline="#0e1e40", fill="",
                           width=1, tags="vfr_b")
        vf_orb.create_oval(13, 13, 43, 43, outline="#0e2a38", fill="",
                           width=1, tags="vfr_c")
        vf_orb.create_rectangle(20, 20, 36, 36,
                                outline=LIVE_CYAN, fill=BG3,
                                width=1, tags="vf_bead")
        self._vf_orb_canvas = vf_orb

        # ── Status label ──
        self.vf_proc_lbl = tk.Label(
            inner, text="ESCUCHANDO", bg=BG3, fg=LIVE_BLUE,
            font=("Courier New", 9))
        self.vf_proc_lbl.pack(pady=(10, 6))

        # ── Wave bars ──
        wave_f = tk.Frame(inner, bg=BG3, height=28)
        wave_f.pack(fill="x")
        wave_f.pack_propagate(False)
        self._vf_bars = []
        for i in range(10):
            b = tk.Frame(wave_f, bg=LIVE_CYAN, width=3, height=8)
            b.pack(side="left", padx=2)
            self._vf_bars.append(b)
            self._vf_bars_current.append(8.0)
            self._vf_bars_targets.append(8.0 + (i * 1.7) % 18)
            self._vf_bars_speeds.append(0.04 + (i % 3) * 0.015)

        # ── Sub text ──
        self.vf_sub_lbl = tk.Label(
            inner, text="habla cuando quieras", bg=BG3, fg=LIVE_BLUE,
            font=F_MONO8)
        self.vf_sub_lbl.pack(pady=(6, 10))

        # ── Screen capture button ──
        cap_btn = tk.Label(
            inner, text="📷  ver pantalla", bg=BG2, fg=T2,
            font=F_MONO8, cursor="hand2", padx=10, pady=4,
            highlightbackground=BD_MED, highlightthickness=1)
        cap_btn.pack(pady=(0, 6))
        cap_btn.bind("<Button-1>", lambda e: self._capturar_pantalla())
        cap_btn.bind("<Enter>", lambda e: cap_btn.config(fg=T1))
        cap_btn.bind("<Leave>", lambda e: cap_btn.config(fg=T2))

        # ── Close ──
        close_btn = tk.Label(
            inner, text="cerrar sesión de voz", bg=BG3, fg=T2,
            font=F_MONO, cursor="hand2", padx=14, pady=5,
            highlightbackground=BD_MED, highlightthickness=1)
        close_btn.pack()
        close_btn.bind("<Button-1>", lambda e: self._hide_voice_float())
        close_btn.bind("<Enter>",
                       lambda e: close_btn.config(fg=T1, bg=BG2))
        close_btn.bind("<Leave>",
                       lambda e: close_btn.config(fg=T2, bg=BG3))

    def _toggle_voice_float(self):
        if self._voice_float_visible:
            self._hide_voice_float()
        else:
            self._show_voice_float()

    def _show_voice_float(self):
        if not self._en_chat:
            self._nueva_conversacion()
            self.root.after(300, self._show_voice_float)
            return
        if not hasattr(self, 'voice_float'):
            return

        self._voice_float_visible = True
        # Position: bottom-right, above input, left of right panel
        self.voice_float.place(
            relx=1.0, rely=1.0, anchor="se",
            x=-(216 + 16), y=-80, width=204)

        self._vf_anim_running = True
        self._animate_voice_float()

        # Start voice module
        if not self._voz_modulo:
            self._voz_modulo = ModuloVoz(
                client=self.client,
                callback_texto=self._on_texto_voz,
                callback_estado=self._on_voz_estado,
                callback_apagar=self._hide_voice_float,
                callback_memoria=(
                    self.memoria.agregar if self.memoria else None),
            )
            self._voz_modulo.iniciar()

        # Mic button highlight
        try:
            self._ib_mic.config(bg="#0d2a30",
                                highlightbackground=CYAN)
            self._ib_mic.itemconfig("icon", fill=CYAN)
        except Exception:
            pass

        # Right panel status
        try:
            self.rp_voice_lbl.config(text="activo", fg=CYAN)
            self.rp_status.config(text="escuchando")
        except Exception:
            pass

    def _hide_voice_float(self):
        self._voice_float_visible = False
        self._vf_anim_running     = False
        if hasattr(self, 'voice_float'):
            self.voice_float.place_forget()

        if self._voz_modulo:
            self._voz_modulo.detener()
            self._voz_modulo = None

        # Flush transcriptions
        self._ventana_voz_cerrada()

        # Reset UI
        try:
            self._ib_mic.config(bg=BG2,
                                highlightbackground=BG3)
            self._ib_mic.itemconfig("icon", fill=T3)
        except Exception:
            pass
        try:
            self.rp_voice_lbl.config(text="ready", fg=CYAN)
            self.rp_status.config(text="online")
        except Exception:
            pass

    def _on_voz_estado(self, estado: str):
        self._vf_voice_estado = estado
        textos = {
            "escuchando": ("ESCUCHANDO",  "habla cuando quieras"),
            "procesando": ("PROCESANDO",  "analizando audio..."),
            "hablando":   ("RESPONDIENDO","generando respuesta..."),
            "idle":       ("EN ESPERA",   "di \"Zelic\" para activar"),
        }
        proc, sub = textos.get(estado, ("...", ""))
        try:
            self.root.after(0, lambda: self.vf_proc_lbl.config(text=proc))
            self.root.after(0, lambda: self.vf_sub_lbl.config(text=sub))
        except Exception:
            pass

    def _capturar_pantalla(self):
        """Toma captura de pantalla y la analiza por voz."""
        import io, base64
        try:
            import mss
            from PIL import Image
        except ImportError:
            return

        def _hacer():
            try:
                if hasattr(self, 'voice_float'):
                    self.root.after(0, self.voice_float.place_forget)
                time.sleep(0.5)
                with mss.mss() as sct:
                    monitor = sct.monitors[1]
                    cap     = sct.grab(monitor)
                    img     = Image.frombytes(
                        "RGB", cap.size, cap.bgra, "raw", "BGRX")
                    img     = img.resize((1280, 720), Image.LANCZOS)
                    buf     = io.BytesIO()
                    img.save(buf, format="JPEG", quality=65)
                    b64     = base64.b64encode(buf.getvalue()).decode()

                resp = vision_pantalla._analizar_imagen(
                    self.client,
                    base64.b64decode(b64),
                    "Describe brevemente qué está haciendo el usuario.",
                    "gemini-2.5-flash"
                )
                if resp and self._en_chat:
                    self.root.after(
                        0, lambda: self._agregar_mensaje(
                            "zelic", f"👁 {resp}"))
            except Exception as ex:
                print(f"[Captura] {ex}")
            finally:
                if self._voice_float_visible and hasattr(self, 'voice_float'):
                    self.root.after(
                        400, lambda: self.voice_float.place(
                            relx=1.0, rely=1.0, anchor="se",
                            x=-(216+16), y=-80, width=204))

        threading.Thread(target=_hacer, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════════
    #  NAV ACTIONS
    # ══════════════════════════════════════════════════════════════════════════

    def _nav_home(self):
        if self._nav_drawer_visible:
            self._hide_nav_drawer()
        self._nueva_conversacion()

    def _nav_chat(self):
        if self._nav_drawer_visible:
            self._hide_nav_drawer()
        else:
            self._show_nav_drawer()

    def _nav_memory(self): pass
    def _nav_tools(self):  pass
    def _nav_config(self): pass

    def _nav_files(self):
        self._adjuntar_archivo()

    def _show_nav_drawer(self):
        self._nav_drawer_visible = True
        self.nav_drawer.pack(side="left", fill="y", before=self.center)
        self._cargar_historial_sidebar()

    def _hide_nav_drawer(self):
        self._nav_drawer_visible = False
        self.nav_drawer.pack_forget()

    # ══════════════════════════════════════════════════════════════════════════
    #  MESSAGES
    # ══════════════════════════════════════════════════════════════════════════

    def _agregar_mensaje(self, rol, texto):
        if not self._en_chat:
            return
        es_usuario = rol == "usuario"
        es_sistema = rol == "sistema"

        # Separator row
        row = tk.Frame(self.mensajes_frame, bg=BG0)
        row.pack(fill="x")
        tk.Frame(row, bg=BD_DIM, height=1).pack(fill="x")

        content = tk.Frame(row, bg=BG0)
        content.pack(fill="x", padx=32, pady=12)

        if es_sistema:
            tk.Label(content, text=texto, bg=BG0, fg=T3,
                     font=F_MONO8).pack(anchor="w")
            self._scroll_abajo()
            return

        inner = tk.Frame(content, bg=BG0)
        inner.pack(fill="x")

        if es_usuario:
            # Avatar right
            av = tk.Canvas(inner, width=26, height=26, bg=BG0,
                           highlightthickness=0)
            av.pack(side="right", anchor="n", padx=(10, 0))
            av.create_rectangle(2, 2, 24, 24, fill=BD_DIM, outline=BD_MED)
            av.create_text(13, 13, text="S", fill=T3, font=F_MONO8)

            # Right column
            rc = tk.Frame(inner, bg=BG0)
            rc.pack(side="right", anchor="n")
            tk.Label(rc, text="tú", bg=BG0, fg=T3,
                     font=F_MONO8).pack(anchor="e")
            bubble = tk.Frame(rc, bg=BG3,
                              highlightbackground=BD_MED,
                              highlightthickness=1,
                              padx=14, pady=10)
            bubble.pack(anchor="e")
            tk.Label(bubble, text=texto, bg=BG3, fg=T0,
                     font=("Segoe UI", 11), wraplength=380,
                     justify="left", anchor="w").pack()

        else:
            # Avatar left
            av = tk.Canvas(inner, width=26, height=26, bg=BG0,
                           highlightthickness=0)
            av.pack(side="left", anchor="n", padx=(0, 10))
            av.create_rectangle(2, 2, 24, 24, fill="#1a2a50",
                                outline=BD_BLUE)
            av.create_rectangle(9, 9, 17, 17, outline=BLUE_A,
                                fill="", width=1)

            rc = tk.Frame(inner, bg=BG0)
            rc.pack(side="left", fill="x", expand=True, anchor="n")

            mw = tk.Frame(rc, bg=BG0)
            mw.pack(anchor="w")
            tk.Label(mw, text="zelic", bg=BG0, fg=T3,
                     font=F_MONO8).pack(side="left")
            tk.Label(mw, text=" // chat", bg=BG0, fg=BLUE_A,
                     font=("Courier New", 8, "bold"),
                     ).pack(side="left")

            tk.Label(rc, text=texto, bg=BG0, fg="#c8d8f8",
                     font=("Segoe UI", 11), wraplength=480,
                     justify="left", anchor="w").pack(anchor="w", pady=(4, 0))

        self._scroll_abajo()

    def _mostrar_typing(self):
        self.typing_frame = tk.Frame(self.mensajes_frame, bg=BG0)
        self.typing_frame.pack(fill="x")
        tk.Frame(self.typing_frame, bg=BD_DIM, height=1).pack(fill="x")

        content = tk.Frame(self.typing_frame, bg=BG0)
        content.pack(fill="x", padx=32, pady=12)

        inner = tk.Frame(content, bg=BG0)
        inner.pack(fill="x")

        av = tk.Canvas(inner, width=26, height=26, bg=BG0,
                       highlightthickness=0)
        av.pack(side="left", anchor="n", padx=(0, 10))
        av.create_rectangle(2, 2, 24, 24, fill="#1a2a50", outline=BD_BLUE)
        av.create_rectangle(9, 9, 17, 17, outline=BLUE_A, fill="", width=1)

        rc = tk.Frame(inner, bg=BG0)
        rc.pack(side="left", anchor="n")

        mw = tk.Frame(rc, bg=BG0)
        mw.pack(anchor="w")
        tk.Label(mw, text="zelic", bg=BG0, fg=T3, font=F_MONO8).pack(side="left")
        self._typing_tag = tk.Label(mw, text=" procesando",
                                    bg=BG0, fg=T3, font=F_MONO8)
        self._typing_tag.pack(side="left")

        dots_f = tk.Frame(rc, bg=BG0)
        dots_f.pack(anchor="w", pady=(4, 0))
        self._typing_dots = []
        for i in range(3):
            d = tk.Canvas(dots_f, width=7, height=7, bg=BG0,
                          highlightthickness=0)
            d.pack(side="left", padx=3)
            d.create_oval(1, 1, 6, 6, fill=BLUE_A, outline="", tags="dot")
            self._typing_dots.append(d)

        self._scroll_abajo()
        self._animate_typing(0)

    def _animate_typing(self, step):
        if not hasattr(self, 'typing_frame') or \
           not self.typing_frame.winfo_exists():
            return
        for i, d in enumerate(self._typing_dots):
            try:
                alpha = 1.0 if i == step % 3 else 0.2
                color = self._blend(BLUE_A, alpha)
                d.itemconfig("dot", fill=color)
            except Exception:
                return
        self.root.after(320, lambda: self._animate_typing(step + 1))

    def _quitar_typing(self):
        if hasattr(self, "typing_frame"):
            try:
                self.typing_frame.destroy()
            except Exception:
                pass

    def _scroll_abajo(self):
        self.root.after(50, lambda: self.canvas.yview_moveto(1.0))

    # ══════════════════════════════════════════════════════════════════════════
    #  BACKEND / PROCESSING  (lógica original preservada)
    # ══════════════════════════════════════════════════════════════════════════

    def _set_context(self, intent: str, module: str):
        try:
            self.ctx_intent_lbl.config(text=intent)
            self.ctx_module_lbl.config(text=module)
            self.modulo_activo.set(module)
        except Exception:
            pass

    def _cargar_saludo(self):
        try:
            msg = saludo_mod.generar(self.client, self.memoria)
        except Exception:
            msg = "Sistemas nominales. Aquí estoy."
        self.root.after(0, lambda: self._mostrar_y_guardar_saludo(msg))

    def _mostrar_y_guardar_saludo(self, msg: str):
        self._agregar_mensaje("zelic", msg)
        db.guardar_mensaje(self.sesion_id, "model", msg)
        self._cargar_historial_sidebar()

    def _enviar(self):
        if self._placeholder_activo:
            return
        texto = self.entrada.get("1.0", "end").strip()
        if not texto:
            return
        self.entrada.delete("1.0", "end")
        self._ajustar_altura()
        try:
            self.btn_enviar.config(state="disabled")
        except Exception:
            pass
        self._agregar_mensaje("usuario", texto)
        self._mostrar_typing()
        threading.Thread(target=self._procesar, args=(texto,),
                         daemon=True).start()

    def _procesar(self, texto):
        respuesta = "No entendí la solicitud."
        try:
            intencion = clasificar_intencion(
                self.client, texto, ultimo_modulo=self._ultimo_modulo)
            self._ultimo_modulo = intencion
            self.root.after(0, lambda: self._set_context(intencion, intencion))

            if intencion == "chat":
                self.memoria.agregar("user", texto)
                respuesta = chat.responder(self.client, self.memoria)
                self.memoria.agregar("model", respuesta)
                self.total_msgs += 1
                if self.total_msgs == 1:
                    threading.Thread(target=self._generar_nombre_chat,
                                     args=(texto,), daemon=True).start()

            elif intencion == "tareas":
                respuesta = tareas.procesar(self.client, texto)
                self.root.after(0, self._cargar_tareas_rp)

            elif intencion == "vision":
                respuesta = vision_pantalla.analizar(self.client, texto)

            elif intencion == "clima":
                respuesta = clima_mod.responder(self.client, texto)

            elif intencion == "sistema_info":
                respuesta = sysinfo_mod.responder(self.client, texto)

            elif intencion == "imagen":
                respuesta = imagen.generar(self.client, texto)
                db.guardar_imagen(
                    self.sesion_id, texto,
                    "data/imagenes/imagen_generada.png")

            elif intencion == "documento":
                ruta = self.archivo_adjunto
                if not ruta:
                    respuesta = "Primero adjunta un archivo con el botón ⊕"
                else:
                    nombre   = ruta.replace("\\", "/").split("/")[-1]
                    respuesta = documento.analizar(self.client, ruta, texto)
                    db.guardar_documento(self.sesion_id, nombre, respuesta)
                    self.archivo_adjunto = None

            elif intencion == "sistema":
                respuesta = sistema.ejecutar(self.client, texto)
                db.guardar_accion(self.sesion_id, texto)

        except Exception as e:
            respuesta = f"Ocurrió un error: {e}"

        self.root.after(0, self._quitar_typing)
        self.root.after(0, lambda: self._agregar_mensaje("zelic", respuesta))
        self.root.after(0, lambda: self.btn_enviar.config(state="normal"))

    # ══════════════════════════════════════════════════════════════════════════
    #  INPUT HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _quitar_placeholder(self, e=None):
        if self._placeholder_activo:
            self.entrada.delete("1.0", "end")
            self.entrada.config(fg=T0)
            self._placeholder_activo = False

    def _poner_placeholder(self, e=None):
        if not self.entrada.get("1.0", "end").strip():
            self.entrada.insert("1.0", "Ask Zelic…")
            self.entrada.config(fg=T3)
            self._placeholder_activo = True

    def _ajustar_altura(self, e=None):
        lineas = int(self.entrada.index("end-1c").split(".")[0])
        self.entrada.config(height=min(max(lineas, 1), 5))

    def _adjuntar_archivo(self):
        ruta = filedialog.askopenfilename(
            filetypes=[("Documentos", "*.pdf *.txt *.md"), ("Todos", "*.*")])
        if ruta:
            self.archivo_adjunto = ruta
            nombre = ruta.replace("\\", "/").split("/")[-1]
            self._agregar_mensaje("sistema", f"📎 Adjunto: {nombre}")

    def _on_enter(self, event):
        if not event.state & 0x1:
            self._enviar()
            return "break"

    # ══════════════════════════════════════════════════════════════════════════
    #  VOICE HANDLERS  (lógica original preservada)
    # ══════════════════════════════════════════════════════════════════════════

    def _on_texto_voz(self, datos: tuple):
        if not isinstance(datos, tuple) or len(datos) != 2:
            return
        rol, texto = datos
        if self._en_chat:
            self.root.after(0, lambda: self._agregar_mensaje(rol, texto))
        if not self.sesion_id or not texto:
            return
        role_db = "user" if rol == "usuario" else "model"
        db.guardar_mensaje(self.sesion_id, role_db, texto)
        self._transcripciones_voz.append((role_db, texto))
        if rol == "usuario":
            self.total_msgs += 1
            if self.total_msgs == 1:
                threading.Thread(target=self._generar_nombre_chat,
                                 args=(texto,), daemon=True).start()
            self.root.after(0, self._cargar_historial_sidebar)

    def _ventana_voz_cerrada(self):
        if self.memoria and self._transcripciones_voz:
            for role_db, texto in self._transcripciones_voz:
                self.memoria.memoria.append(
                    {"role": role_db, "text": texto})
                if len(self.memoria.memoria) > self.memoria.max_mensajes:
                    self.memoria._comprimir()
        if self._transcripciones_voz:
            self.memoria._detectar_datos_usuario_con_msgs(
                [{"role": r, "text": t}
                 for r, t in self._transcripciones_voz[-4:]])
        self._transcripciones_voz = []

    # ══════════════════════════════════════════════════════════════════════════
    #  SESSION MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def _nueva_conversacion(self):
        if self.sesion_id:
            if self.total_msgs == 0:
                db.eliminar_sesion(self.sesion_id)
            else:
                db.cerrar_sesion(self.sesion_id, self.total_msgs)

        self.sesion_id      = db.nueva_sesion()
        self.total_msgs     = 0
        self._ultimo_modulo = ""

        self.memoria = MemoriaSimple(
            client=self.client,
            sesion_id=self.sesion_id,
            perfil=self.perfil,
            model="gemini-2.5-flash",
            max_mensajes=8,
            num_a_resumir=4,
        )

        self._mostrar_chat()
        self._cargar_sidebar_data()

    def _cargar_sesion(self, sid: int):
        if self._cargando_sesion:
            return
        self._cargando_sesion = True
        self.root.after(300, lambda: setattr(self, '_cargando_sesion', False))

        if self.sesion_id and self.sesion_id != sid:
            if self.total_msgs == 0:
                db.eliminar_sesion(self.sesion_id)
            else:
                db.cerrar_sesion(self.sesion_id, self.total_msgs)

        self.sesion_id  = sid
        self.total_msgs = 999

        self.memoria = MemoriaSimple(
            client=self.client,
            sesion_id=self.sesion_id,
            perfil=self.perfil,
            model="gemini-2.5-flash",
            max_mensajes=8,
            num_a_resumir=4,
        )

        self._mostrar_chat()

        msgs = db.obtener_mensajes_sesion(sid)
        if not msgs:
            self._agregar_mensaje("sistema", "Conversación sin mensajes.")
        else:
            self._agregar_mensaje("sistema", f"── {msgs[0][2][:10]} ──")
            for role, texto, _ in msgs:
                self._agregar_mensaje(
                    "usuario" if role == "user" else "zelic", texto)

        self._cargar_historial_sidebar()

    def _cargar_sidebar_data(self):
        self._cargar_historial_sidebar()
        self._cargar_tareas_rp()

    def _cargar_historial_sidebar(self):
        for w in self.frame_historial.winfo_children():
            w.destroy()

        sesiones = db.obtener_sesiones()
        if not sesiones:
            tk.Label(self.frame_historial,
                     text="Sin conversaciones", bg=BG1, fg=T3,
                     font=F_MONO8, padx=14).pack(anchor="w", pady=6)
            return

        for sid, inicio, total, nombre in sesiones[:15]:
            es_actual = sid == self.sesion_id
            try:
                fecha = inicio[5:10]; hora = inicio[11:16]
            except Exception:
                fecha = hora = ""
            display  = nombre if nombre else f"{fecha} {hora}"
            bg_item  = BG2 if es_actual else BG1

            frame = tk.Frame(self.frame_historial, bg=bg_item, cursor="hand2")
            frame.pack(fill="x", ipady=4)

            if es_actual:
                tk.Frame(frame, bg=BLUE_A, width=2).pack(
                    side="left", fill="y")

            lbl = tk.Label(frame, text=display[:26], bg=bg_item,
                           fg=T1 if es_actual else T2,
                           font=F_MONO8, anchor="w", padx=8)
            lbl.pack(side="left", fill="x", expand=True)

            btn_del = tk.Button(
                frame, text="✕", bg=bg_item, fg=T3,
                font=("Segoe UI", 8), bd=0, cursor="hand2", padx=6,
                activebackground=bg_item, activeforeground="#ff6666",
                command=lambda s=sid: self._eliminar_chat(s))
            btn_del.pack(side="right")

            lbl.bind("<Double-Button-1>",
                     lambda e, s=sid, n=display, l=lbl:
                     self._editar_nombre_chat(s, n, l))
            for w in (frame, lbl):
                w.bind("<Button-1>",
                       lambda e, s=sid: self._cargar_sesion(s))

            def _enter(e, f=frame, b=btn_del, bg=bg_item):
                f.configure(bg=BG2)
                for c in f.winfo_children():
                    if c != b: c.configure(bg=BG2)
                b.configure(bg=BG2, activebackground=BG2, fg="#ff6666")

            def _leave(e, f=frame, b=btn_del, bg=bg_item):
                f.configure(bg=bg)
                for c in f.winfo_children():
                    if c != b: c.configure(bg=bg)
                b.configure(bg=bg, activebackground=bg, fg=T3)

            for w in (frame, lbl):
                w.bind("<Enter>", _enter)
                w.bind("<Leave>", _leave)

    def _generar_nombre_chat(self, primer_mensaje: str):
        from google.genai import types as gtypes
        prompt = (
            f"Genera un nombre MUY corto (máximo 4 palabras) para una "
            f"conversación que empieza con: \"{primer_mensaje}\"\n"
            f"Responde SOLO con el nombre, sin comillas ni puntuación."
        )
        try:
            resp = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[gtypes.Content(
                    role="user",
                    parts=[gtypes.Part(text=prompt)])])
            nombre = resp.text.strip()[:40]
            db.actualizar_nombre_sesion(self.sesion_id, nombre)
            self.root.after(0, self._cargar_historial_sidebar)
        except Exception as e:
            print(f"[Nombre] {e}")

    def _editar_nombre_chat(self, sid, nombre_actual, label_widget):
        entry = tk.Entry(label_widget.master, bg=BG2, fg=T0,
                         font=F_MONO8, bd=0, insertbackground=T0)
        entry.insert(0, nombre_actual)
        entry.pack(fill="x", padx=4)
        entry.focus_set()
        entry.select_range(0, "end")

        def guardar(e=None):
            nuevo = entry.get().strip()[:40]
            if nuevo:
                db.actualizar_nombre_sesion(sid, nuevo)
            entry.destroy()
            self._cargar_historial_sidebar()

        entry.bind("<Return>",   guardar)
        entry.bind("<Escape>",   lambda e: entry.destroy())
        entry.bind("<FocusOut>", guardar)

    def _eliminar_chat(self, sid):
        confirm = tk.Toplevel(self.root)
        confirm.title("Eliminar")
        confirm.geometry("320x148")
        confirm.configure(bg=BG1)
        confirm.attributes("-topmost", True)
        confirm.resizable(False, False)

        tk.Label(confirm, text="¿Eliminar esta conversación?",
                 bg=BG1, fg=T0, font=F_BOLD).pack(pady=(20, 6))
        tk.Label(confirm, text="Esta acción no se puede deshacer.",
                 bg=BG1, fg=T3, font=F_SM).pack(pady=(0, 16))

        btns = tk.Frame(confirm, bg=BG1)
        btns.pack()

        def confirmar():
            db.eliminar_sesion(sid)
            confirm.destroy()
            if sid == self.sesion_id:
                self.sesion_id  = None
                self.total_msgs = 0
                self._nueva_conversacion()
            self._cargar_historial_sidebar()

        tk.Button(btns, text="Cancelar", bg=BG2, fg=T2,
                  font=F_SM, bd=0, padx=16, pady=6, cursor="hand2",
                  command=confirm.destroy).pack(side="left", padx=4)
        tk.Button(btns, text="Eliminar", bg="#4a0a0a", fg="#ff8080",
                  font=F_SM, bd=0, padx=16, pady=6, cursor="hand2",
                  activebackground="#6b0000",
                  command=confirmar).pack(side="left", padx=4)

    # ══════════════════════════════════════════════════════════════════════════
    #  ANIMATIONS
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _blend(hex_color: str, alpha: float) -> str:
        alpha = max(0.0, min(1.0, alpha))
        r1 = int(hex_color[1:3], 16)
        g1 = int(hex_color[3:5], 16)
        b1 = int(hex_color[5:7], 16)
        r  = int(8  + (r1 - 8)  * alpha)
        g  = int(17 + (g1 - 17) * alpha)
        b  = int(31 + (b1 - 31) * alpha)
        return f"#{r:02x}{g:02x}{b:02x}"

    # ── zmark pulse ──
    def _zmark_anim(self):
        try:
            self._zmark_phase += 0.045
            alpha = 0.55 + 0.45 * math.sin(self._zmark_phase)
            color = self._blend(BLUE_A, alpha)
            self._zmark_canvas.itemconfig("zd_inner", fill=color)
        except Exception:
            pass
        self.root.after(55, self._zmark_anim)

    # ── System dot pulse ──
    def _animate_sdot(self):
        try:
            self._sdot_phase += 0.04
            alpha = 0.4 + 0.6 * math.sin(self._sdot_phase)
            color = self._blend(CYAN, alpha)
            self._sdot_canvas.itemconfig("sdot", fill=color)
        except Exception:
            pass
        self.root.after(80, self._animate_sdot)

    # ── Right panel orb ──
    def _animate_rp_orb(self):
        try:
            self._rp_orb_phase += 0.03
            alpha_a = 0.4 + 0.6 * math.sin(self._rp_orb_phase)
            alpha_b = 0.25 + 0.35 * math.sin(self._rp_orb_phase + 0.7)
            self._rp_orb.itemconfig(
                "mo_a", outline=self._blend(BLUE_A, alpha_a))
            self._rp_orb.itemconfig(
                "mo_b", outline=self._blend(BD_BLUE, alpha_b))
        except Exception:
            pass
        self.root.after(60, self._animate_rp_orb)

    # ── Neural bars ──
    def _animate_neural_bars(self, step):
        try:
            for i, b in enumerate(self._neural_bars_w):
                if i >= 4:
                    break
                alpha = 0.28 + 0.72 * abs(math.sin(step * 0.18 + i * 0.7))
                color = self._blend(BLUE_A, alpha)
                b.config(bg=color)
        except Exception:
            pass
        self.root.after(280, lambda: self._animate_neural_bars(step + 1))

    # ── Center orb ──
    def _draw_orb_static(self, canvas, cx, cy):
        for r, col in [
            (42, "#0d1a30"), (34, "#101e36"),
            (26, "#162540"), (18, BD_BLUE_LT)
        ]:
            canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                               outline=col, fill="", width=1,
                               tags=f"rng{r}")
        canvas.create_rectangle(cx-7, cy-7, cx+7, cy+7,
                                outline=BLUE_A, fill="#0a1830",
                                width=1, tags="orb_bead")

    def _animate_orb(self):
        if not self._en_chat or not hasattr(self, '_orb_canvas'):
            return
        try:
            self._orb_frame += 1
            t   = self._orb_frame * 0.033
            ang = self._orb_frame * 1.8

            cx, cy = 42, 42
            for r in (42, 34, 26, 18):
                pulse = math.sin(t + r * 0.08) * 1.4
                nr    = r + pulse
                self._orb_canvas.coords(
                    f"rng{r}",
                    cx-nr, cy-nr, cx+nr, cy+nr)

            self._orb_canvas.delete("arcs")
            for start in (ang, ang + 180):
                self._orb_canvas.create_arc(
                    cx-34, cy-34, cx+34, cy+34,
                    start=start, extent=80,
                    outline="#1a3058", style="arc",
                    width=1, tags="arcs")

            br = 0.55 + 0.45 * math.sin(t * 2.2)
            self._orb_canvas.itemconfig(
                "orb_bead", outline=self._blend(BLUE_A, br))
        except Exception:
            pass
        self.root.after(48, self._animate_orb)

    # ── Voice float ──
    def _animate_voice_float(self):
        if not self._vf_anim_running:
            return
        try:
            self._vf_orb_frame += 1
            t = self._vf_orb_frame * 0.05

            # Bead pulse
            br = 0.55 + 0.45 * math.sin(t * 2.8)
            self._vf_orb_canvas.itemconfig(
                "vf_bead", outline=self._blend(LIVE_CYAN, br))

            # Ring pulse
            for tag, base in (("vfr_a", 1), ("vfr_b", 7), ("vfr_c", 13)):
                alpha = 0.25 + 0.35 * math.sin(t + base * 0.3)
                # just opacity shift via color
                self._vf_orb_canvas.itemconfig(tag)  # no-op, rings are static

            # Wave bars
            for i, bar in enumerate(self._vf_bars):
                if random.random() < 0.025:
                    amp = 22 if self._vf_voice_estado != "idle" else 9
                    self._vf_bars_targets[i] = random.uniform(3, amp)
                cur  = self._vf_bars_current[i]
                tgt  = self._vf_bars_targets[i]
                spd  = self._vf_bars_speeds[i]
                new_h = cur + (tgt - cur) * spd
                self._vf_bars_current[i] = new_h
                bar.config(height=max(2, int(new_h)))

        except Exception:
            pass
        self.root.after(40, self._animate_voice_float)

    # ── Clock ──
    def _tick_clock(self):
        from datetime import datetime
        try:
            self.lbl_clock.config(
                text=datetime.now().strftime("%H:%M"))
        except Exception:
            pass
        self.root.after(9000, self._tick_clock)

    # ── Real system metrics ──
    def _update_metrics(self):
        if _PSUTIL:
            try:
                self.rp_cpu.config(
                    text=f"{psutil.cpu_percent():.0f}%")
                self.rp_ram.config(
                    text=f"{psutil.virtual_memory().used/1e9:.1f} gb")
            except Exception:
                pass
        self.root.after(4500, self._update_metrics)

    # ══════════════════════════════════════════════════════════════════════════
    #  REMINDERS MONITOR
    # ══════════════════════════════════════════════════════════════════════════

    def _iniciar_monitor_recordatorios(self):
        self._revisar_recordatorios()

    def _revisar_recordatorios(self):
        from datetime import datetime
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
        for rid, titulo, fh in tareas.listar_recordatorios(
                solo_pendientes=True):
            if fh <= ahora:
                tareas.completar_recordatorio(rid)
                self._notificar_recordatorio(titulo)
        self.root.after(30000, self._revisar_recordatorios)

    def _notificar_recordatorio(self, titulo: str):
        if self._en_chat:
            self._agregar_mensaje(
                "zelic", f"⏰ Recordatorio: {titulo}")
        alerta = tk.Toplevel(self.root)
        alerta.title("⏰ Recordatorio — Zelic")
        alerta.geometry("360x164")
        alerta.configure(bg=BG1)
        alerta.attributes("-topmost", True)
        alerta.resizable(False, False)
        tk.Label(alerta, text="⏰  Recordatorio", bg=BG1, fg=CYAN,
                 font=("Segoe UI", 13, "bold")).pack(pady=(20, 8))
        tk.Label(alerta, text=titulo, bg=BG1, fg=T0,
                 font=F_UI, wraplength=300).pack(pady=(0, 16))
        tk.Button(alerta, text="Entendido", bg=BLUE, fg="white",
                  font=("Segoe UI", 9, "bold"), bd=0, padx=20, pady=6,
                  cursor="hand2", activebackground=BLUE_A,
                  command=alerta.destroy).pack()

    # ══════════════════════════════════════════════════════════════════════════
    #  CLOSE
    # ══════════════════════════════════════════════════════════════════════════

    def _cerrar(self):
        if self._voz_modulo:
            try:
                self._voz_modulo.detener()
            except Exception:
                pass
        if self.sesion_id:
            if self.total_msgs == 0:
                db.eliminar_sesion(self.sesion_id)
            else:
                db.cerrar_sesion(self.sesion_id, self.total_msgs)
        self.root.destroy()


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    app  = ZelicApp(root)
    root.mainloop()