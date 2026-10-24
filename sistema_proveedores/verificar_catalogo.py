"""
Verificación: ninguna regla del catálogo del Modelo 2 contradice el historial.

Recalcula todo desde la hoja "Envios" (sin usar el código del catálogo) y lo
compara con el modelo entrenado (salidas_m2/modelo2.pkl) y con
salidas_m2/catalogo_proveedores.csv. Dos tipos de contradicción:

  - el catálogo NIEGA algo que el proveedor ha hecho de forma regular (>= 5 veces);
  - el catálogo PERMITE algo que el proveedor nunca ha hecho (combinación
    contenedor-velocidad sin servicios, peso mayor al máximo movido en ese
    contenedor, ciudad sin servicios, velocidad-zona inexistente).

También repite cada envío histórico contra los filtros duros (sin cupos) y
comprueba que el único motivo para excluir al proveedor que de verdad lo hizo
sea una combinación "ocasional" (1 a 4 servicios) publicada en el catálogo.

Uso:
    python verificar_catalogo.py            # sale con código 1 si algo falla
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from modelo2_recomendador import MIN_SERVICIOS, VELOCIDADES, Recomendador


def verificar(env: pd.DataFrame, rec: Recomendador, csv: pd.DataFrame) -> list[tuple[str, bool, str]]:
    cat, res = rec.cat, []
    ok = lambda nombre, cond, detalle="": res.append((nombre, bool(cond), detalle))

    provs = sorted(env.proveedor.unique())
    conts = sorted(env.tipo_contenedor.unique())
    n_pc = env.groupby(["proveedor", "tipo_contenedor"]).size()
    n_pcv = env.groupby(["proveedor", "tipo_contenedor", "nivel_velocidad"]).size()
    pmax = env.groupby(["proveedor", "tipo_contenedor"]).peso_total_kg.max()

    # 1. Contenedores
    malos = [(p, c) for p in provs for c in conts
             if (c in cat.contenedores[p]) != (n_pc.get((p, c), 0) >= MIN_SERVICIOS)]
    ok("Contenedor: 'maneja' <=> al menos 5 envíos en ese contenedor", not malos, str(malos or ""))

    # 2. Velocidad por contenedor
    malos = [(p, c, v) for p in provs for c in conts for v in VELOCIDADES
             if (c in cat.contenedores[p] and cat.ofrece(p, c, v)) != (n_pcv.get((p, c, v), 0) >= MIN_SERVICIOS)]
    ok("Velocidad: 'ofrece' <=> al menos 5 envíos con ese contenedor y esa velocidad", not malos, str(malos or ""))
    nunca = [(p, c, v) for p in provs for c in cat.contenedores[p] for v in VELOCIDADES
             if cat.ofrece(p, c, v) and n_pcv.get((p, c, v), 0) == 0]
    ok("Velocidad: ninguna combinación permitida sin historial", not nunca, str(nunca or ""))

    # 3. Peso por contenedor
    malos = [(p, c) for p in provs for c in cat.contenedores[p] if abs(cat.peso_max[(p, c)] - pmax[(p, c)]) > 1e-9]
    ok("Peso: máximo por proveedor y contenedor = máximo del historial", not malos, str(malos or ""))

    # 4. Ciudades
    hist_c = {p: set(env.loc[env.proveedor == p, "origen"]) | set(env.loc[env.proveedor == p, "destino"]) for p in provs}
    malos = [p for p in provs if cat.ciudades[p] != hist_c[p]]
    ok("Ciudades: cubiertas = ciudades con al menos un envío (origen o destino)", not malos, str(malos or ""))

    # 5. Velocidad-zona
    obs = set(map(tuple, env[["nivel_velocidad", "zona"]].drop_duplicates().to_numpy()))
    ok("Velocidad-zona: posibles = combinaciones observadas", cat.vel_zona_posibles == obs,
       f"mismo día solo en {sorted(z for v, z in obs if v == 'same')}; "
       f"exprés en {sorted(z for v, z in obs if v == 'exp')}")

    # 6. Categoría -> contenedor sin ambigüedad
    amb = env.groupby("categoria_carga").tipo_contenedor.nunique()
    ok("Categoría -> contenedor: cada categoría tiene un único contenedor", (amb == 1).all(),
       str(amb[amb > 1].to_dict() or ""))

    # 7. CSV publicado = conteos del historial
    errores = []
    for r in csv.itertuples():
        n = n_pc.get((r.proveedor, r.tipo_contenedor), 0)
        if r.servicios != n:
            errores.append((r.proveedor, r.tipo_contenedor, "servicios"))
        if n and abs(r.peso_max_atendido_kg - round(pmax[(r.proveedor, r.tipo_contenedor)], 1)) > 0.05:
            errores.append((r.proveedor, r.tipo_contenedor, "peso"))
        for campo in ("velocidades_ofrecidas", "velocidades_ocasionales"):
            txt = getattr(r, campo)
            if txt != "—":
                for item in txt.split(", "):
                    v, k = item.split(" (")
                    if int(k.rstrip(")")) != n_pcv.get((r.proveedor, r.tipo_contenedor, v), 0):
                        errores.append((r.proveedor, r.tipo_contenedor, v))
    ok("catalogo_proveedores.csv: cada conteo coincide con el historial", not errores, str(errores[:10] or ""))

    # 8. Repetición del historial contra los filtros duros (sin cupos)
    excl = {}
    for fila in env.itertuples(index=False):
        s = fila._asdict()
        m = cat.motivos_exclusion(s, s["proveedor"], None)
        if m:
            excl.setdefault((s["proveedor"], s["tipo_contenedor"], s["nivel_velocidad"], tuple(m)), 0)
            excl[(s["proveedor"], s["tipo_contenedor"], s["nivel_velocidad"], tuple(m))] += 1
    no_ocasional = {k: n for k, n in excl.items() if not (0 < n_pcv.get(k[:3], 0) < MIN_SERVICIOS)}
    total = sum(excl.values())
    ok("Historial: el proveedor real solo queda excluido en combinaciones ocasionales publicadas",
       not no_ocasional,
       f"{total} de {len(env):,} envíos ({100 * total / len(env):.2f} %) caen en combinaciones ocasionales: "
       + "; ".join(f"{p} {c} {v} ({n})" for (p, c, v, _), n in sorted(excl.items())))

    # 9. Capacidad: solo para contenedores que el proveedor maneja
    malos = [(r.proveedor, r.tipo_contenedor) for r in rec.cap.itertuples()
             if r.tipo_contenedor not in cat.contenedores[r.proveedor]]
    falt = [(p, c) for p in provs for c in cat.contenedores[p]
            if rec.cap[(rec.cap.proveedor == p) & (rec.cap.tipo_contenedor == c)].empty]
    ok("Capacidad semanal: una fila por cada proveedor-contenedor del catálogo, y solo esas",
       not malos and not falt, str((malos, falt)) if malos or falt else "")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default="base_simulada_mensajeria.xlsx")
    ap.add_argument("--salida", default="salidas_m2")
    a = ap.parse_args()
    env = pd.read_excel(a.datos, sheet_name="Envios")
    rec = Recomendador.cargar(Path(a.salida) / "modelo2.pkl")
    csv = pd.read_csv(Path(a.salida) / "catalogo_proveedores.csv", encoding="utf-8-sig")
    resultados = verificar(env, rec, csv)
    lineas = [f"[{'OK ' if bien else 'FALLA'}] {nombre}" + (f"\n        {det}" if det else "")
              for nombre, bien, det in resultados]
    texto = "VERIFICACIÓN DEL CATÁLOGO CONTRA EL HISTORIAL\n" + "\n".join(lineas)
    texto += f"\n\n{sum(b for _, b, _ in resultados)} de {len(resultados)} comprobaciones superadas.\n"
    print(texto)
    (Path(a.salida) / "verificacion_catalogo.txt").write_text(texto, encoding="utf-8")
    sys.exit(0 if all(b for _, b, _ in resultados) else 1)
