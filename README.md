# 💰 NexSaldo — Sistema Integral de Gestión Financiera Personal y Portafolio de Inversiones

**NexSaldo** ([Spartanhalo007/NexSaldo](https://github.com/Spartanhalo007/NexSaldo)) es una aplicación de escritorio desarrollada en **Python 3.11+**, **CustomTkinter**, **PostgreSQL** y la API financiera de **Yahoo Finance** para la administración integral de finanzas personales, control multimoneda en tiempo real, seguimiento de portafolios de inversión (acciones, ETFs y criptomonedas) y diagnóstico analítico de salud financiera.

## 🚀 Características Principales por Módulo

### 1. 🏠 Resumen Financiero (`VistaResumen`)

* **Balance Neto Consolidado:** Cruza automáticamente todos los **Ingresos** y **Gastos** del período seleccionado, permitiendo visualizar balances positivos y negativos con soporte de eje negativo en la gráfica principal.

* **Selector de Período Inteligente (Estilo Shopify):** Navegación rápida con flechas (`◄` / `►`) y ventana modal con rangos predefinidos (*Hoy, Esta semana, Este mes, Mes pasado, Este trimestre, Este año, Año pasado*) o selección de rango personalizado con calendario interactivo.

* **Filtro Global Multimoneda (`BarraFiltroMoneda`):** Conversión dinámica en tiempo real entre **COP, USD, EUR** y más de 30 divisas mundiales mediante cotizaciones de [Yahoo Finance](https://finance.yahoo.com/), con opción de alternar entre:

  * **Modo Unificado (`Todas convertidas`):** Convierte todos los registros a la moneda seleccionada en pantalla.

  * **Modo Exclusivo (`Solo moneda activa`):** Filtra únicamente los movimientos registrados originalmente en esa divisa.

* **Desglose por Categorías:** Barras de proporción y tarjetas con colores semánticos para identificar rápidamente las categorías de mayor peso en ingresos y gastos.

### 2. 🏦 Cuentas y Transferencias (`VistaCuentas` / `VistaCuentasConDivisa`)

* **Gestión Completa de Cuentas (Crear, Editar y Eliminar):**

  * Soporte para múltiples divisas nativas (`COP`, `USD`, `EUR`, etc.), íconos personalizados (*banco, billetera, efectivo, tarjeta, ahorros, criptomonedas, bolsa, bóveda*), paleta de colores con historial de colores recientes y opción *"Incluir en el balance total"*.

  * **Saldo inicial opcional:** Si el campo de saldo inicial se deja vacío al crear una cuenta, se asume automáticamente como `0.00`.

  * **Edición en sitio (`✏️ Editar`):** Cada tarjeta de cuenta incluye acceso directo al diálogo de edición pre-rellenado con sus datos actuales, ajustando automáticamente el saldo disponible al nuevo valor indicado.

* **Transferencias entre Cuentas con Validación de Fondos:**

  * Registro de transferencias con fecha, comentarios y comprobante fotográfico opcional.

  * **Bloqueo automático por fondos insuficientes:** Impide transferir un monto superior al saldo disponible real de la cuenta de origen.

* **Cuentas Automáticas de Broker:** Integración directa con el módulo de Inversiones para crear o vincular cuentas de plataformas como **eToro, Binance, Interactive Brokers (IBKR), Trii y Hapi**.

### 3. 💸 Gastos (`VistaGastos`) e 📈 Ingresos (`VistaIngresos`)

* **Registro Detallado de Movimientos:**

  * Selector de moneda con conversión en vivo hacia la divisa base antes de guardar.

  * Categorías especializadas (ej. *Alimentación, Casa, Ocio, Salud, Educación, Café, Regalos, Otros gastos* en Gastos; *Salario, Ventas, Intereses, Regalo, Préstamo, Bonificación, Otros ingresos* en Ingresos).

  * Selector de fecha con calendario desplegable, etiquetas de impuestos, notas descriptivas y carga de imágenes/recibos de soporte.

* **Tabla Histórica Filtrable:** Consulta instantánea por período y moneda con totales calculados al pie de página.

### 4. 📊 Inversiones y Portafolio Bursátil (`VistaInversiones`)

* **Buscador de Activos en Tiempo Real (Acciones, ETFs y Criptomonedas):**

  * Búsqueda en vivo conectada a [Yahoo Finance](https://finance.yahoo.com/) para tickers bursátiles (`VOO`, `QQQ`, `AAPL`, `NVDA`, `MSFT`, `LLY`, etc.) y criptoactivos (`BTC-USD`, `SOL-USD`, `ETH-USD`).

* **Compra de Activos con Descuento desde Cuentas (`DialogoAsignarInversion`):**

  * Permite elegir **de qué cuenta descontar el dinero** al registrar una compra (o registrarla manualmente sin descontar de ninguna cuenta).

  * Si la cuenta de origen está en una moneda distinta a la del activo (ej. comprar `VOO` en `USD` descontando desde una cuenta de `Bancolombia` en `COP`), convierte automáticamente el monto al tipo de cambio vigente, verifica que existan fondos suficientes y descuenta el saldo.

* **Venta / Cierre de Posiciones (`💰 Vender` — `DialogoCerrarInversion`):**

  * Cada posición abierta cuenta con el botón **`💰 Vender`** junto al botón de eliminar (`🗑`).

  * Al abrir el diálogo de venta, **pre-carga automáticamente el valor actual de mercado en vivo** y muestra la ganancia o pérdida neta (`+$XX.XX / +YY.YY%`).

  * Crea automáticamente la cuenta del broker (`eToro`, `Binance`, `Trii`, `IBKR`, `Hapi`) con saldo inicial `$0` si aún no existe y la selecciona por defecto como destino de los fondos, permitiendo también elegir cualquier otra cuenta del usuario (con conversión automática de divisa `USD -> COP` si aplica).

  * Acredita el dinero en la cuenta elegida y registra la operación en el **Historial de Posiciones Cerradas (P&L Realizado)**.

* **Gráfica de Montaña de Rendimiento (Estilo eToro):**

  * Curva histórica interactiva del portafolio total o filtrada por activo individual con selectores de horizonte temporal (`1D`, `1S`, `1M`, `3M`, `1A`, `MAX`).

* **Importador Universal de Brokers (CSV / Excel `.xlsx`) con Pre-validación de Duplicados:**

  * Compatible con estados de cuenta de **eToro, Binance, Interactive Brokers, Trii, Hapi** y plantillas estándar de NexSaldo (filtra únicamente posiciones abiertas en reportes de eToro).

  * **Pre-validación instantánea antes de importar:** Clasifica cada fila del archivo como `[NUEVA]` (verde) o `[DUPLICADA — Se omitirá]` (gris) comparando contra la base de datos en tiempo real, y deshabilita el botón de importación cuando hay `0` posiciones nuevas por agregar.

### 5. 🧭 Reportes, Salud Financiera y Centro de Exportación (`VistaReportes`)

Módulo analítico de alto rendimiento (con caché en memoria `O(1)` y precarga asíncrona en segundo plano) que cruza datos de Cuentas, Ingresos, Gastos e Inversiones:

1. **Centro de Exportación de Estados de Cuenta:**

   * **Excel Multi-hoja (`.xlsx`):** Genera un libro con 4 pestañas estilizadas (*Salud y Radiografía*, *Movimientos*, *Comparativa Categorías* y *Posiciones Cerradas*).

   * **Archivo CSV (`.csv`):** Exportación tabular universal codificada en `UTF-8-SIG` para análisis externo.

   * **Estado de Cuenta Imprimible (`.html` / PDF):** Documento ejecutivo listo para abrir en el navegador o imprimir como PDF.

2. **4 Tarjetas KPI de Salud Financiera:**

   * **💰 Tasa de Ahorro (`%`):** Porcentaje de los ingresos del período que el usuario conserva después de cubrir sus gastos:
     

     $$
     \text{Tasa de Ahorro} = \frac{\text{Ingresos} - \text{Gastos}}{\text{Ingresos}} \times 100
     $$

   * **🛡️ Fondo de Emergencia (Meses de Supervivencia):** Calcula cuántos meses podrías mantener tu ritmo de gasto actual utilizando tu **liquidez neta disponible** (saldos de cuentas incluidas en el total ajustados por el déficit de caja del período si los gastos superan a los ingresos):
     

     $$
     \text{Meses de Supervivencia} = \frac{\text{Liquidez Neta Disponible}}{\text{Proyección de Gasto Mensual (30 días)}}
     $$

   * **🔥 Ritmo de Gasto Diario (*Burn Rate*):** Promedio de gasto por día dentro del período seleccionado y su proyección a 30 días.

   * **📈 P&L Total de Inversiones y *Win Rate* (`%`):** Suma de la ganancia/pérdida latente (portafolio abierto) más la ganancia/pérdida realizada (posiciones vendidas), junto con el porcentaje de operaciones ganadoras (*Win Rate*).

3. **Radiografía de Patrimonio y Exposición al Riesgo:**

   * Barra proporcional de **Liquidez en Cuentas vs. Capital Invertido**.

   * Barra de **Exposición Cambiaria** por divisa nativa (`COP`, `USD`, `EUR`, etc.).

   * **Alerta de Concentración Patrimonial:** Detecta automáticamente si una sola cuenta o activo concentra `≥ 50%` del patrimonio total.

4. **Comparativa Mes a Mes (MoM) y Detección de Anomalías:**

   * Compara automáticamente el período actual contra el período inmediatamente anterior de igual duración (ej. *Noviembre vs. Octubre*).

   * Marca con alerta `🚨` cualquier categoría cuyo gasto haya aumentado `≥ 25%` respecto al período previo.

5. **Libro de Posiciones Cerradas (P&L Realizado):**

   * Registro histórico detallado de todas las ventas ejecutadas con `💰 Vender`, mostrando fecha de cierre, activo, monto invertido original, valor final de venta, ganancia/pérdida realizada (`$` y `%`) y cuenta donde se acreditaron los fondos.

## 🏗️ Arquitectura del Proyecto

El proyecto sigue una arquitectura limpia en capas separando modelos de dominio, persistencia, servicios externos, lógica de negocio y presentación gráfica:

```
NexSaldo/
├── app/
│   ├── main.py                         # Punto de entrada de la aplicación
│   ├── configuracion.py                # Carga de variables de entorno (.env) y conexión a BD
│   ├── modelo/                         # Entidades de dominio (Dataclasses inmutables)
│   │   ├── cuenta.py                   # Modelo Cuenta
│   │   ├── movimiento_financiero.py    # Modelo MovimientoFinanciero (INGRESO / GASTO)
│   │   ├── transferencia.py            # Modelo Transferencia entre cuentas
│   │   ├── inversion.py                # Modelos Inversion y ValoracionInversion
│   │   └── cotizacion.py               # Modelo Cotizacion bursátil / cambiaria
│   ├── repositorio/                    # Capa de acceso a datos (PostgreSQL)
│   │   └── repositorio_local.py        # Consultas SQL parametrizadas y gestión transaccional
│   ├── servicio/                       # Servicios externos y motores analíticos
│   │   ├── servicio_bursatil.py        # Cliente Yahoo Finance (precios en vivo, históricos y divisas)
│   │   ├── importador_portafolio.py    # Parser multi-broker CSV / Excel (.xlsx)
│   │   └── analitica_reportes.py       # Motor matemático de Salud Financiera, Radiografía y Exportación
│   ├── gestor/                         # Lógica de negocio y orquestación
│   │   └── gestor_financiero.py        # Validaciones, caché de cotizaciones, cuentas, movimientos y portafolio
│   └── gui/                            # Interfaz gráfica (CustomTkinter)
│       ├── ventana_principal.py        # Navegación lateral con caché de vistas en memoria
│       ├── estilos.py                  # Paleta de colores, tipografía y estilos de tablas
│       ├── formato.py                  # Formateo de monedas y cantidades
│       ├── selector_moneda.py          # Barra de filtro global de divisas
│       ├── dialogo_periodo.py          # Selector de rangos de fecha y calendario
│       ├── dialogo_cuenta.py           # Modal de creación y edición de cuentas
│       ├── dialogo_transferencia.py    # Modal de transferencias entre cuentas
│       ├── dialogo_cerrar_inversion.py # Modal de venta de posiciones y selector de cuenta en compras
│       ├── adaptadores_moneda.py       # Adaptadores multimoneda y edición para Cuentas y Movimientos
│       ├── vista_resumen.py            # Dashboard de Resumen Financiero
│       ├── vista_cuentas.py            # Vista base de Cuentas y Transferencias
│       ├── vista_gastos.py             # Vista de registro y análisis de Gastos
│       ├── vista_ingresos.py           # Vista de registro y análisis de Ingresos
│       ├── vista_inversiones.py        # Vista de Portafolio, Gráfica de Montaña e Importador CSV/XLSX
│       └── vista_reportes.py           # Vista de Salud Financiera, Radiografía, MoM y Exportación
├── base_de_datos/                      # Scripts SQL de inicialización de esquema PostgreSQL
└── pruebas/                            # Suite de pruebas automatizadas con pytest (89+ tests)

```

## ⚙️ Requisitos e Instalación

1. **Clonar el repositorio y crear el entorno virtual:**

   ```
   git clone https://github.com/Spartanhalo007/NexSaldo.git
   cd NexSaldo
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   
   ```

2. **Instalar dependencias:**

   ```
   pip install -r requirements.txt
   
   ```

3. **Configurar la base de datos PostgreSQL (`.env`):**
   Crea un archivo `.env` en la raíz del proyecto con las credenciales de tu instancia local de PostgreSQL:

   ```
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=nexsaldo
   DB_USER=postgres
   DB_PASSWORD=tu_contraseña
   
   ```

4. **Ejecutar la aplicación:**

   ```
   .\.venv\Scripts\python.exe -m app.main
   
   ```

## 🧪 Ejecución de Pruebas Automatizadas (`pytest`)

El proyecto cuenta con una suite de **89 pruebas unitarias y de integración** que validan cuentas, validaciones de saldo, transferencias, importación de brokers con detección de duplicados, compra/venta de inversiones con acreditación/descuento en cuentas, conversión multimoneda y exportación de reportes:

```
.\.venv\Scripts\python.exe -m pytest pruebas\ -q

```