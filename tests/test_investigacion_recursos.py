"""Comprobar los criterios de falta de recursos con casos que no hay en el TAR."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from investigacion_recursos import (
    construir_tabla_intentos,
    interpretar_mensaje_recursos,
    investigar_recursos,
    resumir_intento,
)


def crear_registro(mensaje, peticion="req-a", linea=1):
    """Crear una observación con la misma estructura que entrega el lector de logs."""
    registro = {
        "caso": "referencia:vm-a", "uuid": "vm-a", "experimento": "referencia",
        "etiqueta": "sin_etiqueta_anomalia", "peticion": peticion,
        "fecha": pd.Timestamp("2017-05-14 21:07:37") + pd.Timedelta(milliseconds=linea),
        "archivo": "ejemplo.log", "linea": linea,
        "componente": "nova.compute.claims", "mensaje_original": mensaje,
    }
    registro.update(interpretar_mensaje_recursos(mensaje))
    return registro


SOLICITUD = "Attempting claim: memory 2048 MB, disk 20 GB, vcpus 1 CPU"


class InvestigacionRecursosTests(unittest.TestCase):
    def test_extrae_decimales_y_rechaza_textos_ajenos(self):
        datos = interpretar_mensaje_recursos("Total memory: 64172 MB, used: 512.25 MB")
        self.assertEqual(datos["memoria_usada_mb"], 512.25)
        self.assertIsNone(interpretar_mensaje_recursos("Creating image"))

    def test_compara_con_limite_y_no_con_total(self):
        registros = [
            crear_registro(SOLICITUD),
            crear_registro("Total memory: 4096 MB, used: 4000.00 MB"),
            crear_registro("memory limit: 8192.00 MB, free: 4192.00 MB"),
            crear_registro("Claim successful"),
        ]
        intento = resumir_intento(registros, 1)
        self.assertTrue(intento["memoria_supera_total_declarado"])
        self.assertEqual(intento["margen_memoria_tras_solicitud_mb"], 2144)
        self.assertEqual(intento["evaluacion_reserva"], "sin_deficit_de_memoria_observado")

    def test_deficit_y_limite_exacto(self):
        for libre, evaluacion in [
            (1024, "deficit_segun_memoria_libre_declarada"),
            (2048, "sin_deficit_de_memoria_observado"),
        ]:
            with self.subTest(libre=libre):
                registros = [crear_registro(SOLICITUD), crear_registro(
                    f"memory limit: 4096 MB, free: {libre} MB"
                )]
                self.assertEqual(resumir_intento(registros, 1)["evaluacion_reserva"], evaluacion)

    def test_disco_sin_limite_no_se_convierte_en_rechazo(self):
        registros = [
            crear_registro(SOLICITUD),
            crear_registro("Total disk: 15 GB, used: 0.00 GB"),
            crear_registro("disk limit not specified, defaulting to unlimited"),
            crear_registro("memory limit: 96258 MB, free: 95746 MB"),
        ]
        intento = resumir_intento(registros, 1)
        self.assertTrue(intento["disco_supera_total_declarado"])
        self.assertTrue(intento["disco_sin_limite_de_reserva"])
        self.assertFalse(intento["rechazo_explicito"])
        self.assertEqual(intento["evaluacion_reserva"], "sin_deficit_de_memoria_observado")

    def test_ausencia_de_medidas_no_se_interpreta_como_suficiencia(self):
        intento = resumir_intento([crear_registro(SOLICITUD)], 1)
        self.assertEqual(intento["evaluacion_reserva"], "datos_insuficientes")
        self.assertIsNone(intento["memoria_libre_mb"])

    def test_rechazo_explicito_se_conserva_sin_medidas(self):
        registro = crear_registro("Claim failed: not enough memory")
        intento = resumir_intento([registro], 1)
        self.assertTrue(intento["rechazo_explicito"])
        self.assertEqual(intento["evaluacion_reserva"], "rechazo_explicito_observado")

    def test_separa_reintentos_y_peticiones_intercaladas(self):
        registros = [
            crear_registro(SOLICITUD, "req-a", 1),
            crear_registro(SOLICITUD, "req-b", 2),
            crear_registro("memory limit: 4096 MB, free: 1000 MB", "req-a", 3),
            crear_registro("Claim failed", "req-a", 4),
            crear_registro(SOLICITUD, "req-a", 5),
            crear_registro("Claim successful", "req-a", 6),
        ]
        intentos = construir_tabla_intentos(pd.DataFrame(registros))
        self.assertEqual(len(intentos), 3)
        segundo_a = intentos[
            intentos["peticion"].eq("req-a") & intentos["intento_en_peticion"].eq(2)
        ].iloc[0]
        self.assertEqual(segundo_a["evaluacion_reserva"], "datos_insuficientes")
        self.assertFalse(segundo_a["rechazo_explicito"])
        self.assertTrue(segundo_a["reserva_confirmada"])

    def test_log_ampliado_no_duplica_las_lineas_compartidas(self):
        solicitud = crear_registro(SOLICITUD, linea=1)
        estado = crear_registro("Total memory: 64172 MB, used: 512.00 MB", linea=2)
        campos_evento = [
            "caso", "uuid", "actividad", "fecha", "experimento", "etiqueta",
            "archivo", "linea", "componente", "mensaje_original",
        ]
        eventos = pd.DataFrame([solicitud], columns=campos_evento)
        casos = pd.DataFrame([{"caso": solicitud["caso"], "duracion_creacion_s": 20.5}])
        with TemporaryDirectory() as carpeta:
            resumen = investigar_recursos([solicitud, estado], eventos, casos, Path(carpeta))
            ampliado = pd.read_csv(Path(carpeta) / "eventos_vm_con_recursos.csv")
            self.assertEqual(len(ampliado), 2)
            self.assertEqual(resumen["evaluaciones_reserva"], {"datos_insuficientes": 1})

    def test_sin_registros_de_recursos_deja_cabeceras_y_cobertura(self):
        solicitud = crear_registro(SOLICITUD)
        eventos = pd.DataFrame([solicitud]).drop(columns=[
            "peticion", "tipo_registro", "memoria_solicitada_mb", "disco_solicitado_gb",
            "cpu_solicitada",
        ])
        casos = pd.DataFrame([{"caso": solicitud["caso"], "duracion_creacion_s": None}])
        with TemporaryDirectory() as carpeta:
            resumen = investigar_recursos([], eventos, casos, Path(carpeta))
            tabla = pd.read_csv(Path(carpeta) / "recursos_por_intento.csv")
            self.assertTrue(tabla.empty)
            self.assertIn("evaluacion_reserva", tabla.columns)
            self.assertEqual(resumen["casos_ciclo_sin_registros_recursos"], [solicitud["caso"]])


if __name__ == "__main__":
    unittest.main()
