-- Esquema del almacén (SPEC-almacen-datos.md). Idempotente: crea solo lo que no
-- existe, así que correrlo otra vez no cambia nada. Lo aplica:
--     python -m data_sources.almacen
-- Montos en pesos corrientes, como los da el PMS.

CREATE TABLE IF NOT EXISTS empresa (
    nit           TEXT PRIMARY KEY
                  CONSTRAINT nit_valido CHECK (nit ~ '^[0-9]{6,10}$'),   -- sin dígito de verificación
    razon_social  TEXT NOT NULL,
    ciiu          TEXT,
    municipio     TEXT,
    creada_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Una fila por cada archivo cargado: qué entró y qué cambió
CREATE TABLE IF NOT EXISTS carga (
    id                  BIGSERIAL PRIMARY KEY,
    nit                 TEXT NOT NULL REFERENCES empresa,
    archivo             TEXT NOT NULL,
    cargada_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    desde               DATE NOT NULL,
    hasta               DATE NOT NULL,
    filas_nuevas        INTEGER NOT NULL,
    filas_actualizadas  INTEGER NOT NULL,
    filas_iguales       INTEGER NOT NULL
);

-- Grano diario: semanas y meses se calculan al leer, no se guardan
CREATE TABLE IF NOT EXISTS pms_diario (
    nit                       TEXT NOT NULL REFERENCES empresa,
    fecha                     DATE NOT NULL,
    habitaciones_disponibles  INTEGER NOT NULL
                              CONSTRAINT disponibles_positivas CHECK (habitaciones_disponibles > 0),
    habitaciones_vendidas     INTEGER NOT NULL
                              CONSTRAINT vendidas_no_negativas CHECK (habitaciones_vendidas >= 0),
    ingresos_habitaciones     NUMERIC(16, 2) NOT NULL
                              CONSTRAINT ingresos_no_negativos CHECK (ingresos_habitaciones >= 0),
    tarifa_publicada          NUMERIC(14, 2) CONSTRAINT tarifa_positiva CHECK (tarifa_publicada > 0),
    tarifa_competencia        NUMERIC(14, 2)
                              CONSTRAINT tarifa_competencia_positiva CHECK (tarifa_competencia > 0),
    promocion                 BOOLEAN,
    huespedes                 INTEGER CONSTRAINT huespedes_no_negativos CHECK (huespedes >= 0),
    carga_id                  BIGINT NOT NULL REFERENCES carga,
    actualizado_en            TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (nit, fecha),
    CONSTRAINT vendidas_no_superan_disponibles
        CHECK (habitaciones_vendidas <= habitaciones_disponibles)
);
