"""Ranking: encadena restricciones y scoring, y explica cada recomendación."""

from dataclasses import dataclass

from src.restricciones import (
    DatosProveedores,
    cargar_datos,
    evaluar_proveedores,
    formatear_miles,
)
from src.scoring import (
    ConfigScoring,
    DatosScoring,
    PuntajeProveedor,
    cargar_config,
    cargar_datos_scoring,
    puntuar,
)

TAMANO_TOP = 3
MAX_PALABRAS_EXPLICACION = 20

# Frases por variable: cuando el proveedor es el mejor del corredor y cuando no lo es.
ADJETIVO_LIDER = {"precio": "económico", "tiempo": "rápido", "confiabilidad": "confiable"}
FRASE_NO_LIDER = {
    "precio": "Precio competitivo",
    "tiempo": "Buen tiempo de tránsito",
    "confiabilidad": "Buena puntualidad",
}
NOMBRE_VARIABLE = {"precio": "precio", "tiempo": "tiempo", "confiabilidad": "puntualidad"}


@dataclass(frozen=True)
class DatosRecomendador:
    proveedores: DatosProveedores
    scoring: DatosScoring
    config: ConfigScoring


@dataclass
class OpcionRecomendada:
    posicion: int
    id_proveedor: str
    nombre: str
    puntaje: PuntajeProveedor
    alertas: list
    explicacion: str


@dataclass
class Recomendacion:
    top: list               # OpcionRecomendada, máximo TAMANO_TOP
    elegibles: list         # OpcionRecomendada, todos, en orden
    descartados: list       # EvaluacionProveedor
    casi_elegibles: list    # EvaluacionProveedor con un solo motivo
    alertas: dict           # {id_proveedor: [alertas]} de los elegibles


def cargar_todo():
    return DatosRecomendador(cargar_datos(), cargar_datos_scoring(), cargar_config())


# --- Orden ---

def clave_orden(puntaje):
    """Mayor puntaje; desempate por mayor confiabilidad y luego menor precio."""
    return (-round(puntaje.puntaje, 6), -puntaje.crudos["confiabilidad"], puntaje.crudos["precio"])


# --- Alertas ---

def alertas_de_historial(puntaje):
    """Avisa cuando la confiabilidad se estimó con pocos viajes."""
    conf = puntaje.confiabilidad
    if conf.mezclada:
        return [f"Historial escaso ({conf.viajes} viajes)"]
    return []


# --- Explicación ---

def es_lider(variable, puntaje, todos):
    """True si el proveedor tiene el mejor valor crudo de la variable entre los elegibles."""
    valores = [p.crudos[variable] for p in todos]
    mejor = max(valores) if variable == "confiabilidad" else min(valores)
    return puntaje.crudos[variable] == mejor


def _humanizar(etiqueta):
    return etiqueta.replace("_", " ")


def frase_principal(puntaje, todos):
    """Frase a partir de la variable de mayor aporte (y la segunda, si también lidera)."""
    if len(todos) == 1:
        return "Único proveedor elegible"
    ordenadas = sorted(puntaje.aportes, key=puntaje.aportes.get, reverse=True)
    principal, segunda = ordenadas[0], ordenadas[1]
    if puntaje.aportes[principal] == 0:
        return "Cumple todas las restricciones"
    if principal == "etiquetas":
        fortalezas = [e for e in puntaje.etiquetas if e.tipo == "fortaleza"]
        return f"Fortaleza en {_humanizar(fortalezas[0].etiqueta)}" if fortalezas else "Sin debilidades para esta carga"
    if not es_lider(principal, puntaje, todos):
        if segunda in NOMBRE_VARIABLE and puntaje.aportes[segunda] > 0:
            frase = f"Buen balance de {NOMBRE_VARIABLE[principal]} y {NOMBRE_VARIABLE[segunda]}"
        else:
            frase = FRASE_NO_LIDER[principal]
        if "confiabilidad" in (principal, segunda):
            frase += f" ({puntaje.crudos['confiabilidad']:.0%} a tiempo)"
        return frase
    adjetivos = [ADJETIVO_LIDER[principal]]
    if segunda in ADJETIVO_LIDER and puntaje.aportes[segunda] > 0 and es_lider(segunda, puntaje, todos):
        adjetivos.append(ADJETIVO_LIDER[segunda])
    return f"El más {' y '.join(adjetivos)} del corredor"


def explicar(puntaje, todos, alertas):
    """Explicación corta (máx. 20 palabras): variable de mayor aporte + alertas."""
    partes = [frase_principal(puntaje, todos)] + [a[0].lower() + a[1:] for a in alertas]
    palabras = "; ".join(partes).split()
    return " ".join(palabras[:MAX_PALABRAS_EXPLICACION])


# --- Recomendación ---

def recomendar(solicitud, datos):
    """Filtra con las restricciones, puntúa a los elegibles y arma el top 3."""
    evaluacion = evaluar_proveedores(solicitud, datos.proveedores)
    por_id = {e.proveedor.id_proveedor: e for e in evaluacion.elegibles}
    puntajes = sorted(puntuar(solicitud, list(por_id), datos.scoring, datos.config), key=clave_orden)

    alertas = {p.id_proveedor: por_id[p.id_proveedor].alertas + alertas_de_historial(p) for p in puntajes}
    elegibles = [
        OpcionRecomendada(
            posicion=i,
            id_proveedor=p.id_proveedor,
            nombre=por_id[p.id_proveedor].proveedor.nombre,
            puntaje=p,
            alertas=alertas[p.id_proveedor],
            explicacion=explicar(p, puntajes, alertas[p.id_proveedor]),
        )
        for i, p in enumerate(puntajes, start=1)
    ]
    return Recomendacion(
        top=elegibles[:TAMANO_TOP],
        elegibles=elegibles,
        descartados=evaluacion.descartados,
        casi_elegibles=evaluacion.casi_elegibles,
        alertas=alertas,
    )


def formatear_precio(precio_cop):
    return f"$ {formatear_miles(precio_cop)}"
