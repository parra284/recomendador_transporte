# Validación del Modelo 2

Se reproduce con `python validar_modelo2.py` (~1 minuto). Las tablas completas quedan en `salidas_validacion_m2/`: `resumen.txt`, `resumen.json` y un CSV por prueba.

**Cómo se evita la trampa.** El Modelo 1, el cotizador (incluida la elección entre Ridge y boosting, hecha dentro del entrenamiento con corte en sep-2025) y el catálogo se entrenan solo con los 23.871 envíos hasta el 2026-03-31; el script comprueba que ninguno sea posterior. Antes de recomendar cada uno de los 7.515 envíos de abr-sep 2026, se borran el proveedor, el precio, la tarifa, los tiempos, "a tiempo", los daños y la satisfacción. Los cupos simulados no se aplican, porque son una foto de esta semana, no del pasado. Por velocidad, los 7.515 envíos se puntúan en bloque con los mismos componentes del Modelo 2; el script verifica en 60 envíos al azar que el resultado coincide con `recomendar()` (diferencia máxima 3·10⁻¹⁴ y el mismo primer lugar en todos).

## Resultados

**1-2. Recomendado frente a elegido en su momento** (valores esperados según los modelos; dif = recomendado − elegido)

| | Envíos | Coincidencia | Costo (COP) | Costo (% por envío) | Costo total | Prob. a tiempo | Tiempo esperado |
|---|---|---|---|---|---|---|---|
| **Total** | 7.510 | 31,2 % | −3.424 | +1,3 % | −0,9 % | **+9,1 pts** | −5,4 h |
| Dry | 5.125 | 29,4 % | +2.058 | +1,6 % | +1,2 % | +9,5 pts | −6,1 h |
| Reefer | 1.230 | 31,9 % | +4.693 | +1,7 % | +1,6 % | +8,1 pts | −3,2 h |
| Open Top | 813 | 32,5 % | +2.147 | +1,1 % | +0,2 % | +9,1 pts | −4,7 h |
| Flat Rack | 342 | 52,9 % | −128.010 | −4,0 % | −4,8 % | +6,5 pts | −4,4 h |

Hay dos maneras de medir el costo. Por envío, el promedio de los cocientes sube 1,3 %. En total baja 0,9 %, porque el sistema ahorra sobre todo en los envíos caros (Flat Rack). En la práctica, el costo es el mismo y el servicio es claramente mejor.

Hay 5 envíos sin ningún candidato: Open Top mismo día en Bogotá, una combinación que antes del corte nadie había hecho 5 veces. En otros 5 envíos, el proveedor elegido no habría pasado el catálogo de marzo: llevaban más peso que el máximo visto o eran combinaciones con menos de 5 servicios.

**Hallazgo importante:** sin cupos ni tope, el sistema recomienda a Coordinadora en el **96 %** de los envíos; en el historial se eligió en el 28,5 %. En esta simulación, Coordinadora es de verdad la más puntual y la más rápida, a precio medio, así que gana casi siempre (la hoja Supuestos lo confirma). Recomendar solicitud por solicitud la sobrecargaría. Por eso, en la operación hay que usar la asignación por lotes (`--lote`), con cupos y tope del 35 %.

**3. Resultados reales (solo indicativo)**

| | Envíos | A tiempo real | Esperado por el Modelo 1 | Real − esperado |
|---|---|---|---|---|
| Elegido = recomendado | 2.343 | 76,0 % | 74,1 % | +2,0 pts |
| Elegido ≠ recomendado | 5.167 | 64,3 % | 64,1 % | +0,1 pts |

Los envíos donde se eligió al recomendado llegaron a tiempo 11,7 puntos más seguido. Pero esa diferencia no prueba que el recomendador cause mejores resultados, por **sesgo de selección**. Los dos grupos no son comparables: el que coincide es casi todo Coordinadora (2.140 de 2.343) y el que no coincide es casi todo de otros proveedores. Además, en el historial el proveedor no se eligió al azar: el simulador asigna según la cuota de mercado y el desempeño reciente. Cuando se descuenta lo que el Modelo 1 esperaba para cada envío y proveedor, la ventaja baja a unos 2 puntos.

Un ejemplo muestra el sesgo en sentido contrario. Cuando el sistema recomienda a Inter Rapidísimo y se eligió a Inter, llegó a tiempo solo el 49,5 % de las veces. No es que el recomendador se equivoque: el 95 % de esos envíos van o vienen de Quibdó, una zona especial difícil para todos (46 % a tiempo), y allí Coordinadora no tiene cobertura.

**4. Coherencia.** En las 7.510 recomendaciones hay 0 violaciones de filtros duros (contenedor, cobertura, peso, velocidad por contenedor y velocidad-zona). La comprobación se hace recalculando los filtros desde los datos de entrenamiento, sin usar el código del catálogo.

**5. Sensibilidad.** Se probaron 24 variantes: cada uno de los 12 pesos base ± 10 puntos, renormalizando después a 100 %.
- **Dry:** es el perfil más sensible. Bajar el peso del tiempo (20 → 10) cambia el primer lugar en 379 envíos (7,4 % de Dry, 5,0 % del total). Subir el del precio (45 → 55) lo cambia en 122 envíos (2,4 %).
- **Reefer, Open Top y Flat Rack:** ninguna variante cambia más del 1,3 %.
- **Lectura:** la estabilidad se debe en parte a que un proveedor domina en dos de los tres factores, así que no prueba por sí sola que los pesos estén bien calibrados.

**6. Casos de prueba** (modelo de producción): los 9 casos dan resultados razonables y el script comprueba cada uno con una regla.

| Caso | Top 3 | Lectura |
|---|---|---|
| T-001 | Coordinadora > Inter > TCC | Carga seca típica: compiten los 6 y gana el mejor balance precio-fiabilidad |
| T-002 | TCC > Inter > Servientrega | Coordinadora sin cupos Reefer; gana el de mayor probabilidad de llegar en el plazo (76 %) |
| T-003 | Coordinadora > Inter > TCC | Acero en Open Top: 4-72 y Envía fuera por contenedor |
| T-004 | Coordinadora > TCC > Servientrega | Flat Rack: solo los tres que lo manejan |
| T-005 | — | Exprés a Quibdó no existe: no hay candidatos y propone prioritaria |
| T-006 | Coordinadora > Inter > Servientrega | 60 kg a Pasto: 4-72 fuera por peso, TCC por cobertura |
| T-007 | Coordinadora > TCC > Inter | Mismo día en Medellín: 4-72 fuera; el primero llega en plazo el 83 % de las veces |
| T-008 | — | Flat Rack mismo día: nadie lo ha hecho 5 veces; propone exprés (caso añadido) |
| T-009 | Inter > Servientrega | Reefer de 1.050 kg: TCC fuera por peso (caso añadido) |

**Extra: recuperación de los parámetros ocultos** (hoja Supuestos, solo para validar, relativos a Coordinadora)
- **Precio:** el cotizador recupera el factor de precio de cada proveedor con correlación 0,999. El error máximo es de 4,0 %, en 4-72, que tiene pocos datos.
- **Tiempo prometido:** también lo recupera con correlación 0,999.
- **Puntualidad:** el Modelo 1 ordena a los seis proveedores exactamente igual que el simulador (Spearman 1,00).

## Limitaciones

1. **Datos simulados.** Las cifras muestran que el método funciona; no califican a las empresas reales. Con datos reales, la dominancia de un proveedor y las cifras pueden cambiar.
2. **Costo y puntualidad "esperados" salen de los mismos modelos que recomiendan.** No se puede observar qué habría pasado con otro proveedor, así que en parte el sistema se mide con su propia regla. Lo mitigan dos cosas: los modelos se validaron fuera de muestra y recuperan los parámetros verdaderos del simulador.
3. **"A tiempo" es frente a la promesa de cada proveedor.** Aquí no favorece al recomendado: Coordinadora además promete menos horas y tarda 5,4 h menos en promedio.
4. **La coincidencia (31 %) no mide acierto.** Las decisiones históricas las generó el modelo de elección del simulador, no operarios, y el objetivo no es imitarlas.
5. **La prueba con resultados reales tiene sesgo de selección** y es solo indicativa.
6. **La prueba retrospectiva no aplica cupos ni el tope del 35 %.** En la operación, la asignación por lotes repartiría más (en el lote de 50, Coordinadora quedó en 34 %).
7. **Un solo corte temporal** (6 meses de prueba). Tampoco se probaron los extras de velocidad y plazo, solo los pesos base.
8. **La regla de "al menos 5 servicios" es conservadora** con combinaciones raras: dejó 5 envíos sin candidato.

## Tres frases para la presentación

1. "Entrenado solo con datos hasta marzo de 2026 y probado en 7.510 envíos de abril a septiembre que nunca vio, el sistema recomienda proveedores con 9 puntos más de probabilidad de llegar a tiempo y 5 horas menos de tránsito que los elegidos en su momento, con el mismo costo total (−0,9 %)."
2. "El modelo encuentra los parámetros ocultos del simulador: recupera el factor de precio de cada proveedor con una correlación de 0,999 y ordena a los seis exactamente igual que la verdad en puntualidad."
3. "Es coherente y estable: cero violaciones de filtros duros en 7.510 recomendaciones, y mover cualquier peso ±10 puntos cambia la primera opción en como mucho el 5 % de los envíos."
