# Procedencia y condiciones de los datos

Consulta y descarga: 10 de noviembre de 2026.

## Dataset completo

- Loghub, publicación v8: https://zenodo.org/records/8196385
- DOI: https://doi.org/10.5281/zenodo.8196385
- Repositorio: https://github.com/logpai/loghub
- Descripción OpenStack: https://github.com/logpai/loghub/blob/master/OpenStack/README.md
- Descarga: https://zenodo.org/records/8196385/files/OpenStack.tar.gz?download=1
- MD5: `66bd42c07837a094d9b0ea2d036b5713`.

Los datos de OpenStack se generaron en CloudLab para investigación y contienen
ejecuciones normales y anomalías introducidas. No se presentan como logs de un
cliente comercial en producción. El TAR se conserva sin modificar en
`datos/fuentes/OpenStack.tar.gz`.

Los archivos normal1 y normal2 se procesan juntos como referencia. El archivo
abnormal corresponde al experimento con inyección. Las cuatro UUID etiquetadas
se leen de `anomaly_labels.txt` dentro del TAR.

## Condiciones de distribución de Loghub

Texto publicado en Zenodo:

The datasets are freely available for research or academic work, subject to the
following condition: For any usage or distribution of the loghub datasets,
please refer to the loghub repository URL (https://github.com/logpai/loghub) and
cite the loghub paper (Loghub: A Large Collection of System Log Datasets for
AI-driven Log Analytics) where applicable.

The above license notice shall be included in all copies of the datasets.

Este aviso acompaña tanto la copia original como los CSV derivados.

## Referencias indicadas por los autores

- Jieming Zhu, Shilin He, Pinjia He, Jinyang Liu y Michael R. Lyu.
  "Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics".
  IEEE International Symposium on Software Reliability Engineering, 2023.
  https://arxiv.org/abs/2008.06448
- Min Du, Feifei Li, Guineng Zheng y Vivek Srikumar.
  "DeepLog: Anomaly Detection and Diagnosis from System Logs through Deep Learning".
  ACM CCS, 2017. https://acmccs.github.io/papers/p1285-duA.pdf

Los README originales consultados se incluyen en `datos/fuentes`.
Las plantillas del fichero de muestra se conservan como documentación del
vocabulario; el análisis usa los logs completos del TAR, no la muestra de 2 000 líneas.

## OpenStack y PM4Py

- OpenStack Nova: https://docs.openstack.org/nova/latest/
- PM4Py: https://github.com/process-intelligence-solutions/pm4py
- Ejemplos: https://processintelligence.solutions/pm4py

Los CSV, el código de preparación, los grafos y la comparación constituyen una
aplicación de PM4Py preparada para esta práctica a partir de esos datos.
