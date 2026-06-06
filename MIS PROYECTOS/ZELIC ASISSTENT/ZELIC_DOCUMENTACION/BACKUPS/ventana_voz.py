"""
ventana_voz.py — Ventana Jarvis de voz para Zelic
Círculo animado azul. Se activa con Ctrl+Alt+Z.
Usa STT → Backend → TTS (robusto y totalmente integrado).
"""

import tkinter as tk
import math
import time
import threading
import io
import base64
import mss
from PIL import Image
from core.voz import ModuloVoz

BG           = "#050a12"
AZUL_CORE    = "#00aaff"
AZUL_GLOW    = "#0066cc"
AZUL_DIM     = "#001a33"
TEXT_COLOR   = "#a0d4ff"
TEXT_DIM     = "#2a5a8a"

W, H         = 420, 460
CX, CY       = W // 2, 190
R_CORE       = 60
R_INNER_RING = 82
MAX_ONDAS    = 5
ONDA_MAX_R   = 175


class VentanaVoz:
    def __init__(self, client=None, callback_procesar=None, callback_texto=None, on_cerrar=None, callback_memoria=None):
        self.client            = client
        self.callback_procesar = callback_procesar
        self.callback_memoria  = callback_memoria   ### para pasar a memoria
        self.on_cerrar         = on_cerrar
        self.estado            = "idle"
        self._corriendo        = True
        self._frame            = 0
        self._ondas            = []
        self._voz              = None
        self._tiempo_inicio    = None

        self._build()
        self._animar()
        # Iniciar STT automáticamente
        self.root.after(800, self._iniciar_voz)

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build(self):
        self.root = tk.Toplevel()
        self.root.title("Zelic — Voz")
        self.root.geometry(f"{W}x{H}")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self.canvas = tk.Canvas(self.root, width=W, height=H,
                                bg=BG, highlightthickness=0)
        self.canvas.pack()

        self.id_nombre = self.canvas.create_text(
            CX, CY + R_CORE + 44, text="Zelic",
            fill=TEXT_COLOR, font=("Courier New", 15, "bold")
        )
        self.id_estado = self.canvas.create_text(
            CX, CY + R_CORE + 66, text="Iniciando...",
            fill=TEXT_DIM, font=("Courier New", 9)
        )
        self.id_timer = self.canvas.create_text(
            CX, CY + R_CORE + 88, text="",
            fill=TEXT_DIM, font=("Courier New", 9)
        )

        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.place(x=CX - 110, y=H - 70, width=220)

        tk.Button(
            btn_frame, text="📷 Ver pantalla",
            bg="#003d7a", fg=AZUL_CORE,
            font=("Courier New", 10, "bold"),
            bd=0, cursor="hand2", pady=8,
            activebackground="#005099",
            command=self._capturar_pantalla
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        tk.Button(
            btn_frame, text="■ Cerrar",
            bg="#1a0000", fg="#ff6666",
            font=("Courier New", 10, "bold"),
            bd=0, cursor="hand2", pady=8,
            activebackground="#330000",
            command=self._cerrar
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

        self.root.protocol("WM_DELETE_WINDOW", self._cerrar)

    # ── Control de voz ─────────────────────────────────────────────────────────

    def _iniciar_voz(self):
        self._tiempo_inicio = time.time()
        self.set_estado("escuchando", "Escuchando...")

        self._voz = ModuloVoz(
            client=self.client,
            callback_texto=self._on_texto,
            callback_estado=self._on_estado,
            callback_apagar=self._cerrar,
            callback_memoria=self.callback_memoria,
        )
        self._voz.iniciar()

    def _on_texto(self, datos: tuple):
        """Recibe (rol, texto) de Gemini Live y lo pasa al chat."""
        if self.callback_texto:
            self.callback_texto(datos)

    def _on_procesar(self, texto: str) -> str:
        """No usado en modo Live — Gemini maneja todo."""
        return ""

    def _on_estado(self, estado: str):
        if not self._corriendo:
            return
        textos = {
            "escuchando": "Escuchando...",
            "procesando": "Procesando...",
            "hablando":   "Hablando...",
            "idle":       "En espera",
        }
        try:
            self.root.after(0, lambda: self.set_estado(estado, textos.get(estado, "")))
        except Exception:
            pass

    def _capturar_pantalla(self):
        """Oculta ventana, toma captura y la describe por voz."""
        def _hacer():
            self.root.after(0, self.root.withdraw)
            time.sleep(0.6)
            try:
                with mss.mss() as sct:
                    monitor = sct.monitors[1]
                    captura = sct.grab(monitor)
                    img = Image.frombytes("RGB", captura.size, captura.bgra, "raw", "BGRX")
                    img = img.resize((1280, 720), Image.LANCZOS)
                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=65)
                    img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

                # Pasar al backend con contexto de imagen
                if self.callback_procesar:
                    respuesta = self.callback_procesar(
                        f"__CAPTURA__:{img_b64}"
                    )
                    if respuesta and self.callback_texto:
                        self.callback_texto(("zelic", f"👁 {respuesta}"))
                    from core import voz_tts
                    voz_tts.hablar(respuesta or "")
            except Exception as e:
                print(f"[VentanaVoz] Error captura: {e}")
            finally:
                self.root.after(300, self.root.deiconify)

        threading.Thread(target=_hacer, daemon=True).start()

    # ── Estado visual ──────────────────────────────────────────────────────────

    def set_estado(self, estado: str, subtexto: str = ""):
        self.estado = estado
        if subtexto and self._corriendo:
            try:
                self.canvas.itemconfig(self.id_estado, text=subtexto)
            except Exception:
                pass

    # ── Animación ──────────────────────────────────────────────────────────────

    def _animar(self):
        if not self._corriendo:
            return

        self._frame += 1
        self.canvas.delete("anim")
        t = self._frame * 0.05

        paso = 30
        for x in range(0, W, paso):
            for y in range(0, int(H * 0.85), paso):
                dist = math.sqrt((x - CX) ** 2 + (y - CY) ** 2)
                if dist < ONDA_MAX_R + 20:
                    alpha = max(0, 0.12 - dist / (ONDA_MAX_R * 9))
                    if alpha > 0.02:
                        c = self._mezclar(AZUL_CORE, alpha)
                        self.canvas.create_oval(x-1, y-1, x+1, y+1,
                                                fill=c, outline="", tags="anim")

        intervalos = {"escuchando": 0.6, "hablando": 0.25, "procesando": 0.4, "idle": 1.5}
        cada = intervalos.get(self.estado, 1.5)
        if self._frame % max(1, int(cada / 0.033)) == 0:
            if len(self._ondas) < MAX_ONDAS:
                self._ondas.append({"radio": R_INNER_RING, "alpha": 1.0})

        vivas = []
        for o in self._ondas:
            vel = 1.8 if self.estado == "hablando" else 1.2
            o["radio"] += vel
            o["alpha"] -= 1 / (ONDA_MAX_R / vel)
            if o["alpha"] > 0:
                c = self._mezclar(AZUL_CORE, o["alpha"] * 0.45)
                r = o["radio"]
                self.canvas.create_oval(CX-r, CY-r, CX+r, CY+r,
                                        outline=c, width=1, tags="anim")
                vivas.append(o)
        self._ondas = vivas

        vel_anillo = 0.025 if self.estado != "idle" else 0.008
        for i in range(12):
            ang = math.degrees(t * vel_anillo * math.pi * 2) + i * 30
            rad = math.radians(ang)
            px = CX + R_INNER_RING * math.cos(rad)
            py = CY + R_INNER_RING * math.sin(rad)
            br = 0.3 + 0.7 * ((math.sin(ang * 0.1 + t) + 1) / 2)
            c = self._mezclar(AZUL_CORE, br)
            self.canvas.create_oval(px-3, py-3, px+3, py+3,
                                    fill=c, outline="", tags="anim")

        for i, (ini, ext) in enumerate([(0, 80), (100, 65), (185, 70), (275, 70)]):
            off = t * 2 * (1 if i % 2 == 0 else -1)
            self.canvas.create_arc(
                CX-138, CY-138, CX+138, CY+138,
                start=ini+off, extent=ext,
                outline=AZUL_DIM, width=1, style="arc", tags="anim"
            )

        if self.estado == "hablando":
            pulso = math.sin(t * 6) * 10 + math.sin(t * 3.7) * 5
        elif self.estado == "escuchando":
            pulso = math.sin(t * 3) * 5
        elif self.estado == "procesando":
            pulso = math.sin(t * 8) * 8
        else:
            pulso = math.sin(t * 1.2) * 2

        r = R_CORE + pulso

        for g in range(4, 0, -1):
            rg = r + g * 5
            c = self._mezclar(AZUL_GLOW, 0.05 * g)
            self.canvas.create_oval(CX-rg, CY-rg, CX+rg, CY+rg,
                                    fill=c, outline="", tags="anim")

        self.canvas.create_oval(CX-r, CY-r, CX+r, CY+r,
                                fill=AZUL_DIM, outline=AZUL_CORE,
                                width=2, tags="anim")

        br_z = 0.6 + 0.4 * math.sin(t * 2)
        self.canvas.create_text(CX, CY, text="Z",
                                fill=self._mezclar(AZUL_CORE, br_z),
                                font=("Courier New", 28, "bold"), tags="anim")

        if self._tiempo_inicio:
            elapsed = int(time.time() - self._tiempo_inicio)
            mm, ss = divmod(elapsed, 60)
            self.canvas.itemconfig(self.id_timer, text=f"{mm:02d}:{ss:02d}")

        if self._corriendo:
            self.root.after(33, self._animar)

    @staticmethod
    def _mezclar(hex_color: str, alpha: float) -> str:
        alpha = max(0.0, min(1.0, alpha))
        r1 = int(hex_color[1:3], 16)
        g1 = int(hex_color[3:5], 16)
        b1 = int(hex_color[5:7], 16)
        r = int(5 + (r1 - 5) * alpha)
        g = int(10 + (g1 - 10) * alpha)
        b = int(18 + (b1 - 18) * alpha)
        return f"#{r:02x}{g:02x}{b:02x}"

    # ── Cerrar ─────────────────────────────────────────────────────────────────

    def _cerrar(self):
        self._corriendo = False
        if self._voz:
            self._voz.detener()
            self._voz = None
        if self.on_cerrar:
            self.on_cerrar()
        self.root.destroy()

    def cerrar(self):
        self._cerrar()