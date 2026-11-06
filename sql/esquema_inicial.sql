-- Esquema de base de datos local para NexSaldo
-- Incluye tablas originales, Módulo de Gastos, Divisas Mundiales y Cotizaciones en tiempo real (Yahoo Finance)

CREATE TABLE IF NOT EXISTS categoria (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    tipo VARCHAR(10) NOT NULL DEFAULT 'GASTO' CHECK (tipo IN ('INGRESO', 'GASTO')),
    simbolo VARCHAR(50) NOT NULL DEFAULT 'mercado',
    color CHAR(7) NOT NULL DEFAULT '#FBB718',
    es_predeterminada BOOLEAN NOT NULL DEFAULT FALSE,
    gasto_programado BOOLEAN NOT NULL DEFAULT FALSE,
    frecuencia VARCHAR(20) CHECK (frecuencia IN ('DIARIO', 'SEMANAL', 'QUINCENAL', 'MENSUAL', 'ANUAL')),
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE categoria ADD COLUMN IF NOT EXISTS tipo VARCHAR(10) NOT NULL DEFAULT 'GASTO';
ALTER TABLE categoria ADD COLUMN IF NOT EXISTS simbolo VARCHAR(50) NOT NULL DEFAULT 'mercado';
ALTER TABLE categoria ADD COLUMN IF NOT EXISTS color CHAR(7) NOT NULL DEFAULT '#FBB718';
ALTER TABLE categoria ADD COLUMN IF NOT EXISTS es_predeterminada BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE categoria ADD COLUMN IF NOT EXISTS gasto_programado BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE categoria ADD COLUMN IF NOT EXISTS frecuencia VARCHAR(20);

CREATE TABLE IF NOT EXISTS cuenta (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(60) NOT NULL,
    moneda CHAR(3) NOT NULL,
    saldo_inicial NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (saldo_inicial >= 0),
    simbolo VARCHAR(40) NOT NULL,
    color CHAR(7) NOT NULL,
    incluye_en_total BOOLEAN NOT NULL DEFAULT TRUE,
    nota VARCHAR(200),
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS movimiento_financiero (
    id SERIAL PRIMARY KEY,
    tipo_movimiento VARCHAR(10) NOT NULL CHECK (tipo_movimiento IN ('INGRESO', 'GASTO')),
    fecha DATE NOT NULL,
    valor NUMERIC(14,2) NOT NULL CHECK (valor > 0),
    moneda CHAR(3) NOT NULL,
    categoria_id INTEGER NOT NULL REFERENCES categoria(id),
    descripcion VARCHAR(200),
    cuenta_id INTEGER REFERENCES cuenta(id) ON DELETE SET NULL,
    imagen VARCHAR(300),
    es_programado BOOLEAN NOT NULL DEFAULT FALSE,
    frecuencia VARCHAR(20),
    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE movimiento_financiero ADD COLUMN IF NOT EXISTS cuenta_id INTEGER REFERENCES cuenta(id) ON DELETE SET NULL;
ALTER TABLE movimiento_financiero ADD COLUMN IF NOT EXISTS imagen VARCHAR(300);
ALTER TABLE movimiento_financiero ADD COLUMN IF NOT EXISTS es_programado BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE movimiento_financiero ADD COLUMN IF NOT EXISTS frecuencia VARCHAR(20);

CREATE TABLE IF NOT EXISTS etiqueta (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(40) NOT NULL UNIQUE,
    color CHAR(7) NOT NULL DEFAULT '#408FD1',
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS movimiento_etiqueta (
    movimiento_id INTEGER NOT NULL REFERENCES movimiento_financiero(id) ON DELETE CASCADE,
    etiqueta_id INTEGER NOT NULL REFERENCES etiqueta(id) ON DELETE CASCADE,
    PRIMARY KEY (movimiento_id, etiqueta_id)
);

CREATE TABLE IF NOT EXISTS transferencia (
    id SERIAL PRIMARY KEY,
    cuenta_origen_id INTEGER NOT NULL REFERENCES cuenta(id),
    cuenta_destino_id INTEGER NOT NULL REFERENCES cuenta(id),
    valor NUMERIC(14,2) NOT NULL CHECK (valor > 0),
    moneda CHAR(3) NOT NULL,
    fecha DATE NOT NULL,
    comentarios VARCHAR(200),
    imagen VARCHAR(300),
    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT origen_distinto_de_destino CHECK (cuenta_origen_id <> cuenta_destino_id)
);

-- Ampliar restricciones de moneda existentes para permitir todas las divisas ISO 4217 del mundo
ALTER TABLE cuenta DROP CONSTRAINT IF EXISTS cuenta_moneda_check;
ALTER TABLE movimiento_financiero DROP CONSTRAINT IF EXISTS movimiento_financiero_moneda_check;
ALTER TABLE transferencia DROP CONSTRAINT IF EXISTS transferencia_moneda_check;

CREATE TABLE IF NOT EXISTS color_reciente (
    valor CHAR(7) PRIMARY KEY,
    fecha_uso TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Historial de las últimas divisas usadas por el usuario (para mostrar COP + 4 últimas en el selector)
CREATE TABLE IF NOT EXISTS moneda_reciente (
    codigo CHAR(3) PRIMARY KEY,
    fecha_uso TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Tabla para conservar cotizaciones y tasas de cambio en tiempo real de Yahoo Finance
CREATE TABLE IF NOT EXISTS cotizacion (
    id SERIAL PRIMARY KEY,
    simbolo VARCHAR(20) NOT NULL,
    fecha DATE NOT NULL,
    precio NUMERIC(16,4) NOT NULL CHECK (precio > 0),
    moneda CHAR(3) NOT NULL,
    fuente VARCHAR(40) NOT NULL DEFAULT 'Yahoo Finance (Tiempo real)',
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (simbolo, fecha)
);

INSERT INTO categoria (nombre, tipo, simbolo, color, es_predeterminada) VALUES
    ('Salud', 'GASTO', 'corazon_pulso', '#F28C8C', TRUE),
    ('Ocio', 'GASTO', 'billetera', '#408FD1', TRUE),
    ('Casa', 'GASTO', 'casa', '#FBB718', TRUE),
    ('Café', 'GASTO', 'cubiertos', '#D98A4E', TRUE),
    ('Educación', 'GASTO', 'graduacion', '#9B7EDE', TRUE),
    ('Regalos', 'GASTO', 'regalo', '#E86F9A', TRUE),
    ('Alimentación', 'GASTO', 'mercado', '#7DC98F', TRUE),
    ('Transporte', 'GASTO', 'carro', '#56B4E9', FALSE),
    ('Vivienda', 'GASTO', 'casa', '#E69F00', FALSE),
    ('Salario', 'INGRESO', 'cash', '#7DC98F', FALSE)
ON CONFLICT (nombre) DO UPDATE SET
    simbolo = EXCLUDED.simbolo,
    color = EXCLUDED.color,
    es_predeterminada = EXCLUDED.es_predeterminada;
