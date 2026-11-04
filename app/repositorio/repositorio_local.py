"""Repositorio local sobre PostgreSQL para NexSaldo."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import psycopg2

from app.configuracion import ConfiguracionBD
from app.modelo.categoria import Categoria
from app.modelo.cuenta import Cuenta
from app.modelo.etiqueta import Etiqueta
from app.modelo.movimiento_financiero import MovimientoFinanciero
from app.modelo.transferencia import Transferencia

RUTA_ESQUEMA = Path(__file__).resolve().parents[2] / "sql" / "esquema_inicial.sql"

CATEGORIAS_PREDETERMINADAS_BASE = (
    Categoria(None, "Salud", "GASTO", "corazon_pulso", "#F28C8C", True),
    Categoria(None, "Ocio", "GASTO", "billetera", "#408FD1", True),
    Categoria(None, "Casa", "GASTO", "casa", "#FBB718", True),
    Categoria(None, "Café", "GASTO", "cubiertos", "#D98A4E", True),
    Categoria(None, "Educación", "GASTO", "graduacion", "#9B7EDE", True),
    Categoria(None, "Regalos", "GASTO", "regalo", "#E86F9A", True),
    Categoria(None, "Alimentación", "GASTO", "mercado", "#7DC98F", True),
)


class RepositorioLocal:
    """Gestiona la persistencia local en PostgreSQL."""

    def __init__(self, configuracion: ConfiguracionBD):
        self._configuracion = configuracion
        self._conexion = None
        self.conectar()
        self.aplicar_esquema()

    def conectar(self):
        if self._conexion is None or self._conexion.closed:
            self._conexion = psycopg2.connect(
                host=self._configuracion.host,
                port=self._configuracion.puerto,
                dbname=self._configuracion.nombre,
                user=self._configuracion.usuario,
                password=self._configuracion.contrasena,
            )
        return self._conexion

    def cerrar(self):
        if self._conexion is not None and not self._conexion.closed:
            self._conexion.close()

    def aplicar_esquema(self) -> bool:
        if not RUTA_ESQUEMA.exists():
            return False
        sql = RUTA_ESQUEMA.read_text(encoding="utf-8")
        conexion = self.conectar()
        with conexion.cursor() as cursor:
            cursor.execute(sql)
        conexion.commit()
        return True

    def ejecutar_consulta(self, sql: str, parametros=None):
        conexion = self.conectar()
        with conexion.cursor() as cursor:
            cursor.execute(sql, parametros or ())
            if cursor.description is not None:
                filas = cursor.fetchall()
            else:
                filas = []
        conexion.commit()
        return filas

    # ------------------------------------------------------------------
    # Categorías (compatible con versión original + categorías ricas)
    # ------------------------------------------------------------------
    def obtener_categorias(self) -> List[str]:
        filas = self.ejecutar_consulta("SELECT nombre FROM categoria ORDER BY nombre")
        return [fila[0] for fila in filas]

    def obtener_categorias_detalladas(self, tipo: Optional[str] = None) -> List[Categoria]:
        if tipo:
            sql = """
                SELECT id, nombre, COALESCE(tipo, 'GASTO'), COALESCE(simbolo, 'mercado'),
                       COALESCE(color, '#FBB718'), COALESCE(es_predeterminada, FALSE),
                       COALESCE(gasto_programado, FALSE), frecuencia
                FROM categoria
                WHERE COALESCE(tipo, 'GASTO') = %s
                ORDER BY es_predeterminada DESC, id ASC
            """
            filas = self.ejecutar_consulta(sql, (tipo.upper(),))
        else:
            sql = """
                SELECT id, nombre, COALESCE(tipo, 'GASTO'), COALESCE(simbolo, 'mercado'),
                       COALESCE(color, '#FBB718'), COALESCE(es_predeterminada, FALSE),
                       COALESCE(gasto_programado, FALSE), frecuencia
                FROM categoria
                ORDER BY es_predeterminada DESC, id ASC
            """
            filas = self.ejecutar_consulta(sql)
        return [
            Categoria(
                id=f[0],
                nombre=f[1],
                tipo=f[2],
                simbolo=f[3],
                color=f[4],
                es_predeterminada=bool(f[5]),
                gasto_programado=bool(f[6]),
                frecuencia=f[7],
            )
            for f in filas
        ]

    def insertar_categoria(self, categoria: Categoria) -> Categoria:
        conexion = self.conectar()
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO categoria (
                    nombre, tipo, simbolo, color, es_predeterminada, gasto_programado, frecuencia
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (nombre) DO UPDATE SET
                    tipo = EXCLUDED.tipo,
                    simbolo = EXCLUDED.simbolo,
                    color = EXCLUDED.color,
                    gasto_programado = EXCLUDED.gasto_programado,
                    frecuencia = EXCLUDED.frecuencia
                RETURNING id
                """,
                (
                    categoria.nombre,
                    categoria.tipo,
                    categoria.simbolo,
                    categoria.color,
                    categoria.es_predeterminada,
                    categoria.gasto_programado,
                    categoria.frecuencia,
                ),
            )
            nuevo_id = cursor.fetchone()[0]
        conexion.commit()
        return categoria.con_id(nuevo_id)

    # ------------------------------------------------------------------
    # Etiquetas 100% customizables
    # ------------------------------------------------------------------
    def obtener_etiquetas(self) -> List[Etiqueta]:
        filas = self.ejecutar_consulta(
            "SELECT id, nombre, COALESCE(color, '#408FD1') FROM etiqueta ORDER BY nombre ASC"
        )
        return [Etiqueta(id=f[0], nombre=f[1], color=f[2]) for f in filas]

    def insertar_etiqueta(self, etiqueta: Etiqueta) -> Etiqueta:
        conexion = self.conectar()
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO etiqueta (nombre, color)
                VALUES (%s, %s)
                ON CONFLICT (nombre) DO UPDATE SET color = EXCLUDED.color
                RETURNING id
                """,
                (etiqueta.nombre, etiqueta.color),
            )
            nuevo_id = cursor.fetchone()[0]
        conexion.commit()
        return etiqueta.con_id(nuevo_id)

    def _obtener_etiquetas_de_movimiento(self, movimiento_id: int) -> Tuple[str, ...]:
        filas = self.ejecutar_consulta(
            """
            SELECT e.nombre
            FROM etiqueta e
            JOIN movimiento_etiqueta me ON me.etiqueta_id = e.id
            WHERE me.movimiento_id = %s
            ORDER BY e.nombre ASC
            """,
            (movimiento_id,),
        )
        return tuple(f[0] for f in filas)

    # ------------------------------------------------------------------
    # Movimientos financieros y Gastos
    # ------------------------------------------------------------------
    def insertar_movimiento(self, movimiento: MovimientoFinanciero) -> MovimientoFinanciero:
        conexion = self.conectar()
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM categoria WHERE nombre = %s",
                (movimiento.categoria,),
            )
            fila_cat = cursor.fetchone()
            if fila_cat is None:
                raise LookupError(f"La categoría '{movimiento.categoria}' no existe.")
            categoria_id = fila_cat[0]

            cursor.execute(
                """
                INSERT INTO movimiento_financiero (
                    tipo_movimiento, fecha, valor, moneda, categoria_id,
                    descripcion, cuenta_id, imagen, es_programado, frecuencia
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    movimiento.tipo_movimiento,
                    movimiento.fecha,
                    movimiento.valor,
                    movimiento.moneda,
                    categoria_id,
                    movimiento.descripcion,
                    movimiento.cuenta_id,
                    movimiento.imagen,
                    movimiento.es_programado,
                    movimiento.frecuencia,
                ),
            )
            nuevo_id = cursor.fetchone()[0]

            etiquetas_limpias = getattr(movimiento, "etiquetas", ()) or ()
            for nombre_et in etiquetas_limpias:
                cursor.execute(
                    """
                    INSERT INTO etiqueta (nombre)
                    VALUES (%s)
                    ON CONFLICT (nombre) DO UPDATE SET nombre = EXCLUDED.nombre
                    RETURNING id
                    """,
                    (nombre_et,),
                )
                etiqueta_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO movimiento_etiqueta (movimiento_id, etiqueta_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (nuevo_id, etiqueta_id),
                )
        conexion.commit()
        return movimiento.con_id(nuevo_id)

    def obtener_movimientos(
        self,
        tipo: Optional[str] = None,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> List[MovimientoFinanciero]:
        condiciones = []
        parametros = []
        if tipo is not None:
            condiciones.append("m.tipo_movimiento = %s")
            parametros.append(tipo)
        if fecha_inicio is not None:
            condiciones.append("m.fecha >= %s")
            parametros.append(fecha_inicio)
        if fecha_fin is not None:
            condiciones.append("m.fecha <= %s")
            parametros.append(fecha_fin)

        clausula_where = ""
        if condiciones:
            clausula_where = "WHERE " + " AND ".join(condiciones)

        sql = f"""
            SELECT m.id, m.tipo_movimiento, m.fecha, m.valor, m.moneda,
                   c.nombre, m.descripcion, m.cuenta_id, m.imagen,
                   COALESCE(m.es_programado, FALSE), m.frecuencia
            FROM movimiento_financiero m
            JOIN categoria c ON c.id = m.categoria_id
            {clausula_where}
            ORDER BY m.fecha DESC, m.id DESC
        """
        filas = self.ejecutar_consulta(sql, tuple(parametros))
        resultado = []
        for f in filas:
            etiquetas = self._obtener_etiquetas_de_movimiento(f[0])
            resultado.append(
                MovimientoFinanciero(
                    id=f[0],
                    tipo_movimiento=f[1],
                    fecha=f[2],
                    valor=Decimal(str(f[3])),
                    moneda=f[4].strip(),
                    categoria=f[5],
                    descripcion=f[6],
                    cuenta_id=f[7],
                    etiquetas=etiquetas,
                    imagen=f[8],
                    es_programado=bool(f[9]),
                    frecuencia=f[10],
                )
            )
        return resultado

    def obtener_ultima_fecha_movimiento(self, tipo: str = "GASTO") -> Optional[date]:
        filas = self.ejecutar_consulta(
            """
            SELECT m.fecha
            FROM movimiento_financiero m
            WHERE m.tipo_movimiento = %s
            ORDER BY m.fecha_registro DESC, m.id DESC
            LIMIT 1
            """,
            (tipo,),
        )
        return filas[0][0] if filas else None

    def resumen_mensual(self, anno: int, mes: int) -> List[Tuple[str, str, str, Decimal]]:
        sql = """
            SELECT m.tipo_movimiento, m.moneda, c.nombre, SUM(m.valor)
            FROM movimiento_financiero m
            JOIN categoria c ON c.id = m.categoria_id
            WHERE EXTRACT(YEAR FROM m.fecha) = %s AND EXTRACT(MONTH FROM m.fecha) = %s
            GROUP BY m.tipo_movimiento, m.moneda, c.nombre
            ORDER BY c.nombre
        """
        filas = self.ejecutar_consulta(sql, (anno, mes))
        return [(f[0], f[1].strip(), f[2], Decimal(str(f[3]))) for f in filas]

    def resumen_por_rango(
        self,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        tipo: str = "GASTO",
    ) -> List[Tuple[str, str, Decimal, str, str]]:
        """Retorna [(moneda, categoria_nombre, total_decimal, color, simbolo), ...] para el rango."""
        condiciones = ["m.tipo_movimiento = %s"]
        parametros: list = [tipo]
        if fecha_inicio is not None:
            condiciones.append("m.fecha >= %s")
            parametros.append(fecha_inicio)
        if fecha_fin is not None:
            condiciones.append("m.fecha <= %s")
            parametros.append(fecha_fin)

        where_sql = "WHERE " + " AND ".join(condiciones)
        sql = f"""
            SELECT m.moneda, c.nombre, SUM(m.valor),
                   COALESCE(c.color, '#FBB718'), COALESCE(c.simbolo, 'mercado')
            FROM movimiento_financiero m
            JOIN categoria c ON c.id = m.categoria_id
            {where_sql}
            GROUP BY m.moneda, c.nombre, c.color, c.simbolo
            ORDER BY SUM(m.valor) DESC, c.nombre ASC
        """
        filas = self.ejecutar_consulta(sql, tuple(parametros))
        return [
            (f[0].strip(), f[1], Decimal(str(f[2])), f[3], f[4])
            for f in filas
        ]

    def eliminar_movimiento(self, id_movimiento: int) -> bool:
        conexion = self.conectar()
        with conexion.cursor() as cursor:
            cursor.execute(
                "DELETE FROM movimiento_financiero WHERE id = %s RETURNING id",
                (id_movimiento,),
            )
            eliminado = cursor.fetchone() is not None
        conexion.commit()
        return eliminado

    # ------------------------------------------------------------------
    # Cuentas y Saldos (descuenta gastos asociados a cuenta_id e incluye ingresos)
    # ------------------------------------------------------------------
    def insertar_cuenta(self, cuenta: Cuenta) -> Cuenta:
        conexion = self.conectar()
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO cuenta (nombre, moneda, saldo_inicial, simbolo, color, incluye_en_total, nota)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    cuenta.nombre,
                    cuenta.moneda,
                    cuenta.saldo_inicial,
                    cuenta.simbolo,
                    cuenta.color,
                    cuenta.incluye_en_total,
                    cuenta.nota,
                ),
            )
            nuevo_id = cursor.fetchone()[0]
        conexion.commit()
        return cuenta.con_id(nuevo_id)

    def obtener_cuentas(self) -> List[Tuple[Cuenta, Decimal]]:
        sql = """
            SELECT c.id, c.nombre, c.moneda, c.saldo_inicial, c.simbolo,
                   c.color, c.incluye_en_total, c.nota,
                   c.saldo_inicial
                   + COALESCE((SELECT SUM(t.valor) FROM transferencia t WHERE t.cuenta_destino_id = c.id), 0)
                   - COALESCE((SELECT SUM(t.valor) FROM transferencia t WHERE t.cuenta_origen_id = c.id), 0)
                   + COALESCE((SELECT SUM(m.valor) FROM movimiento_financiero m WHERE m.cuenta_id = c.id AND m.tipo_movimiento = 'INGRESO'), 0)
                   - COALESCE((SELECT SUM(m.valor) FROM movimiento_financiero m WHERE m.cuenta_id = c.id AND m.tipo_movimiento = 'GASTO'), 0)
                   AS saldo_actual
            FROM cuenta c
            ORDER BY c.nombre
        """
        filas = self.ejecutar_consulta(sql)
        resultado = []
        for f in filas:
            cuenta = Cuenta(
                id=f[0],
                nombre=f[1],
                moneda=f[2].strip(),
                saldo_inicial=Decimal(str(f[3])),
                simbolo=f[4],
                color=f[5],
                incluye_en_total=bool(f[6]),
                nota=f[7],
            )
            resultado.append((cuenta, Decimal(str(f[8]))))
        return resultado

    def obtener_cuenta(self, id_cuenta: int) -> Optional[Cuenta]:
        filas = self.ejecutar_consulta(
            """
            SELECT id, nombre, moneda, saldo_inicial, simbolo, color, incluye_en_total, nota
            FROM cuenta
            WHERE id = %s
            """,
            (id_cuenta,),
        )
        if not filas:
            return None
        f = filas[0]
        return Cuenta(
            id=f[0],
            nombre=f[1],
            moneda=f[2].strip(),
            saldo_inicial=Decimal(str(f[3])),
            simbolo=f[4],
            color=f[5],
            incluye_en_total=bool(f[6]),
            nota=f[7],
        )

    def saldos_de_cuentas(self) -> Dict[int, Decimal]:
        sql = """
            SELECT c.id,
                   c.saldo_inicial
                   + COALESCE((SELECT SUM(t.valor) FROM transferencia t WHERE t.cuenta_destino_id = c.id), 0)
                   - COALESCE((SELECT SUM(t.valor) FROM transferencia t WHERE t.cuenta_origen_id = c.id), 0)
                   + COALESCE((SELECT SUM(m.valor) FROM movimiento_financiero m WHERE m.cuenta_id = c.id AND m.tipo_movimiento = 'INGRESO'), 0)
                   - COALESCE((SELECT SUM(m.valor) FROM movimiento_financiero m WHERE m.cuenta_id = c.id AND m.tipo_movimiento = 'GASTO'), 0)
            FROM cuenta c
        """
        filas = self.ejecutar_consulta(sql)
        return {f[0]: Decimal(str(f[1])) for f in filas}

    # ------------------------------------------------------------------
    # Transferencias y Colores Recientes
    # ------------------------------------------------------------------
    def insertar_transferencia(self, transferencia: Transferencia) -> Transferencia:
        conexion = self.conectar()
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO transferencia (
                    cuenta_origen_id, cuenta_destino_id, valor, moneda, fecha, comentarios, imagen
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    transferencia.cuenta_origen_id,
                    transferencia.cuenta_destino_id,
                    transferencia.valor,
                    transferencia.moneda,
                    transferencia.fecha,
                    transferencia.comentarios,
                    transferencia.imagen,
                ),
            )
            nuevo_id = cursor.fetchone()[0]
        conexion.commit()
        return transferencia.con_id(nuevo_id)

    def obtener_transferencias(self, fecha_inicio=None, fecha_fin=None):
     condiciones = []
     parametros = []
     if fecha_inicio is not None:
         condiciones.append("t.fecha >= %s")
         parametros.append(fecha_inicio)
     if fecha_fin is not None:
         condiciones.append("t.fecha <= %s")
         parametros.append(fecha_fin)
     where_sql = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
     filas = self.ejecutar_consulta(
         f"""
         SELECT t.id, t.fecha, co.nombre, cd.nombre, t.valor, t.moneda, t.comentarios
         FROM transferencia t
         JOIN cuenta co ON co.id = t.cuenta_origen_id
         JOIN cuenta cd ON cd.id = t.cuenta_destino_id
         {where_sql}
         ORDER BY t.fecha DESC, t.id DESC
         """,
         tuple(parametros),
     )
     return [
         (
             f[0],
             f[1],
             f[2],
             f[3],
             Decimal(str(f[4])),
             f[5].strip(),
             f[6],
         )
         for f in filas
     ]

    def registrar_color_reciente(self, color: str):
        conexion = self.conectar()
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO color_reciente (valor, fecha_uso)
                VALUES (%s, CURRENT_TIMESTAMP)
                ON CONFLICT (valor) DO UPDATE SET fecha_uso = CURRENT_TIMESTAMP
                """,
                (color.upper(),),
            )
        conexion.commit()

    def obtener_colores_recientes(self, maximo: int = 8) -> List[str]:
        filas = self.ejecutar_consulta(
            """
            SELECT valor FROM color_reciente
            ORDER BY fecha_uso DESC
            LIMIT %s
            """,
            (maximo,),
        )
        return [f[0] for f in filas]
