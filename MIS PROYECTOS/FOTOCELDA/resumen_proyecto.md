# Sistema de Cronometraje Deportivo en Tiempo Real
**Proyecto personal — Patinaje de VELOCDIAD**

## Descripción
Desarrollo de un sistema completo de cronometraje deportivo para eventos de patinaje de velocidad, integrando hardware de fotocelda física con una interfaz web moderna y transmisión en vivo por OBS.

## Problema a resolver
El sistema de cronometraje existente (software propietario "Competition Time") era obsoleto, inestable y no permitía integración con producción de video. Se necesitaba una solución moderna que:
- Controlara la fotocelda por red
- Mostrara el tiempo en vivo en transmisiones por OBS
- Detectara automáticamente el corte del rayo infrarrojo
- Funcionara desde múltiples dispositivos en red local

## Lo que se hizo

### 1. Ingeniería inversa del protocolo UDP
Se capturó el tráfico de red del software original con **Wireshark**, analizando los paquetes en JSON para descifrar el protocolo propietario de la fotocelda:

| Comando | Bytes | Función |
|---------|-------|---------|
| START   | `3c1e` | Iniciar cronómetro |
| STOP    | `3c80` | Detener cronómetro |
| RESET   | `3c1b` | Reiniciar cronómetro |
| POLL    | `3c9b` | Solicitar tiempo actual |

**Formato de respuesta:** `e5` (header) + 4 bytes ASCII → ej. `0744` = 7.44 segundos. Cada byte llega en un paquete UDP individual desde el puerto 20142, y la fotocelda solo responde a comandos enviados desde el puerto **20147** (dato crítico descubierto por ingeniería inversa).

### 2. Bridge Python (WebSocket → UDP)
Servidor Python con `asyncio` y `websockets` que actúa como puente entre la interfaz web y la fotocelda:
- Recibe comandos desde el navegador vía WebSocket
- Los reenvía como bytes UDP al hardware
- Realiza **polling cada 150ms** al dispositivo con `3c9b`
- Detecta congelamiento del tiempo (2 respuestas iguales consecutivas) → dispara **AUTO-STOP automático**
- Transmite el estado del cronómetro a todos los clientes conectados (broadcast)
- Levanta servidor HTTP integrado para servir los archivos HTML

### 3. Panel de control web
Interfaz HTML/CSS/JS accesible desde cualquier dispositivo en la red local:
- Botones START / STOP / RESET con atajos de teclado
- Cronómetro local sincronizado con los comandos
- Log de eventos en tiempo real
- Conexión WebSocket con reconexión automática
- Auto-detección de IP del servidor

### 4. Overlay para OBS
Página HTML transparente diseñada para usarse como **Browser Source** en OBS Studio:
- Muestra el tiempo en formato `SS.cc` (segundos y centésimas)
- Se conecta al bridge por WebSocket y recibe actualizaciones en tiempo real
- Animaciones de estado: verde (corriendo), rojo (detenido), gris (listo)
- Marco con esquinas decorativas y branding del evento
- Se actualiza automáticamente al detectar el AUTO-STOP de la fotocelda
- Funciona desde una PC diferente a la de control

## Stack técnico
- **Python 3.12** — asyncio, websockets, socket UDP, threading, http.server
- **HTML / CSS / JS** — vanilla, sin frameworks
- **Fuentes** — Share Tech Mono + Rajdhani (Google Fonts)
- **Herramientas de análisis** — Wireshark, análisis de capturas JSON
- **Transmisión** — OBS Studio con Browser Source

## Arquitectura final
```
Fotocelda (UDP 192.168.0.3:20142)
        ↕ UDP
PC Control
├── iniciar.py (Bridge Python)
│   ├── WebSocket Server :8765
│   ├── HTTP Server :3000
│   └── Polling UDP cada 150ms
├── control.html → operador
└── overlay.html → OBS (PC transmisión)
        ↕ WebSocket
PC Transmisión
└── OBS Studio → Browser Source → overlay.html
```

## Resultado
Sistema funcional en producción, capaz de detectar el corte del rayo infrarrojo en menos de **300ms** y actualizar el overlay de transmisión automáticamente con el tiempo exacto de la fotocelda.

#######################################################################################################################################

LO QUE APRENDI: 

Ingeniería inversa con Wireshark.
Redes UDP.
Python asíncrono.
WebSockets.
Desarrollo web.
Integración con hardware.
OBS Studio.
Uso en un entorno real.