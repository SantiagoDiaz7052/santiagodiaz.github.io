## CUENTA VUELTAS

HOLA, se inicia un nuevo proyecto de cronodeportivo, ya como fotocelda fue un exito se desea implementar un cuenta vueltas que funcione de la misma manera que la fotocelda (inalambrico y uso en obs para transmisiones).

se haran unas bitacoras de la construccion de este proyecto:

# 12 - 06 -2026

Estaba editando un video publicitario del club, ya me hiba a dormir, y cuando me distraje con esto, un turnero con un control. lo destape y vi que el "JEFE" que controla el funcionamiento del turnero es el Control, que es una placa "PIC16F877", y esta proyecta en un tablero led, tiene un cable ethernet que esta conectada al tablero, yo dije: "sera que se le puede hacer ingieneria inversa". GRAVE ERROR, empezo a echar humo el "PIC16F877" en el jack de carga, la causa fue que el "PIC16F877" tambien alimenta el tablero led, entonces hubo una sobrecarga de energia.

Aparte la idea que tengo es...:

Si vieron el portafolio tengo un proyecto titulado "CARRITO ARDUINO" (puedes echarle un vistazo para entender mejor), bueno ese carrito utilizaba una placa esp8266 wifi, entonces quiero integrarlo en el "PIC16F877" para que tambien reflecte lo del tablero en la red, y poderla manejar y mostrar con el mismo programa de "FOTOCELDA" (te recomiendo echarle un vistazo ;) ). bueno entonces voy a seguir investigando para mirar como empiezo a crear todo esto

la placa utiliza RS485, que segun tengo entendido es una forma segura de transmitir datos, ahora se supone que se debe obtener mediante el esp8266 del "carrito arudino" los datos del "PIC16F877"