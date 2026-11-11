"""Investigar las reservas de recursos con los valores que declaran los logs.

Este módulo lo llama 01_preparar_datos.py. No hace falta ejecutarlo por separado.
Las cifras de reserva son datos contables de Nova: no miden uso real de RAM o CPU.
"""

import json  # Permite guardar las conclusiones y sus límites de interpretación.
import re  # Extrae los números de mensajes con una estructura conocida.

import pandas as pd  # Construye las tablas de observaciones y de intentos.


NUMERO = r"-?\d+(?:\.\d+)?"  # Acepta enteros y decimales, también negativos.
PETICION = re.compile(r"\[(req-[0-9a-fA-F-]{36})\b")  # Identifica la petición de Nova.

# Cada regla indica: patrón del mensaje, nombre de actividad y tipo de registro.
# Los grupos con nombre se convertirán en columnas numéricas del CSV.
REGLAS_RECURSOS = [
    (
        re.compile(
            rf"^Attempting claim: memory (?P<memoria_solicitada_mb>{NUMERO}) MB, "
            rf"disk (?P<disco_solicitado_gb>{NUMERO}) GB, "
            rf"vcpus (?P<cpu_solicitada>{NUMERO}) CPU$"
        ),
        "Reservar recursos", "solicitud",
    ),
    (
        re.compile(
            rf"^Total memory: (?P<memoria_total_mb>{NUMERO}) MB, "
            rf"used: (?P<memoria_usada_mb>{NUMERO}) MB$"
        ),
        "Consultar memoria contabilizada", "estado",
    ),
    (
        re.compile(
            rf"^memory limit: (?P<memoria_limite_mb>{NUMERO}) MB, "
            rf"free: (?P<memoria_libre_mb>{NUMERO}) MB$"
        ),
        "Consultar límite de memoria", "limite",
    ),
    (
        re.compile(
            rf"^Total disk: (?P<disco_total_gb>{NUMERO}) GB, "
            rf"used: (?P<disco_usado_gb>{NUMERO}) GB$"
        ),
        "Consultar disco contabilizado", "estado",
    ),
    (
        re.compile(r"^disk limit not specified, defaulting to unlimited$"),
        "Registrar disco sin límite de reserva", "disco_sin_limite",
    ),
    (
        re.compile(
            rf"^Total vcpu: (?P<cpu_total>{NUMERO}) VCPU, "
            rf"used: (?P<cpu_usada>{NUMERO}) VCPU$"
        ),
        "Consultar CPU contabilizada", "estado",
    ),
    (
        re.compile(r"^vcpu limit not specified, defaulting to unlimited$"),
        "Registrar CPU sin límite de reserva", "cpu_sin_limite",
    ),
    (re.compile(r"^Claim successful\b"), "Recursos reservados", "confirmacion"),
    # Estas frases explícitas se conservan si aparecen; en el TAR actual no aparecen.
    (re.compile(r"^(?:Claim failed|Unable to claim resources)\b", re.IGNORECASE),
     "Rechazo explícito de reserva", "rechazo"),
]

# Columnas que permiten unir las distintas líneas de un mismo intento de reserva.
CAMPOS_MEDIDAS = [
    "memoria_solicitada_mb", "memoria_total_mb", "memoria_usada_mb",
    "memoria_limite_mb", "memoria_libre_mb",
    "disco_solicitado_gb", "disco_total_gb", "disco_usado_gb",
    "cpu_solicitada", "cpu_total", "cpu_usada",
]
CAMPOS_CONTEXTO = ["caso", "uuid", "experimento", "etiqueta", "peticion"]
COLUMNAS_INTENTOS = [
    *CAMPOS_CONTEXTO, *CAMPOS_MEDIDAS, "intento_en_peticion", "fecha_primer_registro",
    "archivo_primer_registro", "linea_primer_registro", "registros_observados",
    "registros_sin_clasificar", "solicitud_observada", "reserva_confirmada",
    "rechazo_explicito", "disco_sin_limite_de_reserva", "cpu_sin_limite_de_reserva",
    "evaluacion_memoria", "margen_memoria_tras_solicitud_mb",
    "memoria_supera_total_declarado", "disco_supera_total_declarado",
    "cpu_supera_total_declarado", "evaluacion_reserva",
]
COLUMNAS_RECURSOS = [
    "caso", "uuid", "actividad", "fecha", "experimento", "etiqueta",
    "archivo", "linea", "componente", "mensaje_original", "peticion", "tipo_registro",
    *CAMPOS_MEDIDAS,  # El asterisco incorpora los elementos de esta lista.
]


def interpretar_mensaje_recursos(mensaje):
    """Devolver la actividad y sus cantidades, o None si no hay una regla conocida."""
    for patron, actividad, tipo_registro in REGLAS_RECURSOS:
        coincidencia = patron.match(mensaje)  # Prueba una estructura del vocabulario.
        if coincidencia is None:
            continue  # Prueba la siguiente regla.

        datos = {"actividad": actividad, "tipo_registro": tipo_registro}
        for nombre_columna, texto_numero in coincidencia.groupdict().items():
            datos[nombre_columna] = float(texto_numero)  # Convierte texto a número.
        return datos

    return None  # No se clasifica automáticamente cualquier mensaje de diagnóstico.


def evaluar_memoria(intento):
    """Comparar la memoria solicitada con la libre según el límite de reserva."""
    solicitada = intento["memoria_solicitada_mb"]
    disponible = intento["memoria_libre_mb"]
    if solicitada is None or disponible is None:
        return "datos_insuficientes", None  # La ausencia de cifras no equivale a cero.

    margen = disponible - solicitada  # MB que quedarían tras aceptar la solicitud.
    if margen < 0:
        return "solicitud_supera_memoria_libre_declarada", margen

    return "solicitud_cabe_en_memoria_libre_declarada", margen


def resumir_intento(registros, numero_intento):
    """Reunir una solicitud y los diagnósticos asociados a esa reserva."""
    primero = registros[0]
    intento = {campo: primero[campo] for campo in CAMPOS_CONTEXTO}
    intento.update({campo: None for campo in CAMPOS_MEDIDAS})  # Datos ausentes explícitos.
    intento.update({
        "intento_en_peticion": numero_intento,
        "fecha_primer_registro": primero["fecha"],
        "archivo_primer_registro": primero["archivo"],
        "linea_primer_registro": primero["linea"],
        "registros_observados": len(registros),
        "registros_sin_clasificar": 0,  # Permite revisar mensajes fuera de las reglas.
        "solicitud_observada": False,
        "reserva_confirmada": False,
        "rechazo_explicito": False,
        "disco_sin_limite_de_reserva": False,
        "cpu_sin_limite_de_reserva": False,
    })

    for registro in registros:  # Cada línea aporta solo algunas de las columnas.
        for campo in CAMPOS_MEDIDAS:
            valor = registro.get(campo)
            if pd.notna(valor):  # Conserva el último valor observado dentro del intento.
                intento[campo] = valor

        tipo = registro["tipo_registro"]
        if tipo == "solicitud":
            intento["solicitud_observada"] = True
        elif tipo == "confirmacion":
            intento["reserva_confirmada"] = True
        elif tipo == "rechazo":
            intento["rechazo_explicito"] = True
        elif tipo == "disco_sin_limite":
            intento["disco_sin_limite_de_reserva"] = True
        elif tipo == "cpu_sin_limite":
            intento["cpu_sin_limite_de_reserva"] = True
        elif tipo == "no_clasificado":
            intento["registros_sin_clasificar"] += 1

    diagnostico, margen = evaluar_memoria(intento)
    intento["evaluacion_memoria"] = diagnostico
    intento["margen_memoria_tras_solicitud_mb"] = margen

    # Compara también contra los totales, sin confundirlos con límites de reserva.
    campos_por_recurso = [
        ("memoria", "memoria_total_mb", "memoria_usada_mb", "memoria_solicitada_mb"),
        ("disco", "disco_total_gb", "disco_usado_gb", "disco_solicitado_gb"),
        ("cpu", "cpu_total", "cpu_usada", "cpu_solicitada"),
    ]
    for recurso, campo_total, campo_usado, campo_solicitado in campos_por_recurso:
        total = intento[campo_total]
        usado = intento[campo_usado]
        solicitado = intento[campo_solicitado]
        supera_total = None  # Sin las tres cifras no se puede hacer la comparación.
        if total is not None and usado is not None and solicitado is not None:
            supera_total = usado + solicitado > total
        intento[f"{recurso}_supera_total_declarado"] = supera_total

    # Un rechazo es evidencia textual; un margen negativo es una comparación numérica.
    if intento["rechazo_explicito"]:
        intento["evaluacion_reserva"] = "rechazo_explicito_observado"
    elif diagnostico == "solicitud_supera_memoria_libre_declarada":
        intento["evaluacion_reserva"] = "deficit_segun_memoria_libre_declarada"
    elif diagnostico == "datos_insuficientes":
        intento["evaluacion_reserva"] = "datos_insuficientes"
    else:
        intento["evaluacion_reserva"] = "sin_deficit_de_memoria_observado"

    return intento


def construir_tabla_intentos(recursos):
    """Separar las reservas por caso, petición y aparición de una nueva solicitud."""
    intentos = []
    # Una VM puede tener varias peticiones: no se mezclan sus medidas.
    for _, grupo in recursos.groupby(["caso", "peticion"], sort=False):
        registros_intento = []
        numero_intento = 1
        for registro in grupo.to_dict(orient="records"):
            if registro["tipo_registro"] == "solicitud" and registros_intento:
                intentos.append(resumir_intento(registros_intento, numero_intento))
                registros_intento = []  # La siguiente reserva empieza sin datos heredados.
                numero_intento += 1
            registros_intento.append(registro)

        if registros_intento:  # También conserva grupos sin solicitud observada.
            intentos.append(resumir_intento(registros_intento, numero_intento))

    return pd.DataFrame(intentos, columns=COLUMNAS_INTENTOS)  # También escribe cabecera si está vacía.


def investigar_recursos(filas_recursos, eventos, casos, carpeta_datos):
    """Guardar evidencias, intentos de reserva, un log ampliado y un informe JSON."""
    recursos = pd.DataFrame(filas_recursos, columns=COLUMNAS_RECURSOS)
    recursos["fecha"] = pd.to_datetime(recursos["fecha"], format="%Y-%m-%d %H:%M:%S.%f")
    recursos = recursos.sort_values(["caso", "fecha", "archivo", "linea"], kind="stable")
    recursos.to_csv(carpeta_datos / "eventos_recursos.csv", index=False)

    # El log ampliado sirve para ver en PM4Py dónde se consultan los recursos.
    ampliado = pd.concat([eventos, recursos[eventos.columns]], ignore_index=True)
    # Solicitud y confirmación ya estaban en el ciclo: se incluye cada línea una vez.
    ampliado = ampliado.drop_duplicates(subset=["caso", "archivo", "linea"])
    ampliado = ampliado.sort_values(["caso", "fecha", "archivo", "linea"], kind="stable")
    ampliado.to_csv(carpeta_datos / "eventos_vm_con_recursos.csv", index=False)

    intentos = construir_tabla_intentos(recursos)
    # Es la duración completa de creación del caso, no la duración de cada reserva.
    duraciones = casos.set_index("caso")["duracion_creacion_s"]
    intentos["duracion_creacion_caso_s"] = intentos["caso"].map(duraciones)
    intentos.to_csv(carpeta_datos / "recursos_por_intento.csv", index=False)

    resumen = {
        "registros_recursos": len(recursos),
        "eventos_log_ampliado": len(ampliado),
        "intentos_observados": len(intentos),
        "casos_con_datos_recursos": int(recursos["caso"].nunique()),
        "casos_ciclo_sin_registros_recursos": sorted(set(casos["caso"]) - set(recursos["caso"])),
        "registros_sin_clasificar": int(recursos["tipo_registro"].eq("no_clasificado").sum()),
        "combinaciones_distintas_de_medidas": 0,
        "evaluaciones_reserva": {},
        "reservas_confirmadas": 0,
        "rechazos_explicitos": 0,
        "intentos_con_memoria_evaluable": 0,
        "margen_memoria_minimo_mb": None,
        "intentos_que_superan_total_disco_declarado": 0,
        "intentos_con_disco_sin_limite_de_reserva": 0,
        "cobertura": "Mensajes de nova.compute.claims con marca [instance: UUID]; los desconocidos se conservan sin clasificar.",
        "criterios": {
            "memoria": "Déficit si memoria solicitada > memoria libre declarada según el límite de reserva.",
            "disco_y_cpu": "Se conservan totales y solicitudes; sin límite declarado no se infiere un rechazo.",
            "rechazo": "Solo las frases Claim failed y Unable to claim resources se cuentan como rechazo explícito.",
        },
        "limitaciones": [
            "Usado significa recurso contabilizado en estos mensajes, no utilización real medida.",
            "El total puede diferir del límite de reserva; superar el total no demuestra un fallo.",
            "Un dato ausente no equivale a cero ni demuestra que haya recursos suficientes.",
            "La evaluación de memoria no garantiza disponibilidad de disco, CPU u otros recursos.",
            "Las reglas no cubren todos los errores posibles de OpenStack ni mensajes sin VM identificada.",
            "Las etiquetas de anomalía de la fuente se conservan; no se atribuye su causa a los recursos.",
        ],
    }
    if not intentos.empty:
        resumen["evaluaciones_reserva"] = intentos["evaluacion_reserva"].value_counts().to_dict()
        resumen["reservas_confirmadas"] = int(intentos["reserva_confirmada"].sum())
        resumen["combinaciones_distintas_de_medidas"] = len(intentos[CAMPOS_MEDIDAS].drop_duplicates())
        resumen["rechazos_explicitos"] = int(intentos["rechazo_explicito"].sum())
        margenes = intentos["margen_memoria_tras_solicitud_mb"].dropna()
        resumen["intentos_con_memoria_evaluable"] = len(margenes)
        if not margenes.empty:
            resumen["margen_memoria_minimo_mb"] = float(margenes.min())
        resumen["intentos_que_superan_total_disco_declarado"] = int(
            intentos["disco_supera_total_declarado"].eq(True).sum()
        )
        resumen["intentos_con_disco_sin_limite_de_reserva"] = int(
            intentos["disco_sin_limite_de_reserva"].sum()
        )

    texto_json = json.dumps(resumen, ensure_ascii=False, indent=2)
    (carpeta_datos / "investigacion_recursos.json").write_text(texto_json + "\n", encoding="utf-8")
    print(f"Investigación de recursos: {len(recursos)} registros; {len(intentos)} intentos")
    print(f"Rechazos explícitos de reserva: {resumen['rechazos_explicitos']}")
    return resumen
