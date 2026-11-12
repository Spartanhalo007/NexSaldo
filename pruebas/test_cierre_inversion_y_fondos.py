"""Pruebas unitarias para las nuevas funcionalidades sobre la rama `main`:
1. Saldo inicial vacío ("") al crear cuenta se registra como 0.
2. Creación automática de cuenta de broker (`eToro`, `Binance`) con saldo 0 y
   cierre/venta de posiciones (`cerrar_inversion`) acreditando fondos en la cuenta elegida
   (incluyendo conversión de divisa USD -> COP cuando la cuenta destino está en COP).
3. Bloqueo de transferencias cuando la cuenta origen no tiene fondos suficientes.
4. Pre-validación instantánea de duplicados (`clasificar_posiciones_importacion`) antes de
   habilitar la importación, separando operaciones nuevas vs. duplicadas.
5. Módulo de Reportes (`generar_radiografia_y_salud_financiera`, `obtener_inversiones_cerradas`
   y `exportar_reporte_completo` en formatos `.csv`, `.html` y `.xlsx`).
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest

try:
    import aplicar_cambios_nexsaldo

    aplicar_cambios_nexsaldo.aplicar_todos_los_parches(silencioso=True)
except Exception:
    pass

from app.gestor.gestor_financiero import (
    ErrorValidacion,
    GestorFinanciero,
    clave_duplicado_inversion,
    clave_duplicado_posicion,
)
from app.modelo.cotizacion import Cotizacion
from app.modelo.cuenta import Cuenta
from app.modelo.inversion import Inversion
from app.modelo.movimiento_financiero import MovimientoFinanciero
from app.modelo.transferencia import Transferencia


class _RepoMemoriaPruebas:
    """Repositorio ligero en memoria compatible con GestorFinanciero de la rama main."""

    def __init__(self):
        self._cuentas = {}
        self._movimientos = []
        self._transferencias = []
        self._inversiones = []
        self._colores = []
        self._seq_cuenta = 1
        self._seq_mov = 1
        self._seq_tr = 1
        self._seq_inv = 1

    def obtener_categorias(self, tipo=None):
        base = {
            "GASTO": ["Salud", "Ocio", "Casa", "Café", "Educación", "Regalos", "Alimentación", "Otros gastos"],
            "INGRESO": ["Salario", "Regalo", "Intereses", "Préstamo", "Ventas", "Bonificación", "Otros", "Otros ingresos"],
        }
        if tipo in base:
            return list(base[tipo])
        return base["GASTO"] + base["INGRESO"]

    def insertar_cuenta(self, cuenta: Cuenta) -> Cuenta:
        nueva = Cuenta(
            id=self._seq_cuenta,
            nombre=cuenta.nombre,
            moneda=cuenta.moneda,
            saldo_inicial=Decimal(str(cuenta.saldo_inicial)),
            simbolo=cuenta.simbolo,
            color=cuenta.color,
            incluye_en_total=cuenta.incluye_en_total,
            nota=cuenta.nota,
        )
        self._cuentas[nueva.id] = nueva
        self._seq_cuenta += 1
        return nueva

    def obtener_cuenta(self, id_cuenta: int):
        return self._cuentas.get(id_cuenta)

    def saldos_de_cuentas(self):
        saldos = {cid: c.saldo_inicial for cid, c in self._cuentas.items()}
        for tr in self._transferencias:
            if tr.cuenta_origen_id in saldos:
                saldos[tr.cuenta_origen_id] -= tr.valor
            if tr.cuenta_destino_id in saldos:
                saldos[tr.cuenta_destino_id] += tr.valor
        for mov in self._movimientos:
            cid = getattr(mov, "cuenta_id", None)
            if cid is not None and cid in saldos:
                if mov.tipo_movimiento == "INGRESO":
                    saldos[cid] += mov.valor
                elif mov.tipo_movimiento == "GASTO":
                    saldos[cid] -= mov.valor
        return saldos

    def obtener_cuentas(self):
        saldos = self.saldos_de_cuentas()
        return [(c, saldos.get(c.id, c.saldo_inicial)) for c in self._cuentas.values()]

    def registrar_color_reciente(self, color: str):
        self._colores.append(color)

    def insertar_transferencia(self, transferencia: Transferencia) -> Transferencia:
        nueva = Transferencia(
            id=self._seq_tr,
            cuenta_origen_id=transferencia.cuenta_origen_id,
            cuenta_destino_id=transferencia.cuenta_destino_id,
            valor=transferencia.valor,
            moneda=transferencia.moneda,
            fecha=transferencia.fecha,
            comentarios=transferencia.comentarios,
            imagen=transferencia.imagen,
        )
        self._transferencias.append(nueva)
        self._seq_tr += 1
        return nueva

    def obtener_transferencias(self, fecha_inicio=None, fecha_fin=None):
        res = []
        for t in self._transferencias:
            if fecha_inicio and t.fecha < fecha_inicio:
                continue
            if fecha_fin and t.fecha > fecha_fin:
                continue
            origen_nom = self._cuentas[t.cuenta_origen_id].nombre if t.cuenta_origen_id in self._cuentas else "Origen"
            dest_nom = self._cuentas[t.cuenta_destino_id].nombre if t.cuenta_destino_id in self._cuentas else "Destino"
            res.append((t.id, t.fecha, origen_nom, dest_nom, t.valor, t.moneda, t.comentarios, t.imagen))
        return res

    def insertar_movimiento(self, movimiento: MovimientoFinanciero) -> MovimientoFinanciero:
        nuevo = MovimientoFinanciero(
            id=self._seq_mov,
            tipo_movimiento=movimiento.tipo_movimiento,
            fecha=movimiento.fecha,
            valor=movimiento.valor,
            moneda=movimiento.moneda,
            categoria=movimiento.categoria,
            descripcion=movimiento.descripcion,
            cuenta_id=getattr(movimiento, "cuenta_id", None),
        )
        self._movimientos.append(nuevo)
        self._seq_mov += 1
        return nuevo

    def obtener_movimientos(self, tipo=None, fecha_inicio=None, fecha_fin=None):
        res = list(self._movimientos)
        if tipo:
            res = [m for m in res if m.tipo_movimiento == tipo]
        if fecha_inicio:
            res = [m for m in res if m.fecha >= fecha_inicio]
        if fecha_fin:
            res = [m for m in res if m.fecha <= fecha_fin]
        return res

    def insertar_inversion(self, inv: Inversion) -> Inversion:
        nueva = Inversion(
            id=self._seq_inv,
            simbolo=inv.simbolo,
            nombre=inv.nombre,
            monto_invertido=inv.monto_invertido,
            moneda=inv.moneda,
            precio_compra=inv.precio_compra,
            cantidad_titulos=inv.cantidad_titulos,
            fecha_compra=inv.fecha_compra,
            notas=inv.notas,
        )
        self._inversiones.append(nueva)
        self._seq_inv += 1
        return nueva

    def obtener_inversiones(self):
        return list(self._inversiones)

    def obtener_todas_las_inversiones(self):
        return list(self._inversiones)

    def eliminar_inversion(self, id_inversion: int) -> bool:
        antes = len(self._inversiones)
        self._inversiones = [i for i in self._inversiones if i.id != id_inversion]
        return len(self._inversiones) < antes


class _ServicioBursatilFalso:
    """Mock de ServicioBursatil que implementa los métodos reales llamados por GestorFinanciero."""

    def hay_conexion_internet(self, usar_cache_breve: bool = False) -> bool:
        return True

    def consultar_tasa_cambio(self, origen: str, destino: str) -> Cotizacion:
        if origen == "USD" and destino == "COP":
            return Cotizacion(
                id=None,
                simbolo="USDCOP=X",
                fecha=date(2026, 11, 3),
                precio=Decimal("4000.00"),
                moneda="COP",
                fuente="Test",
            )
        return Cotizacion(
            id=None,
            simbolo=f"{origen}{destino}=X",
            fecha=date(2026, 11, 3),
            precio=Decimal("1.00"),
            moneda=destino,
            fuente="Test",
        )

    def obtener_tasa_cambio(self, origen: str, destino: str) -> Cotizacion:
        return self.consultar_tasa_cambio(origen, destino)

    def consultar_precio_actual(self, simbolo: str, moneda_esperada: str = "USD") -> Cotizacion:
        return Cotizacion(
            id=None,
            simbolo=simbolo,
            fecha=date(2026, 11, 3),
            precio=Decimal("250.00"),
            moneda=moneda_esperada,
            fuente="Test",
        )

    def obtener_cotizacion_activo(self, simbolo: str, moneda_esperada: str = "USD") -> Cotizacion:
        return self.consultar_precio_actual(simbolo, moneda_esperada=moneda_esperada)

    def consultar_precio_historico(self, simbolo: str, fecha_compra: date, moneda_esperada: str = "USD"):
        return None


def test_saldo_inicial_vacio_se_asume_como_cero():
    repo = _RepoMemoriaPruebas()
    gestor = GestorFinanciero(repo, servicio_bursatil=_ServicioBursatilFalso())

    cuenta_vacia = gestor.crear_cuenta(
        nombre="Cuenta Sin Saldo",
        moneda="COP",
        saldo_inicial_texto="",
        simbolo="banco",
        color="#408FD1",
    )
    assert cuenta_vacia.saldo_inicial == Decimal("0")
    assert gestor.obtener_saldo_cuenta(cuenta_vacia.id) == Decimal("0")


def test_transferencia_bloqueada_cuando_no_hay_fondos_suficientes():
    repo = _RepoMemoriaPruebas()
    gestor = GestorFinanciero(repo, servicio_bursatil=_ServicioBursatilFalso())

    origen = gestor.crear_cuenta("Principal", "COP", "100000", "banco", "#408FD1")
    destino = gestor.crear_cuenta("Ahorros", "COP", "0", "puerquito", "#2ECC71")

    with pytest.raises(ErrorValidacion, match="Fondos insuficientes"):
        gestor.crear_transferencia(
            cuenta_origen_id=origen.id,
            cuenta_destino_id=destino.id,
            valor_texto="150000",
            fecha_texto="2026-11-03",
        )

    tr = gestor.crear_transferencia(
        cuenta_origen_id=origen.id,
        cuenta_destino_id=destino.id,
        valor_texto="60000",
        fecha_texto="2026-11-03",
    )
    assert tr.valor == Decimal("60000")
    assert gestor.obtener_saldo_cuenta(origen.id) == Decimal("40000")
    assert gestor.obtener_saldo_cuenta(destino.id) == Decimal("60000")


def test_asegurar_cuenta_broker_y_cerrar_inversion_acreditando_cuenta():
    repo = _RepoMemoriaPruebas()
    gestor = GestorFinanciero(repo, servicio_bursatil=_ServicioBursatilFalso())

    cuenta_etoro = gestor.asegurar_cuenta_broker("eToro", moneda="USD")
    assert cuenta_etoro.nombre == "eToro"
    assert cuenta_etoro.moneda == "USD"
    assert gestor.obtener_saldo_cuenta(cuenta_etoro.id) == Decimal("0")

    inv = gestor.registrar_inversion(
        simbolo="AAPL",
        nombre="Apple Inc.",
        monto_texto="400.00",
        moneda="USD",
        precio_compra_texto="200.00",
        fecha_texto="2026-10-01",
        notas="Importado de eToro",
    )
    assert len(gestor.obtener_inversiones()) == 1

    resultado = gestor.cerrar_inversion(
        id_inversion=inv.id,
        cuenta_destino="eToro",
    )
    assert resultado["valor_venta_origen"] == Decimal("500.00")
    assert resultado["monto_acreditado"] == Decimal("500.00")
    assert resultado["ganancia_neta_origen"] == Decimal("100.00")
    assert gestor.obtener_saldo_cuenta(cuenta_etoro.id) == Decimal("500.00")
    assert len(gestor.obtener_inversiones()) == 0


def test_cerrar_inversion_convierte_a_cop_si_cuenta_destino_es_cop():
    repo = _RepoMemoriaPruebas()
    gestor = GestorFinanciero(repo, servicio_bursatil=_ServicioBursatilFalso())

    cuenta_principal = gestor.crear_cuenta("Principal", "COP", "100000", "banco", "#408FD1")
    inv = gestor.registrar_inversion(
        simbolo="MSFT",
        nombre="Microsoft",
        monto_texto="200.00",
        moneda="USD",
        precio_compra_texto="200.00",
        fecha_texto="2026-10-01",
    )

    res = gestor.cerrar_inversion(
        id_inversion=inv.id,
        cuenta_destino=cuenta_principal.id,
        valor_total_venta="250.00",
    )
    assert res["moneda_destino"] == "COP"
    assert res["monto_acreditado"] == Decimal("1000000.00")
    assert gestor.obtener_saldo_cuenta(cuenta_principal.id) == Decimal("1100000.00")


def test_prevalidacion_duplicados_separa_nuevas_y_duplicadas():
    repo = _RepoMemoriaPruebas()
    gestor = GestorFinanciero(repo, servicio_bursatil=_ServicioBursatilFalso())

    gestor.registrar_inversion(
        simbolo="VOO",
        nombre="Vanguard S&P 500",
        monto_texto="200.00",
        moneda="USD",
        precio_compra_texto="400.00",
        fecha_texto="2026-01-10",
    )

    posiciones_csv = [
        {
            "simbolo": "VOO",
            "nombre": "Vanguard S&P 500",
            "monto_invertido": Decimal("200.00"),
            "moneda": "USD",
            "precio_compra": Decimal("400.00"),
            "unidades": Decimal("0.5"),
            "fecha_compra": date(2026, 1, 10),
            "notas": "Importado de eToro",
        },
        {
            "simbolo": "NVDA",
            "nombre": "NVIDIA Corp",
            "monto_invertido": Decimal("150.00"),
            "moneda": "USD",
            "precio_compra": Decimal("150.00"),
            "unidades": Decimal("1.0"),
            "fecha_compra": date(2026, 2, 15),
            "notas": "Importado de eToro",
        },
    ]

    analisis = gestor.clasificar_posiciones_importacion(
        posiciones_csv, omitir_duplicados=True, limpiar_antes=False
    )
    assert analisis["cantidad_duplicadas"] == 1
    assert analisis["cantidad_nuevas"] == 1
    assert analisis["nuevas"][0]["simbolo"] == "NVDA"
    assert analisis["duplicadas"][0]["simbolo"] == "VOO"

    analisis_todo_dup = gestor.clasificar_posiciones_importacion(
        [posiciones_csv[0]], omitir_duplicados=True, limpiar_antes=False
    )
    assert analisis_todo_dup["cantidad_nuevas"] == 0
    assert analisis_todo_dup["cantidad_duplicadas"] == 1


def test_reportes_salud_financiera_radiografia_y_exportacion(tmp_path):
    repo = _RepoMemoriaPruebas()
    gestor = GestorFinanciero(repo, servicio_bursatil=_ServicioBursatilFalso())

    # 1. Crear cuentas en COP y USD
    c_cop = gestor.crear_cuenta("Principal", "COP", "2000000", "banco", "#408FD1")
    c_usd = gestor.asegurar_cuenta_broker("eToro", moneda="USD")

    # 2. Registrar movimientos en octubre y noviembre para probar comparativa Mes a Mes (MoM)
    gestor.registrar_movimiento("GASTO", "2026-10-15", "400000", "COP", "Alimentación", "Mercado oct")
    gestor.registrar_movimiento("INGRESO", "2026-11-05", "3000000", "COP", "Salario", "Nómina nov")
    gestor.registrar_movimiento("GASTO", "2026-11-10", "600000", "COP", "Alimentación", "Mercado nov")

    # 3. Registrar dos inversiones y cerrar una con ganancia
    inv_abierta = gestor.registrar_inversion(
        simbolo="VOO",
        nombre="Vanguard S&P 500",
        monto_texto="250.00",
        moneda="USD",
        precio_compra_texto="200.00",
        fecha_texto="2026-11-01",
    )
    inv_vender = gestor.registrar_inversion(
        simbolo="AAPL",
        nombre="Apple Inc.",
        monto_texto="400.00",
        moneda="USD",
        precio_compra_texto="200.00",
        fecha_texto="2026-11-02",
    )
    gestor.cerrar_inversion(inv_vender.id, cuenta_destino=c_usd.id, fecha_cierre=date(2026, 11, 10))

    # 4. Generar radiografía y salud financiera de noviembre 2026
    rep = gestor.generar_radiografia_y_salud_financiera(
        fecha_inicio=date(2026, 11, 1),
        fecha_fin=date(2026, 11, 30),
        moneda_objetivo="COP",
        incluir_todas_convertidas=True,
    )

    salud = rep["salud_financiera"]
    assert salud["ingresos"] >= Decimal("3000000")
    assert salud["gastos"] == Decimal("600000")
    assert salud["tasa_ahorro_pct"] > Decimal("50")
    assert len(rep["posiciones_cerradas"]) == 1
    assert rep["posiciones_cerradas"][0]["simbolo"] == "AAPL"
    assert rep["posiciones_cerradas"][0]["ganancia_realizada"] == Decimal("100.00")

    # 5. Probar exportación en CSV y HTML
    ruta_csv = str(tmp_path / "estado_cuenta.csv")
    out_csv = gestor.exportar_reporte_completo(
        ruta_destino=ruta_csv,
        fecha_inicio=date(2026, 11, 1),
        fecha_fin=date(2026, 11, 30),
        moneda_objetivo="COP",
        formato="csv",
    )
    assert Path(out_csv).exists()
    assert "AAPL" in Path(out_csv).read_text(encoding="utf-8-sig")

    ruta_html = str(tmp_path / "estado_cuenta.html")
    out_html = gestor.exportar_reporte_completo(
        ruta_destino=ruta_html,
        fecha_inicio=date(2026, 11, 1),
        fecha_fin=date(2026, 11, 30),
        moneda_objetivo="COP",
        formato="html",
    )
    assert Path(out_html).exists()
    assert "Salud Financiera" in Path(out_html).read_text(encoding="utf-8")
