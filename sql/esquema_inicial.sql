-- Esquema inicial de NexSaldo (Incremento 1).
-- Crea las tablas categoria y movimiento_financiero si no existen.
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
