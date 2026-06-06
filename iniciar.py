"""
iniciar.py — Bridge WebSocket + HTTP + polling fotocelda
"""
import asyncio, json, socket, logging, threading, time
import http.server, websockets

# ── Config ───────────────────────────────────────────
IP_RELOJ     = "192.168.0.3"
PUERTO_RELOJ = 20142
WS_PORT      = 8765
HTTP_PORT    = 3000
POLLING_MS   = 150
FREEZE_COUNT = 2    # 2 respuestas iguales = STOP

COMANDOS = {
    "START": bytes.fromhex("3c1e"),
    "STOP":  bytes.fromhex("3c80"),
    "RESET": bytes.fromhex("3c1b"),
}
CMD_TIEMPO = bytes.fromhex("3c9b")

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()
logging.getLogger("websockets").setLevel(logging.WARNING)

# ── Dos sockets independientes ────────────────────────
# Control: para START/STOP/RESET
udp_ctrl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_ctrl.settimeout(0.5)

# Polling: socket propio que se abre y cierra en cada consulta
# para evitar conflictos con udp_ctrl
def leer_tiempo_udp():
    """
    Abre un socket nuevo por cada consulta desde puerto 20147
    (mismo que usa Competition Time — la fotocelda solo responde a ese puerto).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.08)
    try:
        s.bind(("", 20147))  # puerto fijo que acepta la fotocelda
    except OSError:
        pass  # si ya está ocupado, continuar igual
    try:
        s.sendto(CMD_TIEMPO, (IP_RELOJ, PUERTO_RELOJ))
        buf = []
        deadline = time.time() + 0.25
        while time.time() < deadline:
            try:
                data, _ = s.recvfrom(1024)
                buf.extend(data)
                if len(buf) >= 5:
                    break
            except socket.timeout:
                pass

        log.debug(f"Poll buf={[hex(b) for b in buf]}")

        # Buscar header 0xe5 + 4 bytes ASCII
        for i, b in enumerate(buf):
            if b == 0xe5 and i + 4 <= len(buf) - 1:
                raw = "".join(chr(buf[i+j]) for j in range(1, 5))
                if raw.isdigit():
                    return raw
        # Sin header
        if len(buf) >= 4:
            raw = "".join(chr(b) for b in buf[:4])
            if raw.isdigit():
                return raw
    except Exception as e:
        log.debug(f"Poll error: {e}")
    finally:
        s.close()
    return None

def enviar_udp(cmd):
    payload = COMANDOS.get(cmd)
    if not payload:
        return f"Comando desconocido: {cmd}"
    try:
        udp_ctrl.sendto(payload, (IP_RELOJ, PUERTO_RELOJ))
        log.info(f"UDP → {cmd} [{payload.hex()}]")
        try:
            data, _ = udp_ctrl.recvfrom(1024)
            return f"OK resp={data.hex()}"
        except socket.timeout:
            return "OK sin_respuesta"
    except Exception as e:
        return f"ERROR {e}"

# ── Estado global ─────────────────────────────────────
estado = {
    "fase":     "listo",
    "start_at": 0,
    "elapsed":  0,
}
clientes = set()

async def broadcast(msg):
    if not clientes:
        return
    data = json.dumps(msg)
    await asyncio.gather(*[c.send(data) for c in clientes], return_exceptions=True)

# ── Polling loop ──────────────────────────────────────
async def polling_loop():
    ultimo_raw     = None
    contador_igual = 0

    while True:
        await asyncio.sleep(POLLING_MS / 1000)

        if estado["fase"] != "corriendo":
            ultimo_raw     = None
            contador_igual = 0
            continue

        raw = await asyncio.to_thread(leer_tiempo_udp)
        if raw is None:
            continue

        seg = int(raw[:2])
        dec = int(raw[2:4])
        log.debug(f"Poll: {raw} → {seg}.{dec:02d}s  igual={contador_igual}/{FREEZE_COUNT}")

        if raw == ultimo_raw:
            contador_igual += 1
            if contador_igual >= FREEZE_COUNT:
                ms_fotocelda      = seg * 1000 + dec * 10
                estado["fase"]    = "detenido"
                estado["elapsed"] = ms_fotocelda
                contador_igual    = 0
                ultimo_raw        = None
                log.info(f"AUTO-STOP → {seg}.{dec:02d}s")
                await broadcast({
                    "tipo":    "auto_stop",
                    "elapsed": ms_fotocelda,
                    "display": f"{seg:02d}.{dec:02d}",
                })
        else:
            contador_igual = 0
            ultimo_raw     = raw

# ── WebSocket handler ─────────────────────────────────
async def handler(websocket):
    clientes.add(websocket)
    log.info(f"WS conectado: {websocket.remote_address}  (total: {len(clientes)})")

    await websocket.send(json.dumps({
        "tipo":        "sync",
        "fase":        estado["fase"],
        "elapsed":     estado["elapsed"],
        "start_at":    estado["start_at"],
        "server_time": int(time.time() * 1000),
    }))

    try:
        async for msg in websocket:
            try:
                data = json.loads(msg)
                cmd  = data.get("cmd", "").upper()
                res  = await asyncio.to_thread(enviar_udp, cmd)
                await websocket.send(json.dumps({"tipo": "ack", "cmd": cmd, "res": res}))

                now_ms = int(time.time() * 1000)
                if cmd == "START" and estado["fase"] != "corriendo":
                    estado["fase"]     = "corriendo"
                    estado["start_at"] = now_ms - estado["elapsed"]
                elif cmd == "STOP" and estado["fase"] == "corriendo":
                    estado["elapsed"]  = now_ms - estado["start_at"]
                    estado["fase"]     = "detenido"
                    estado["start_at"] = 0
                elif cmd == "RESET":
                    estado["fase"]     = "listo"
                    estado["elapsed"]  = 0
                    estado["start_at"] = 0

                await broadcast({
                    "tipo":        "cron",
                    "cmd":         cmd,
                    "fase":        estado["fase"],
                    "elapsed":     estado["elapsed"],
                    "start_at":    estado["start_at"],
                    "server_time": now_ms,
                })
            except Exception as e:
                await websocket.send(json.dumps({"tipo": "error", "msg": str(e)}))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clientes.discard(websocket)
        log.info(f"WS desconectado: {websocket.remote_address}  (total: {len(clientes)})")

# ── HTTP ──────────────────────────────────────────────
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def iniciar_http():
    http.server.HTTPServer(("0.0.0.0", HTTP_PORT), QuietHandler).serve_forever()

# ── Main ──────────────────────────────────────────────
async def main():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_local = s.getsockname()[0]
        s.close()
    except:
        ip_local = "TU-IP"

    print()
    print("=" * 54)
    print("  CRONOMETRAJE PATINAJE")
    print("=" * 54)
    print(f"  Reloj UDP   →  {IP_RELOJ}:{PUERTO_RELOJ}")
    print(f"  Panel       →  http://localhost:{HTTP_PORT}/control.html")
    print(f"  Otra PC     →  http://{ip_local}:{HTTP_PORT}/overlay.html")
    print(f"  Polling     →  cada {POLLING_MS}ms  |  freeze={FREEZE_COUNT} muestras")
    print("=" * 54)
    print("  Ctrl+C para detener\n")

    threading.Thread(target=iniciar_http, daemon=True).start()

    async with websockets.serve(handler, "0.0.0.0", WS_PORT):
        await asyncio.gather(
            asyncio.Future(),
            polling_loop(),
        )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDetenido.")