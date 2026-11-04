# NexSaldo

Prototipo de aplicación de escritorio para el registro de finanzas personales
(ingresos, gastos, activos) y el seguimiento de inversiones en ETFs y acciones
con datos de cierre de Yahoo Finance. Proyecto de tesis, Universidad Manuela
Beltrán. Desarrollo individual, uso local.

## Estado actual: Incremento 4 (2026-11-03)

Implementado hasta ahora:

- Estructura del proyecto con separación de responsabilidades (RNF-08).
- Configuración de conexión a PostgreSQL mediante variables de entorno
  (`.env`), sin contraseñas en el código.
- Esquema de la base de datos: tablas `categoria`,
  `movimiento_financiero`, `cuenta`, `transferencia` y `color_reciente`.
- Interfaz gráfica basada en el mockup de la tesis (customtkinter sobre
  tkinter, tipografía Instrument Sans incluida): barra lateral de
  navegación (Resumen, Cuentas, Gastos, Ingresos, Inversiones, Reportes,
  Categorías, Configuración, Modo Oscuro) y módulos de movimientos,
  resumen y cuentas.
- Gestión de ingresos y gastos (CU-01 parcial): registro con validaciones,
  consulta y eliminación con confirmación.
- Lógica de negocio (`GestorFinanciero`, `MovimientoFinanciero`): importes
  con `Decimal`, valor mayor que cero, tipos INGRESO/GASTO, monedas COP/USD.
- Resumen financiero del mes (preparación de RF-05): dona de gastos por
  categoría, totales por moneda (sin sumar monedas distintas) y desglose
  por categoría.
- Módulo Cuentas: balance total por moneda (con botón de copiar), lista
  de cuentas con íconos re-colorables (Bootstrap Icons / Material Design
  Icons, licencias MIT), creación de cuentas (nombre, saldo inicial,
  divisa COP/USD, símbolo y color obligatorios, colores recientes y rueda
  de selección, opción de excluir del balance total, nota), y transferencias
  entre cuentas de la misma moneda con exigencia de saldo suficiente,
  calculadora incorporada, selector de fecha con calendario, comentarios
  e imagen adjunta opcional (máx. 2 MB). Historial de transferencias con
  filtros día/semana/mes/año/período.
- Pruebas automatizadas (53) de lógica y de integración con PostgreSQL.

Pendiente:

- Modificación y eliminación de cuentas ya creadas.
- Modificación de movimientos ya guardados (resto de CU-01).
- Los demás módulos de la barra lateral (Inversiones, Reportes,
  Categorías, Configuración) se informan como pendientes en la propia
  interfaz; no presentan funciones inexistentes.
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

Ejecute con la cuenta de administrador de PostgreSQL:

```powershell
psql -U postgres -f sql\preparar_base_datos.sql
```

El script le pedirá por consola la contraseña del rol (no hace falta editar
el archivo: la contraseña real nunca queda escrita en él). Esto crea:

- El rol `nexsaldo_app`, sin privilegios de superusuario.
- La base de datos `nexsaldo`, de su propiedad.
- Retiro de los permisos de `PUBLIC` sobre esa base de datos: ninguna otra
  cuenta local puede conectarse a ella.

Use la misma contraseña en el archivo `.env` (`NEXSALDO_DB_CONTRASENA`).

Nota: si ejecuta el script dos veces, verá un error porque el rol ya existe;
es esperable y no necesita repetir el paso.

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

## Ejecutar la aplicación (Incremento 4)

Con el servicio de PostgreSQL iniciado y el archivo `.env` configurado:

```powershell
.venv\Scripts\python -m app.main
```

Requiere instalar la dependencia nueva (Pillow) antes de la primera
ejecución de esta versión:

```powershell
.venv\Scripts\pip install -r requirements.txt
```

Además, la base de datos necesita las tablas nuevas de este incremento
(cuenta, transferencia, color_reciente). Es idempotente: se puede
reejecutar sobre una base existente:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql" -U nexsaldo_app -d nexsaldo -f sql\esquema_inicial.sql
```

Abre la ventana principal: la barra lateral reproduce el mockup (logo,
botones en píldora, colores esmeralda y dorado) y la vista inicial es el
Resumen Financiero del mes (dona de gastos por categoría, totales por
moneda). Los botones Gastos e Ingresos abren el módulo de movimientos
(registro, consulta y eliminación con confirmación). El botón Cuentas
abre el módulo de cuentas: balance total por moneda, lista de cuentas,
crear nueva cuenta y transferencias con su historial. El resto de módulos
muestra un aviso de que están pendientes de implementación.

## Ejecutar las pruebas automatizadas

Las pruebas requieren `requirements-dev.txt` y la base de datos local en
ejecución (usan el `.env` del proyecto; si no existe, las pruebas de
integración se omiten y las de lógica se ejecutan igualmente):

```powershell
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest pruebas
```

Resultado esperado: 53 pruebas superadas. Los datos que insertan las pruebas
son ficticios ("dato ficticio de prueba automatizada") y se eliminan solos.

## Decisiones registradas

- **Moneda**: cada movimiento guarda su moneda (COP o USD). La aplicación no
  suma importes de monedas distintas mientras no se apruebe una regla de
  conversión.
- **Categorías**: catálogo inicial precargado; su edición desde la aplicación
  se implementará en un incremento posterior.
- **Tecnologías**: Python 3.11, tkinter, PostgreSQL local, yfinance (datos de
  cierre). Sin FastAPI, servicios en la nube ni base de datos distinta.
