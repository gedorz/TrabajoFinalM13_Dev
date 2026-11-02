# Proyecto IA Clasica:

# Objetivo

El objetivo es crear una herramientas usando (Dialogflow ES, expresiones regulares, OCR y servicios de voz) 
construyendo un asistente conversacional por voz que resuelva un caso de uso concreto.

# Descripcion del proyecto

Construir un agente conversacional para la empresa kit robotic, 
que se dedica a la venta de productos para armar drones de bajo coste. 
al que el usuario habla y que responde por voz.
El agente debe resolver un flujo de negocio con varios turnos y, además, ser capaz de responder preguntas
sobre un pequeño conjunto de documentos que habréis procesado previamente con OCR.

## Puesta en marcha

```bash
py -3.11 -m venv .venv
.venv\Scripts\activate          # Windows
python.exe -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# para la aplicacion de voz ejecute 
 python .\cliente_voz.py    
```


## Instalacion de Tesseract.

Son dos cosas: el programa y el paquete de Python.
esta aplicacion se instala desde: 
- https://github.com/UB-Mannheim/tesseract/wiki
- Windows: instalador de UB Mannheim, **marcando el paquete de idioma español** durante la instalación.
- Si el ejecutable no está en el `PATH`, `ocr.py` detecta automáticamente 
    la instalación en `C:\Program Files\Tesseract-OCR\tesseract.exe`. 
    Si está instalado en otra carpeta, ajustad `ejecutable_windows` al principio de `ocr.py`.
- Para usar también `tesseract --version` desde la terminal, 
    añadid `C:\Program Files\Tesseract-OCR` al `PATH` y abrid una terminal nueva. 
    El entorno virtual y `pip install pytesseract` no instalan el programa Tesseract.

Error típico: `Failed loading language 'spa'`. Significa que falta el `spa.traineddata`. Se arregla reinstalando con el idioma marcado, o bajando el fichero a la carpeta `tessdata`.

Probad el OCR solo, antes de meterlo en el webhook:


# Arquitectura de referencia para este proyecto

El siguiente esquema muestra el flujo completo que debe cubrir el prototipo. Las cajas con línea
discontinua son mejoras opcionales.


```mermaid
flowchart TB
    usuario("Usuario (voz)")
    dialogflow("Dialogflow ES<br/>STT y TTS nativos")
    webhook("Webhook FastAPI<br/>regex y lógica de negocio")
    llm("LLM<br/>contexto = texto OCR")

    documentos("Documentos<br/>3-5 ficheros")
    ocr("OCR + regex<br/>proceso offline")

    telegram("Telegram")
    stt("STT / TTS externo")
    vectorial("Base vectorial")

    usuario <--> dialogflow
    dialogflow <--> webhook
    webhook <--> llm

    documentos --> ocr
    ocr --> llm

    dialogflow -.-> telegram
    webhook -.-> stt
    llm -.-> vectorial

    classDef usuario fill:#ffffff,stroke:#555555,color:#333333;
    classDef dialogflow fill:#e5dafa,stroke:#8055e8,color:#6941c6;
    classDef servicio fill:#c5f3f7,stroke:#159da8,color:#237f88;
    classDef documento fill:#ffead0,stroke:#ed7d31,color:#c96a27;
    classDef opcional fill:#ffffff,stroke:#999999,stroke-dasharray:6 4,color:#777777;

    class usuario usuario;
    class dialogflow dialogflow;
    class webhook,llm servicio;
    class documentos,ocr documento;
    class telegram,stt,vectorial opcional;
```

Línea discontinua = extra opcional para subir nota.

# Mapa de intenciones reducido

Mapa de intenciones mínimo esperado, con un único contexto activo.

```mermaid
flowchart LR
    subgraph globales["Intenciones globales"]
        direction TB
        bienvenida("bienvenida")
        solicitar_servicio("solicitar_servicio")
        consulta_documental("consulta_documental")
        fallback("fallback")
    end

    subgraph contexto["Contexto · ctx_solicitud_en_curso"]
        direction LR
        recogida("Recogida de datos<br/>regex obligatorio")
        confirmacion("Confirmación<br/>follow-up sí/no")
        recogida --> confirmacion
    end

    solicitar_servicio --> contexto
    consulta_documental -.->|al webhook RAG| contexto

    classDef intencion fill:#e5dafa,stroke:#8055e8,color:#6941c6;
    classDef paso fill:#c5f3f7,stroke:#159da8,color:#237f88;

    class bienvenida,solicitar_servicio,consulta_documental,fallback intencion;
    class recogida,confirmacion paso;
    style globales fill:none,stroke:none,color:#888888;
    style contexto fill:#ffffff,stroke:#159da8,stroke-width:2px,stroke-dasharray:6 4,color:#237f88;
```


