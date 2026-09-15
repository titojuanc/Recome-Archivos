# Recome-Archivos Constitution# Recome-Archivos Constitution



Este repositorio implementa el **Módulo de Archivos Exportables (Reportes)** de RecoMe,Este repositorio implementa el **Módulo de Archivos Exportables (Reportes)** de RecoMe,

sistema distribuido de recomendaciones de películas y videojuegos. RecoMe se compone desistema distribuido de recomendaciones de películas y videojuegos. RecoMe se compone de

cuatro repositorios independientes (`api-general`, `recomendaciones`, `notificaciones`,cuatro repositorios independientes (`api-general`, `recomendaciones`, `notificaciones`,

`frontend`), cada uno mantenido por un equipo distinto y con límites de responsabilidad`frontend`), cada uno mantenido por un equipo distinto y con límites de responsabilidad

estrictos entre sí. Este documento rige exclusivamente las decisiones internas deestrictos entre sí. Este documento rige exclusivamente las decisiones internas de

`Recome-Archivos` y NUNCA puede contradecir las reglas cross-repo del sistema mayor`Recome-Archivos` y NUNCA puede contradecir las reglas cross-repo del sistema mayor

(cero acceso directo a bases ajenas salvo excepción documentada, `api-general` como(cero acceso directo a bases ajenas salvo excepción documentada, `api-general` como

única puerta de entrada de los frontends, contratos de eventos/REST documentados deúnica puerta de entrada de los frontends, contratos de eventos/REST documentados de

forma centralizada en `api-general`, autenticación servicio-a-servicio vía API keyforma centralizada en `api-general`, autenticación servicio-a-servicio vía API key

interna).interna).



## Alcance del módulo## Alcance del módulo



Este repo tiene **exactamente tres responsabilidades**, y ninguna más:Este repo tiene **exactamente tres responsabilidades**, y ninguna más:



1. Un **worker** (Python + `pika`) que consume el evento `reporte.generar` y publica el1. Un **worker** (Python + `pika`) que consume el evento `reporte.generar` y publica el

   evento `reporte.listo` contra el RabbitMQ del sistema. El broker es infraestructura   evento `reporte.listo` contra el RabbitMQ del sistema. El broker es infraestructura

   compartida propiedad del repo `notificaciones`; este repo es únicamente **cliente**   compartida propiedad del repo `notificaciones`; este repo es únicamente **cliente**

   del broker — no lo despliega, no lo administra, no define su topología base.   del broker — no lo despliega, no lo administra, no define su topología base.

2. Una **base de datos SQL de reportes/anuncios**, con la tabla `anuncio` (impresiones y2. Una **base de datos SQL de reportes/anuncios**, con la tabla `anuncio` (impresiones y

   clicks de anuncios), que el worker consulta para construir los reportes.   clicks de anuncios), que el worker consulta para construir los reportes.

3. Un **webserver de archivos** que expone los reportes Excel generados (persistidos en3. Un **webserver de archivos** que expone los reportes Excel generados (persistidos en

   MinIO), con acceso restringido a los usuarios indicados. Este webserver es controlado   MinIO), con acceso restringido a los usuarios indicados. Este webserver es controlado

   en exclusiva por este repo — ningún otro módulo lo administra ni lo despliega.   en exclusiva por este repo — ningún otro módulo lo administra ni lo despliega.



Flujo funcional de referencia (documentado como contexto, no como principio): un usuarioFlujo funcional de referencia (documentado como contexto, no como principio): un usuario

solicita un reporte a través de `api-general`; `api-general` publica `reporte.generar`;solicita un reporte a través de `api-general`; `api-general` publica `reporte.generar`;

el worker de este módulo lo consume, consulta `anuncio`, genera el Excel, lo persiste enel worker de este módulo lo consume, consulta `anuncio`, genera el Excel, lo persiste en

MinIO y lo expone vía el webserver propio; finalmente el worker publica `reporte.listo`MinIO y lo expone vía el webserver propio; finalmente el worker publica `reporte.listo`

con la URL de acceso, evento que consume `api-general` (nunca el usuario final nicon la URL de acceso, evento que consume `api-general` (nunca el usuario final ni

Notificaciones directamente) para decidir cómo hacérselo llegar.Notificaciones directamente) para decidir cómo hacérselo llegar.



## Core Principles## Core Principles



### I. Responsabilidad Acotada (NON-NEGOTIABLE)### I. Responsabilidad Acotada (NON-NEGOTIABLE)

Este repo es dueño únicamente de: la generación de reportes Excel a partir de la tablaEste repo es dueño únicamente de: la generación de reportes Excel a partir de la tabla

`anuncio`, el almacenamiento en MinIO, y el webserver que expone esos archivos. Está`anuncio`, el almacenamiento en MinIO, y el webserver que expone esos archivos. Está

explícitamente fuera de alcance y NUNCA debe incorporarse a este repo: envío deexplícitamente fuera de alcance y NUNCA debe incorporarse a este repo: envío de

notificaciones push/mail (responsabilidad exclusiva del módulo `notificaciones`), deploynotificaciones push/mail (responsabilidad exclusiva del módulo `notificaciones`), deploy

o administración del broker RabbitMQ, lógica de decisión de qué o cuándo notificar alo administración del broker RabbitMQ, lógica de decisión de qué o cuándo notificar al

usuario, y cualquier lógica de negocio de recomendación, catálogo o autenticación deusuario, y cualquier lógica de negocio de recomendación, catálogo o autenticación de

usuarios. Toda funcionalidad propuesta que no encaje en estas tres responsabilidades seusuarios. Toda funcionalidad propuesta que no encaje en estas tres responsabilidades se

rechaza o se deriva al repo correspondiente.rechaza o se deriva al repo correspondiente.



### II. Aislamiento de Datos, con Única Excepción Documentada (NON-NEGOTIABLE)### II. Aislamiento de Datos, con Única Excepción Documentada (NON-NEGOTIABLE)

El worker no lee ni escribe directamente sobre ninguna base de datos ajena del sistemaEl worker no lee ni escribe directamente sobre ninguna base de datos ajena del sistema

(DB General, DB Logs, DB Recomendaciones, etc.) — eso sigue absolutamente prohibido, sin(DB General, DB Logs, DB Recomendaciones, etc.) — eso sigue absolutamente prohibido, sin

excepción. La **única** excepción admitida es la tabla `anuncio`: su base de datos esexcepción. La **única** excepción admitida es la tabla `anuncio`: su base de datos es

compartida por diseño con `api-general`, que también la controla/accede. Por esto:compartida por diseño con `api-general`, que también la controla/accede. Por esto:

- El schema de `anuncio` no es propiedad unilateral de este repo; cualquier cambio a su- El schema de `anuncio` no es propiedad unilateral de este repo; cualquier cambio a su

  estructura debe coordinarse explícitamente con `api-general` antes de aplicarse, igual  estructura debe coordinarse explícitamente con `api-general` antes de aplicarse, igual

  que un contrato de evento.  que un contrato de evento.

- Esta excepción no habilita, ni por analogía ni por conveniencia, acceso directo a- Esta excepción no habilita, ni por analogía ni por conveniencia, acceso directo a

  ninguna otra base del sistema. Agregar una nueva excepción de este tipo requiere  ninguna otra base del sistema. Agregar una nueva excepción de este tipo requiere

  enmendar esta constitution explícitamente, no una decisión ad-hoc de implementación.  enmendar esta constitution explícitamente, no una decisión ad-hoc de implementación.



### III. Contratos como Fuente Externa de Verdad### III. Contratos como Fuente Externa de Verdad

El schema de los eventos que este repo consume (`reporte.generar`) y publicaEl schema de los eventos que este repo consume (`reporte.generar`) y publica

(`reporte.listo`), el schema de la tabla `anuncio` compartida, y cualquier endpoint REST(`reporte.listo`), el schema de la tabla `anuncio` compartida, y cualquier endpoint REST

que este repo exponga (por ejemplo, estado o descarga de un reporte) viven documentadosque este repo exponga (por ejemplo, estado o descarga de un reporte) viven documentados

en el repo `api-general`, como fuente única de verdad. Ningún cambio a estos contratos seen el repo `api-general`, como fuente única de verdad. Ningún cambio a estos contratos se

implementa en este repo sin antes actualizar esa documentación y coordinar con los reposimplementa en este repo sin antes actualizar esa documentación y coordinar con los repos

consumidores/publicadores afectados. Un cambio a un contrato compartido nunca seconsumidores/publicadores afectados. Un cambio a un contrato compartido nunca se

considera "interno" a este repo.considera "interno" a este repo.



### IV. Validación Estricta de Payloads### IV. Validación Estricta de Payloads

El worker valida cada evento `reporte.generar` recibido contra el schema documentado enEl worker valida cada evento `reporte.generar` recibido contra el schema documentado en

`api-general` antes de procesarlo. Eventos inválidos o incompletos se rechazan o se`api-general` antes de procesarlo. Eventos inválidos o incompletos se rechazan o se

enrutan a dead-letter; el worker nunca "adivina" o completa con valores por defecto unenrutan a dead-letter; el worker nunca "adivina" o completa con valores por defecto un

campo faltante o mal tipado.campo faltante o mal tipado.



### V. Acceso a Archivos Restringido### V. Acceso a Archivos Restringido

El webserver de archivos nunca expone reportes de forma pública o anónima. Todo accesoEl webserver de archivos nunca expone reportes de forma pública o anónima. Todo acceso

se valida contra el usuario indicado para ese reporte, en cada configuración y en cadase valida contra el usuario indicado para ese reporte, en cada configuración y en cada

cambio a esa configuración. Este webserver es controlado en exclusiva por este repo:cambio a esa configuración. Este webserver es controlado en exclusiva por este repo:

ningún otro módulo decide su topología, sus reglas de acceso, ni lo despliega.ningún otro módulo decide su topología, sus reglas de acceso, ni lo despliega.



### VI. El Feedback Va a `api-general`, No al Usuario Final### VI. El Feedback Va a `api-general`, No al Usuario Final

El evento `reporte.listo` se publica exclusivamente hacia `api-general`. Este módulo noEl evento `reporte.listo` se publica exclusivamente hacia `api-general`. Este módulo no

le habla directo al usuario final, no decide cómo notificarlo, y no coordinale habla directo al usuario final, no decide cómo notificarlo, y no coordina

directamente con el módulo de Notificaciones. Es `api-general` quien decide y ejecutadirectamente con el módulo de Notificaciones. Es `api-general` quien decide y ejecuta

cómo hacerle llegar la URL del reporte al usuario.cómo hacerle llegar la URL del reporte al usuario.



### VII. Test-First (NON-NEGOTIABLE)### VII. Test-First (NON-NEGOTIABLE)

TDD para toda la lógica propia: transformación de datos de `anuncio` a Excel, manejo deTDD para toda la lógica propia: transformación de datos de `anuncio` a Excel, manejo de

archivos y publicación/consumo de eventos. Se exigen además contract tests contra losarchivos y publicación/consumo de eventos. Se exigen además contract tests contra los

schemas documentados en `api-general` (eventos y schema de `anuncio`), y pruebas deschemas documentados en `api-general` (eventos y schema de `anuncio`), y pruebas de

integración contra el broker RabbitMQ, contra la base de datos de reportes y contraintegración contra el broker RabbitMQ, contra la base de datos de reportes y contra

MinIO/webserver. Todo esto corre en CI y debe pasar antes de cualquier deploy.MinIO/webserver. Todo esto corre en CI y debe pasar antes de cualquier deploy.



### VIII. Simplicidad### VIII. Simplicidad

Se prefiere siempre la solución más simple que no rompa el aislamiento de datos (másSe prefiere siempre la solución más simple que no rompa el aislamiento de datos (más

allá de la única excepción documentada en el Principio II) ni los contratos compartidos.allá de la única excepción documentada en el Principio II) ni los contratos compartidos.

"Por simplicidad" nunca es justificación válida para agregar una nueva excepción de"Por simplicidad" nunca es justificación válida para agregar una nueva excepción de

acceso a datos, un acceso directo a otro repo, o una responsabilidad fuera del alcanceacceso a datos, un acceso directo a otro repo, o una responsabilidad fuera del alcance

definido, sin antes enmendar esta constitution.definido, sin antes enmendar esta constitution.



## Stack Tecnológico## Stack Tecnológico



- **Worker**: Python + `pika` como cliente de RabbitMQ (consumo de `reporte.generar`,- **Worker**: Python + `pika` como cliente de RabbitMQ (consumo de `reporte.generar`,

  publicación de `reporte.listo`), con lógica de transformación de datos a Excel (p. ej.  publicación de `reporte.listo`), con lógica de transformación de datos a Excel (p. ej.

  `openpyxl` o librería equivalente).  `openpyxl` o librería equivalente).

- **DB de reportes**: motor SQL (a definir), con la tabla `anuncio` (impresiones y- **DB de reportes**: motor SQL (a definir), con la tabla `anuncio` (impresiones y

  clicks), compartida por diseño con `api-general` según la excepción documentada en el  clicks), compartida por diseño con `api-general` según la excepción documentada en el

  Principio II.  Principio II.

- **Storage de archivos generados**: MinIO.- **Storage de archivos generados**: MinIO.

- **Webserver de archivos**: Nginx (u otro equivalente), exponiendo los objetos de MinIO- **Webserver de archivos**: Nginx (u otro equivalente), exponiendo los objetos de MinIO

  con acceso restringido — nunca acceso público anónimo — bajo control exclusivo de este  con acceso restringido — nunca acceso público anónimo — bajo control exclusivo de este

  repo.  repo.



Este stack refleja decisiones ya coordinadas a nivel de sistema; no se reabre ni seEste stack refleja decisiones ya coordinadas a nivel de sistema; no se reabre ni se

reemplaza sin justificación fuerte y coordinación explícita con los otros equipos.reemplaza sin justificación fuerte y coordinación explícita con los otros equipos.



## Comunicación Cross-Repo## Comunicación Cross-Repo



- Este repo es **solo cliente** del RabbitMQ del sistema: consume `reporte.generar` y- Este repo es **solo cliente** del RabbitMQ del sistema: consume `reporte.generar` y

  publica `reporte.listo`, pero no despliega ni administra el broker (esa infraestructura  publica `reporte.listo`, pero no despliega ni administra el broker (esa infraestructura

  pertenece al repo `notificaciones`).  pertenece al repo `notificaciones`).

- No expone endpoints REST a los frontends: no es accesible directamente desde Frontend- No expone endpoints REST a los frontends: no es accesible directamente desde Frontend

  Usuario ni Frontend Vendedor/Admin. Cualquier endpoint que exponga (estado/descarga) es  Usuario ni Frontend Vendedor/Admin. Cualquier endpoint que exponga (estado/descarga) es

  consumido internamente por `api-general`, nunca directamente por un frontend.  consumido internamente por `api-general`, nunca directamente por un frontend.

- Las llamadas de servicio-a-servicio (si las hubiera, p. ej. desde `api-general` hacia un- Las llamadas de servicio-a-servicio (si las hubiera, p. ej. desde `api-general` hacia un

  endpoint interno de este repo) usan la API key interna compartida por entorno, distinta  endpoint interno de este repo) usan la API key interna compartida por entorno, distinta

  de la autenticación de usuarios finales.  de la autenticación de usuarios finales.

- Cualquier cambio a los contratos de `reporte.generar`, `reporte.listo`, al schema de- Cualquier cambio a los contratos de `reporte.generar`, `reporte.listo`, al schema de

  `anuncio`, o a un endpoint REST expuesto por este repo, se coordina primero actualizando  `anuncio`, o a un endpoint REST expuesto por este repo, se coordina primero actualizando

  la documentación en `api-general` y notificando a los repos consumidores/publicadores  la documentación en `api-general` y notificando a los repos consumidores/publicadores

  antes de mergear o deployar.  antes de mergear o deployar.



## Testing y Calidad## Testing y Calidad



- TDD obligatorio para la lógica propia (transformación a Excel, manejo de archivos,- TDD obligatorio para la lógica propia (transformación a Excel, manejo de archivos,

  handlers de eventos): tests escritos antes de la implementación, ciclo  handlers de eventos): tests escritos antes de la implementación, ciclo

  Red-Green-Refactor.  Red-Green-Refactor.

- Contract tests contra los schemas de `reporte.generar`, `reporte.listo` y de la tabla- Contract tests contra los schemas de `reporte.generar`, `reporte.listo` y de la tabla

  `anuncio` documentados en `api-general`, ejecutados en CI antes de cada deploy, para  `anuncio` documentados en `api-general`, ejecutados en CI antes de cada deploy, para

  detectar rupturas de compatibilidad de forma temprana.  detectar rupturas de compatibilidad de forma temprana.

- Pruebas de integración contra el broker RabbitMQ, contra la base de datos de reportes y- Pruebas de integración contra el broker RabbitMQ, contra la base de datos de reportes y

  contra MinIO/webserver, como parte del pipeline de CI.  contra MinIO/webserver, como parte del pipeline de CI.

- Ningún deploy se aprueba si rompe un contrato compartido sin la coordinación- Ningún deploy se aprueba si rompe un contrato compartido sin la coordinación

  correspondiente documentada en `api-general`.  correspondiente documentada en `api-general`.



## Governance## Governance



Esta constitution prevalece sobre cualquier práctica o decisión interna del equipo que laEsta constitution prevalece sobre cualquier práctica o decisión interna del equipo que la

contradiga. Ninguna decisión de implementación puede violar las reglas cross-repo delcontradiga. Ninguna decisión de implementación puede violar las reglas cross-repo del

sistema RecoMe (aislamiento de datos salvo la excepción documentada en el Principio II,sistema RecoMe (aislamiento de datos salvo la excepción documentada en el Principio II,

`api-general` como única puerta de entrada, contratos documentados centralmente) alegando`api-general` como única puerta de entrada, contratos documentados centralmente) alegando

simplicidad, urgencia o conveniencia técnica.simplicidad, urgencia o conveniencia técnica.



Toda enmienda a esta constitution —incluyendo cualquier nueva excepción de acceso aToda enmienda a esta constitution —incluyendo cualquier nueva excepción de acceso a

datos, cualquier ampliación de responsabilidades, o cualquier cambio de stack— debe:datos, cualquier ampliación de responsabilidades, o cualquier cambio de stack— debe:

1. Documentarse explícitamente en este archivo con su justificación.1. Documentarse explícitamente en este archivo con su justificación.

2. Ser coordinada con los equipos de los repos afectados cuando la enmienda impacte un2. Ser coordinada con los equipos de los repos afectados cuando la enmienda impacte un

   contrato compartido (eventos, schema de `anuncio`, endpoints REST).   contrato compartido (eventos, schema de `anuncio`, endpoints REST).

3. Incluir, si corresponde, un plan de migración para el código y los datos existentes.3. Incluir, si corresponde, un plan de migración para el código y los datos existentes.



Todo PR debe verificar cumplimiento de los principios de este documento antes deTodo PR debe verificar cumplimiento de los principios de este documento antes de

mergear, en particular el Principio I (responsabilidad acotada) y el Principio IImergear, en particular el Principio I (responsabilidad acotada) y el Principio II

(aislamiento de datos con única excepción documentada). Cualquier complejidad agregada(aislamiento de datos con única excepción documentada). Cualquier complejidad agregada

debe justificarse explícitamente en la revisión.debe justificarse explícitamente en la revisión.



**Version**: 1.0.0 | **Ratified**: 2026-09-14 | **Last Amended**: 2026-09-14**Version**: 1.0.0 | **Ratified**: 2026-09-14 | **Last Amended**: 2026-09-14

