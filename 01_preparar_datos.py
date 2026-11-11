"""Preparar los logs de OpenStack para analizarlos posteriormente con PM4Py.

Recorrido de los datos:
    TAR original -> mensajes seleccionados -> tabla de eventos -> archivos CSV.

Conceptos usados en este script:
    Evento: una actividad de una VM registrada en un momento concreto.
    Caso: una VM dentro de un experimento, identificada por experimento + UUID.
    DataFrame: una tabla de pandas, formada por filas y columnas.
    Ventana de creación: eventos entre reservar recursos y completar la creación.

"""

from pathlib import Path  # Construye rutas de archivos independientes del sistema.
import hashlib  # Calcula la huella del archivo para comprobar su identidad.
import json  # Guarda el resumen de la preparación en formato JSON.
import re  # Busca estructuras de texto mediante expresiones regulares.
import tarfile  # Lee los archivos que contiene el TAR comprimido.

import pandas as pd  # Permite trabajar con tablas y fechas.

# Estas funciones conservan e investigan los mensajes de recursos del mismo TAR.
from investigacion_recursos import PETICION, interpretar_mensaje_recursos, investigar_recursos


# __file__ es este script; resolve() obtiene su ruta absoluta y parent su carpeta.
CARPETA = Path(__file__).resolve().parent
CARPETA_DATOS = CARPETA / "datos"  # El operador / une partes de una ruta.
ARCHIVO = CARPETA_DATOS / "fuentes" / "OpenStack.tar.gz"
MD5_PUBLICADO = "66bd42c07837a094d9b0ea2d036b5713"  # Huella esperada del TAR.

# re.compile() prepara un patrón que se reutilizará al leer cada línea.
# La r inicial permite escribir las barras de la expresión regular literalmente.
# (?P<nombre>...) asigna un nombre al fragmento capturado para recuperarlo después.
CABECERA = re.compile(
    r"^\S+\s+"  # Salta el primer campo: el nombre del fichero original.
    r"(?P<fecha>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)"  # Fecha del evento.
    r"\s+\d+"  # Salta los espacios y el identificador numérico del proceso.
    r"\s+(?P<nivel>\w+)"  # Captura el nivel, aunque no se usa como filtro.
    r"\s+(?P<componente>\S+)"  # Captura el componente que escribió el mensaje.
    r"\s+(?P<contenido>.*)$"  # Captura todo el contenido restante.
)

# Un UUID tiene grupos de 8-4-4-4-12 caracteres hexadecimales separados por guiones.
UUID = r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}"
# Los paréntesis que rodean UUID permiten recuperar ese identificador como grupo 1.
INSTANCIA = re.compile(r"\[instance:\s*(" + UUID + r")\]")

# Cada pareja relaciona el inicio de un mensaje técnico con una actividad legible.
# Los mensajes que no coincidan con estas diez reglas no forman parte del modelo.
ACTIVIDADES = [
    ("Attempting claim:", "Reservar recursos"),
    ("Claim successful", "Recursos reservados"),
    ("Creating image", "Preparar imagen"),
    ("VM Started (Lifecycle Event)", "VM iniciada"),
    ("VM Paused (Lifecycle Event)", "VM pausada"),
    ("VM Resumed (Lifecycle Event)", "VM reanudada"),
    ("Instance spawned successfully.", "Creación completada"),
    ("Terminating instance", "Iniciar eliminación"),
    ("Instance destroyed successfully.", "Instancia destruida"),
    ("VM Stopped (Lifecycle Event)", "VM detenida"),
]

# Este conjunto indica qué actividades conservamos dentro de la ventana de creación.
ACTIVIDADES_CREACION = {
    "Reservar recursos",
    "Recursos reservados",
    "Preparar imagen",
    "VM iniciada",
    "VM pausada",
    "VM reanudada",
    "Creación completada",
}


def verificar_archivo_original():
    """Detener el programa si el TAR no coincide con el archivo esperado."""
    contenido_archivo = ARCHIVO.read_bytes()  # Lee los bytes del TAR completo.
    huella_calculada = hashlib.md5(contenido_archivo).hexdigest()  # MD5 en texto.

    if huella_calculada != MD5_PUBLICADO:  # Compara la huella con la publicada.
        raise ValueError("El TAR no coincide con el checksum publicado en Zenodo.")


def leer_uuids_anomalas(tar):
    """Leer las etiquetas originales; aquí no se detectan anomalías nuevas."""
    with tar.extractfile("anomaly_labels.txt") as archivo_etiquetas:
        contenido_etiquetas = archivo_etiquetas.read()  # Lee los bytes del fichero.

    texto_etiquetas = contenido_etiquetas.decode("utf-8")  # Convierte bytes a texto.
    uuids_encontradas = re.findall(UUID, texto_etiquetas)  # Busca todos los UUID.
    return set(uuids_encontradas)  # Un conjunto evita duplicados y facilita búsquedas.


def identificar_experimento(nombre_archivo):
    """Distinguir la ejecución con inyección del registro de referencia."""
    if "abnormal" in nombre_archivo:  # Consulta si el nombre contiene ese texto.
        return "con_inyeccion"

    return "referencia"  # normal1 y normal2 pertenecen al mismo experimento.


def identificar_actividad(mensaje):
    """Traducir un mensaje técnico a una de las diez actividades seleccionadas."""
    for prefijo, nombre_actividad in ACTIVIDADES:  # Lee cada pareja de la lista.
        if mensaje.startswith(prefijo):  # Comprueba cómo empieza el mensaje.
            return nombre_actividad  # Devuelve la primera actividad que coincida.

    return None  # None indica que el mensaje no pertenece al modelo elegido.


def obtener_etiqueta(experimento, uuid, uuids_anomalas):
    """Asignar una etiqueta conocida de la fuente, sin inferir normalidad."""
    pertenece_a_inyeccion = experimento == "con_inyeccion"
    aparece_en_etiquetas = uuid in uuids_anomalas

    if pertenece_a_inyeccion and aparece_en_etiquetas:  # Deben cumplirse ambas.
        return "anomalia_inyectada"

    return "sin_etiqueta_anomalia"  # No equivale a garantizar que la VM sea normal.


def leer_eventos_de_logs():
    """Leer eventos del ciclo y de recursos, etiquetas y contadores de lectura."""
    filas_eventos = []  # Cada elemento será un diccionario con un evento.
    filas_recursos = []  # Conserva también los diagnósticos de reserva de Nova.
    contadores = {
        "lineas_por_archivo": {},  # Relaciona cada log con su número de líneas.
        "lineas_sin_cabecera_reconocida": 0,
        "lineas_con_instancia": 0,  # Incluye mensajes que luego pueden descartarse.
    }

    # with cierra el TAR al terminar; no se extraen sus rutas al disco.
    with tarfile.open(ARCHIVO, "r:gz") as tar:
        uuids_anomalas = leer_uuids_anomalas(tar)

        for miembro in tar.getmembers():  # Recorre las entradas del TAR.
            if not miembro.isfile():  # Ignora las entradas que no sean archivos.
                continue  # Pasa a la siguiente entrada.
            if not miembro.name.endswith(".log"):  # Solo queremos los logs.
                continue

            nombre_archivo = miembro.name
            experimento = identificar_experimento(nombre_archivo)
            contadores["lineas_por_archivo"][nombre_archivo] = 0

            with tar.extractfile(miembro) as archivo_log:  # Abre el log dentro del TAR.
                # enumerate devuelve el número y el contenido de cada línea, desde 1.
                for numero_linea, bytes_linea in enumerate(archivo_log, start=1):
                    contadores["lineas_por_archivo"][nombre_archivo] += 1
                    texto_linea = bytes_linea.decode("utf-8", errors="replace")
                    texto_linea = texto_linea.rstrip("\r\n")  # Quita el salto final.
                    cabecera = CABECERA.match(texto_linea)  # Reconoce los campos.

                    if cabecera is None:  # La línea no tiene la estructura esperada.
                        contadores["lineas_sin_cabecera_reconocida"] += 1
                        continue

                    contenido = cabecera["contenido"]  # Recupera el grupo con ese nombre.
                    instancia = INSTANCIA.search(contenido)  # Busca [instance: UUID].
                    if instancia is None:  # Sin VM identificada no podemos asignar caso.
                        continue

                    contadores["lineas_con_instancia"] += 1
                    uuid = instancia.group(1).lower()  # UUID capturado, en minúsculas.
                    # end() indica dónde termina la marca [instance: UUID].
                    mensaje = contenido[instancia.end():].strip()  # Texto posterior.
                    actividad = identificar_actividad(mensaje)
                    datos_recursos = None
                    if cabecera["componente"] == "nova.compute.claims":
                        datos_recursos = interpretar_mensaje_recursos(mensaje)
                        if datos_recursos is None:  # Conserva también vocabulario desconocido.
                            datos_recursos = {
                                "actividad": "Mensaje de reserva sin clasificar",
                                "tipo_registro": "no_clasificado",
                            }
                    # Ahora un diagnóstico de recursos también puede conservar la línea.
                    if actividad is None and datos_recursos is None:
                        continue

                    etiqueta = obtener_etiqueta(experimento, uuid, uuids_anomalas)
                    evento = {
                        "caso": f"{experimento}:{uuid}",  # Una VM en un experimento.
                        "uuid": uuid,  # Identificador original de la VM.
                        "actividad": actividad,  # Nombre que utilizará PM4Py.
                        "fecha": cabecera["fecha"],  # Fecha todavía en formato texto.
                        "experimento": experimento,
                        "etiqueta": etiqueta,
                        "archivo": nombre_archivo,  # Procedencia para revisar el evento.
                        "linea": numero_linea,
                        "componente": cabecera["componente"],
                        "mensaje_original": mensaje,  # Conserva los detalles técnicos.
                    }
                    if actividad is not None:
                        filas_eventos.append(evento)  # Mantiene el ciclo original.

                    if datos_recursos is not None:
                        evento_recurso = evento.copy()  # No modifica el evento del ciclo.
                        evento_recurso.update(datos_recursos)  # Añade actividad y cantidades.
                        peticion = PETICION.search(contenido)
                        evento_recurso["peticion"] = peticion.group(1) if peticion else ""
                        filas_recursos.append(evento_recurso)

    return filas_eventos, filas_recursos, uuids_anomalas, contadores


def construir_tabla_eventos(filas_eventos):
    """Convertir los eventos en una tabla ordenada y con fechas calculables."""
    eventos = pd.DataFrame(filas_eventos)  # Cada diccionario se convierte en una fila.
    eventos["fecha"] = pd.to_datetime(
        eventos["fecha"],  # Columna de texto que queremos convertir.
        format="%Y-%m-%d %H:%M:%S.%f",  # Año-mes-día hora:minuto:segundo.fracción.
    )

    eventos = eventos.sort_values(
        ["caso", "fecha", "archivo", "linea"],  # Agrupa por caso y ordena por tiempo.
        kind="stable",  # Conserva el orden previo cuando todas las claves empatan.
    )
    # Archivo y línea resuelven empates; no prueban el orden físico de esos eventos.
    return eventos


def analizar_creacion_por_caso(eventos):
    """Recortar ventanas de creación y resumir la cobertura de todos los casos.

    Solo medimos si hay un inicio y un final únicos, y aparecen en ese orden.
    Esta regla no exige que estén presentes todas las actividades intermedias.
    """
    ventanas_creacion = []  # Guardará una tabla de eventos por ventana válida.
    resumenes_casos = []  # Guardará un diccionario por caso, válido o excluido.

    for caso, eventos_caso in eventos.groupby("caso", sort=True):
        # Reinicia las posiciones a 0, 1, 2... dentro de este caso.
        eventos_caso = eventos_caso.reset_index(drop=True)

        es_inicio = eventos_caso["actividad"] == "Reservar recursos"  # True/False por fila.
        es_final = eventos_caso["actividad"] == "Creación completada"
        posiciones_inicio = eventos_caso.index[es_inicio].tolist()  # Posiciones coincidentes.
        posiciones_final = eventos_caso.index[es_final].tolist()

        tiene_inicio_unico = len(posiciones_inicio) == 1
        tiene_final_unico = len(posiciones_final) == 1
        limites_validos = False  # Se mantiene en False si faltan límites o se repiten.
        duracion_segundos = None  # No inventamos una duración para casos excluidos.

        if tiene_inicio_unico and tiene_final_unico:
            posicion_inicio = posiciones_inicio[0]  # Primer y único elemento de la lista.
            posicion_final = posiciones_final[0]
            limites_validos = posicion_inicio <= posicion_final

        if limites_validos:
            # iloc selecciona por posición; el extremo derecho no se incluye, de ahí +1.
            ventana = eventos_caso.iloc[posicion_inicio:posicion_final + 1]
            es_actividad_creacion = ventana["actividad"].isin(ACTIVIDADES_CREACION)
            ventana = ventana[es_actividad_creacion]  # Conserva solo actividades de creación.
            ventanas_creacion.append(ventana)

            fecha_inicio = eventos_caso.loc[posicion_inicio, "fecha"]  # Celda del inicio.
            fecha_final = eventos_caso.loc[posicion_final, "fecha"]
            intervalo = fecha_final - fecha_inicio  # La resta produce un intervalo temporal.
            duracion_segundos = intervalo.total_seconds()  # Lo expresa en segundos.

        primer_evento = eventos_caso.iloc[0]  # Primera fila del caso ordenado.
        ultimo_evento = eventos_caso.iloc[-1]  # -1 accede a la última fila.
        resumen_caso = {
            "caso": caso,
            "uuid": primer_evento["uuid"],
            "experimento": primer_evento["experimento"],
            "etiqueta": primer_evento["etiqueta"],
            "eventos_observados": len(eventos_caso),
            "inicios_creacion": len(posiciones_inicio),
            "finales_creacion": len(posiciones_final),
            "creacion_con_limites_observados": limites_validos,
            "duracion_creacion_s": duracion_segundos,
            "primera_actividad": primer_evento["actividad"],
            "ultima_actividad": ultimo_evento["actividad"],
        }
        resumenes_casos.append(resumen_caso)  # Incluye también los casos sin duración.

    # concat une las ventanas; ignore_index numera de nuevo las filas de la tabla final.
    eventos_creacion = pd.concat(ventanas_creacion, ignore_index=True)
    casos = pd.DataFrame(resumenes_casos)  # Una fila por VM y experimento.
    return eventos_creacion, casos


def guardar_tablas(eventos, eventos_creacion, casos):
    """Guardar las cinco tablas CSV que utilizará el análisis posterior."""
    # index=False evita guardar la numeración interna de pandas como columna adicional.
    eventos.to_csv(CARPETA_DATOS / "eventos_vm.csv", index=False)
    eventos_creacion.to_csv(CARPETA_DATOS / "eventos_creacion.csv", index=False)
    casos.to_csv(CARPETA_DATOS / "casos_vm.csv", index=False)

    casos_medibles = casos[casos["creacion_con_limites_observados"]]  # Filtra filas True.
    casos_medibles.to_csv(CARPETA_DATOS / "duracion_creacion.csv", index=False)

    mapa_actividades = pd.DataFrame(
        ACTIVIDADES,  # Cada pareja de la lista será una fila.
        columns=["prefijo_original", "actividad"],  # Nombres de las dos columnas.
    )
    mapa_actividades.to_csv(CARPETA_DATOS / "mapa_actividades.csv", index=False)


def crear_metadatos(eventos, eventos_creacion, casos, uuids_anomalas, contadores):
    """Reunir recuentos y decisiones para poder revisar la preparación."""
    lineas_por_archivo = contadores["lineas_por_archivo"]
    numero_casos = len(casos)
    # Al sumar una columna booleana, cada True cuenta como 1 y cada False como 0.
    numero_casos_medibles = int(casos["creacion_con_limites_observados"].sum())

    return {
        "fuente": "https://zenodo.org/records/8196385",
        "archivo_md5": MD5_PUBLICADO,
        "lineas_por_archivo": lineas_por_archivo,
        "lineas_totales": sum(lineas_por_archivo.values()),  # Suma los tres logs.
        "lineas_sin_cabecera_reconocida": contadores["lineas_sin_cabecera_reconocida"],
        "lineas_con_instancia": contadores["lineas_con_instancia"],
        "eventos_seleccionados": len(eventos),
        "casos_con_eventos_seleccionados": numero_casos,
        "casos_creacion_con_limites_observados": numero_casos_medibles,
        "casos_excluidos_del_analisis_temporal_creacion": numero_casos - numero_casos_medibles,
        "eventos_creacion": len(eventos_creacion),
        "uuids_etiquetadas_por_la_fuente": sorted(uuids_anomalas),  # Orden reproducible.
        "politica_tiempo": "Reloj original sin zona horaria declarada; se calculan diferencias dentro del mismo caso.",
        "seleccion": "Diez prefijos explícitos; las notificaciones repetidas se conservan.",
    }


def guardar_metadatos(metadatos):
    """Escribir el resumen como un JSON legible, conservando los acentos."""
    texto_json = json.dumps(metadatos, ensure_ascii=False, indent=2)
    ruta_resumen = CARPETA_DATOS / "preparacion.json"
    ruta_resumen.write_text(texto_json + "\n", encoding="utf-8")


def mostrar_resumen(metadatos):
    """Mostrar en la consola los principales recuentos de la preparación."""
    print(f"Líneas leídas: {metadatos['lineas_totales']}")
    print(
        f"Eventos seleccionados: {metadatos['eventos_seleccionados']}; "
        f"casos: {metadatos['casos_con_eventos_seleccionados']}"
    )
    print(
        "Creación con inicio y final observados: "
        f"{metadatos['casos_creacion_con_limites_observados']} casos"
    )
    print(
        "Casos excluidos de esa medición: "
        f"{metadatos['casos_excluidos_del_analisis_temporal_creacion']}"
    )


def main():
    """Ejecutar la preparación en orden: esta función es el mapa del programa."""
    verificar_archivo_original()  # 1. Comprobar que usamos el dataset esperado.
    filas_eventos, filas_recursos, uuids_anomalas, contadores = leer_eventos_de_logs()  # 2. Leer.
    eventos = construir_tabla_eventos(filas_eventos)  # 3. Convertir fechas y ordenar.
    eventos_creacion, casos = analizar_creacion_por_caso(eventos)  # 4. Medir cada VM.
    guardar_tablas(eventos, eventos_creacion, casos)  # 5. Escribir los CSV.
    investigar_recursos(filas_recursos, eventos, casos, CARPETA_DATOS)  # Analizar reservas.
    metadatos = crear_metadatos(
        eventos, eventos_creacion, casos, uuids_anomalas, contadores
    )  # 6. Reunir los recuentos y las decisiones de preparación.
    guardar_metadatos(metadatos)  # 7. Guardar el resumen JSON.
    mostrar_resumen(metadatos)  # 8. Informar del resultado por consola.


# Solo ejecuta main() al lanzar este archivo; no al importarlo desde otro programa.
if __name__ == "__main__":
    main()
