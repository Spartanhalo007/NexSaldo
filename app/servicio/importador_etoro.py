"""Importador de portafolios desde eToro (Estado de Cuenta Excel .xlsx y archivos .csv).

Correcciones clave de precisión financiera:
1. Conversión de Criptomonedas de eToro a Yahoo Finance: En eToro el campo 'Details' es 'BTC/USD'
   o 'SOL/USD', pero en Yahoo Finance 'BTC' sin '-USD' es un ETF de $40 (lo que causaba un falso -99%)
   y 'SOL' es una acción solar de $2. Ahora se mapean automáticamente a 'BTC-USD', 'SOL-USD', 'ETH-USD', etc.
2. Conversión decimal exacta (`_limpiar_decimal`): En eToro todos los números usan coma (',') o punto ('.')
   ÚNICAMENTE como separador decimal (nunca como separador de miles), y los números pequeños usan notación
   científica (ej. '5.81E-4'). Ya no se elimina la coma en cantidades con 3, 5 o 7 decimales (ej. '1,235' unidades).
3. Exclusión estricta del 100% de posiciones cerradas e importación de cada operación abierta individual.
"""

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET
import zipfile

from app.modelo.inversion import (
    CATALOGO_ACTIVOS_BURSATILES,
    MAPA_CRIPTO_A_YAHOO,
    normalizar_simbolo_yahoo,
)

MAPA_NOMBRES_CATALOGO: Dict[str, str] = {
    item["simbolo"].upper(): item["nombre"] for item in CATALOGO_ACTIVOS_BURSATILES
}

MAPA_NOMBRES_ETORO_A_TICKER: Dict[str, str] = {
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
    "solana": "SOL-USD",
    "ripple": "XRP-USD",
    "cardano": "ADA-USD",
    "dogecoin": "DOGE-USD",
    "polkadot": "DOT-USD",
    "avalanche": "AVAX-USD",
    "chainlink": "LINK-USD",
    "litecoin": "LTC-USD",
    "take-two": "TTWO",
    "take two": "TTWO",
    "vanguard s&p 500": "VOO",
    "spdr s&p 500": "SPY",
    "invesco qqq": "QQQ",
    "nasdaq 100": "QQQ",
    "vanguard total stock": "VTI",
    "schwab u.s. dividend": "SCHD",
    "spdr gold": "GLD",
    "apple": "AAPL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "amazon": "AMZN",
    "meta platforms": "META",
    "tesla": "TSLA",
    "berkshire hathaway": "BRK-B",
    "nu holdings": "NU",
    "nubank": "NU",
    "mercadolibre": "MELI",
    "bancolombia": "CIB",
    "ecopetrol": "EC",
    "coca-cola": "KO",
    "electronic arts": "EA",
    "sony": "SONY",
    "nintendo": "NTDOY",
    "advanced micro devices": "AMD",
    "netflix": "NFLX",
    "spotify": "SPOT",
    "walt disney": "DIS",
    "palantir": "PLTR",
    "uber": "UBER",
    "jpmorgan": "JPM",
    "visa": "V",
}


def _normalizar_id_posicion(valor: object) -> str:
    """Normaliza un Position ID de eToro para que coincida exactamente entre hojas."""
    if valor is None:
        return ""
    texto = str(valor).strip().lstrip("#").strip()
    if not texto or texto in ("-", "—", "N/A", "None", "null"):
        return ""
    try:
        dec = Decimal(texto.replace(",", "."))
        if dec == dec.to_integral_value():
            return str(int(dec))
    except InvalidOperation:
        pass
    limpio = re.sub(r"\.0+$", "", texto)
    solo_digitos = "".join(ch for ch in limpio if ch.isdigit())
    return solo_digitos if len(solo_digitos) >= 4 else limpio


def _limpiar_decimal(valor: object) -> Optional[Decimal]:
    """Convierte cadenas numéricas de eToro (incluyendo decimales con coma como '1,235' o '0,00245'
    y notación científica como '5.81E-4') a `Decimal` sin alterar su magnitud."""
    if valor is None:
        return None
    if isinstance(valor, (int, float, Decimal)):
        try:
            return Decimal(str(valor))
        except InvalidOperation:
            return None
    texto = str(valor).strip()
    if not texto or texto in ("-", "—", "N/A", "null", "None"):
        return None

    # Conservar dígitos, punto, coma, signo y exponente científico (e / E)
    limpio = re.sub(r"[^0-9,.\-eE+]", "", texto)
    if not limpio or limpio in ("-", ".", ",", "+"):
        return None

    if "," in limpio and "." in limpio:
        if limpio.rfind(",") > limpio.rfind("."):
            limpio = limpio.replace(".", "").replace(",", ".")
        else:
            limpio = limpio.replace(",", "")
    elif "," in limpio:
        # En eToro nunca se usan separadores de miles; una coma única es SIEMPRE separador decimal
        if limpio.count(",") == 1:
            limpio = limpio.replace(",", ".")
        else:
            limpio = limpio.replace(",", "")

    try:
        return Decimal(limpio)
    except InvalidOperation:
        return None


def _parsear_fecha(valor: object) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor or "").strip()
    if not texto:
        return date.today()
    primer_token = texto.split(" ")[0].strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(primer_token, fmt).date()
        except ValueError:
            continue
    # Soporte para fechas seriales de Excel (ej. 45519.604)
    try:
        serial = float(primer_token.replace(",", "."))
        if 30000 <= serial <= 65000:
            return date(1899, 12, 30) + timedelta(days=int(serial))
    except ValueError:
        pass
    return date.today()


def _extraer_ticker_de_texto(
    texto_instrumento: str,
    detalle_extra: str = "",
    tipo_activo: str = "",
) -> Tuple[str, str]:
    """Extrae el símbolo bursátil o de criptomoneda (ej. 'TTWO', 'VOO', 'BTC-USD', 'SOL-USD')
    a partir del campo 'Details' de eToro (ej. 'TTWO/USD', 'BTC/USD') y el 'Asset type' ('Crypto', 'Stocks', 'ETF')."""
    det = (detalle_extra or "").strip()
    inst = (texto_instrumento or "").strip()
    es_cripto = any(
        w in (tipo_activo or "").strip().lower()
        for w in ("crypto", "cripto", "criptomoneda")
    )

    # 1. Formato estándar de 'Details' en eToro Account Activity: 'TTWO/USD', 'BTC/USD', 'SOL/USD'
    for candidato in (det, inst):
        if "/" in candidato:
            base = candidato.split("/")[0].strip().upper()
            if 1 <= len(base) <= 12 and all(c.isalnum() or c in ("-", ".") for c in base):
                sim_norm = normalizar_simbolo_yahoo(base, es_cripto=es_cripto)
                if base in MAPA_CRIPTO_A_YAHOO:
                    return sim_norm, MAPA_CRIPTO_A_YAHOO[base][1]
                nombre = MAPA_NOMBRES_CATALOGO.get(
                    sim_norm,
                    inst if (inst and inst.upper() != candidato.upper() and "/" not in inst) else sim_norm,
                )
                return sim_norm, nombre

    # 2. Paréntesis con ticker al final: ej. 'Take-Two Interactive Software (TTWO)' o 'Bitcoin (BTC)'
    m_par = re.search(r"\(([A-Z0-9.\-]{1,10})\)", inst.upper())
    if m_par:
        base = m_par.group(1)
        sim_norm = normalizar_simbolo_yahoo(base, es_cripto=es_cripto)
        if base in MAPA_CRIPTO_A_YAHOO:
            return sim_norm, MAPA_CRIPTO_A_YAHOO[base][1]
        nombre_limpio = re.sub(r"^(Buy|Comprar|Open|Abrir)\s+", "", inst, flags=re.IGNORECASE).strip()
        return sim_norm, nombre_limpio or MAPA_NOMBRES_CATALOGO.get(sim_norm, sim_norm)

    # 3. Si el campo ya es directamente un ticker (ej. 'TTWO', 'VOO', 'BTC', 'BTC-USD', 'SOL')
    limpio_inst = re.sub(r"^(Buy|Comprar|Open|Abrir)\s+", "", inst, flags=re.IGNORECASE).strip()
    if (
        1 <= len(limpio_inst) <= 12
        and " " not in limpio_inst
        and all(c.isalnum() or c in ("-", ".") for c in limpio_inst)
    ):
        base = limpio_inst.upper()
        sim_norm = normalizar_simbolo_yahoo(base, es_cripto=es_cripto)
        if base in MAPA_CRIPTO_A_YAHOO:
            return sim_norm, MAPA_CRIPTO_A_YAHOO[base][1]
        return sim_norm, MAPA_NOMBRES_CATALOGO.get(sim_norm, sim_norm)

    # 4. Búsqueda por nombre de empresa o criptomoneda
    combinado_low = f"{limpio_inst} {det}".lower()
    for fragmento, ticker_map in MAPA_NOMBRES_ETORO_A_TICKER.items():
        if fragmento in combinado_low:
            return ticker_map, MAPA_NOMBRES_CATALOGO.get(ticker_map, limpio_inst or ticker_map)

    # 5. Último recurso: primera palabra como ticker
    palabras = [p for p in re.split(r"[^A-Za-z0-9.\-]+", limpio_inst.upper()) if p]
    if palabras:
        base = palabras[0][:10]
        sim_norm = normalizar_simbolo_yahoo(base, es_cripto=es_cripto)
        return sim_norm, limpio_inst or sim_norm
    return "", ""


def _leer_hojas_xlsx(ruta_xlsx: Path) -> Dict[str, List[List[str]]]:
    try:
        import openpyxl  # type: ignore

        wb = openpyxl.load_workbook(ruta_xlsx, data_only=True, read_only=True)
        hojas_op: Dict[str, List[List[str]]] = {}
        for nombre_sh in wb.sheetnames:
            ws = wb[nombre_sh]
            filas_sh: List[List[str]] = []
            for row in ws.iter_rows(values_only=True):
                fila_str = [
                    (
                        v.strftime("%Y-%m-%d %H:%M:%S")
                        if isinstance(v, (datetime, date))
                        else (str(v).strip() if v is not None else "")
                    )
                    for v in row
                ]
                if any(c for c in fila_str):
                    filas_sh.append(fila_str)
            hojas_op[nombre_sh] = filas_sh
        wb.close()
        if hojas_op:
            return hojas_op
    except Exception:
        pass

    return _leer_hojas_xlsx_nativo(ruta_xlsx)


def _leer_hojas_xlsx_nativo(ruta_xlsx: Path) -> Dict[str, List[List[str]]]:
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    hojas: Dict[str, List[List[str]]] = {}

    with zipfile.ZipFile(ruta_xlsx, "r") as zf:
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            raiz_ss = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in raiz_ss.findall("main:si", ns):
                partes_t = [t.text or "" for t in si.findall(".//main:t", ns)]
                shared_strings.append("".join(partes_t))

        mapa_rels: Dict[str, str] = {}
        if "xl/_rels/workbook.xml.rels" in zf.namelist():
            raiz_rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            for rel in raiz_rels:
                rid = rel.attrib.get("Id", "")
                target = rel.attrib.get("Target", "")
                if rid and target:
                    target_norm = target.lstrip("/")
                    if not target_norm.startswith("xl/"):
                        target_norm = f"xl/{target_norm}"
                    mapa_rels[rid] = target_norm

        lista_hojas: List[Tuple[str, str]] = []
        if "xl/workbook.xml" in zf.namelist():
            raiz_wb = ET.fromstring(zf.read("xl/workbook.xml"))
            for idx, sh in enumerate(raiz_wb.findall(".//main:sheet", ns), start=1):
                nombre_sh = sh.attrib.get("name", f"Sheet{idx}")
                rid = None
                for k, v in sh.attrib.items():
                    if k.endswith("}id") or k == "r:id":
                        rid = v
                        break
                ruta_xml = mapa_rels.get(rid or "", f"xl/worksheets/sheet{idx}.xml")
                lista_hojas.append((nombre_sh, ruta_xml))

        for nombre_hoja, ruta_xml in lista_hojas:
            if ruta_xml not in zf.namelist():
                continue
            raiz_hoja = ET.fromstring(zf.read(ruta_xml))
            filas_hoja: List[List[str]] = []
            for row_el in raiz_hoja.findall(".//main:sheetData/main:row", ns):
                celdas_dict: Dict[int, str] = {}
                max_col = 0
                col_cursor = 0
                for c_el in row_el.findall("main:c", ns):
                    ref = c_el.attrib.get("r", "")
                    tipo_c = c_el.attrib.get("t", "")
                    col_letras = "".join(ch for ch in ref if ch.isalpha())
                    if col_letras:
                        col_idx = 0
                        for ch in col_letras:
                            col_idx = col_idx * 26 + (ord(ch.upper()) - ord("A") + 1)
                        col_cursor = col_idx
                    else:
                        col_cursor += 1
                        col_idx = col_cursor
                    max_col = max(max_col, col_idx)

                    valor_txt = ""
                    if tipo_c == "s":
                        v_el = c_el.find("main:v", ns)
                        if v_el is not None and v_el.text is not None:
                            try:
                                s_idx = int(v_el.text)
                                if 0 <= s_idx < len(shared_strings):
                                    valor_txt = shared_strings[s_idx]
                            except ValueError:
                                valor_txt = v_el.text
                    elif tipo_c == "inlineStr":
                        partes = [t.text or "" for t in c_el.findall(".//main:t", ns)]
                        valor_txt = "".join(partes)
                    else:
                        v_el = c_el.find("main:v", ns)
                        if v_el is not None and v_el.text is not None:
                            valor_txt = v_el.text
                    celdas_dict[col_idx] = valor_txt.strip()

                if max_col > 0:
                    fila_lista = [celdas_dict.get(i, "") for i in range(1, max_col + 1)]
                    if any(celda for celda in fila_lista):
                        filas_hoja.append(fila_lista)
            hojas[nombre_hoja] = filas_hoja

    return hojas


def _convertir_filas_a_diccionarios(filas: List[List[str]]) -> List[Dict[str, str]]:
    if len(filas) < 2:
        return []

    palabras_clave_cabecera = {
        "position id", "id de posición", "id de posicion", "action", "acción", "accion",
        "amount", "importe", "monto", "units", "unidades", "units / contracts",
        "unidades / contratos", "type", "tipo", "details", "detalles", "symbol",
        "símbolo", "simbolo", "ticker", "instrument", "instrumento", "open rate",
        "tasa de apertura", "precio", "close date", "fecha de cierre",
    }

    idx_cabecera = 0
    mejor_puntaje = 0
    for idx, fila in enumerate(filas[:20]):
        celdas_low = {c.strip().lower() for c in fila if c.strip()}
        puntaje = len(celdas_low & palabras_clave_cabecera)
        if puntaje > mejor_puntaje:
            mejor_puntaje = puntaje
            idx_cabecera = idx

    encabezados = [c.strip().lower() for c in filas[idx_cabecera]]
    registros: List[Dict[str, str]] = []
    for fila in filas[idx_cabecera + 1 :]:
        if not any(c.strip() for c in fila):
            continue
        item: Dict[str, str] = {}
        for col_i, nombre_col in enumerate(encabezados):
            if not nombre_col:
                continue
            val = fila[col_i].strip() if col_i < len(fila) else ""
            if nombre_col not in item or not item[nombre_col]:
                item[nombre_col] = val
        if item:
            registros.append(item)
    return registros


def _obtener_campo_exacto_o_parcial(
    fila: Dict[str, str],
    candidatos_exactos: Tuple[str, ...],
    excluir_subcadenas: Tuple[str, ...] = (),
) -> str:
    for cand in candidatos_exactos:
        if cand in fila and fila[cand] != "":
            return fila[cand]
    for k, v in fila.items():
        if not v:
            continue
        k_low = k.strip().lower()
        if any(exc in k_low for exc in excluir_subcadenas):
            continue
        if any(cand in k_low for cand in candidatos_exactos):
            return v
    return ""


def _es_tipo_apertura_etoro(tipo_mov: str) -> bool:
    t = tipo_mov.strip().lower()
    if not t:
        return False
    palabras_excluidas = (
        "close", "closed", "cerrad", "cerrar", "cierre", "profit", "loss",
        "ganancia", "pérdida", "perdida", "beneficio", "rollover", "overnight",
        "dividend", "dividendo", "deposit", "depósito", "deposito", "withdraw",
        "retiro", "retirada", "fee", "comisión", "comision", "interest",
        "interés", "interes", "adjust", "ajuste", "cancel", "transfer",
    )
    if any(exc in t for exc in palabras_excluidas):
        return False

    patrones_apertura = (
        "open position",
        "position opened",
        "abrir posición",
        "abrir posicion",
        "posición abierta",
        "posicion abierta",
    )
    return any(p in t for p in patrones_apertura)


def _es_tipo_cierre_etoro(tipo_mov: str) -> bool:
    t = tipo_mov.strip().lower()
    if not t:
        return False
    if "rollover" in t or "overnight" in t or "dividend" in t or "dividendo" in t:
        return False
    patrones_cierre = (
        "position closed",
        "close position",
        "profit/loss",
        "p/l of trade",
        "posición cerrada",
        "posicion cerrada",
        "cerrar posición",
        "cerrar posicion",
        "cierre de posición",
        "cierre de posicion",
        "ganancias/pérdidas",
        "ganancias/perdidas",
        "beneficio/pérdida",
        "beneficio/perdida",
        "liquidación",
        "liquidacion",
        "liquidation",
    )
    return any(p in t for p in patrones_cierre)


def parsear_archivo_etoro_o_csv(
    ruta_archivo: str, agrupar_por_ticker: bool = False
) -> List[Dict[str, object]]:
    """Analiza un archivo `.xlsx` o `.csv` exportado de eToro y devuelve ÚNICAMENTE las posiciones
    ACTUALMENTE ABIERTAS, mapeando criptomonedas a su símbolo real en Yahoo Finance (`BTC-USD`, `SOL-USD`, etc.)."""
    ruta = Path(ruta_archivo)
    if not ruta.exists():
        raise ValueError("El archivo seleccionado no existe.")

    ext = ruta.suffix.lower()
    hojas_filas: Dict[str, List[List[str]]] = {}

    if ext == ".xlsx":
        hojas_filas = _leer_hojas_xlsx(ruta)
    elif ext in (".csv", ".txt", ".tsv"):
        contenido = ruta.read_text(encoding="utf-8-sig", errors="replace")
        muestra = contenido[:2048]
        delimitador = ";" if muestra.count(";") > muestra.count(",") else ","
        if "\t" in muestra and muestra.count("\t") > muestra.count(delimitador):
            delimitador = "\t"
        lector = csv.reader(contenido.splitlines(), delimiter=delimitador)
        hojas_filas["CSV"] = [list(fila) for fila in lector if any(c.strip() for c in fila)]
    else:
        raise ValueError("Formato no soportado. Selecciona un archivo Excel (.xlsx) o CSV (.csv).")

    posiciones_crudas: List[Dict[str, object]] = []

    hojas_cerradas: List[str] = []
    hojas_actividad: List[str] = []

    for nombre_h, filas_h in hojas_filas.items():
        n_low = nombre_h.strip().lower()
        if any(w in n_low for w in ("closed", "cerrada", "cerrado")):
            hojas_cerradas.append(nombre_h)
            continue
        if any(w in n_low for w in ("activity", "actividad", "transactions", "transacciones")):
            hojas_actividad.append(nombre_h)
            continue
        regs_prueba = _convertir_filas_a_diccionarios(filas_h[:5])
        if regs_prueba:
            cols = set(regs_prueba[0].keys())
            if any(c in cols for c in ("close date", "fecha de cierre", "close rate", "tasa de cierre")):
                hojas_cerradas.append(nombre_h)
            elif ("details" in cols or "detalles" in cols) and ("position id" in cols or "id de posición" in cols or "id de posicion" in cols):
                hojas_actividad.append(nombre_h)

    ids_cerrados: Set[str] = set()
    for nh_cerr in hojas_cerradas:
        for reg in _convertir_filas_a_diccionarios(hojas_filas[nh_cerr]):
            pid_raw = _obtener_campo_exacto_o_parcial(
                reg, ("position id", "id de posición", "id de posicion", "id posición", "id posicion", "id")
            )
            pid_norm = _normalizar_id_posicion(pid_raw)
            if pid_norm:
                ids_cerrados.add(pid_norm)

    for nh_act in hojas_actividad:
        registros_act = _convertir_filas_a_diccionarios(hojas_filas[nh_act])
        for reg in registros_act:
            tipo_mov = _obtener_campo_exacto_o_parcial(
                reg,
                ("type", "tipo", "action", "acción", "accion"),
                excluir_subcadenas=("asset", "activo"),
            )
            pid_raw = _obtener_campo_exacto_o_parcial(
                reg, ("position id", "id de posición", "id de posicion", "id posición", "id posicion")
            )
            pid_norm = _normalizar_id_posicion(pid_raw)
            if pid_norm and _es_tipo_cierre_etoro(tipo_mov):
                ids_cerrados.add(pid_norm)

    if hojas_actividad:
        ids_abiertos_ya_agregados: Set[str] = set()
        for nh_act in hojas_actividad:
            registros_act = _convertir_filas_a_diccionarios(hojas_filas[nh_act])
            for reg in registros_act:
                tipo_mov = _obtener_campo_exacto_o_parcial(
                    reg,
                    ("type", "tipo", "action", "acción", "accion"),
                    excluir_subcadenas=("asset", "activo"),
                )
                if not _es_tipo_apertura_etoro(tipo_mov):
                    continue

                pid_raw = _obtener_campo_exacto_o_parcial(
                    reg, ("position id", "id de posición", "id de posicion", "id posición", "id posicion")
                )
                pid_norm = _normalizar_id_posicion(pid_raw)

                if not pid_norm or pid_norm in ids_cerrados or pid_norm in ids_abiertos_ya_agregados:
                    continue

                detalles = _obtener_campo_exacto_o_parcial(
                    reg, ("details", "detalles", "instrument", "instrumento")
                )
                if not detalles:
                    continue

                tipo_activo = _obtener_campo_exacto_o_parcial(
                    reg, ("asset type", "tipo de activo", "asset")
                )

                monto = _limpiar_decimal(
                    _obtener_campo_exacto_o_parcial(
                        reg, ("amount", "importe", "monto", "invested"),
                        excluir_subcadenas=("equity", "balance", "saldo"),
                    )
                )
                unidades = _limpiar_decimal(
                    _obtener_campo_exacto_o_parcial(
                        reg,
                        ("units / contracts", "unidades / contratos", "units", "unidades", "shares", "cantidad"),
                    )
                )
                precio_ap = _limpiar_decimal(
                    _obtener_campo_exacto_o_parcial(
                        reg, ("open rate", "tasa de apertura", "price", "precio")
                    )
                )
                fecha_op = _parsear_fecha(
                    _obtener_campo_exacto_o_parcial(
                        reg, ("date", "fecha", "open date", "fecha de apertura")
                    )
                )

                simbolo, nombre = _extraer_ticker_de_texto(detalles, detalles, tipo_activo=tipo_activo)
                if not simbolo or monto is None or monto <= Decimal("0"):
                    continue

                monto_abs = abs(monto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                unidades_abs = abs(unidades) if (unidades is not None and unidades != Decimal("0")) else None

                if (precio_ap is None or precio_ap <= Decimal("0")) and unidades_abs is not None and unidades_abs > Decimal("0"):
                    precio_ap = (monto_abs / unidades_abs).quantize(
                        Decimal("0.00000001"), rounding=ROUND_HALF_UP
                    )

                ids_abiertos_ya_agregados.add(pid_norm)
                posiciones_crudas.append(
                    {
                        "simbolo": simbolo,
                        "nombre": nombre,
                        "monto_invertido": monto_abs,
                        "moneda": "USD",
                        "precio_compra": precio_ap,
                        "unidades": unidades_abs,
                        "fecha_compra": fecha_op,
                        "position_id": pid_norm,
                        "notas": f"eToro ID #{pid_norm}",
                    }
                )

    if not posiciones_crudas and not hojas_actividad:
        for nombre_h, filas_h in hojas_filas.items():
            if nombre_h in hojas_cerradas:
                continue
            for reg in _convertir_filas_a_diccionarios(filas_h):
                fecha_cierre_txt = _obtener_campo_exacto_o_parcial(
                    reg, ("close date", "fecha de cierre", "closed")
                )
                if fecha_cierre_txt and fecha_cierre_txt not in ("-", "—"):
                    continue

                pid_raw = _obtener_campo_exacto_o_parcial(
                    reg, ("position id", "id de posición", "id de posicion")
                )
                pid_norm = _normalizar_id_posicion(pid_raw)
                if pid_norm and pid_norm in ids_cerrados:
                    continue

                inst = _obtener_campo_exacto_o_parcial(
                    reg,
                    (
                        "symbol", "símbolo", "simbolo", "ticker", "instrument",
                        "instrumento", "action", "acción", "activo", "name", "nombre",
                    ),
                )
                detalles = _obtener_campo_exacto_o_parcial(
                    reg, ("details", "detalles", "ticker", "symbol")
                )
                tipo_activo = _obtener_campo_exacto_o_parcial(
                    reg, ("asset type", "tipo de activo", "type", "tipo")
                )
                monto = _limpiar_decimal(
                    _obtener_campo_exacto_o_parcial(
                        reg,
                        (
                            "amount", "importe", "monto", "invested",
                            "valor invertido", "capital", "net", "total", "valor",
                        ),
                        excluir_subcadenas=("profit", "spread", "fee", "dividend"),
                    )
                )
                unidades = _limpiar_decimal(
                    _obtener_campo_exacto_o_parcial(
                        reg,
                        (
                            "units / contracts", "unidades / contratos", "units",
                            "unidades", "shares", "cantidad", "títulos", "titulos",
                        ),
                    )
                )
                precio_ap = _limpiar_decimal(
                    _obtener_campo_exacto_o_parcial(
                        reg,
                        (
                            "open rate", "tasa de apertura", "buy price",
                            "precio compra", "precio de compra", "price", "precio", "avg price",
                        ),
                        excluir_subcadenas=("close", "cierre", "take profit", "stop"),
                    )
                )
                moneda = (
                    _obtener_campo_exacto_o_parcial(reg, ("currency", "moneda", "divisa"))
                    .strip()
                    .upper()
                    or "USD"
                )
                if len(moneda) != 3:
                    moneda = "USD"
                fecha_op = _parsear_fecha(
                    _obtener_campo_exacto_o_parcial(
                        reg, ("open date", "fecha de apertura", "date", "fecha"),
                        excluir_subcadenas=("close", "cierre"),
                    )
                )

                simbolo, nombre = _extraer_ticker_de_texto(inst, detalles, tipo_activo=tipo_activo)
                if not simbolo:
                    continue

                if (monto is None or monto <= Decimal("0")) and unidades and precio_ap:
                    monto = (abs(unidades) * abs(precio_ap)).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                if monto is None or monto <= Decimal("0"):
                    continue

                monto_abs = abs(monto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                unidades_abs = abs(unidades) if (unidades is not None and unidades != Decimal("0")) else None
                if (precio_ap is None or precio_ap <= Decimal("0")) and unidades_abs is not None and unidades_abs > Decimal("0"):
                    precio_ap = (monto_abs / unidades_abs).quantize(
                        Decimal("0.00000001"), rounding=ROUND_HALF_UP
                    )

                posiciones_crudas.append(
                    {
                        "simbolo": simbolo,
                        "nombre": nombre,
                        "monto_invertido": monto_abs,
                        "moneda": moneda,
                        "precio_compra": precio_ap,
                        "unidades": unidades_abs,
                        "fecha_compra": fecha_op,
                        "position_id": pid_norm,
                        "notas": f"eToro ID #{pid_norm}" if pid_norm else "Importado desde CSV/Excel",
                    }
                )

    if not posiciones_crudas:
        return []

    if not agrupar_por_ticker:
        return posiciones_crudas

    agrupadas: Dict[Tuple[str, str], Dict[str, object]] = {}
    for pos in posiciones_crudas:
        clave = (str(pos["simbolo"]), str(pos["moneda"]))
        if clave not in agrupadas:
            agrupadas[clave] = dict(pos)
            agrupadas[clave]["_conteo"] = 1
        else:
            actual = agrupadas[clave]
            m_ant: Decimal = actual["monto_invertido"]  # type: ignore[assignment]
            m_nue: Decimal = pos["monto_invertido"]  # type: ignore[assignment]
            m_tot = m_ant + m_nue

            u_ant: Optional[Decimal] = actual.get("unidades")  # type: ignore[assignment]
            u_nue: Optional[Decimal] = pos.get("unidades")  # type: ignore[assignment]
            p_ant: Optional[Decimal] = actual.get("precio_compra")  # type: ignore[assignment]
            p_nue: Optional[Decimal] = pos.get("precio_compra")  # type: ignore[assignment]

            if u_ant is None and p_ant and p_ant > Decimal("0"):
                u_ant = m_ant / p_ant
            if u_nue is None and p_nue and p_nue > Decimal("0"):
                u_nue = m_nue / p_nue

            u_tot = (u_ant + u_nue) if (u_ant is not None and u_nue is not None) else None
            p_prom = (
                (m_tot / u_tot).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
                if (u_tot is not None and u_tot > Decimal("0"))
                else (p_ant or p_nue)
            )

            actual["monto_invertido"] = m_tot.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            actual["unidades"] = u_tot
            actual["precio_compra"] = p_prom
            actual["_conteo"] = int(actual.get("_conteo", 1)) + 1
            actual["notas"] = f"eToro ({actual['_conteo']} operaciones abiertas consolidadas)"

    return list(agrupadas.values())


def generar_plantilla_csv_etoro(ruta_destino: str) -> None:
    encabezados = ["Position ID", "Symbol", "Name", "Amount", "Currency", "Open Rate", "Units", "Open Date"]
    ejemplos = [
        ["284001", "TTWO", "Take-Two Interactive Software, Inc.", "200.00", "USD", "150.00", "1.333333", "2026-03-15"],
        ["284002", "TTWO", "Take-Two Interactive Software, Inc.", "50.00", "USD", "156.25", "0.320000", "2026-05-10"],
        ["284003", "BTC-USD", "Bitcoin (BTC)", "300.00", "USD", "88000.00", "0.003409", "2026-07-01"],
        ["284004", "SOL-USD", "Solana (SOL)", "150.00", "USD", "145.00", "1.034483", "2026-08-10"],
    ]
    with open(ruta_destino, "w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.writer(fh)
        escritor.writerow(encabezados)
        escritor.writerows(ejemplos)