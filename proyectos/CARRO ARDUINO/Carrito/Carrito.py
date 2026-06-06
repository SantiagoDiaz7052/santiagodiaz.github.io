import socket
import keyboard  # pip install keyboard
import time

# IP del carro (mira en el monitor serial, normalmente 192.168.4.1)
CAR_IP = "192.168.4.1"
PORT = 80

print("Conectando al carro Wi-Fi...")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((CAR_IP, PORT))
print("✅ Conectado al carro")

last_cmd = ""

try:
    while True:
        cmd = ""

        if keyboard.is_pressed("up"):
            cmd = "F"  # Adelante
        elif keyboard.is_pressed("down"):
            cmd = "B"  # Atrás
        elif keyboard.is_pressed("left"):
            cmd = "L"  # Izquierda
        elif keyboard.is_pressed("right"):
            cmd = "R"  # Derecha
        else:
            cmd = "S"  # Parar automáticamente

        # Enviar solo si el comando cambió
        if cmd != last_cmd:
            sock.sendall(cmd.encode())
            last_cmd = cmd

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\n🛑 Programa detenido por el usuario")

finally:
    sock.sendall(b"S")
    sock.close()
    print("🔌 Conexión cerrada correctamente.")