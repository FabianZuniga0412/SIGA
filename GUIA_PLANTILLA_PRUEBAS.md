# Guía rápida de plantillas (SIGA)

Archivos incluidos:
- `plantilla_pruebas_siga.csv`: registro de cada prueba individual
- `plantilla_resumen_siga.csv`: resumen de métricas con fórmulas

## Cómo usar en Google Sheets (recomendado)
1. Crea una hoja nueva.
2. Importa `plantilla_pruebas_siga.csv` en una pestaña llamada exactamente: `plantilla_pruebas_siga`.
3. Importa `plantilla_resumen_siga.csv` en otra pestaña llamada: `Resumen`.
4. Verifica que las fórmulas de `Resumen` se calculen.
5. Si tu configuración regional usa `;` en fórmulas, reemplaza `,` por `;`.

## Campos clave para tu reporte
En `plantilla_pruebas_siga.csv` llena siempre:
- `Resultado` (`Exito` o `Fallo`)
- `Tiempo_Validacion_ms`
- `Escenario_Iluminacion` (`Buena`, `Media`, `Mala`)
- `Escenario_Red` (`Normal`, `Lenta`, `Sin red`)
- `Dispositivo` (`Desktop`, `Movil`)
- `Motivo_Fallo` cuando aplique

## Gráficas recomendadas para el documento
1. Barras: `Tasa_Exito_%` por escenario (buena/mala luz, red normal/lenta/sin red, desktop/móvil)
2. Barras: `Tiempo_Promedio_ms` y `P95_ms` por escenario

## Texto listo para pegar (Resultados)
- Se ejecutaron **N** pruebas en total.
- La tasa de éxito global fue **X%**.
- El tiempo promedio de validación fue **Y ms**, con un p95 de **Z ms**.
- En condiciones de buena iluminación se obtuvo **A%**, mientras que en mala iluminación **B%**.
- Bajo red lenta/sin red, la validación completa cayó a **C%**, aunque el registro offline se conservó en **D%** de los casos.

## Texto listo para pegar (Discusión)
- El rendimiento observado (**X%**) quedó [por encima/por debajo] de la meta de **95%**.
- La principal limitación fue [iluminación/red/dispositivo], con impacto en [tasa de éxito/latencia].
- En móvil se observó [mejor/peor] desempeño respecto a escritorio, posiblemente por [cámara, autofocus, estabilidad de red].
- El modo offline permitió [solo logging / validación parcial], por lo que se recomienda [colas de reintento, confirmación diferida, sincronización automática].
