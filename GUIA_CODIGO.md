# Cómo se obtiene el análisis, paso a paso

## Cómo leer el script de preparación

Empieza por `main()`, al final de `01_preparar_datos.py`. Python ejecuta sus
instrucciones de arriba abajo. Cada llamada encarga un paso a una función:

| Función | Qué hace | Qué devuelve |
| --- | --- | --- |
| `verificar_archivo_original()` | Comprueba la huella del TAR | Nada; detiene el programa si no coincide |
| `leer_eventos_de_logs()` | Lee etiquetas y logs, selecciona mensajes y construye eventos | Eventos del ciclo, registros de recursos, UUID etiquetados y contadores |
| `construir_tabla_eventos(...)` | Crea la tabla, convierte las fechas y ordena | Tabla de eventos |
| `analizar_creacion_por_caso(...)` | Busca los límites y calcula duraciones | Tabla de eventos de creación y tabla de casos |
| `guardar_tablas(...)` | Escribe los cinco CSV | Nada; guarda archivos |
| `investigar_recursos(...)` | Compara solicitudes con cifras de reserva y conserva las evidencias | CSV de recursos, log ampliado e informe JSON; devuelve el resumen |
| `crear_metadatos(...)` | Reúne los recuentos y las decisiones | Diccionario de resumen |
| `guardar_metadatos(...)` | Escribe `preparacion.json` | Nada; guarda un archivo |
| `mostrar_resumen(...)` | Muestra los recuentos | Nada; escribe en la consola |

Las funciones se definen con `def`, pero su cuerpo se ejecuta cuando se las llama.
`return` devuelve un resultado a la instrucción que hizo la llamada. Por ejemplo:

```python
eventos = construir_tabla_eventos(filas_eventos)
```

`filas_eventos` entra en la función; la tabla que devuelve se guarda en `eventos`.
Cuando una función devuelve varios resultados, se asignan en el mismo orden:

```python
eventos_creacion, casos = analizar_creacion_por_caso(eventos)
```

En el código, `#` introduce un comentario explicativo. Los textos entre triples
comillas describen el propósito del archivo o de una función. La sangría indica
qué instrucciones pertenecen a una función, un bucle `for` o una condición `if`.

## 1. Qué es una línea del log

OpenStack escribe mensajes con una fecha, un componente y un contenido.
Algunos contenidos incluyen el identificador de la VM:

```text
[instance: 544fd51c-4edc-4780-baae-ba1d80a0acfc] Creating image
```

Ese mensaje existe en el archivo con inyección, a las
`2017-05-14 21:07:37.924`. En el CSV se representa como:

| caso | actividad | fecha |
| --- | --- | --- |
| con_inyeccion:544fd51c-4edc-4780-baae-ba1d80a0acfc | Preparar imagen | 2017-05-14 21:07:37.924 |

Muchas líneas del archivo son consultas HTTP o diagnósticos del nodo. Para
nuestro modelo seleccionamos diez clases de mensajes que tienen una VM
identificada y representan operaciones o notificaciones de su ciclo de vida.

## 2. Leer el archivo comprimido

En `01_preparar_datos.py`:

```python
with tarfile.open(ARCHIVO, "r:gz") as tar:
    uuids_anomalas = leer_uuids_anomalas(tar)
```

Dentro de `leer_uuids_anomalas`, la lectura se divide en pasos:

```python
with tar.extractfile("anomaly_labels.txt") as archivo_etiquetas:
    contenido_etiquetas = archivo_etiquetas.read()

texto_etiquetas = contenido_etiquetas.decode("utf-8")
uuids_encontradas = re.findall(UUID, texto_etiquetas)
return set(uuids_encontradas)
```

`tarfile` permite leer el TAR comprimido. `extractfile` abre el contenido de un
miembro del archivo sin instalar nada ni ejecutar sus mensajes.

El fichero `anomaly_labels.txt` identifica cuatro VMs con anomalías introducidas
por los autores. Esa información se conserva en la columna `etiqueta`.
El nombre `openstack_abnormal.log` no convierte todas sus VMs en casos etiquetados:
en ese mismo archivo hay otras 194 VMs con eventos seleccionados, de las cuales
192 tienen los dos límites requeridos para medir la creación.

## 3. Extraer los campos de cada mensaje

`CABECERA` e `INSTANCIA` son expresiones regulares: patrones para localizar la
fecha, el componente y un texto con la forma `[instance: UUID]`.

El script toma la fecha del evento. El primer campo de cada línea es un nombre
de fichero que puede contener otra fecha; esa fecha del nombre no se utiliza
como momento del evento.

Después comprobamos el inicio del mensaje:

```python
def identificar_actividad(mensaje):
    for prefijo, nombre_actividad in ACTIVIDADES:
        if mensaje.startswith(prefijo):
            return nombre_actividad

    return None
```

`ACTIVIDADES` contiene parejas como:

```python
("Creating image", "Preparar imagen")
```

Si el mensaje empieza por ese prefijo, lo convertimos en la actividad
"Preparar imagen". `None` significa que no corresponde a ninguna actividad
seleccionada. El mapa completo queda en `datos/mapa_actividades.csv`.
`return` termina la función en la primera coincidencia; si ninguna regla
coincide, se llega a `return None`.

## 4. Construir los casos y ordenar

```python
"caso": f"{experimento}:{uuid}"
```

Un caso es una VM dentro de su experimento. El prefijo distingue la ejecución
de referencia de la ejecución con inyección. Los archivos normal1 y normal2
se combinan como partes del registro de referencia: una VM que atraviesa esa
frontera mantiene el mismo caso.

```python
eventos["fecha"] = pd.to_datetime(eventos["fecha"], format="%Y-%m-%d %H:%M:%S.%f")
eventos = eventos.sort_values(["caso", "fecha", "archivo", "linea"], kind="stable")
```

Convertimos las fechas en valores temporales y ordenamos los eventos de cada
caso. El archivo y la línea sirven para resolver empates de forma reproducible.
El CSV también conserva esos campos y el mensaje original para poder auditar
de dónde sale cada evento.

## 5. Delimitar la creación

El registro de ciclo de vida contiene tanto creación como eliminación.
Para estudiar el tiempo de creación necesitamos fijar sus límites:

- Inicio observado: `Attempting claim`, traducido como "Reservar recursos".
- Final observado: `Instance spawned successfully.`, traducido como "Creación completada".

Para cada VM buscamos ambos eventos. Se incluye en esta medición si hay un
inicio y un final únicos y aparecen en ese orden. Recortamos la secuencia a
esa ventana y a los siete tipos de actividad de creación.
Tener ambos límites no garantiza que se hayan observado todas las actividades
intermedias: esa comprobación no forma parte del criterio de selección.

Con esta regla se incluyen 2 064 casos y se excluyen 5 de la medición temporal.
Los cinco siguen presentes en `eventos_vm.csv`; el archivo `casos_vm.csv`
permite revisar los límites ausentes o ambiguos. Su exclusión no les asigna
automáticamente una etiqueta de fallo.

```python
intervalo = fecha_final - fecha_inicio
duracion_segundos = intervalo.total_seconds()
```

Por ejemplo, la VM etiquetada `544fd51c-...` inicia la reserva a las
21:07:37.102 y completa la creación a las 21:08:19.735. La diferencia es 42,633 s.

## 6. Preparar los CSV para PM4Py

En `02_analizar_procesos.py`:

```python
datos = pd.read_csv(nombre_csv)
log = pm4py.format_dataframe(
    datos,
    case_id="caso",
    activity_key="actividad",
    timestamp_key="fecha",
)
```

Este es el mismo patrón que en el primer ejemplo. Ahora las columnas proceden
de registros de OpenStack que hemos transformado y documentado.

## 7. Descubrir el grafo de frecuencias

```python
dfg, inicios, finales = pm4py.discover_dfg(log)
pm4py.save_vis_dfg(dfg, inicios, finales, "grafo.png")
```

PM4Py cuenta parejas consecutivas dentro de cada caso. Cada rectángulo es
una actividad y el contador de cada flecha es el número de apariciones de esa
sucesión. El grafo de ciclo incluye todos los eventos seleccionados, incluso
las secuencias que empiezan o terminan a mitad del ciclo observado.

Las notificaciones "VM reanudada" se conservan. En la variante dominante hay
una antes y otra después de la notificación "Creación completada". Esto registra
dos mensajes; por sí solo no demuestra dos operaciones solicitadas por un usuario.

## 8. Descubrir el grafo de tiempos

```python
dfg, inicios, finales = pm4py.discover_performance_dfg(log)
pm4py.save_vis_performance_dfg(
    dfg, inicios, finales, "tiempos.png", aggregation_measure="mean"
)
```

En las ventanas de creación, las flechas muestran el tiempo medio entre
notificaciones consecutivas. Los PNG de PM4Py usan etiquetas abreviadas;
los CSV de resultados contienen los valores con decimales.

Un intervalo largo señala una zona que merece investigación. Puede incluir
operaciones internas y esperas: no equivale automáticamente al tiempo de CPU
ni demuestra la causa del retraso.

## 9. Comparar grupos

Filtramos la ejecución con inyección y distinguimos sus VMs con y sin etiqueta:

```python
grupo = log[
    log["experimento"].eq("con_inyeccion")
    & log["etiqueta"].eq("anomalia_inyectada")
]
```

Se generan dos grafos de tiempos comparables. La figura adicional representa
una VM por punto. El desplazamiento vertical de los puntos es solo una ayuda
visual para evitar solapamientos; el eje horizontal muestra la duración medida.

Las etiquetas son conocidas de antemano por el fichero de los autores.
Esta práctica realiza una comparación descriptiva, sin entrenar un clasificador.

## 10. Investigar una posible falta de recursos

El mismo script `01_preparar_datos.py` conserva ahora los mensajes de recursos
de `nova.compute.claims`. Llama al módulo `investigacion_recursos.py`, donde las
reglas y los cálculos están comentados. Se ejecuta con el comando habitual:

```powershell
.\.venv\Scripts\python.exe 01_preparar_datos.py
```

Se generan cuatro archivos adicionales:

| Archivo en `datos/` | Qué puedes revisar |
| --- | --- |
| `eventos_recursos.csv` | Cada mensaje de reserva de una VM, sus cifras reconocidas, actividad, fecha, petición y línea original |
| `recursos_por_intento.csv` | Una fila por intento de reserva, con sus medidas y evaluación |
| `eventos_vm_con_recursos.csv` | Ciclo de vida con las consultas de recursos intercaladas por fecha |
| `investigacion_recursos.json` | Recuentos, criterios de clasificación y límites del análisis |

La tabla de intentos separa las VMs, las peticiones `req-...` y las nuevas
solicitudes. Así un reintento no hereda las medidas o el rechazo del anterior.
Los grupos que carecen de solicitud observada también se conservan.
Si falta un valor se deja vacío: no se sustituye por cero.
Los mensajes de este componente con una VM identificada que no encajan en
las reglas se conservan como `no_clasificado`, con el texto original, para
revisarlos manualmente. El informe cuenta esos mensajes y enumera los casos
del ciclo que no tienen registros de recursos.

### Ejemplo real: interpretar la memoria

La VM `544fd51c-...` tiene estos mensajes:

```text
Attempting claim: memory 2048 MB, disk 20 GB, vcpus 1 CPU
Total memory: 64172 MB, used: 512.00 MB
memory limit: 96258.00 MB, free: 95746.00 MB
```

El código extrae `2048`, `64172`, `512`, `96258` y `95746` como números, sin
alterar los mensajes. La memoria libre indicada por el log corresponde al
límite de reserva: `96258 - 512 = 95746 MB`. No se confunde con el total.

La evaluación usa una regla explícita:

```python
margen = memoria_libre_declarada - memoria_solicitada
```

En este ejemplo: `95746 - 2048 = 93698 MB`. La solicitud cabe en la memoria
libre declarada. Si el resultado fuese negativo, se señalaría un déficit
según esas cifras. Sin ambas medidas, se clasificaría como datos insuficientes.
No hay un umbral arbitrario como «80 % de uso».

### Ejemplo real: interpretar el disco

```text
Attempting claim: memory 2048 MB, disk 20 GB, vcpus 1 CPU
Total disk: 15 GB, used: 0.00 GB
disk limit not specified, defaulting to unlimited
```

La solicitud de 20 GB supera el total de 15 GB indicado. Se conserva esa
observación en `disco_supera_total_declarado`, junto con la indicación de
que no hay límite de reserva. Esto no se clasifica como rechazo ni demuestra
que el almacenamiento se haya agotado. Para CPU se conserva la misma distinción
entre total, cantidad solicitada y ausencia de límite.

`Claim successful` registra una reserva confirmada. Las frases explícitas
`Claim failed` o `Unable to claim resources`, si aparecen en este componente,
se conservan como rechazos. Estas dos reglas no cubren todos los errores
posibles de OpenStack. La ausencia de coincidencias no demuestra que no haya
otros fallos en el sistema.

Las cifras «used» de estos mensajes representan recursos contabilizados para
la reserva; no son mediciones de utilización real de RAM o CPU. Una creación
lenta o una etiqueta de anomalía tampoco demuestra falta de recursos.
`duracion_creacion_caso_s` permite contrastar las cifras con la duración del
caso completo, sin atribuir una causa automáticamente.

Al ejecutar `02_analizar_procesos.py`, se añade el grafo
`resultados/grafo_ciclo_con_recursos_frecuencias.png` y su versión SVG.
Muestra dónde aparecen las consultas de recursos dentro de las secuencias.
Las diez actividades del log original siguen disponibles para comparar.

Las pruebas incluyen déficits simulados, límites exactos, información ausente,
rechazos y reintentos que no deben mezclar sus medidas:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
