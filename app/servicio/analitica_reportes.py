"""Servicio modular de analítica financiera, radiografía patrimonial y exportación de estados de cuenta.

Separa la lógica matemática de diagnóstico financiero y la generación de reportes (.xlsx, .csv, .html)
fuera de `GestorFinanciero`, cumpliendo el Principio de Responsabilidad Única (SRP) y manteniendo
funciones pequeñas, puras y documentadas.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List, Optional

DOS_DECIMALES = Decimal("0.01")
UN_DECIMAL = Decimal("0.1")
CIEN = Decimal("100")

UMBRAL_AHORRO_EXCELENTE = Decimal("20")
UMBRAL_AHORRO_SALUDABLE = Decimal("10")
UMBRAL_CONCENTRACION_ALTA = Decimal("50.0")
UMBRAL_ANOMALIA_GASTO_PCT = Decimal("25.0")


def cuantizar_moneda(valor: object) -> Decimal:
    """Redondea cualquier valor numérico a 2 decimales con ROUND_HALF_UP."""
    return Decimal(str(valor)).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)


def calcular_porcentaje(parte: Decimal, total: Decimal, decimales: Decimal = UN_DECIMAL) -> Decimal:
    """Calcula `(parte / total) * 100` de forma segura evitando división por cero."""
    if total <= Decimal("0"):
        return Decimal("0.0")
    return ((parte / total) * CIEN).quantize(decimales, rounding=ROUND_HALF_UP)


def calcular_variacion_porcentual(actual: Decimal, anterior: Decimal) -> Optional[Decimal]:
    """Devuelve la variación porcentual `((actual - anterior) / anterior) * 100` o `None` si no hay base previa."""
    if anterior <= Decimal("0"):
        return None
    return (((actual - anterior) / anterior) * CIEN).quantize(UN_DECIMAL, rounding=ROUND_HALF_UP)


def diagnosticar_tasa_ahorro(ingresos: Decimal, gastos: Decimal, tasa_pct: Decimal) -> str:
    """Clasifica la tasa de ahorro del periodo en un diagnóstico legible para la interfaz y los reportes."""
    if ingresos <= Decimal("0") and gastos <= Decimal("0"):
        return "Sin ingresos ni gastos registrados en el periodo"
    if tasa_pct >= UMBRAL_AHORRO_EXCELENTE:
        return "Excelente capacidad de ahorro (≥ 20%)"
    if tasa_pct >= UMBRAL_AHORRO_SALUDABLE:
        return "Saludable (entre 10% y 19% ahorrado)"
    if tasa_pct >= Decimal("0"):
        return "Margen ajustado (< 10% ahorrado)"
    return "Déficit en el periodo (gastos superan ingresos)"


def construir_comparativa_categorias(
    gastos_actual: Dict[str, Decimal],
    gastos_previo: Dict[str, Decimal],
) -> List[Dict[str, object]]:
    """Cruza el gasto por categoría del periodo actual frente al periodo previo e identifica anomalías."""
    categorias = sorted(
        set(gastos_actual) | set(gastos_previo),
        key=lambda c: gastos_actual.get(c, Decimal("0")),
        reverse=True,
    )
    resultado: List[Dict[str, object]] = []
    for cat in categorias:
        act_v = cuantizar_moneda(gastos_actual.get(cat, Decimal("0")))
        prv_v = cuantizar_moneda(gastos_previo.get(cat, Decimal("0")))
        if act_v <= Decimal("0") and prv_v <= Decimal("0"):
            continue
        delta_pct = calcular_variacion_porcentual(act_v, prv_v)
        es_anomalia = (delta_pct >= UMBRAL_ANOMALIA_GASTO_PCT) if delta_pct is not None else (act_v > Decimal("0"))
        resultado.append(
            {
                "categoria": cat,
                "actual": act_v,
                "anterior": prv_v,
                "variacion_pct": delta_pct,
                "es_anomalia": es_anomalia,
            }
        )
    return resultado


def generar_reporte_analitico(
    gestor,
    fecha_inicio: date,
    fecha_fin: date,
    moneda_objetivo: str = "COP",
    incluir_todas_convertidas: bool = True,
) -> Dict[str, object]:
    """Orquesta el cálculo completo del módulo Reportes delegando en helpers especializados."""
    mon = gestor._validar_moneda(moneda_objetivo)
    actual = gestor._calcular_ingresos_y_gastos_rango(
        fecha_inicio, fecha_fin, moneda_objetivo=mon, incluir_todas_convertidas=incluir_todas_convertidas
    )
    ingresos = cuantizar_moneda(actual.get("ingresos", Decimal("0")))
    gastos = cuantizar_moneda(actual.get("gastos", Decimal("0")))
    gastos_cat_actual: Dict[str, Decimal] = actual.get("gastos_por_categoria", {})  # type: ignore[assignment]

    ahorro_neto = cuantizar_moneda(ingresos - gastos)
    tasa_ahorro_pct = (
        calcular_porcentaje(ahorro_neto, ingresos)
        if ingresos > Decimal("0")
        else (Decimal("-100.0") if gastos > Decimal("0") else Decimal("0.0"))
    )

    dias_periodo = max(1, (fecha_fin - fecha_inicio).days + 1)
    gasto_diario = cuantizar_moneda(gastos / Decimal(str(dias_periodo)))
    proyeccion_mensual = cuantizar_moneda(gasto_diario * Decimal("30"))

    # 1. Liquidez en cuentas y exposición cambiaria
    liquidez_total, mapa_divisas, entidades = _analizar_cuentas_y_divisas(
        gestor, mon, incluir_todas_convertidas
    )

    # 2. Portafolio abierto y posiciones cerradas
    val_inv, pnl_abierto, gan_abiertas, eval_abiertas = _analizar_inversiones_abiertas(
        gestor, mon, incluir_todas_convertidas, mapa_divisas, entidades
    )
    cerradas = gestor.obtener_inversiones_cerradas(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    pnl_realizado, gan_cerradas, eval_cerradas = _analizar_inversiones_cerradas(
        gestor, cerradas, mon
    )

    total_ganadoras = gan_abiertas + gan_cerradas
    total_evaluadas = eval_abiertas + eval_cerradas
    win_rate_pct = (
        calcular_porcentaje(Decimal(str(total_ganadoras)), Decimal(str(total_evaluadas)))
        if total_evaluadas > 0
        else Decimal("0.0")
    )

    meses_supervivencia = (
        (liquidez_total / proyeccion_mensual).quantize(UN_DECIMAL, rounding=ROUND_HALF_UP)
        if proyeccion_mensual > Decimal("0")
        else None
    )

    # 3. Radiografía de patrimonio y concentración
    patrimonio_total = cuantizar_moneda(liquidez_total + val_inv)
    pct_liq = calcular_porcentaje(liquidez_total, patrimonio_total)
    pct_inv = (CIEN - pct_liq).quantize(UN_DECIMAL) if patrimonio_total > Decimal("0") else Decimal("0.0")

    exposicion_divisas = [
        {
            "moneda": cod,
            "valor_convertido": val,
            "porcentaje": calcular_porcentaje(val, patrimonio_total),
        }
        for cod, val in sorted(mapa_divisas.items(), key=lambda p: p[1], reverse=True)
    ]

    entidades_ordenadas = sorted(entidades, key=lambda e: e["valor_convertido"], reverse=True)  # type: ignore[arg-type,return-value]
    for ent in entidades_ordenadas:
        ent["porcentaje"] = calcular_porcentaje(ent["valor_convertido"], patrimonio_total)  # type: ignore[arg-type]

    alerta_concentracion = _evaluar_alerta_concentracion(entidades_ordenadas, patrimonio_total)

    # 4. Comparativa contra el periodo inmediatamente anterior (MoM)
    prev_fin = fecha_inicio - timedelta(days=1)
    prev_ini = prev_fin - timedelta(days=dias_periodo - 1)
    prev_datos = gestor._calcular_ingresos_y_gastos_rango(
        prev_ini, prev_fin, moneda_objetivo=mon, incluir_todas_convertidas=incluir_todas_convertidas
    )
    ing_prev = cuantizar_moneda(prev_datos.get("ingresos", Decimal("0")))
    gas_prev = cuantizar_moneda(prev_datos.get("gastos", Decimal("0")))
    gastos_cat_prev: Dict[str, Decimal] = prev_datos.get("gastos_por_categoria", {})  # type: ignore[assignment]

    return {
        "periodo": {
            "fecha_inicio": fecha_inicio.isoformat(),
            "fecha_fin": fecha_fin.isoformat(),
            "dias": dias_periodo,
            "moneda": mon,
        },
        "salud_financiera": {
            "ingresos": ingresos,
            "gastos": gastos,
            "ahorro_neto": ahorro_neto,
            "tasa_ahorro_pct": tasa_ahorro_pct,
            "diagnostico_ahorro": diagnosticar_tasa_ahorro(ingresos, gastos, tasa_ahorro_pct),
            "gasto_diario_promedio": gasto_diario,
            "proyeccion_gasto_mensual": proyeccion_mensual,
            "meses_supervivencia": meses_supervivencia,
            "pnl_abierto": cuantizar_moneda(pnl_abierto),
            "pnl_realizado": cuantizar_moneda(pnl_realizado),
            "pnl_total_combinado": cuantizar_moneda(pnl_abierto + pnl_realizado),
            "win_rate_pct": win_rate_pct,
        },
        "radiografia": {
            "patrimonio_total": patrimonio_total,
            "liquidez_cuentas": cuantizar_moneda(liquidez_total),
            "valor_inversiones": cuantizar_moneda(val_inv),
            "pct_liquidez": pct_liq,
            "pct_inversiones": pct_inv,
            "exposicion_divisas": exposicion_divisas,
            "distribucion_entidades": entidades_ordenadas,
            "alerta_concentracion": alerta_concentracion,
        },
        "comparativa_mom": {
            "etiqueta_periodo_anterior": f"{prev_ini.isoformat()} a {prev_fin.isoformat()}",
            "ingresos_anterior": ing_prev,
            "gastos_anterior": gas_prev,
            "variacion_ingresos_pct": calcular_variacion_porcentual(ingresos, ing_prev),
            "variacion_gastos_pct": calcular_variacion_porcentual(gastos, gas_prev),
            "categorias_comparadas": construir_comparativa_categorias(gastos_cat_actual, gastos_cat_prev),
        },
        "posiciones_cerradas": cerradas,
    }


def _analizar_cuentas_y_divisas(gestor, mon: str, incluir_todas: bool):
    liquidez_total = Decimal("0.00")
    mapa_divisas: Dict[str, Decimal] = {}
    entidades: List[Dict[str, object]] = []

    for cuenta, saldo in gestor.obtener_cuentas():
        if not cuenta.incluye_en_total or (not incluir_todas and cuenta.moneda != mon):
            continue
        val_conv = gestor._convertir_monto_seguro(saldo, cuenta.moneda, mon)
        val_pos = max(Decimal("0.00"), cuantizar_moneda(val_conv))
        liquidez_total += val_pos
        if val_pos > Decimal("0"):
            mapa_divisas[cuenta.moneda] = mapa_divisas.get(cuenta.moneda, Decimal("0")) + val_pos
            entidades.append(
                {
                    "nombre": cuenta.nombre,
                    "tipo": "CUENTA",
                    "moneda_origen": cuenta.moneda,
                    "valor_convertido": val_pos,
                }
            )
    return liquidez_total, mapa_divisas, entidades


def _analizar_inversiones_abiertas(gestor, mon: str, incluir_todas: bool, mapa_divisas: dict, entidades: list):
    valor_inversiones = Decimal("0.00")
    pnl_abierto = Decimal("0.00")
    ganadoras = 0
    evaluadas = 0

    for inv in gestor.obtener_inversiones():
        if not incluir_todas and inv.moneda != mon:
            continue
        precio_unit = gestor._obtener_precio_unitario_seguro(inv.simbolo, inv.moneda, permitir_red=False)
        val_nativo = (
            cuantizar_moneda(inv.cantidad_titulos * precio_unit)
            if (precio_unit is not None and precio_unit > Decimal("0") and inv.cantidad_titulos > Decimal("0"))
            else cuantizar_moneda(inv.monto_invertido)
        )
        gan_nativa = val_nativo - inv.monto_invertido
        evaluadas += 1
        if gan_nativa >= Decimal("0"):
            ganadoras += 1

        val_conv = gestor._convertir_monto_seguro(val_nativo, inv.moneda, mon)
        gan_conv = gestor._convertir_monto_seguro(gan_nativa, inv.moneda, mon)
        valor_inversiones += val_conv
        pnl_abierto += gan_conv
        mapa_divisas[inv.moneda] = mapa_divisas.get(inv.moneda, Decimal("0")) + val_conv
        entidades.append(
            {
                "nombre": f"{inv.simbolo} ({inv.nombre[:16]})",
                "tipo": "INVERSION",
                "moneda_origen": inv.moneda,
                "valor_convertido": val_conv,
            }
        )
    return valor_inversiones, pnl_abierto, ganadoras, evaluadas


def _analizar_inversiones_cerradas(gestor, cerradas: List[Dict[str, object]], mon: str):
    pnl_realizado = Decimal("0.00")
    ganadoras = 0
    for op in cerradas:
        gan_op = Decimal(str(op.get("ganancia_realizada", "0")))
        mon_op = str(op.get("moneda_origen", "USD"))
        if gan_op >= Decimal("0"):
            ganadoras += 1
        pnl_realizado += gestor._convertir_monto_seguro(gan_op, mon_op, mon)
    return pnl_realizado, ganadoras, len(cerradas)


def _evaluar_alerta_concentracion(entidades_ordenadas: List[Dict[str, object]], patrimonio_total: Decimal) -> str:
    if entidades_ordenadas and len(entidades_ordenadas) > 1 and entidades_ordenadas[0]["porcentaje"] >= UMBRAL_CONCENTRACION_ALTA:  # type: ignore[operator]
        top_e = entidades_ordenadas[0]
        return f"⚠️ Concentración alta: '{top_e['nombre']}' concentra el {top_e['porcentaje']:.1f}% de tu patrimonio."
    if patrimonio_total > Decimal("0"):
        return "✅ Diversificación saludable entre cuentas líquidas y activos."
    return "Sin patrimonio registrado todavía."


# ===========================================================================
# Exportación de Estados de Cuenta (.xlsx, .csv, .html)
# ===========================================================================

def exportar_estado_cuenta(
    gestor,
    ruta_destino: str,
    fecha_inicio: date,
    fecha_fin: date,
    moneda_objetivo: str = "COP",
    incluir_todas_convertidas: bool = True,
    formato: str = "xlsx",
) -> str:
    """Exporta el Estado de Cuenta completo en el formato indicado (.xlsx, .csv o .html)."""
    rep = generar_reporte_analitico(
        gestor,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        moneda_objetivo=moneda_objetivo,
        incluir_todas_convertidas=incluir_todas_convertidas,
    )
    movimientos = _obtener_movimientos_rango(gestor, fecha_inicio, fecha_fin)
    fmt = (formato or "xlsx").strip().lower()
    destino = Path(ruta_destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "xlsx":
        try:
            return _exportar_xlsx(destino, rep, movimientos, fecha_inicio, fecha_fin)
        except ImportError:
            destino = destino.with_suffix(".csv")
            return _exportar_csv(destino, rep, movimientos, fecha_inicio, fecha_fin)

    if fmt == "html":
        return _exportar_html(destino, rep, fecha_inicio, fecha_fin)

    return _exportar_csv(destino, rep, movimientos, fecha_inicio, fecha_fin)


def _obtener_movimientos_rango(gestor, fecha_inicio: date, fecha_fin: date):
    try:
        return gestor._repositorio.obtener_movimientos(
            None, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
        )
    except TypeError:
        return [
            m
            for m in gestor._repositorio.obtener_movimientos()
            if fecha_inicio <= m.fecha <= fecha_fin
        ]


def _exportar_xlsx(destino: Path, rep: Dict[str, object], movimientos: list, f_ini: date, f_fin: date) -> str:
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    salud = rep["salud_financiera"]  # type: ignore[index]
    radio = rep["radiografia"]  # type: ignore[index]
    mom = rep["comparativa_mom"]  # type: ignore[index]
    cerradas = rep["posiciones_cerradas"]  # type: ignore[index]
    mon = rep["periodo"]["moneda"]  # type: ignore[index]

    wb = openpyxl.Workbook()
    ws_res = wb.active
    ws_res.title = "Salud y Radiografia"

    header_fill = PatternFill("solid", fgColor="1E293B")
    header_font = Font(bold=True, color="FFFFFF")

    def _estilizar_fila_cabecera(ws, num_fila: int = 1) -> None:
        for cell in ws[num_fila]:
            cell.fill = header_fill
            cell.font = header_font

    ws_res.append(["ESTADO DE CUENTA Y SALUD FINANCIERA — NEXSALDO"])
    ws_res["A1"].font = Font(bold=True, size=14)
    ws_res.append(["Periodo", f"{f_ini.isoformat()} a {f_fin.isoformat()}", "Moneda base", mon])
    ws_res.append([])
    ws_res.append(["Indicador de Salud Financiera", f"Valor ({mon})", "Detalle / Diagnóstico"])
    _estilizar_fila_cabecera(ws_res, 4)

    filas_kpi = [
        ("Ingresos Totales", float(salud["ingresos"]), ""),
        ("Gastos Totales", float(salud["gastos"]), ""),
        ("Ahorro Neto (Flujo de Caja)", float(salud["ahorro_neto"]), salud["diagnostico_ahorro"]),
        ("Tasa de Ahorro (%)", float(salud["tasa_ahorro_pct"]), "% de ingresos conservados"),
        (
            "Fondo de Emergencia (Meses)",
            float(salud["meses_supervivencia"]) if salud["meses_supervivencia"] is not None else "Infinito",
            "Liquidez / Gasto mensual proyectado",
        ),
        ("Ritmo de Gasto Diario", float(salud["gasto_diario_promedio"]), f"Proyección 30d: {salud['proyeccion_gasto_mensual']}"),
        ("Patrimonio Neto Total", float(radio["patrimonio_total"]), radio["alerta_concentracion"]),
        ("Liquidez en Cuentas", float(radio["liquidez_cuentas"]), f"{radio['pct_liquidez']}% del patrimonio"),
        ("Valor en Inversiones", float(radio["valor_inversiones"]), f"{radio['pct_inversiones']}% del patrimonio"),
        ("P&L Inversiones (Abierto + Realizado)", float(salud["pnl_total_combinado"]), f"Win Rate: {salud['win_rate_pct']}%"),
    ]
    for fila in filas_kpi:
        ws_res.append(list(fila))

    ws_mov = wb.create_sheet("Movimientos")
    ws_mov.append(["Fecha", "Tipo", "Categoría", "Valor", "Moneda", "Descripción"])
    _estilizar_fila_cabecera(ws_mov)
    for m in movimientos:
        ws_mov.append([
            m.fecha.isoformat() if hasattr(m.fecha, "isoformat") else str(m.fecha),
            m.tipo_movimiento,
            m.categoria,
            float(m.valor),
            m.moneda,
            m.descripcion or "",
        ])

    ws_mom = wb.create_sheet("Comparativa Categorias")
    ws_mom.append(["Categoría", f"Actual ({mon})", f"Periodo Anterior ({mon})", "Variación (%)", "¿Anomalía?"])
    _estilizar_fila_cabecera(ws_mom)
    for c_item in mom["categorias_comparadas"]:
        ws_mom.append([
            c_item["categoria"],
            float(c_item["actual"]),
            float(c_item["anterior"]),
            float(c_item["variacion_pct"]) if c_item["variacion_pct"] is not None else "Nuevo",
            "SÍ" if c_item["es_anomalia"] else "NO",
        ])

    ws_cer = wb.create_sheet("Posiciones Cerradas")
    ws_cer.append(["Fecha Cierre", "Símbolo", "Nombre", "Invertido", "Valor Venta", "Ganancia Realizada", "Moneda", "Cuenta Destino"])
    _estilizar_fila_cabecera(ws_cer)
    for op in cerradas:
        ws_cer.append([
            op["fecha_cierre"],
            op["simbolo"],
            op["nombre"],
            float(op["monto_invertido"]),
            float(op["valor_venta"]),
            float(op["ganancia_realizada"]),
            op["moneda_origen"],
            op["cuenta_destino"],
        ])

    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = max((len(str(c.value or "")) for c in col), default=12)
            sheet.column_dimensions[col[0].column_letter].width = min(max(max_len + 3, 12), 42)

    wb.save(str(destino))
    return str(destino)


def _exportar_html(destino: Path, rep: Dict[str, object], f_ini: date, f_fin: date) -> str:
    salud = rep["salud_financiera"]  # type: ignore[index]
    radio = rep["radiografia"]  # type: ignore[index]
    mom = rep["comparativa_mom"]  # type: ignore[index]
    cerradas = rep["posiciones_cerradas"]  # type: ignore[index]
    mon = rep["periodo"]["moneda"]  # type: ignore[index]

    filas_mom = []
    for c in mom["categorias_comparadas"]:
        var_txt = f"{c['variacion_pct']:+.1f}%" if c["variacion_pct"] is not None else "Nuevo"
        filas_mom.append(
            f"<tr><td>{c['categoria']}</td><td>{c['actual']:,.2f} {mon}</td>"
            f"<td>{c['anterior']:,.2f} {mon}</td><td>{var_txt}</td></tr>"
        )
    filas_mom_html = "".join(filas_mom) or "<tr><td colspan='4'>Sin gastos registrados</td></tr>"

    filas_cer_html = "".join(
        f"<tr><td>{op['fecha_cierre']}</td><td><b>{op['simbolo']}</b> ({op['nombre']})</td>"
        f"<td>{op['monto_invertido']:,.2f} {op['moneda_origen']}</td>"
        f"<td>{op['valor_venta']:,.2f} {op['moneda_origen']}</td>"
        f"<td>{op['ganancia_realizada']:+,.2f} {op['moneda_origen']}</td>"
        f"<td>{op['cuenta_destino']}</td></tr>"
        for op in cerradas
    ) or "<tr><td colspan='6'>Sin posiciones cerradas en el periodo</td></tr>"

    texto_emergencia = (
        f"{salud['meses_supervivencia']:.1f} meses"
        if salud["meses_supervivencia"] is not None
        else "∞ meses"
    )
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Estado de Cuenta NexSaldo ({f_ini.isoformat()} a {f_fin.isoformat()})</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 32px; color: #0F172A; background: #F8FAFC; }}
  h1 {{ margin-bottom: 4px; color: #0F172A; }}
  .sub {{ color: #475569; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 24px; }}
  .card {{ background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px; }}
  .card h3 {{ margin: 0 0 6px 0; font-size: 13px; color: #64748B; }}
  .card .val {{ font-size: 20px; font-weight: bold; color: #0F172A; }}
  table {{ width: 100%; border-collapse: collapse; background: #FFFFFF; margin-bottom: 24px; border-radius: 8px; overflow: hidden; }}
  th {{ background: #1E293B; color: #FFFFFF; text-align: left; padding: 10px; font-size: 13px; }}
  td {{ padding: 9px 10px; border-bottom: 1px solid #E2E8F0; font-size: 13px; }}
</style>
</head>
<body>
  <h1>Estado de Cuenta y Salud Financiera — NexSaldo</h1>
  <div class="sub">Periodo: <b>{f_ini.isoformat()}</b> a <b>{f_fin.isoformat()}</b> · Moneda Base: <b>{mon}</b></div>
  <div class="grid">
    <div class="card"><h3>Tasa de Ahorro</h3><div class="val">{salud['tasa_ahorro_pct']:+.1f}% ({salud['ahorro_neto']:,.2f} {mon})</div><div>{salud['diagnostico_ahorro']}</div></div>
    <div class="card"><h3>Fondo de Emergencia</h3><div class="val">{texto_emergencia}</div><div>Liquidez: {radio['liquidez_cuentas']:,.2f} {mon}</div></div>
    <div class="card"><h3>Patrimonio Neto Total</h3><div class="val">{radio['patrimonio_total']:,.2f} {mon}</div><div>{radio['alerta_concentracion']}</div></div>
    <div class="card"><h3>P&L Total Inversiones</h3><div class="val">{salud['pnl_total_combinado']:+,.2f} {mon}</div><div>Win Rate: {salud['win_rate_pct']:.0f}%</div></div>
  </div>
  <h2>Comparativa por Categoría vs. Periodo Anterior</h2>
  <table>
    <thead><tr><th>Categoría</th><th>Gasto Actual</th><th>Periodo Anterior</th><th>Variación</th></tr></thead>
    <tbody>{filas_mom_html}</tbody>
  </table>
  <h2>Historial de Posiciones Cerradas (P&L Realizado)</h2>
  <table>
    <thead><tr><th>Fecha Cierre</th><th>Activo</th><th>Invertido</th><th>Valor Venta</th><th>Ganancia Realizada</th><th>Cuenta Destino</th></tr></thead>
    <tbody>{filas_cer_html}</tbody>
  </table>
</body>
</html>"""
    destino.write_text(html, encoding="utf-8")
    return str(destino)


def _exportar_csv(destino: Path, rep: Dict[str, object], movimientos: list, f_ini: date, f_fin: date) -> str:
    salud = rep["salud_financiera"]  # type: ignore[index]
    radio = rep["radiografia"]  # type: ignore[index]
    mom = rep["comparativa_mom"]  # type: ignore[index]
    cerradas = rep["posiciones_cerradas"]  # type: ignore[index]
    mon = rep["periodo"]["moneda"]  # type: ignore[index]

    with destino.open("w", newline="", encoding="utf-8-sig") as f_csv:
        writer = csv.writer(f_csv)
        writer.writerow(["ESTADO DE CUENTA Y SALUD FINANCIERA — NEXSALDO"])
        writer.writerow(["Periodo", f"{f_ini.isoformat()} a {f_fin.isoformat()}", "Moneda", mon])
        writer.writerow([])
        writer.writerow(["SECCIÓN 1: SALUD FINANCIERA Y RADIOGRAFÍA PATRIMONIAL"])
        writer.writerow(["Indicador", "Valor", "Moneda / Unidad", "Diagnóstico"])
        writer.writerow(["Ingresos del Periodo", f"{salud['ingresos']:.2f}", mon, ""])
        writer.writerow(["Gastos del Periodo", f"{salud['gastos']:.2f}", mon, ""])
        writer.writerow(["Ahorro Neto", f"{salud['ahorro_neto']:.2f}", mon, salud["diagnostico_ahorro"]])
        writer.writerow(["Tasa de Ahorro", f"{salud['tasa_ahorro_pct']:.1f}", "%", ""])
        writer.writerow([
            "Fondo de Emergencia",
            f"{salud['meses_supervivencia']:.1f}" if salud["meses_supervivencia"] is not None else "Infinito",
            "meses",
            "",
        ])
        writer.writerow(["Patrimonio Neto Total", f"{radio['patrimonio_total']:.2f}", mon, radio["alerta_concentracion"]])
        writer.writerow(["Liquidez en Cuentas", f"{radio['liquidez_cuentas']:.2f}", mon, f"{radio['pct_liquidez']}%"])
        writer.writerow(["Valor en Inversiones", f"{radio['valor_inversiones']:.2f}", mon, f"{radio['pct_inversiones']}%"])
        writer.writerow(["P&L Total Inversiones", f"{salud['pnl_total_combinado']:.2f}", mon, f"Win Rate {salud['win_rate_pct']}%"])
        writer.writerow([])
        writer.writerow(["SECCIÓN 2: COMPARATIVA POR CATEGORÍA VS PERIODO ANTERIOR"])
        writer.writerow(["Categoría", "Gasto Actual", "Gasto Anterior", "Variación %"])
        for c_item in mom["categorias_comparadas"]:
            writer.writerow([
                c_item["categoria"],
                f"{c_item['actual']:.2f}",
                f"{c_item['anterior']:.2f}",
                f"{c_item['variacion_pct']:+.1f}%" if c_item["variacion_pct"] is not None else "Nuevo",
            ])
        writer.writerow([])
        writer.writerow(["SECCIÓN 3: POSICIONES CERRADAS (P&L REALIZADO)"])
        writer.writerow(["Fecha Cierre", "Símbolo", "Nombre", "Invertido", "Valor Venta", "Ganancia Realizada", "Moneda", "Cuenta Destino"])
        for op in cerradas:
            writer.writerow([
                op["fecha_cierre"],
                op["simbolo"],
                op["nombre"],
                f"{op['monto_invertido']:.2f}",
                f"{op['valor_venta']:.2f}",
                f"{op['ganancia_realizada']:.2f}",
                op["moneda_origen"],
                op["cuenta_destino"],
            ])
        writer.writerow([])
        writer.writerow(["SECCIÓN 4: MOVIMIENTOS DEL PERIODO"])
        writer.writerow(["Fecha", "Tipo", "Categoría", "Valor", "Moneda", "Descripción"])
        for m in movimientos:
            writer.writerow([
                m.fecha.isoformat() if hasattr(m.fecha, "isoformat") else str(m.fecha),
                m.tipo_movimiento,
                m.categoria,
                f"{m.valor:.2f}",
                m.moneda,
                m.descripcion or "",
            ])
    return str(destino)
