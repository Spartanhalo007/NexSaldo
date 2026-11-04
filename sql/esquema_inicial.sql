-- Esquema inicial de NexSaldo (Incrementos 1 y 4).
-- Crea las tablas categoria, movimiento_financiero, cuenta, transferencia
-- y color_reciente si no existen.
-- Los importes usan NUMERIC: los cálculos en Python se harán con Decimal,
-- nunca con float.

CREATE TABLE IF NOT EXISTS categoria (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(50) NOT NULL UNIQUE,
    fecha_creacion  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS movimiento_financiero (
    id              SERIAL PRIMARY KEY,
    tipo_movimiento VARCHAR(10) NOT NULL
                    CHECK (tipo_movimiento IN ('INGRESO', 'GASTO')),
    fecha           DATE NOT NULL,
    valor           NUMERIC(14,2) NOT NULL CHECK (valor > 0),
    moneda          CHAR(3) NOT NULL CHECK (moneda IN ('COP', 'USD')),
    categoria_id    INTEGER NOT NULL REFERENCES categoria(id),
    descripcion     VARCHAR(200),
    fecha_registro  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_movimiento_fecha
    ON movimiento_financiero (fecha);

-- Catálogo inicial de categorías (datos de arranque, no datos personales).
-- En incrementos posteriores el usuario podrá crear, modificar y eliminar
-- categorías desde la aplicación.
INSERT INTO categoria (nombre) VALUES
    ('Alimentación'),
    ('Vivienda'),
    ('Transporte'),
    ('Servicios'),
    ('Salud'),
    ('Entretenimiento'),
    ('Educación'),
    ('Salario'),
    ('Otros ingresos'),
    ('Otros gastos')
ON CONFLICT (nombre) DO NOTHING;

-- Cuentas personales (Incremento 4: módulo Cuentas).
-- simbolo guarda la clave del catálogo de íconos (app/gui/recursos/iconos).
-- color guarda el color elegido por el usuario en formato #RRGGBB.
CREATE TABLE IF NOT EXISTS cuenta (
    id               SERIAL PRIMARY KEY,
    nombre           VARCHAR(60) NOT NULL,
    moneda           CHAR(3) NOT NULL CHECK (moneda IN ('COP', 'USD')),
    saldo_inicial    NUMERIC(14,2) NOT NULL DEFAULT 0
                     CHECK (saldo_inicial >= 0),
    simbolo          VARCHAR(40) NOT NULL,
    color            CHAR(7) NOT NULL,
    incluye_en_total BOOLEAN NOT NULL DEFAULT TRUE,
    nota             VARCHAR(200),
    fecha_creacion   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Transferencias entre cuentas: la plata que se mueve de una cuenta a otra.
-- Solo entre cuentas de la misma moneda (no hay regla de conversión aprobada).
-- imagen guarda la ruta del adjunto opcional (carpeta adjuntos/, no versionada).
CREATE TABLE IF NOT EXISTS transferencia (
    id                SERIAL PRIMARY KEY,
    cuenta_origen_id  INTEGER NOT NULL REFERENCES cuenta(id),
    cuenta_destino_id INTEGER NOT NULL REFERENCES cuenta(id),
    valor             NUMERIC(14,2) NOT NULL CHECK (valor > 0),
    moneda            CHAR(3) NOT NULL CHECK (moneda IN ('COP', 'USD')),
    fecha             DATE NOT NULL,
    comentarios       VARCHAR(200),
    imagen            VARCHAR(300),
    fecha_registro    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT origen_distinto_de_destino
        CHECK (cuenta_origen_id <> cuenta_destino_id)
);

CREATE INDEX IF NOT EXISTS idx_transferencia_fecha
    ON transferencia (fecha);

-- Últimos colores usados en cuentas (para ofrecerlos de nuevo).
CREATE TABLE IF NOT EXISTS color_reciente (
    valor      CHAR(7) PRIMARY KEY,
    fecha_uso  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
