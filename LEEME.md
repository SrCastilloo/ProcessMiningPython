# OpenStack y PM4Py: de registros técnicos a un proceso analizable

Práctica preparada el 10 de noviembre de 2026. El dataset se obtuvo en CloudLab;
los eventos son de mayo de 2017. Los resultados describen ese experimento.

## Objetivo

Estudiar el proceso de creación de máquinas virtuales a partir de registros
externos de OpenStack. Generar grafos de frecuencias y tiempos, y comparar las
VMs etiquetadas con anomalías por los autores con las que no tienen esa etiqueta.

El registro completo publicado está incluido. No se necesita instalar OpenStack
ni conectarse a una nube para ejecutar esta práctica.

## Qué hace cada script

| Archivo | Entrada | Salida principal |
| --- | --- | --- |
| `01_preparar_datos.py` | TAR de logs originales y etiquetas de sus autores | CSV de eventos, casos y duraciones |
| `02_analizar_procesos.py` | CSV preparados | Grafos PM4Py, variantes y comparación de tiempos |

El primer script también llama a `investigacion_recursos.py`: conserva las
solicitudes y los diagnósticos de memoria, disco y CPU, y compara la memoria
solicitada con la libre declarada. Los resultados adicionales están en
`datos/eventos_recursos.csv`, `datos/recursos_por_intento.csv` y
`datos/investigacion_recursos.json`. El log `datos/eventos_vm_con_recursos.csv`
incluye estas consultas para generar un grafo ampliado en el segundo script.
La sección 10 de `GUIA_CODIGO.md` explica las reglas y cómo interpretar las cifras.

La separación permite observar un paso nuevo respecto al ejemplo de solicitudes:
antes de llamar a PM4Py hay que convertir los mensajes técnicos en eventos.

