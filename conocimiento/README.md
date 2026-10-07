# Base de conocimiento

Notas que el sistema usa como ÚNICA fuente para responder preguntas de
criterio económico o teoría (tipo 2). Una nota por concepto, corta y
autocontenida: el buscador recupera notas completas.

Encabezado obligatorio:

    ---
    titulo: Nombre del concepto
    temas: [palabras, clave, que, usaría, un, gerente]
    fuente: de dónde sale (libro, entidad, elaboración propia)
    revisado: false   # true cuando el economista la revisó
    ---

Mientras una nota tenga `revisado: false`, las respuestas que la usen lo
advierten. Después de agregar o editar notas, reconstruir el índice (con el
servidor de LM Studio encendido):

    python -m app.rag.ingest
