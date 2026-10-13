# Spec: interfaz web

Estado: decisiones aprobadas por el economista el 12/10/2026 (tecnología,
estructura y paleta); construida el 12/10/2026 y retirada la de Streamlit.
Verificado: navegación sin recarga (View Transitions), respuesta con el modelo
real, carga de SECOLINSA en dos pasos, escritorio y celular (390 px), 274 tests.
Falta la prueba del economista (criterio 1).

Cambio del 13/10/2026 (pedido del economista): el chat es uno solo para toda
la interfaz, en una burbuja flotante, y conversa (ver `docs/decisiones.md`);
cada módulo pasa a ser un tablero con gráficas, tablas y hallazgos calculados
solo con Python. Hechos el chat y los tableros de Balance y Macro. Ese mismo día:
la sesión empieza sin empresa y los balances se suben en la portada, donde
cada archivo se lee al momento (reemplaza el diálogo de dos pasos).

## Objetivo

Que el gerente de una pyme haga preguntas sobre su empresa en una interfaz
visual e ilustrada, al estilo de la referencia que eligió el economista
(ilustraciones planas grandes, bloques de color y formas orgánicas, títulos
grandes), sin el parpadeo de Streamlit: al cambiar de módulo o recibir una
respuesta, solo cambia la parte nueva, con una transición suave.

## Decisiones

- **FastAPI + plantillas Jinja + HTMX**, sin React (decisión previa del
  proyecto). FastAPI ya estaba en la arquitectura (`app/main.py`). HTMX
  reemplaza fragmentos de la página; la navegación entre módulos usa View
  Transitions (fundido corto, desactivado con `prefers-reduced-motion`).
- **Portada con módulos ilustrados**: Balance financiero y Entorno macro
  activos; Evaluación de proyectos y Econometría como "próximamente". Cada
  módulo tiene su ilustración, su color y su tablero.
- **Chat global en una burbuja flotante** (`<details>` fuera de `#pagina`):
  la navegación no lo reemplaza, una conversación por sesión con memoria de
  los últimos 3 turnos; las preguntas de ejemplo de cada módulo lo abren. En
  el celular ocupa toda la pantalla. Al cambiar de empresa se vacía con el
  evento `empresa-cambiada`.
- **Paleta menta y coral** sobre fondo gris azulado frío (no crema, para no
  caer en el lugar común crema + coral + serif).
- **Sesiones en memoria** (MVP de un solo proceso): cookie con un token
  aleatorio; la empresa cargada y las conversaciones viven en el servidor.
  La sesión empieza sin empresa: el hotel de demostración queda solo para el
  set de evaluación y `app/demo.py`.
- **Cifras rastreables** (de la interfaz anterior): cada cifra calculada de la
  respuesta muestra su indicador y fórmula al pasar el cursor o enfocarla.
  El texto del modelo se escapa antes de marcarlo; un convertidor mínimo de
  Markdown (párrafos, listas, negrita) arma el HTML.
- **Carga de balances en vivo** en la tarjeta "Su empresa" de la portada:
  razón social, CIIU, unidad y archivos en un solo formulario; cualquier
  cambio se envía (con 500 ms de espera) y cada archivo vuelve leído, con su
  fecha de corte (propuesta a partir del nombre), activo, pasivo y patrimonio,
  o el error de ese archivo. Los archivos se suman de a uno, se ordenan por
  fecha y se pueden quitar; la porción de largo plazo va en un desplegable
  por archivo. Mismas validaciones que antes.

## Diseño

Color (tokens en `frontend/static/estilo.css`):

| Token | Hex | Uso |
|---|---|---|
| fondo | `#E6EEF1` | página |
| lámina | `#FFFFFF` | tarjetas y conversación |
| menta | `#3CC6A6` | Balance, formas, resaltado de cifras |
| menta clara | `#CDEFE4` | fondos de ilustración, resaltador |
| coral | `#F2726B` | Entorno macro, formas; nunca texto pequeño |
| salmón | `#F8CEC6` | Proyectos, formas suaves |
| petróleo | `#1F4E5F` | títulos, botones, Econometría |
| tinta | `#22333A` | texto |

Tipografía: Outfit (800) para títulos, geométrica y gruesa como en la
referencia; Manrope para el texto y las cifras (números tabulares).

Composición:

```
Portada                                   Módulo
┌ Economista IA ─────── Empresa ▾ ●┐      ┌ Economista IA ───── Empresa ▾ ●┐
│ Su economista    [ilustración:   │      │ [ilustración] │ conversación     │
│ de cabecera       hotel, Andes,  │      │ Balance       │                  │
│ (empresa actual)  monedas]       │      │ financiero    │                  │
│ ┌──────────┐ ┌──────────┐        │      │ preguntas de  │                  │
│ │ Balance  │ │ Entorno  │        │      │ ejemplo       │ [pregunta    ]   │
│ ├──────────┤ ├──────────┤        │      └───────────────┴──────────────────┘
│ │Proyectos │ │Econometr.│        │
└──────────────────────────────────┘
```

Principios: la ilustración es la protagonista y lo demás es sobrio; las
formas de color se salen del borde de las láminas, como en la referencia;
sin sombras ni etiquetas en mayúsculas; el coral nunca es color de texto
pequeño (contraste); foco visible y diseño que funciona en el celular.

## Estructura

```
app/main.py                    aplicación FastAPI (estáticos, rutas)
frontend/web.py                rutas HTML y fragmentos HTMX, sesiones
frontend/modulos.py            módulos: nombre, color, ilustración, ejemplos
frontend/cifras.py             cifras rastreables, renglones, Markdown mínimo
frontend/templates/*.html      plantillas Jinja
frontend/static/               estilo.css, htmx.min.js (2.0.4), ilustraciones/*.svg
tests/frontend/                tests con TestClient y un LLM falso
```

Rutas: `GET /` portada; `GET /modulo/{clave}`; `POST /preguntar` (devuelve
la pregunta y un marcador que pide la respuesta); `GET /respuesta/{id}`
(corre el orquestador con la conversación previa; puede tardar un minuto);
`GET /chat` (la conversación, para refrescarla); `POST /empresa` (cualquier
cambio de la tarjeta), `POST /empresa/quitar/{i}`, `POST /empresa/borrar`;
`GET /empresa`, `POST /empresa/demo`, `POST /empresa/archivos`,
`POST /empresa/cargar`; `GET /estado-modelo`.

## Comandos

```
python -m pytest -v
python -m uvicorn app.main:app --port 8000      # http://localhost:8000
.\iniciar.ps1                                   # LM Studio + modelo + interfaz
```

## Tests

- Portada y módulos responden; módulo desconocido → 404; "próximamente" no
  tiene conversación.
- Preguntar devuelve la pregunta escapada y el marcador; la respuesta (LLM
  falso) trae las cifras marcadas, los avisos y los supuestos.
- El HTML del modelo nunca se inserta; el Markdown mínimo arma párrafos,
  listas y negritas.
- Empresa: sin empresa al empezar; cada archivo se lee al subirlo (totales,
  orden por fecha, error por archivo sin bloquear los demás, unidad en miles,
  porción de largo plazo, quitar, empezar de nuevo); sin empresa el chat
  conversa pero no calcula.

## Límites

- Siempre: escapar el texto del modelo; contraste AA en texto; respetar
  `prefers-reduced-motion`.
- Preguntar antes: guardar sesiones o archivos en disco; agregar más
  dependencias de interfaz.
- Nunca: insertar HTML generado por el modelo; dependencias de CDN en tiempo
  de ejecución para el JavaScript (HTMX va dentro del proyecto).

## Criterios de éxito

1. El economista navega entre la portada y los módulos sin parpadeo y hace
   preguntas con el modelo real.
2. La carga de balances funciona con los CSV de prueba (SECOLINSA) y con el
   hotel de demostración.
3. Se ve bien en escritorio y en un celular (390 px).
4. Suite completa en verde.
