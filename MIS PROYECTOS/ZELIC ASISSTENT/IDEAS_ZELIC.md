Hola esto es zelic, aqui estara la historia de la creacion de este gran proyecto


## ideas zelic


clima
leer estado de pc
escribir
matematicas

para abrir apps, que se maneje solo y busque la aplicacion desde "buscar
busquedas en la internet 
implementar boton de voz en vivo

prompts repetitivos y varias citas al mismo modelo, repititendo codigo

borrar papelera

que se pueda interrumpir, tolerancia de voz y reanudar lo interrumpido, apagate, que repita mi nombre,

Base de datos para empresas
Zelic maneja todos los pcs desde un pc servidor

elexa

tareas == recordatorios, y que mustre los proximos a cumplirse, ademas una ventana donde esten todos

## controlar pc

### que le digas hola zelic, y te de toda la info necearia, hora, clima, estado del pc, tareas, etc...

## solo para iniciar que mande mensajes por whastapp

### arreglar coherecnia peticion de sistema del usuario


########## SONIDOOOOOOS #

#########################################################################

ERRRORES

3#### falla base de datos...

falla memoria largo plazo en voz en vivo


### borrar saludo

no hay titulos automaticos

implemetar saludo en el inicio solo una vez, tal como otras ias

rediseñar el panel lateral + correcion de memoria  (dbl hp)  

orquestador no -> mejor que zelic tome la mejor decision

## autimatizaciones

## DEJA DE GUARDAR EL NOMBRE DE LA CONVERSACION (CUANDO PASA ESO ES QUE ALGO DE MEMORIA SE DAÑO)(ADEMAS SE MULTIPLICAN LOS MENSAJES)

## se demora en la 1 respuesta de el .voz

## no hay relacion entre chats

## recordar solo cosas importantes


sonidos de generacion, y que hable constantemente


#######################################

logs ERRRORES:

Task was destroyed but it is pending!
task: <Task pending name='Task-29' coro=<BaseApiClient.aclose() running at C:\Users\Santiago Diaz\Desktop\ZELIC\env\Lib\site-packages\google\genai\_api_client.py:2100>>
C:\Users\Santiago Diaz\AppData\Local\Programs\Python\Python312\Lib\asyncio\base_events.py:711: RuntimeWarning: coroutine 'BaseApiClient.aclose' was never awaited
  self._ready.clear()

voz en vivo


##########################################################################################################


ZELIC/
├── interfaz.py          ← punto de entrada principal
├── orquestador.py       ← clasifica intención del mensaje
├── memoria_simple.py    ← memoria con resumen automático
├── ventana_voz.py       ← ventana Jarvis animada (círculo azul)
├── database.py          ← funciones SQLite
├── core/
│   ├── chat.py          ← conversación con Gemini
│   ├── tareas.py        ← tareas y recordatorios
│   ├── clima.py         ← clima con wttr.in
│   ├── sistema.py       ← abrir apps/URLs/explorar archivos
│   ├── sistema_info.py  ← métricas CPU/RAM/GPU
│   ├── documento.py     ← analizar PDFs
│   ├── imagen.py        ← generar imágenes
│   ├── saludo.py        ← saludo personalizado al iniciar
│   ├── vision_pantalla.py ← ver pantalla con Gemini Vision
│   ├── voz.py           ← Gemini Live API (modo voz)
│   ├── voz_stt.py       ← STT con speech_recognition (backup)
│   └── voz_tts.py       ← edge-tts para hablar
├── CONFIG/
│   └── config.py        ← API_KEY desde .env con load_dotenv
└── data/
    ├── zelic.db
    ├── zelic_memoria.json
    └── imagenes/


    ####################################################################################################3

CORRECCIONES = {
        "yoselin": "Zelic", "joselin": "Zelic", "celic": "Zelic",
        "selic": "Zelic", "zelick": "Zelic", "zellic": "Zelic",
        "zélic": "Zelic", "xelic": "Zelic", "jelic": "Zelic",
        "sélick": "Zelic", "selick": "Zelic", "sélic": "Zelic",
        "siri": "Zelic", "felix": "Zelic", "celic": "Zelic"
    }

