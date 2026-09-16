"""Textos en español. Una clave por cadena visible.

Convención de las claves: `pantalla.elemento`. Se ordenan por pantalla, no
alfabéticamente, para que al traducir se lea como un guion.
"""

TEXTOS = {
    # --- Panel del propietario ---------------------------------------------
    "panel.titulo": "Panel",
    "panel.subtitulo": "Tus casas, tus inquilinos y lo que hay que atender hoy.",

    "panel.propiedades": "Propiedades",
    "panel.propiedades.def": "Casas asociadas a tu cuenta.",
    "panel.inquilinos": "Inquilinos activos",
    "panel.inquilinos.def": "Personas con un contrato vigente. Quien tiene dos casas cuenta una vez.",
    "panel.tickets": "Reportes abiertos",
    "panel.tickets.def": "Sin resolver: recibidos y en proceso.",
    "panel.ocupacion": "Ocupación",
    "panel.ocupacion.def": "Casas con contrato vigente ÷ total de tus casas.",

    "panel.emergencias": "Emergencias",
    "panel.emergencias.def": "Reportes urgentes sin resolver.",
    "panel.masviejo": "Reporte más antiguo",
    "panel.masviejo.def": "Días que lleva abierto el más rezagado.",
    "panel.vacias": "Casas vacías",
    "panel.vacias.def": "Sin contrato vigente registrado.",
    "panel.mensajes": "Mensajes sin leer",
    "panel.mensajes.def": "En tu bandeja.",

    "panel.revisar.titulo": "Datos por revisar",
    "panel.revisar.intro": "Nada de esto está roto, pero sin ello los reportes salen incompletos.",
    "panel.revisar.nada": "Todo en orden: no hay datos pendientes de capturar.",
    "panel.revisar.discrepancia": "{n} casa(s) no coinciden con lo publicado en el sitio",
    "panel.revisar.sin_renta": "{n} contrato(s) vigentes sin renta capturada",
    "panel.revisar.sin_fechas": "{n} contrato(s) vigentes sin fecha de inicio o de fin",
    "panel.revisar.sin_zona": "{n} casa(s) sin zona",
    "panel.revisar.sin_m2": "{n} casa(s) sin metros cuadrados",
    "panel.revisar.sin_recamaras": "{n} casa(s) sin número de recámaras",

    "panel.vacio.titulo": "Todavía no tienes casas registradas",
    "panel.vacio.texto": "Cuando el administrador te asigne propiedades aparecerán aquí.",
    "panel.vacio.sin_contratos": "Aún no has registrado ningún contrato de arrendamiento, "
                                 "así que la ocupación sale en 0 %. No es un error: "
                                 "los contratos no están cargados.",
    "panel.vacio.filtro": "Ningún inmueble coincide con este filtro.",

    # --- Filtros -----------------------------------------------------------
    "filtros.zona": "Zona",
    "filtros.recamaras": "Recámaras",
    "filtros.m2": "Tamaño",
    "filtros.ocupacion": "Ocupación",
    "filtros.aplicar": "Filtrar",
    "filtros.limpiar": "Limpiar",
    "filtros.exportar": "Descargar CSV",
    "filtros.todas": "Todas",
    "filtros.sin_dato": "Sin dato",
    "filtros.resumen": "Mostrando {n} de {total} casas",
    "filtros.resumen.sin_zona": "{n} sin zona",
    "filtros.resumen.sin_m2": "{n} sin metros",
    "filtros.ignorado": "Se ignoró un filtro que no se reconoce: {campo}.",
    "filtros.seleccion_parcial": "Algunas casas del enlace ya no están disponibles.",

    "ocupacion.ocupada": "Ocupada",
    "ocupacion.vacante": "Vacía",
    "ocupacion.revisar": "No coincide con el sitio",

    "m2.hasta80": "Hasta 80 m²",
    "m2.80a150": "80 a 150 m²",
    "m2.mas150": "Más de 150 m²",

    "recamaras.1": "1 recámara",
    "recamaras.2": "2 recámaras",
    "recamaras.3": "3 recámaras",
    "recamaras.4mas": "4 o más",

    # --- Tabla de cartera ---------------------------------------------------
    "tabla.casa": "Casa",
    "tabla.zona": "Zona",
    "tabla.recamaras": "Rec.",
    "tabla.m2": "m²",
    "tabla.ocupacion": "Ocupación",
    "tabla.tickets": "Reportes",
    "tabla.seleccionar": "Incluir en el reporte",

    # --- Exportación --------------------------------------------------------
    "csv.tope": "El filtro devuelve {n} filas y el máximo son {tope}. "
                "Afina el filtro y vuelve a intentarlo.",
}
