"""
ASIGNACIÓN POR LOTES — reparte varias solicitudes entre proveedores a la vez
============================================================================

El Modelo 2 puntúa cada solicitud por separado (no se cambia nada de esa lógica).
Cuando llegan varias solicitudes juntas, elegir para cada una su primera opción
puede romper dos reglas del lote:

  1. CUPOS: un proveedor no puede recibir más envíos de un contenedor que los
     cupos disponibles esta semana (salidas_m2/capacidad_semana.csv).
  2. CONCENTRACIÓN: ningún proveedor recibe más del 35 % del lote
     (tope = parte entera de 0,35 × tamaño del lote).

Problema (programación entera, con PuLP):

    maximizar   Σ puntaje[i,p] · x[i,p]  −  1000 · Σ sin_asignar[i]
    sujeto a    Σ_p x[i,p] + sin_asignar[i] = 1          cada solicitud, un proveedor (o ninguno)
                Σ_i x[i,p] (contenedor c) ≤ cupos[p,c]   cupos por proveedor y contenedor
                Σ_i x[i,p] ≤ tope                         35 % del lote
                x[i,p] solo existe si p pasa los filtros duros del catálogo para i

La penalización de 1000 (los puntajes van de 0 a 100) hace que primero se asigne
el mayor número posible de solicitudes y, entre esas soluciones, la de mayor
puntaje total. Una solicitud queda sin asignar solo si no hay forma de atenderla.

Si PuLP (o un solver para PuLP) no está instalado se usa una heurística voraz
por "arrepentimiento": en cada paso atiende la solicitud que más perdería si no
recibe ya su mejor opción disponible. Es rápida y suele quedar cerca, pero decide
una solicitud a la vez y no puede deshacer decisiones, así que no garantiza el
óptimo. Con PuLP el resultado es el óptimo exacto y además se reporta cuánto
habría sacado la heurística.

Instalación del solver:  pip install pulp highspy
(PuLP 3 o superior ya no trae CBC incluido; HiGHS es libre y se instala con pip.)
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

import pandas as pd

from modelo2_recomendador import CONCENTRACION_MAX

PENALIZACION_SIN_ASIGNAR = 1000.0


# --------------------------------------------------------------------------
# Solvers
# --------------------------------------------------------------------------

def solver_pulp():
    """Devuelve un solver de PuLP disponible (HiGHS o CBC) o None."""
    try:
        import pulp
    except ImportError:
        return None
    for nombre in ("HiGHS", "PULP_CBC_CMD", "HiGHS_CMD", "COIN_CMD"):
        clase = getattr(pulp, nombre, None)
        if clase is None:
            continue
        try:
            s = clase(msg=False)
            if s.available():
                return s
        except Exception:
            continue
    return None


def _resolver_pulp(cand: pd.DataFrame, cupos: dict | None, tope: int | None, solver) -> dict:
    import pulp
    prob = pulp.LpProblem("asignacion_lote", pulp.LpMaximize)
    # PuLP 4 crea las variables desde el problema; PuLP 2 con LpVariable. Se aceptan ambas versiones.
    binaria = ((lambda nombre: prob.add_variable(nombre, cat="Binary")) if hasattr(prob, "add_variable")
               else (lambda nombre: pulp.LpVariable(nombre, cat="Binary")))
    x = {(r.codigo, r.proveedor): binaria(f"x_{k}") for k, r in enumerate(cand.itertuples())}
    codigos = list(dict.fromkeys(cand.codigo))
    sin = {c: binaria(f"sin_{k}") for k, c in enumerate(codigos)}
    pts = {(r.codigo, r.proveedor): r.puntaje for r in cand.itertuples()}
    prob += pulp.lpSum(pts[k] * v for k, v in x.items()) - PENALIZACION_SIN_ASIGNAR * pulp.lpSum(sin.values())
    for c in codigos:
        prob += pulp.lpSum(v for (i, _), v in x.items() if i == c) + sin[c] == 1
    if cupos is not None:
        for (p, cont), n in cupos.items():
            filas = cand[(cand.proveedor == p) & (cand.tipo_contenedor == cont)]
            if len(filas):
                prob += pulp.lpSum(x[(r.codigo, r.proveedor)] for r in filas.itertuples()) <= n
    if tope is not None:
        for p in cand.proveedor.unique():
            prob += pulp.lpSum(v for (_, q), v in x.items() if q == p) <= tope
    ret = prob.solve(solver)
    if hasattr(pulp, "LpStatus") and hasattr(prob, "status"):      # PuLP 2
        estado = pulp.LpStatus[prob.status]
    else:                                                          # PuLP 4
        estado = getattr(getattr(ret, "status", None), "name", str(ret))
    if estado != "Optimal":
        raise RuntimeError(f"El solver no encontró el óptimo: {estado}")
    asign = {c: None for c in codigos}
    for (i, p), v in x.items():
        if v.value() is not None and v.value() > 0.5:
            asign[i] = p
    return asign


def _resolver_voraz(cand: pd.DataFrame, cupos: dict | None, tope: int | None) -> dict:
    opciones = {c: g.sort_values("puntaje", ascending=False)[["proveedor", "tipo_contenedor", "puntaje"]]
                .itertuples(index=False, name=None)
                for c, g in cand.groupby("codigo", sort=False)}
    opciones = {c: list(o) for c, o in opciones.items()}
    usados_pc, usados_p, asign = Counter(), Counter(), {}

    def libre(p, cont):
        if cupos is not None and (p, cont) in cupos and usados_pc[(p, cont)] >= cupos[(p, cont)]:
            return False
        return tope is None or usados_p[p] < tope

    pendientes = list(opciones)
    while pendientes:
        elegido, mayor = None, -math.inf
        for c in pendientes:
            factibles = [o for o in opciones[c] if libre(o[0], o[1])]
            if not factibles:
                elegido, mayor = c, math.inf  # sin opciones: se cierra ya como sin asignar
                break
            arrepentimiento = factibles[0][2] - (factibles[1][2] if len(factibles) > 1 else 0.0)
            if arrepentimiento > mayor:
                elegido, mayor = c, arrepentimiento
        factibles = [o for o in opciones[elegido] if libre(o[0], o[1])]
        if factibles:
            p, cont, _ = factibles[0]
            asign[elegido] = p
            usados_pc[(p, cont)] += 1
            usados_p[p] += 1
        else:
            asign[elegido] = None
        pendientes.remove(elegido)
    return asign


def _resolver(cand, cupos, tope, metodo):
    if metodo in ("auto", "pulp"):
        s = solver_pulp()
        if s is not None:
            return _resolver_pulp(cand, cupos, tope, s), f"programación entera (PuLP + {s.name})"
        if metodo == "pulp":
            raise RuntimeError("PuLP o su solver no están instalados: pip install pulp highspy")
    return _resolver_voraz(cand, cupos, tope), "heurística voraz (sin garantía de óptimo)"


# --------------------------------------------------------------------------
# Asignación del lote
# --------------------------------------------------------------------------

def leer_cupos(cupos_csv: str | Path | None, rec) -> dict:
    if cupos_csv is not None and Path(cupos_csv).exists():
        cap = pd.read_csv(cupos_csv, encoding="utf-8-sig")
    else:
        cap = rec.cap
    return {(r.proveedor, r.tipo_contenedor): int(r.disponibles) for r in cap.itertuples()}


def asignar_lote(codigos: list[str], rec=None, cupos: dict | None = None, cupos_csv="salidas_m2/capacidad_semana.csv",
                 max_cuota: float = CONCENTRACION_MAX, metodo: str = "auto",
                 modelo="salidas_m2/modelo2.pkl") -> dict:
    """Reparte las solicitudes entre proveedores maximizando la suma de puntajes del Modelo 2.

    Restricciones: cupos disponibles por proveedor y contenedor, y como máximo
    max_cuota del lote por proveedor. Devuelve el detalle por solicitud, el
    resumen de escenarios, el reparto por proveedor y el uso de cupos.
    """
    if rec is None:
        from modelo2_recomendador import Recomendador
        rec = Recomendador.cargar(modelo)
    codigos = list(dict.fromkeys(codigos))           # sin repetidos, en el orden recibido
    cupos = leer_cupos(cupos_csv, rec) if cupos is None else dict(cupos)
    n = len(codigos)
    tope = math.floor(max_cuota * n + 1e-9)
    avisos = []
    if tope < 1:
        avisos.append(f"Con {n} solicitud(es), el {max_cuota:.0%} del lote es menos de un envío: "
                      f"la regla de concentración no se aplica a este lote.")
        tope = None

    # 1) puntajes de cada solicitud con el Modelo 2, sin filtrar por cupos (los cupos van en el lote)
    filas, info = [], {}
    for c in codigos:
        s = rec.solicitud(c)
        res = rec.recomendar(s, usar_cupos=False)
        sol = res["solicitud"]
        info[c] = {"tipo_contenedor": sol["tipo_contenedor"], "ruta": f"{sol['origen']} → {sol['destino']}",
                   "excluidos": res["excluidos"], "proveedor_historico": s.get("proveedor_historico")}
        for x in res["ranking"].itertuples():
            filas.append({"codigo": c, "proveedor": x.proveedor, "tipo_contenedor": sol["tipo_contenedor"],
                          "puntaje": float(x.puntaje), "precio_cop": x.precio_cop,
                          "tiempo_esperado_h": x.tiempo_esperado_h, "fiabilidad": x.fiabilidad})
    cand = pd.DataFrame(filas, columns=["codigo", "proveedor", "tipo_contenedor", "puntaje", "precio_cop",
                                        "tiempo_esperado_h", "fiabilidad"])
    sin_candidatos = [c for c in codigos if c not in set(cand.codigo)]

    # 2) escenarios: sin restricciones, cada restricción por separado y ambas
    escenarios = {}
    for nombre, cp, tp in [("Sin restricciones", None, None), ("Solo cupos", cupos, None),
                           ("Solo tope 35 %", None, tope), ("Cupos + tope 35 %", cupos, tope)]:
        if cand.empty:
            asign, metodo_usado = {}, "—"
        elif cp is None and tp is None:  # el óptimo sin restricciones es la primera opción de cada una
            asign = cand.loc[cand.groupby("codigo").puntaje.idxmax()].set_index("codigo").proveedor.to_dict()
            metodo_usado = "primera opción de cada solicitud"
        else:
            asign, metodo_usado = _resolver(cand, cp, tp, metodo)
        asign = {c: asign.get(c) for c in codigos}
        escenarios[nombre] = {"asignacion": asign, "metodo": metodo_usado}
    final = escenarios["Cupos + tope 35 %"]
    metodo_final = final["metodo"]
    comparacion_voraz = None
    if metodo_final.startswith("programación") and not cand.empty:
        comparacion_voraz = {c: p for c, p in _resolver_voraz(cand, cupos, tope).items()}

    pts = {(r.codigo, r.proveedor): r.puntaje for r in cand.itertuples()}
    total = lambda a: sum(pts[(c, p)] for c, p in a.items() if p is not None)
    resumen = pd.DataFrame([{
        "escenario": k, "asignadas": sum(p is not None for p in v["asignacion"].values()),
        "sin_asignar": sum(p is None for p in v["asignacion"].values()),
        "puntaje_total": total(v["asignacion"]), "metodo": v["metodo"]} for k, v in escenarios.items()])
    base = resumen.puntaje_total.iat[0]
    resumen["puntaje_medio"] = resumen.puntaje_total / resumen.asignadas.where(resumen.asignadas > 0)
    resumen["perdida_vs_sin_restricciones"] = base - resumen.puntaje_total

    # 3) detalle por solicitud
    asign = final["asignacion"]
    usados_pc = Counter((p, info[c]["tipo_contenedor"]) for c, p in asign.items() if p)
    usados_p = Counter(p for p in asign.values() if p)
    detalle = []
    for c in codigos:
        cont = info[c]["tipo_contenedor"]
        g = cand[cand.codigo == c].sort_values("puntaje", ascending=False).reset_index(drop=True)
        fila = {"codigo": c, "ruta": info[c]["ruta"], "contenedor": cont, "candidatos": len(g),
                "proveedor_historico": info[c]["proveedor_historico"]}
        if g.empty:
            fila.update(primera_opcion=None, pts_primera=None, asignado=None, opcion_asignada=None,
                        pts_asignado=None, perdida=None, quedo_con_primera="no",
                        motivo="Ningún proveedor pasa los filtros duros: ver alternativas con --codigo")
            detalle.append(fila)
            continue
        p1, s1 = g.proveedor.iat[0], g.puntaje.iat[0]
        pa = asign[c]
        fila.update(primera_opcion=p1, pts_primera=s1, asignado=pa)
        if pa is None:
            fila.update(opcion_asignada=None, pts_asignado=None, perdida=s1, quedo_con_primera="no",
                        motivo="Sin asignar: todos sus candidatos están sin cupos o en el tope")
        else:
            sa = pts[(c, pa)]
            pos = int(g.index[g.proveedor == pa][0]) + 1
            perdida = s1 - sa
            if pa == p1:
                motivo, quedo = "—", "sí"
            elif perdida < 0.05:
                motivo, quedo = f"Empate con {p1}: misma puntuación", "sí (empate)"
            elif (p1, cont) in cupos and cupos[(p1, cont)] == 0:
                motivo, quedo = f"{p1} no tiene cupos de {cont} esta semana", "no"
            elif ((p1, cont) in cupos and usados_pc[(p1, cont)] >= cupos[(p1, cont)]) or \
                    (tope is not None and usados_p[p1] >= tope):
                partes = []
                if (p1, cont) in cupos and usados_pc[(p1, cont)] >= cupos[(p1, cont)]:
                    k = cupos[(p1, cont)]
                    partes.append(f"su único cupo de {cont} se usó" if k == 1 else f"sus {k} cupos de {cont} se usaron")
                if tope is not None and usados_p[p1] >= tope:
                    partes.append(f"llegó al tope del {max_cuota:.0%} ({tope} de {n})")
                motivo = (f"{p1}: " + " y ".join(partes) +
                          " en solicitudes donde perder la primera opción costaba más")
                quedo = "no"
            else:
                motivo, quedo = "Reparto conjunto del lote (efecto indirecto de las restricciones)", "no"
            fila.update(opcion_asignada=pos, pts_asignado=sa, perdida=perdida, quedo_con_primera=quedo, motivo=motivo)
        detalle.append(fila)
    detalle = pd.DataFrame(detalle)

    # 4) reparto por proveedor y uso de cupos
    provs = sorted(set(cand.proveedor) | set(rec.m1.proveedores))
    reparto = pd.DataFrame({"proveedor": provs})
    hist = Counter(info[c]["proveedor_historico"] for c in codigos if info[c]["proveedor_historico"])
    if sum(hist.values()) == n:
        reparto["historico_real"] = reparto.proveedor.map(hist).fillna(0).astype(int)
    for k in ("Sin restricciones", "Cupos + tope 35 %"):
        cnt = Counter(p for p in escenarios[k]["asignacion"].values() if p)
        reparto[k] = reparto.proveedor.map(cnt).fillna(0).astype(int)
    reparto["pct_sin_restricciones"] = reparto["Sin restricciones"] / n
    reparto["pct_con_restricciones"] = reparto["Cupos + tope 35 %"] / n
    uso = pd.DataFrame([{"proveedor": p, "tipo_contenedor": cont, "cupos_disponibles": k,
                         "pedidos_sin_restricciones": sum(1 for c, q in escenarios["Sin restricciones"]["asignacion"].items()
                                                          if q == p and info[c]["tipo_contenedor"] == cont),
                         "asignados": usados_pc[(p, cont)], "quedan": k - usados_pc[(p, cont)]}
                        for (p, cont), k in sorted(cupos.items())])
    uso = uso[(uso.pedidos_sin_restricciones > 0) | (uso.asignados > 0)].reset_index(drop=True)

    # 5) comprobaciones de los criterios de aceptación
    supera_cupos = uso[uso.asignados > uso.cupos_disponibles]
    supera_tope = reparto[reparto["Cupos + tope 35 %"] > tope] if tope is not None else reparto.iloc[0:0]
    comprobaciones = {
        "ningun_proveedor_supera_cupos": supera_cupos.empty,
        "ningun_proveedor_supera_tope": supera_tope.empty,
        "max_pct_proveedor": float(reparto.pct_con_restricciones.max()) if n else 0.0,
    }
    if sin_candidatos:
        avisos.append("Sin candidatos aun sin cupos (no entran al reparto): " + ", ".join(sin_candidatos))

    return {"detalle": detalle, "resumen": resumen, "reparto": reparto, "uso_cupos": uso, "tope": tope, "n": n,
            "max_cuota": max_cuota, "metodo": metodo_final, "comprobaciones": comprobaciones, "avisos": avisos,
            "voraz_total": total(comparacion_voraz) if comparacion_voraz is not None else None,
            "voraz_sin_asignar": (sum(p is None for p in comparacion_voraz.values())
                                  if comparacion_voraz is not None else None),
            "candidatos": cand}


# --------------------------------------------------------------------------
# Salida en texto
# --------------------------------------------------------------------------

def imprimir_lote(res: dict, archivo_csv: str | Path | None = "salidas_m2/asignacion_lote.csv") -> None:
    n, tope, d = res["n"], res["tope"], res["detalle"]
    print("=" * 110)
    print(f"ASIGNACIÓN POR LOTE: {n} solicitudes · método: {res['metodo']}")
    print(f"Restricciones: cupos disponibles por proveedor y contenedor (capacidad_semana.csv, SIMULADOS) · "
          + (f"máximo {res['max_cuota']:.0%} del lote por proveedor = {tope} envío{'s' if tope != 1 else ''}" if tope else "sin tope de concentración"))
    for a in res["avisos"]:
        print(f"  Aviso: {a}")

    print("\nDETALLE POR SOLICITUD (pérdida = puntaje de su primera opción − puntaje del asignado)")
    print(f"  {'Código':<9} {'Ruta':<28} {'Cont.':<9} {'1.ª opción':<17} {'Pts':>5}   {'Asignado':<17} {'Opc.':>4} "
          f"{'Pts':>5} {'Pérdida':>7}  {'¿1.ª?':<11} Motivo")
    for x in d.itertuples():
        f = lambda v, fmt: format(v, fmt) if v is not None and not pd.isna(v) else "—"
        print(f"  {x.codigo:<9} {x.ruta[:28]:<28} {x.contenedor:<9} {x.primera_opcion or '—':<17} {f(x.pts_primera, '5.1f'):>5}   "
              f"{x.asignado or '—':<17} {f(x.opcion_asignada, '.0f') + '.ª' if x.opcion_asignada else '—':>4} "
              f"{f(x.pts_asignado, '5.1f'):>5} {f(x.perdida, '7.1f'):>7}  {x.quedo_con_primera:<11} {x.motivo}")

    r = res["resumen"]
    print("\nPUNTAJE TOTAL POR ESCENARIO")
    print(f"  {'Escenario':<20} {'Asignadas':>9} {'Sin asignar':>11} {'Puntaje total':>13} {'Medio':>6} {'Pérdida':>8}  Método")
    for x in r.itertuples():
        print(f"  {x.escenario:<20} {x.asignadas:>9} {x.sin_asignar:>11} {x.puntaje_total:>13.1f} "
              f"{x.puntaje_medio:>6.1f} {x.perdida_vs_sin_restricciones:>8.1f}  {x.metodo}")
    final = r.iloc[-1]
    no_primera = d[d.quedo_con_primera == "no"]
    print(f"\n  Con las restricciones se pierden {final.perdida_vs_sin_restricciones:.1f} puntos "
          f"({final.perdida_vs_sin_restricciones / r.puntaje_total.iat[0]:.1%} del total); "
          f"{(d.quedo_con_primera != 'no').sum()} de {n} solicitudes quedan con su primera opción y {len(no_primera)} no.")
    if res["voraz_total"] is not None:
        dif = final.puntaje_total - res["voraz_total"]
        comp = "igual al óptimo" if abs(dif) < 0.05 else f"{dif:.1f} puntos menos que el óptimo"
        if res["voraz_sin_asignar"]:
            comp += f", con {res['voraz_sin_asignar']} sin asignar"
        print(f"  La heurística voraz habría sacado {res['voraz_total']:.1f} puntos ({comp}).")

    rp = res["reparto"]
    print("\nREPARTO POR PROVEEDOR")
    cols = (["historico_real"] if "historico_real" in rp else []) + ["Sin restricciones", "Cupos + tope 35 %"]
    nombres = {"historico_real": "Histórico real", "Sin restricciones": "Sin restricc.", "Cupos + tope 35 %": "Con restricc."}
    print(f"  {'Proveedor':<17} " + " ".join(f"{nombres[c]:>16}" for c in cols))
    for _, fila in rp.iterrows():
        print(f"  {fila['proveedor']:<17} " + " ".join(f"{int(fila[c]):>8} ({fila[c] / n:>4.0%})  " for c in cols))

    u = res["uso_cupos"]
    print("\nCUPOS (solo los pares proveedor-contenedor que intervienen)")
    print(f"  {'Proveedor':<17} {'Contenedor':<10} {'Disponibles':>11} {'Pedidos 1.ª opción':>18} {'Asignados':>9} {'Quedan':>6}")
    for x in u.itertuples():
        marca = "  ← lleno" if x.quedan == 0 else ""
        print(f"  {x.proveedor:<17} {x.tipo_contenedor:<10} {x.cupos_disponibles:>11} {x.pedidos_sin_restricciones:>18} "
              f"{x.asignados:>9} {x.quedan:>6}{marca}")

    c = res["comprobaciones"]
    print(f"\nCOMPROBACIONES: ningún proveedor supera sus cupos: {'OK' if c['ningun_proveedor_supera_cupos'] else 'FALLA'} · "
          + (f"ninguno supera el tope: {'OK' if c['ningun_proveedor_supera_tope'] else 'FALLA'} "
             f"(máximo {c['max_pct_proveedor']:.0%} del lote)" if tope is not None
             else "tope del 35 %: no aplica a un lote tan pequeño"))
    if archivo_csv is not None and Path(archivo_csv).parent.exists():
        d.to_csv(archivo_csv, index=False, encoding="utf-8-sig")
        print(f"Detalle guardado en {archivo_csv}")
    print()
