# NexSaldo

Prototipo de aplicación de escritorio para el registro de finanzas personales
(ingresos, gastos, activos) y el seguimiento de inversiones en ETFs y acciones
con datos de cierre de Yahoo Finance. Proyecto de tesis, Universidad Manuela
Beltrán. Desarrollo individual, uso local.

## Estado actual: Incremento 1 (2026-11-01)

Implementado en este incremento:

- Estructura del proyecto con separación de responsabilidades (RNF-08):
  configuración, acceso a datos y scripts de comprobación.
- Configuración de conexión a PostgreSQL mediante variables de entorno
  (`.env`), sin contraseñas en el código.
- Esquema inicial de la base de datos: tablas `categoria` y
  `movimiento_financiero` (preparación de CU-01 / RF-01).
- Script de verificación manual de conexión y esquema.

Pendiente (no incluido en este incremento):

- Lógica de registro, validaciones y gestión completa de movimientos (CU-01).
- Interfaz gráfica (tkinter).
- Creación, modificación y eliminación de categorías desde la aplicación.
- Activos personales, inversiones, vista consolidada, reportes y patrimonio neto.

## Requisitos

- Windows con Python 3.11 y PostgreSQL instalados (cuentan como instalados
  en el equipo de desarrollo).
- Las dependencias se instalan en un entorno virtual (sección siguiente).

## Instalación (PowerShell, en la raíz del proyecto)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

Edite `.env` y reemplace `CAMBIAR_ESTA_CONTRASENA` por la contraseña del rol
`nexsaldo_app`. No suba ese archivo al repositorio.

## Preparación de la base de datos (una sola vez)

1. Abra `sql\preparar_base_datos.sql` y reemplace
   `CAMBIAR_ESTA_CONTRASENA` por la contraseña que usará la aplicación.
2. Ejecute con la cuenta de administrador de PostgreSQL:

```powershell
psql -U postgres -f sql\preparar_base_datos.sql
```

Esto crea el rol `nexsaldo_app` (sin privilegios de superusuario) y la base de
datos `nexsaldo` de su propiedad.

### Configuración de PostgreSQL que usted debe aplicar (fuera del código)

- En `postgresql.conf`: `listen_addresses = 'localhost'` para que PostgreSQL
  solo acepte conexiones del mismo equipo (RNF-03).
- En `pg_hba.conf`: conexiones locales con autenticación por contraseña
  (`scram-sha-256`), sin entradas `trust`.
- Reinicie el servicio de PostgreSQL después de cambiar estos archivos.

## Verificación del Incremento 1

```powershell
.venv\Scripts\python scripts\verificar_conexion.py
```

Resultado esperado: mensajes `[OK]` de conexión, de aplicación del esquema y la
lista de categorías iniciales. Si algo falla, el script muestra `[ERROR]` con
la causa y no presenta la operación como exitosa.

## Decisiones registradas

- **Moneda**: cada movimiento guarda su moneda (COP o USD). La aplicación no
  suma importes de monedas distintas mientras no se apruebe una regla de
  conversión.
- **Categorías**: catálogo inicial precargado; su edición desde la aplicación
  se implementará en un incremento posterior.
- **Tecnologías**: Python 3.11, tkinter, PostgreSQL local, yfinance (datos de
  cierre). Sin FastAPI, servicios en la nube ni base de datos distinta.
