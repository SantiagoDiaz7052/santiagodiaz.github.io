boy, la secretaria de whassap que da ascesoria informacion y todo el trabajo pesado de una secreteraia de forma automatica

## Como surgio el proyecto...

Mis padres tienen un clunb deportivo, y mi madrastra es la que se encarga de la secretaria y papeleo del club. ¿que pasaba?, muchas veces le toca estar todo el dia respondiendo mensajes y whastapp bussnes no es lo suficientemente eficaz.

Ahi la idea de "BOY", una secretaria virtual que se encargara de la acesoria, informacion, inscripcion, eventos deportivos, tienda deportiva online, etc..., la idea principal fue la automatizacion

## el inicio

El proyecto se inicio a mediados del mes de abril, se inicio montando un server pero nada mas, ahi me enfoque mas en zelic, pero es hora de retomar el proyecto y hacer algo profesional

a finales del mes de mayo "BOY" era capaz de responder preguntas basicas, y en la 1ra semana de abril ya tenia una personalidad base y contexto suficiente para dar informacion y ascesoria. y ademas de tener una base de datos en la nube con SUPABASE donde se guarda toda la inforacion del club y chats de las personas

## bitacora

## 11-06-2026

hoy se desea implementar la funcion de pagos en linea mediante un comprobante de pago de nequi/bancolombia, y que la secretaria solo tenga que validar si realmete llego el pago

Boy analiza las imagenes correctamente

ahora vamos a subir el codigo a RENDER mediante github para no depender del pc

## 12-06-2026

despues del dia de ayer de haber estado trabajando todo el dia en subir el codigo a render, crear un repositorio aparte de subir sin querer el .env del proyecto y que la clave api fuera bloqueada, creee una nueva y hoy el 12-06-2026, ten ia un error que el bot no respondia, ni la IA podia acertar con el error, despues me di cuentra que faltanban las apis de twillo, por eso no respondia.

actualmente despues de +10 horas de trabajo Boy acepta comprobantes de pago y LO MAS imoportante vive en la nuve con render

La satisfaccion que se siente es idescriptible, el hecho de hacer un proyecto importante y que todo este transcurriendo tan bien me da esa motivacion para seguir adelante, para que los errores y los bugs sean solo un aprendizaje mas...

#########################################

- que la memoria tenga mas valor que la base de datos en el prompt

hay un nuevo problema:
el dinero llega a 2 cuentas diferentes, entonces esas 2 personas tendriar que estar validadndo a cada rato si realmente llego la plata, entonces lo mejor seria:

Flujo
👤 Usuario envía comprobante.

🤖 Boy:

Analiza la imagen.
Extrae:
Nombre.
Valor.
Fecha.
Hora.
Entidad bancaria.
Número de referencia (si existe).

Busca anomalías:
Texto borroso o alterado.
Inconsistencias en formatos.
Recortes extraños.
Datos faltantes.
Comprobante reutilizado.

Si la confianza es alta:
Registra el pago.
Responde al usuario.
Lo almacena en la base de datos.

:Base de datos


Algo parecido a:

{
  "mensualidades": {
    "Girardot": {
      "Iniciacion": [
        {
          "nombre": "Juan Perez",
          "valor": 80000,
          "fecha": "2026-06-12",
          "medio": "Nequi",
          "estado": "registrado"
        }
      ]
    }
  }
}

O mejor aun, una tabla:

Nombre	     #  Ciudad	   #Grupo    	#Concepto	    #Valor	    #Fecha
Juan Pérez 	 #  Girardot   #Intermedio	#Mensualidad	#$80.000	#12/06/2026
María López	 #  Melgar	   #Avanzado	#Evento     	#$50.000	#12/06/2026

Eso luego permite generar reportes facilmente.

basicamente se confia en la imagen con un porcentaj, y la IA analiza exaustvamente y determina si el pago esta bien o mal. si esta mal se pide que envie el comprobante nuevamente y si esta bien se agregue a la base de datos.

si alguien llegase a editar la imagen de manera casi perfecta y quedara registrado los encargado del la contabilidad del club se darian cuenta y determinarian qeu persona fue consultando la base de datos o chat. este escenario es muuuuy poco probable pero no imposible, por eso quiero hacer un sistema fuerte pero simple paro no tener que obtener la clave api de cada uno de los bancos y cada uno de los registros de pago en cada cuenta. la idea de boy es REDUCIR el trabajo pesado de la secretaria a un 95% y el 5% sea manual.

## 25 - 06 - 2026

despues de pensar bastante la arquitectura de BOY, se decidio utiliza una llave bre-b bancolombia, con eso todo llega a la cuenta deseada independientemente si la plata viene de otra plataforma como nequi o daviplata.

tambien se decidio confiar en la imagen de comprobante de pago. ya que para acceder a los movimientos en bancolombia o pedir dinero al usuario requerian pasarelas como whompi.

ahora estoy organizando la base de datos para que quede todo full organizado y evitar dolores de cabeza a futuro

El bot ahora puede responder:

"¿Cuánto debo?" → consultar_estado_pago
"¿Qué he pagado?" → consultar_estado_pago
"¿Estoy al día?" → consultar_estado_pago

Resumen de arquitectura
Capa	Responsabilidad	Dependencias
Router	Recibe HTTP, delega	Solo application
Application	Coordina flujo	domain, repositories, adapters
Domain	Lógica de negocio	Nada (puro)
Repositories	Persistencia	services/supabase_client
Adapters	Infraestructura externa	Solo SDKs externos

Fase 1: Conceptos, Config, Obligaciones	✅
Fase 2: ProcesoPago + Flujo conversacional	✅
Fase 3: Refactor Gemini + Adaptadores	✅
Fase 4: Automatización + Recordatorios	✅

el dia que quiera cambiar por ejemplo a postgresql o gemini por open ai, no tocare el dominio

Antes BOY pensaba:
mensualidad

Ahora piensa:
obligación

Eso hace que el sistema pueda cobrar prácticamente cualquier cosa.

ProcesoPago - contexto con comprobante

NO hardcodes

## tests de produccion

☐ Inscribir deportista 

☐ Consultar deportista

☐ Crear obligación

☐ Consultar obligaciones

☐ Iniciar pago

☐ Enviar comprobante válido

☐ Enviar comprobante inválido

☐ Enviar comprobante repetido

☐ Error 503 Gemini

☐ Error 429 Gemini

☐ Dos pagos simultáneos

☐ Pago de obligación inexistente

☐ Usuario sin obligaciones

## 26 - 06 -2026

ok me toco refinar otra vez la aquitectura:

                PAPÁ HABLA CON BOY
                        │
                        ▼
            ¿Ya tienes matrícula?
                  │         │
                 Sí         No
                 │          │
                 │      Proceso de matrícula
                 │          │
                 │      Paga matrícula
                 │          │
                 │    Verificación comprobante
                 │          │
                 │
        Deportista creado
        estado = INACTIVO
        nivel = definido
                 │
                 ▼
        Debe activar el mes
                 │
        Paga mensualidad
                 │
        Verificación
                 │
        estado = ACTIVO

se tienen en cuenta los posibles errores humanos como el de los padres al hacer el pago, tambien se maneja la memoria para que BOY recuerde cosas puntuales, ademas en el flujo se explica como funciona lo da la activacion de la mensualidad, y aparte se desactiva al finalizar el mes y tienen un plazo de 10 dias para reactivarla o si no se le cobrara una mora de 10.000 cop. las conversaciones con todos los papas son por id's, y los padres pueden inscribir a sus 2 hijos sin comnflictos

Esta parte es mas personal, es increible lo lejos que he llegado y lo que me falta por recorrer, me acuerdo de hace un año haciendo una calculadora en python y ahora tengo un sistema con IA de consultas e inscripciones de deportistastas mediante una base de datos, aparte veo mis otros proyectos como ZELIC o CRONODEPORTIVO, y digo: guau, he avanzado mucho, pero aun estan los miedos de que pasara si no funciona o si soy capaz de hacerlo. pero me he demostrado que soy capaz de hacer todo...