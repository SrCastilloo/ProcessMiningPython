"""Descubrir grafos y comparar tiempos de creación con los datos de OpenStack."""

from pathlib import Path
import json
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pm4py


CARPETA = Path(__file__).resolve().parent
SALIDA = CARPETA / "resultados"


def preparar_log(nombre):
    """Los CSV usan exactamente las columnas que ya conoces: caso, actividad, fecha."""
    datos = pd.read_csv(CARPETA / "datos" / nombre, dtype={"caso": str})
    return pm4py.format_dataframe(
        datos, case_id="caso", activity_key="actividad", timestamp_key="fecha"
    )


def guardar_tiempos(log, nombre, titulo):
    dfg, inicios, finales = pm4py.discover_performance_dfg(log)
    for extension in ("png", "svg"):
        pm4py.save_vis_performance_dfg(
            dfg, inicios, finales, str(SALIDA / f"{nombre}.{extension}"),
            aggregation_measure="mean", rankdir="TB", graph_title=titulo,
        )
    return dfg


def main():
    if shutil.which("dot") is None:
        raise SystemExit("Graphviz no está disponible. Comprueba el comando: dot -V")
    SALIDA.mkdir(exist_ok=True)
    ciclo = preparar_log("eventos_vm.csv")
    creacion = preparar_log("eventos_creacion.csv")

    # Primer grafo: frecuencias del ciclo de vida observado, con todos los casos.
    dfg, inicios, finales = pm4py.discover_dfg(ciclo)
    for extension in ("png", "svg"):
        pm4py.save_vis_dfg(
            dfg, inicios, finales, str(SALIDA / f"grafo_ciclo_frecuencias.{extension}"),
            rankdir="TB", graph_title="OpenStack: eventos del ciclo de vida",
        )

    # El log ampliado muestra también las consultas de memoria, disco y CPU.
    ciclo_con_recursos = preparar_log("eventos_vm_con_recursos.csv")
    dfg_recursos, inicios_recursos, finales_recursos = pm4py.discover_dfg(ciclo_con_recursos)
    for extension in ("png", "svg"):
        pm4py.save_vis_dfg(
            dfg_recursos, inicios_recursos, finales_recursos,
            str(SALIDA / f"grafo_ciclo_con_recursos_frecuencias.{extension}"),
            rankdir="TB", graph_title="OpenStack: ciclo de vida y diagnóstico de recursos",
        )

    # Segundo grafo: tiempos de creación, con límites observados en cada caso.
    tiempos = guardar_tiempos(
        creacion, "grafo_creacion_tiempos", "OpenStack: creación, tiempo medio"
    )
    frecuencias, _, _ = pm4py.discover_dfg(creacion)
    pd.DataFrame([
        {"origen": a, "destino": b, "ocurrencias": frecuencias[(a, b)],
         "media_s": float(m["mean"]), "mediana_s": float(m["median"])}
        for (a, b), m in sorted(tiempos.items())
    ]).to_csv(SALIDA / "transiciones_creacion.csv", index=False)

    # Comparación dentro del MISMO experimento con inyección de fallos.
    mismo_experimento = creacion[creacion["experimento"].eq("con_inyeccion")]
    comparacion_etapas = []
    for etiqueta, nombre, titulo in [
        ("sin_etiqueta_anomalia", "grafo_creacion_sin_etiqueta", "Creación: sin etiqueta de anomalía"),
        ("anomalia_inyectada", "grafo_creacion_anomalias", "Creación: anomalías etiquetadas"),
    ]:
        grupo = mismo_experimento[mismo_experimento["etiqueta"].eq(etiqueta)]
        tiempos_grupo = guardar_tiempos(grupo, nombre, titulo)
        for (origen, destino), metricas in tiempos_grupo.items():
            comparacion_etapas.append({
                "etiqueta": etiqueta, "origen": origen, "destino": destino,
                "media_s": float(metricas["mean"]),
            })
    pd.DataFrame(comparacion_etapas).to_csv(SALIDA / "comparacion_etapas.csv", index=False)

    duraciones = pd.read_csv(CARPETA / "datos" / "duracion_creacion.csv")
    estadisticas = duraciones.groupby(["experimento", "etiqueta"])["duracion_creacion_s"].agg(
        casos="count", media_s="mean", mediana_s="median", minimo_s="min", maximo_s="max"
    ).reset_index()
    estadisticas.to_csv(SALIDA / "comparacion_grupos.csv", index=False)

    # Una variante es una secuencia completa de actividades de un caso.
    for nombre_log, log in [("ciclo", ciclo), ("creacion", creacion)]:
        variantes = pm4py.get_variants_as_tuples(log)
        pd.DataFrame([
            {"casos": int(n), "secuencia": " | ".join(variante)}
            for variante, n in sorted(variantes.items(), key=lambda x: x[1], reverse=True)
        ]).to_csv(SALIDA / f"variantes_{nombre_log}.csv", index=False)

    # Figura adicional: cada punto representa una VM del mismo experimento.
    # El desplazamiento vertical solo evita que se solapen los puntos.
    figura, eje = plt.subplots(figsize=(10, 4.5), layout="constrained")
    rng = np.random.default_rng(20261110)
    experimento = duraciones[duraciones["experimento"].eq("con_inyeccion")]
    grupos = [
        ("sin_etiqueta_anomalia", "Sin etiqueta de anomalía", "#2563a6"),
        ("anomalia_inyectada", "Anomalía inyectada", "#dc6b26"),
    ]
    etiquetas = []
    for y, (etiqueta, texto, color) in enumerate(grupos):
        valores = experimento.loc[experimento["etiqueta"].eq(etiqueta), "duracion_creacion_s"]
        eje.scatter(valores, y + rng.uniform(-0.09, 0.09, len(valores)),
                    s=34 if y == 0 else 74, color=color, alpha=0.55 if y == 0 else 1)
        media = valores.mean()
        eje.plot([media, media], [y - 0.19, y + 0.19], color="#162739", linewidth=2.3)
        eje.text(media, y + 0.29, f"Media: {media:.2f} s", ha="center", fontsize=11)
        etiquetas.append(f"{texto}\n(n = {len(valores)})")
    eje.set_yticks([0, 1], etiquetas)
    eje.set_ylim(-0.32, 1.57)
    eje.set_xlim(0, 58)
    eje.set_xlabel("Tiempo desde reservar recursos hasta creación completada (segundos)")
    eje.set_title("OpenStack: mismo recorrido, distintos tiempos de creación", loc="left", weight="bold", pad=14)
    eje.grid(axis="x", alpha=0.2)
    eje.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        eje.spines[lado].set_visible(False)
    for extension in ("png", "svg"):
        figura.savefig(SALIDA / f"comparacion_tiempos.{extension}", dpi=160)
    plt.close(figura)

    resumen = {
        "version_pm4py": pm4py.__version__,
        "casos_ciclo": int(ciclo["case:concept:name"].nunique()),
        "eventos_ciclo": len(ciclo),
        "casos_creacion": int(creacion["case:concept:name"].nunique()),
        "eventos_creacion": len(creacion),
        "variantes_creacion": len(pm4py.get_variants_as_tuples(creacion)),
        "comparacion_grupos": json.loads(estadisticas.to_json(orient="records")),
        "nota": "Etiquetas originales del dataset; comparación descriptiva, con cuatro casos etiquetados.",
    }
    (SALIDA / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(estadisticas.to_string(index=False))
    print(f"\nGrafos y tablas guardados en: {SALIDA}")


if __name__ == "__main__":
    main()
