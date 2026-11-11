# Resultados del análisis de OpenStack

## Datos utilizados

Se utilizó el TAR completo de Loghub v8 publicado en Zenodo, verificado con su
checksum. Los tres logs contienen 207 820 líneas:

| Archivo | Líneas |
| --- | ---: |
| openstack_abnormal.log | 18 434 |
| openstack_normal1.log | 52 312 |
| openstack_normal2.log | 137 074 |

51 553 líneas tienen una cabecera reconocida y una etiqueta `[instance: UUID]`.
Tras seleccionar los diez tipos de actividad documentados quedan 22 721
eventos de 2 069 casos. Ocho líneas del TAR no tienen la cabecera reconocida;
el resto de exclusiones corresponde a mensajes sin instancia o ajenos al mapa.

## Cobertura temporal

2 064 casos tienen un inicio y un final únicos observados de creación.
La duración se mide desde "Reservar recursos" hasta "Creación completada".
Las ventanas contienen 14 448 eventos, siete por caso.

Los otros cinco casos se conservan en el análisis exploratorio del ciclo, pero
se excluyen de esa medición temporal. La ausencia de un límite en el registro
no demuestra, por sí sola, un fallo de creación.

## Recorridos

En las ventanas de creación hay una variante: las mismas siete actividades
seleccionadas en el mismo orden. Esto incluye los cuatro casos etiquetados.

En el ciclo observado completo hay seis variantes. La dominante tiene 2 062
casos e incluye dos notificaciones "VM reanudada". Las variantes pequeñas
incluyen secuencias con límites ausentes y deben revisarse con el log original.
Las pausas y reanudaciones también aparecen en el recorrido de referencia.

## Comparación de duraciones

| Grupo | Casos con límites observados | Media (s) | Mediana (s) | Mínimo (s) | Máximo (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Referencia, sin etiqueta de anomalía | 1 868 | 20,434 | 20,384 | 10,792 | 23,195 |
| Experimento con inyección, sin etiqueta de anomalía | 192 | 20,478 | 20,422 | 18,726 | 27,467 |
| Experimento con inyección, anomalía etiquetada | 4 | 39,055 | 37,302 | 30,173 | 51,442 |

Dentro del mismo experimento, la media del grupo etiquetado es 1,907 veces la
del grupo sin etiqueta, aproximadamente un 90,7 % mayor.
La media de todos los 2 064 casos es 20,474 s; al agregar todos los casos se
atenúa mucho la diferencia de los cuatro etiquetados.

| UUID etiquetado (abreviado) | Duración de creación (s) |
| --- | ---: |
| 544fd51c-... | 42,633 |
| ae651dff-... | 30,173 |
| a445709b-... | 51,442 |
| 1643649d-... | 31,970 |

## Dónde aparece la diferencia

Comparación de los intervalos medios dentro del experimento con inyección:

| Relación | Sin etiqueta (192 casos), s | Etiquetados (4 casos), s |
| --- | ---: | ---: |
| Reservar recursos → Recursos reservados | 0,037297 | 0,039250 |
| Recursos reservados → Preparar imagen | 0,611125 | 0,702750 |
| Preparar imagen → VM iniciada | 13,139625 | 31,690500 |
| VM iniciada → VM pausada | 0,071365 | 0,066250 |
| VM pausada → VM reanudada | 6,610208 | 6,548000 |
| VM reanudada → Creación completada | 0,008776 | 0,007750 |

La mayor diferencia se observa entre "Preparar imagen" y "VM iniciada".
Esto identifica un intervalo a investigar. Los mensajes seleccionados no
permiten atribuirlo de manera concluyente a CPU, disco, red o al hipervisor.

## Investigación de falta de recursos

Se conservan 16 520 mensajes de `nova.compute.claims`, agrupados en 2 065
intentos de reserva de 2 065 casos. Los cuatro casos restantes del ciclo no
tienen estos registros; se enumeran en `datos/investigacion_recursos.json`.
No hay mensajes de este componente con VM identificada pendientes de clasificar.
El log ampliado contiene 35 111 eventos y conserva las consultas de recursos.

En los 2 065 intentos se observan las mismas cifras de reserva:

| Medida | Valor declarado |
| --- | ---: |
| Memoria solicitada | 2 048 MB |
| Memoria total | 64 172 MB |
| Memoria contabilizada como usada | 512 MB |
| Límite de reserva de memoria | 96 258 MB |
| Memoria libre según ese límite | 95 746 MB |
| Margen tras descontar la solicitud | 93 698 MB |
| Disco solicitado | 20 GB |
| Disco total | 15 GB |
| Disco contabilizado como usado | 0 GB |
| CPU solicitada | 1 vCPU |
| CPU total | 16 vCPU |
| CPU contabilizada como usada | 0 vCPU |

Todos los intentos tienen `Claim successful`. Ninguno supera la memoria libre
declarada y no aparecen las frases de rechazo explícito reconocidas por las
reglas. Tanto disco como CPU se declaran sin límite de reserva. La solicitud
de disco supera el total indicado, pero esa diferencia no prueba un rechazo
ni agotamiento de almacenamiento.

Las cifras observadas son iguales en los casos con y sin etiqueta de anomalía.
Estos mensajes no aportan evidencia de falta de memoria de reserva que explique
la diferencia de tiempos. Tampoco descartan problemas de rendimiento de disco,
CPU, red o hipervisor: son cifras contables de reserva, no mediciones de uso
real ni de latencia. Las reglas de rechazo no cubren todos los errores posibles
de OpenStack.

Las evidencias están en `datos/eventos_recursos.csv` y la evaluación por
reserva en `datos/recursos_por_intento.csv`. El nuevo grafo es
`resultados/grafo_ciclo_con_recursos_frecuencias.png` y su versión SVG.
Las nueve pruebas automáticas incluyen déficits simulados y reintentos, además
de los casos sin déficit que contiene este TAR.

## Interpretación y límites

- Las etiquetas de anomalía proceden de `anomaly_labels.txt`, no del nombre
  del archivo ni de una clasificación automática construida en esta práctica.
- Los cuatro casos etiquetados sí contienen una notificación de creación
  completada. "Anomalía" no se utiliza aquí como sinónimo de creación abortada.
- El modelo conserva una selección explícita de eventos. Que las ventanas
  tengan la misma variante no implica que todos sus detalles internos sean iguales.
- Las marcas originales no declaran zona horaria. Se comparan diferencias
  dentro del caso asumiendo relojes coherentes; no se ha auditado la sincronización.
- Los intervalos son tiempos transcurridos entre notificaciones. Pueden incluir
  esperas y el momento de emisión de los logs. No equivalen al tiempo de CPU.
- El inicio de nuestra medición es la reserva de recursos registrada, no el
  envío de una solicitud externa; el final tampoco acredita que una aplicación
  alojada en la VM esté lista para recibir tráfico.
- Cuatro casos etiquetados permiten una observación descriptiva de este
  experimento. No prueban una regla general para todos los proveedores cloud.
- El DFG agrega sucesiones; en el ciclo con variantes, una ruta que combina
  flechas de varios casos puede no existir como traza completa en los datos.

## Comprobaciones realizadas

El archivo coincide con el MD5 publicado. Las frecuencias del DFG de creación
coinciden con un recuento independiente de parejas consecutivas. Son 12 384
transiciones: 14 448 eventos menos 2 064 casos. La suma de las seis medias por
etapa coincide con la media de las duraciones de creación, porque esos casos
comparten la misma secuencia. Se han renderizado e inspeccionado los gráficos.
