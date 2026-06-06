import socket

IP_RELOJ = "192.168.0.3"
PUERTO_RELOJ = 20142

# comandos

START = bytes.fromhex("3c1e")
STOP = bytes.fromhex("3c80")
RESET = bytes.fromhex("3c1b")



sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(2)

def enviar(comando, nombre):
    try:
        sock.sendto(comando, (IP_RELOJ, PUERTO_RELOJ))

        try:
            data, addr = sock.recvfrom(1024)
            print(f"{nombre} -> Respuesta: {data.hex()}")
        except socket.timeout:
            print(f"{nombre} -> Sin respuesta")

    except Exception as e:
        print("Error:", e)

print("\n=== CONTROL DE CRONOMETRAJE ===")
print("1 = START")
print("2 = STOP")
print("3 = RESET")
print("0 = SALIR")

while True:
    opcion = input("\nComando: ")

    if opcion == "1":
        enviar(START, "START")

    elif opcion == "2":
        enviar(STOP, "STOP")

    elif opcion == "3":
        enviar(RESET, "RESET")

    elif opcion == "0":
        break

    else:
        print("Opción inválida")