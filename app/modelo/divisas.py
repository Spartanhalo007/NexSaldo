"""Catálogo ISO 4217 de todas las divisas fiduciarias del mundo (sin criptomonedas)."""

from typing import Dict, List, Sequence, Tuple

# Diccionario {codigo_iso: (nombre_espanol, simbolo_prefijo)}
DIVISAS_MUNDIALES: Dict[str, Tuple[str, str]] = {
    "AED": ("Dírham de los Emiratos Árabes Unidos", "AED"),
    "AFN": ("Afgani afgano", "AFN"),
    "ALL": ("Lek albanés", "ALL"),
    "AMD": ("Dram armenio", "AMD"),
    "ANG": ("Florín antillano neerlandés", "ANG"),
    "AOA": ("Kwanza angoleño", "AOA"),
    "ARS": ("Peso argentino", "AR$"),
    "AUD": ("Dólar australiano", "A$"),
    "AWG": ("Florín arubeño", "AWG"),
    "AZN": ("Manat azerbaiyano", "AZN"),
    "BAM": ("Marco convertible de Bosnia y Herzegovina", "BAM"),
    "BBD": ("Dólar de Barbados", "BBD"),
    "BDT": ("Taka bangladesí", "BDT"),
    "BGN": ("Lev búlgaro", "BGN"),
    "BHD": ("Dinar bareiní", "BHD"),
    "BIF": ("Franco burundés", "BIF"),
    "BMD": ("Dólar bermudeño", "BMD"),
    "BND": ("Dólar de Brunéi", "BND"),
    "BOB": ("Boliviano", "Bs."),
    "BRL": ("Real brasileño", "R$"),
    "BSD": ("Dólar bahameño", "BSD"),
    "BTN": ("Ngultrum butanés", "BTN"),
    "BWP": ("Pula botsuano", "BWP"),
    "BYN": ("Rublo bielorruso", "BYN"),
    "BZD": ("Dólar beliceño", "BZD"),
    "CAD": ("Dólar canadiense", "CA$"),
    "CDF": ("Franco congoleño", "CDF"),
    "CHF": ("Franco suizo", "CHF"),
    "CLP": ("Peso chileno", "CLP$"),
    "CNY": ("Yuan renminbi chino", "CN¥"),
    "COP": ("Peso colombiano", "$"),
    "CRC": ("Colón costarricense", "₡"),
    "CUP": ("Peso cubano", "CUP"),
    "CVE": ("Escudo caboverdiano", "CVE"),
    "CZK": ("Corona checa", "Kč"),
    "DJF": ("Franco yibutiano", "DJF"),
    "DKK": ("Corona danesa", "DKK"),
    "DOP": ("Peso dominicano", "RD$"),
    "DZD": ("Dinar argelino", "DZD"),
    "EGP": ("Libra egipcia", "EGP"),
    "ERN": ("Nakfa eritreo", "ERN"),
    "ETB": ("Birr etíope", "ETB"),
    "EUR": ("Euro", "€"),
    "FJD": ("Dólar fiyiano", "FJD"),
    "FKP": ("Libra malvinense", "FKP"),
    "GBP": ("Libra esterlina", "£"),
    "GEL": ("Lari georgiano", "GEL"),
    "GHS": ("Cedi ghanés", "GHS"),
    "GIP": ("Libra gibraltareña", "GIP"),
    "GMD": ("Dalasi gambiano", "GMD"),
    "GNF": ("Franco guineano", "GNF"),
    "GTQ": ("Quetzal guatemalteco", "Q"),
    "GYD": ("Dólar guyanés", "GYD"),
    "HKD": ("Dólar de Hong Kong", "HK$"),
    "HNL": ("Lempira hondureño", "L"),
    "HTG": ("Gourde haitiano", "HTG"),
    "HUF": ("Forinto húngaro", "Ft"),
    "IDR": ("Rupia indonesia", "Rp"),
    "ILS": ("Nuevo séquel israelí", "₪"),
    "INR": ("Rupia india", "₹"),
    "IQD": ("Dinar iraquí", "IQD"),
    "IRR": ("Rial iraní", "IRR"),
    "ISK": ("Corona islandesa", "ISK"),
    "JMD": ("Dólar jamaiquino", "J$"),
    "JOD": ("Dinar jordano", "JOD"),
    "JPY": ("Yen japonés", "¥"),
    "KES": ("Chelín keniano", "KES"),
    "KGS": ("Som kirguís", "KGS"),
    "KHR": ("Riel camboyano", "KHR"),
    "KMF": ("Franco comorense", "KMF"),
    "KRW": ("Won surcoreano", "₩"),
    "KWD": ("Dinar kuwaití", "KWD"),
    "KYD": ("Dólar de las Islas Caimán", "KYD"),
    "KZT": ("Tenge kazajo", "₸"),
    "LAK": ("Kip laosiano", "₭"),
    "LBP": ("Libra libanesa", "LBP"),
    "LKR": ("Rupia esrilanquesa", "LKR"),
    "LRD": ("Dólar liberiano", "LRD"),
    "LSL": ("Loti lesotense", "LSL"),
    "LYD": ("Dinar libio", "LYD"),
    "MAD": ("Dírham marroquí", "MAD"),
    "MDL": ("Leu moldavo", "MDL"),
    "MGA": ("Ariary malgache", "MGA"),
    "MKD": ("Denar macedonio", "MKD"),
    "MMK": ("Kyat birmano", "MMK"),
    "MNT": ("Tugrik mongol", "₮"),
    "MOP": ("Pataca macaense", "MOP"),
    "MRU": ("Uguiya mauritano", "MRU"),
    "MUR": ("Rupia mauriciana", "MUR"),
    "MVR": ("Rufiyaa maldiva", "MVR"),
    "MWK": ("Kwacha malauí", "MWK"),
    "MXN": ("Peso mexicano", "MX$"),
    "MYR": ("Ringgit malayo", "RM"),
    "MZN": ("Metical mozambiqueño", "MZN"),
    "NAD": ("Dólar namibio", "NAD"),
    "NGN": ("Naira nigeriano", "₦"),
    "NIO": ("Córdoba nicaragüense", "C$"),
    "NOK": ("Corona noruega", "NOK"),
    "NPR": ("Rupia nepalí", "NPR"),
    "NZD": ("Dólar neozelandés", "NZ$"),
    "OMR": ("Rial omaní", "OMR"),
    "PAB": ("Balboa panameño", "B/."),
    "PEN": ("Sol peruano", "S/"),
    "PGK": ("Kina papú", "PGK"),
    "PHP": ("Peso filipino", "₱"),
    "PKR": ("Rupia pakistaní", "PKR"),
    "PLN": ("Złoty polaco", "zł"),
    "PYG": ("Guaraní paraguayo", "₲"),
    "QAR": ("Riyal catarí", "QAR"),
    "RON": ("Leu rumano", "RON"),
    "RSD": ("Dinar serbio", "RSD"),
    "RUB": ("Rublo ruso", "₽"),
    "RWF": ("Franco ruandés", "RWF"),
    "SAR": ("Riyal saudí", "SAR"),
    "SBD": ("Dólar de las Islas Salomón", "SBD"),
    "SCR": ("Rupia seychellense", "SCR"),
    "SDG": ("Libra sudanesa", "SDG"),
    "SEK": ("Corona sueca", "SEK"),
    "SGD": ("Dólar singapurense", "S$"),
    "SHP": ("Libra de Santa Elena", "SHP"),
    "SLE": ("Leone sierraleonés", "SLE"),
    "SOS": ("Chelín somalí", "SOS"),
    "SRD": ("Dólar surinamés", "SRD"),
    "SSP": ("Libra sursudanesa", "SSP"),
    "STN": ("Dobra santotomense", "STN"),
    "SYP": ("Libra siria", "SYP"),
    "SZL": ("Lilangeni suazi", "SZL"),
    "THB": ("Baht tailandés", "฿"),
    "TJS": ("Somoni tayiko", "TJS"),
    "TMT": ("Manat turcomano", "TMT"),
    "TND": ("Dinar tunecino", "TND"),
    "TOP": ("Paʻanga tongano", "TOP"),
    "TRY": ("Lira turca", "₺"),
    "TTD": ("Dólar de Trinidad y Tobago", "TT$"),
    "TWD": ("Nuevo dólar taiwanés", "NT$"),
    "TZS": ("Chelín tanzano", "TZS"),
    "UAH": ("Grivna ucraniana", "₴"),
    "UGX": ("Chelín ugandés", "UGX"),
    "USD": ("Dólar estadounidense", "US$"),
    "UYU": ("Peso uruguayo", "$U"),
    "UZS": ("Som uzbeko", "UZS"),
    "VES": ("Bolívar venezolano", "Bs.D"),
    "VND": ("Dong vietnamita", "₫"),
    "VUV": ("Vatu vanuatuense", "VUV"),
    "WST": ("Tala samoano", "WST"),
    "XAF": ("Franco CFA de África Central", "FCFA"),
    "XCD": ("Dólar del Caribe Oriental", "EC$"),
    "XOF": ("Franco CFA de África Occidental", "CFA"),
    "XPF": ("Franco CFP", "CFPF"),
    "YER": ("Rial yemení", "YER"),
    "ZAR": ("Rand sudafricano", "ZAR"),
    "ZMW": ("Kwacha zambiano", "ZMW"),
}

CODIGOS_DIVISAS_ORDENADOS: Tuple[str, ...] = tuple(sorted(DIVISAS_MUNDIALES.keys()))
MONEDAS_VALIDAS: Tuple[str, ...] = CODIGOS_DIVISAS_ORDENADOS


def es_divisa_valida(codigo: str) -> bool:
    if not isinstance(codigo, str):
        return False
    return codigo.strip().upper() in DIVISAS_MUNDIALES


def obtener_prefijo_divisa(codigo: str) -> str:
    if not isinstance(codigo, str):
        return "$"
    limpio = codigo.strip().upper()
    if limpio in DIVISAS_MUNDIALES:
        return DIVISAS_MUNDIALES[limpio][1]
    return limpio


def obtener_nombre_divisa(codigo: str) -> str:
    if not isinstance(codigo, str):
        return ""
    limpio = codigo.strip().upper()
    if limpio in DIVISAS_MUNDIALES:
        return DIVISAS_MUNDIALES[limpio][0]
    return limpio


def etiqueta_divisa(codigo: str) -> str:
    """Devuelve 'COP — Peso colombiano'."""
    limpio = codigo.strip().upper()
    nombre = obtener_nombre_divisa(limpio)
    return f"{limpio} — {nombre}"


def extraer_codigo_divisa(texto_opcion: str) -> str:
    """Extrae el código ISO de 3 letras desde 'USD — Dólar estadounidense' o 'USD'."""
    if not isinstance(texto_opcion, str):
        return "COP"
    limpio = texto_opcion.strip()
    if "—" in limpio:
        limpio = limpio.split("—", 1)[0].strip()
    elif "-" in limpio:
        limpio = limpio.split("-", 1)[0].strip()
    codigo = limpio[:3].upper()
    return codigo if codigo in DIVISAS_MUNDIALES else "COP"


def construir_lista_selector_divisas(recientes: Sequence[str]) -> List[str]:
    """Construye la lista para el desplegable:
    1) Primero siempre COP y las últimas 4 divisas usadas (hasta 5 recientes en el tope).
    2) Luego todas las divisas del mundo en estricto orden alfabético (A-Z).
    """
    top_5: List[str] = ["COP"]
    for cod in recientes:
        if not isinstance(cod, str):
            continue
        c = cod.strip().upper()
        if c in DIVISAS_MUNDIALES and c not in top_5:
            top_5.append(c)
        if len(top_5) >= 5:
            break

    opciones: List[str] = [etiqueta_divisa(c) for c in top_5]
    for cod_alfabetico in CODIGOS_DIVISAS_ORDENADOS:
        if cod_alfabetico not in top_5:
            opciones.append(etiqueta_divisa(cod_alfabetico))
    return opciones
