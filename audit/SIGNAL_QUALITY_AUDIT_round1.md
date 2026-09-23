Auditoría de calidad de señales — 22 de septiembre de 2026
Repositorio revisado: Space Sentiment Index, commit 0cce8d2.

El sistema tiene una separación modular útil, controles de ausencia de datos, contracción de muestras sociales pequeñas y persistencia de snapshots. Sin embargo, encontré fallos que permiten introducir evidencia vencida, atribuir eventos a la empresa equivocada y presentar cambios de cobertura como mejoras de señal. La validación histórica tampoco demuestra todavía que las señales publicadas tengan la eficacia que sugieren sus métricas.

No se modificó la lógica de la aplicación. Esta revisión combina inspección de código, ejecución de la suite existente y 11 casos reproducibles sintéticos. No constituye una medición de rentabilidad real: no se evaluó un historial operativo completo ni se certificó la disponibilidad actual de todos los proveedores.

**Verificación realizada**

- Suite: python -m pytest tests/ -q → 170 passed, 1 failed en 35.28 segundos.
- Falló tests/test_cli.py::test_cli_collect_news: no había noticias recientes de ASTS pese al mensaje de éxito. Ejecutada sola: 1 passed. La causa exacta del fallo de conjunto queda pendiente; el resultado exige revisar estado compartido, datos residuales y aislamiento.
- Frontend: npm run build → correcto; TypeScript y Vite completaron la compilación.
- Reproducciones: python -m audit.reproduce_signal_audit → 11 escenarios confirmados. El script no usa red ni base productiva; sus aserciones documentan defectos actuales, no el comportamiento deseado.
- La suite original sí contiene caminos hacia yfinance sin sustitución, por ejemplo collect-market en tests/test_cli.py. No debe describirse como completamente aislada de red.
- No se hizo una prueba visual automatizada del navegador; los hallazgos de interfaz son de revisión estática.

P1 significa prioridad alta por impacto en señales o su validación. P2 significa impacto secundario, operativo o condicionado a un escenario concreto. No se estima aquí la frecuencia real de cada fallo en producción.

**1. P1 — Una consulta nueva puede presentar precios viejos como actuales**

Ubicación: app/collectors/market_provider.py:175 y :234; app/jobs/runner.py:214; app/api/dashboard.py:41.

El proveedor marca AVAILABLE cualquier serie válida con al menos cinco filas. Guarda candle_date y observed_at, pero no exige que la última vela corresponda a la sesión esperada. El dashboard calcula antigüedad desde la creación del snapshot del análisis, no desde la observación de precios.

Reproducción: una serie terminada el 30/01/2020 devuelve status=AVAILABLE. Al procesarla ahora, un snapshot nuevo puede figurar fresco aunque el precio sea antiguo.

Además, el pipeline usa la última vela diaria durante la sesión: volumen parcial y cierre provisional se comparan con días completos. Esto puede producir cambios de señal intradía y penalizaciones artificiales de volumen.

Corrección propuesta: validar frescura por sesión bursátil, distinguir vela cerrada de provisional y bloquear confirmaciones operativas con precios obsoletos. Conservar por separado hora de consulta, fecha de vela, hora de disponibilidad y estado de sesión.

**2. P1 — Contratos cerrados o resueltos contribuyen al PMS**

Ubicación: app/scoring/prediction.py:36 y :79; app/jobs/runner.py:297; app/collectors/polymarket_provider.py:425.

El parser identifica CLOSED/RESOLVED, pero el scorer solamente comprueba ticker y quality_score. El pipeline puntúa directamente los contratos en memoria. El filtro de contratos activos del repositorio no protege ese camino.

Reproducción: contrato RESOLVED, vencido hace dos días y con probabilidad YES=100% → PMS=80.0. Un resultado conocido puede parecer una expectativa prospectiva favorable. También puede aparecer en el score y no en el listado de contratos activos del detalle.

Corrección propuesta: centralizar elegibilidad y exigir estado activo, vigencia, precio válido y frescura tanto en ingesta como en scoring. La documentación oficial separa estados del evento y de sus mercados: https://docs.polymarket.com/api-reference/events/list-events.

**3. P1 — Se sustituyen ceros legítimos por datos del evento padre**

Ubicación: app/collectors/polymarket_provider.py:378 y :383; app/database/repository.py:270 aproximadamente, dentro de save_prediction_markets.

El uso de cadenas con “or” confunde cero con ausencia. Un contrato con liquidity=0 puede heredar la liquidez agregada del evento; un oneDayPriceChange=0 puede heredar otro cambio de precio. El repositorio vuelve a tratar un cambio de 0 como dato faltante y puede reemplazarlo por una comparación local de entre 18 y 30 horas.

Impacto: calidad de mercado y momentum ficticios, precisamente en contratos que deberían tener menos peso.

Corrección propuesta: diferenciar None de 0, conservar la procedencia de cada campo y no atribuir liquidez agregada a un contrato individual. Conservar “cambio desconocido” como ausencia; usar puntos históricos con tolerancia explícita. Hallazgo por inspección, no incluido en las 11 reproducciones.

**4. P1 — Noticias y catalizadores sin atribución correcta por empresa**

Ubicación: app/sentiment/weighting.py:120 y :190; app/jobs/runner.py:104 y :164; app/sentiment/classifier.py:113.

Los términos genéricos space/launch/rocket alcanzan relevancia 0.40, exactamente el umbral de inclusión. Un título sectorial puede participar como evidencia específica de ASTS aunque no la mencione. Además, las llamadas a detect_catalysts omiten ticker; el clasificador de sentimiento también puntúa el documento completo sin separar entidades.

Reproducciones:
- “Rocket launch success and growth”, sin ASTS → relevancia 0.4 y news_score=88.1 para ASTS.
- “NASA selects SpaceX over Rocket Lab for contract”, procesado para SPCX → GOVERNMENT_CONTRACT BEARISH CRITICAL. La misma función con ticker=SPCX devuelve BULLISH.

Corrección propuesta: exigir vínculo explícito para noticias directas; procesar noticias sectoriales mediante impactos separados. Pasar ticker al detector y resolver sujeto, acción, beneficiario y perjudicado. Añadir corpus de frases con múltiples empresas, negaciones, rumores y comparaciones.

**5. P1 — Alertas críticas de noticias antiguas y resoluciones por ausencia de datos**

Ubicación: app/jobs/runner.py:160 y :279; app/database/repository.py:489.

Los catalizadores se generan a partir de todo lo recibido en la consulta, antes del filtro temporal que luego usa el news_score. El feed no se limita explícitamente a tres días. Una noticia antigua puede generar hoy una alerta crítica y reaparecer cada vez que vuelva al feed.

Reproducción: un artículo publicado hace 90 días sigue aportando GOVERNMENT_CONTRACT CRITICAL durante la ingesta.

En sentido inverso, si la consulta falla o deja de devolver una noticia, catalysts_found puede quedar vacío y save_alerts resuelve el episodio aunque el riesgo no se haya resuelto.

Corrección propuesta: generar alertas desde evidencia persistida vigente, con fecha del evento, identificador de noticia y política de expiración. Diferenciar “no observado por error” de “resuelto”.

**6. P1 — El volumen alto suma momentum alcista aun cuando el precio cae**

Ubicación: app/scoring/momentum.py:56; app/technical/scorer.py, bloque Volume Ratio.

El volumen agrega puntos positivos sin comprobar dirección ni posición del cierre. Una caída con fuerte negociación obtiene mejor puntuación que la misma caída con volumen normal.

Reproducción: precios 110 → 100 en seis observaciones; volumen 1x → momentum 41.0; volumen 3x → momentum 51.0.

Corrección propuesta: usar volumen como confirmación de una dirección ya definida, o como medida separada de intensidad. Volumen alto por sí solo no identifica compras institucionales.

**7. P1 — Cambios de cobertura se convierten en falsas aceleraciones del SMI**

Ubicación: app/scoring/smi.py:180 y :230; app/jobs/runner.py:365.

Al faltar una fuente se redistribuyen pesos. Después se compara ese SMI con el anterior sin controlar qué fuentes y pesos estaban presentes. Cambia la composición del índice, aunque las evidencias supervivientes sean idénticas.

Reproducción: social=0 y noticias=100 → SMI=40. Si desaparece social y noticias sigue en 100 → SMI=100, momentum de +60 puntos.

Corrección propuesta: separar variación por nueva evidencia de variación por cobertura; calcular deltas sobre fuentes comunes y pesos comparables. Si no existe comparabilidad, mostrar “no comparable” y no emitir una alerta de aceleración.

**8. P1 — La cobertura permite compras fuertes sin confirmación de mercado**

Ubicación: app/scoring/smi.py:193; app/scoring/signal.py:99 y :121.

data_quality es porcentaje de pilares presentes, no calidad efectiva. Dos pilares son 33.3%, superan el límite de 30%, y pueden producir compras fuertes. La ausencia de mercado solo agrega un texto; no cambia base_signal. confidence tampoco es un requisito para comprar.

Reproducción: social=100 y noticias=100, sin datos técnicos ni precio → STRONG BUY (NO MKT DATA), calidad 33.3%.

Corrección propuesta: distinguir score informativo de señal operable. Si la señal pretende ser de ejecución, exigir cotización vigente y corroboración suficiente; conservar el estado de observación cuando faltan. Medir calidad por frescura, diversidad, datos válidos y tamaño efectivo. Dos fuentes que repiten la misma noticia no son dos confirmaciones independientes.

**9. P1 — El bootstrap no empareja por fechas ni por exposición**

Ubicación: app/backtesting/engine.py:302 y :329.

Con igual número de operaciones empareja las posiciones de dos listas; con longitudes distintas usa posiciones relativas. No consulta timestamps ni tickers. Igual número de trades no significa operaciones simultáneas. Los bloques tampoco garantizan mantener juntos todos los activos del mismo día.

Reproducción: desplazar todas las operaciones B diez años deja exactamente iguales los resultados estadísticos; en el ejemplo el intervalo sigue [0.5, 0.5].

Impacto: la significancia usada para atribuir valor incremental a Polymarket y ajustar pesos no está respaldada por el emparejamiento temporal anunciado.

Corrección propuesta: construir retornos netos diarios de ambos portfolios sobre el mismo calendario, incluyendo efectivo, y remuestrear bloques comunes de fechas. Definir antes la hipótesis y separar calibración de evaluación. Actualmente el ajuste dinámico está desactivado por defecto; el defecto ya afecta al informe estadístico.

**10. P1 — El backtest no reconstruye las señales históricas con su configuración**

Ubicación: app/backtesting/engine.py:406, :482, :521 y :836.

Se leen effective_weights, base_signal y rules_version del snapshot, pero la evaluación recalcula con static_weights y reglas actuales. Los cambios de configuración pueden alterar retrospectivamente las entradas evaluadas.

Reproducción: snapshots con señal STRONG BUY, SMI=100 y pesos guardados concentrados en social generan cero entradas al recalcular con los pesos estáticos.

Corrección propuesta: separar dos modos: evaluación de señales efectivamente publicadas y experimento hipotético A/B con configuración congelada. Persistir configuración base y reglas necesarias para reconstrucción. No reutilizar pesos finales como pesos base sin más: se aplicaría otra vez la modulación por calidad.

**11. P1 — Precios de entrada y métricas históricas no representan todavía una ejecución completa**

Ubicación: app/backtesting/engine.py:443, :572, :597, :201 y :229.

La entrada usa el precio del mismo snapshot que contiene la señal; después del cierre ese precio puede ser el cierre anterior, no ejecutable cuando se conoció la información. El horizonte suma días calendario, permite tolerancias amplias y anualiza como si fueran sesiones homogéneas.

El portfolio valora posiciones abiertas por el capital originalmente asignado. No hay valoración diaria a mercado; por tanto, portfolio_max_drawdown_pct puede omitir pérdidas intermedias. Sharpe y significancia se calculan sobre retornos brutos de trades, mientras los costos y límites de capital viven en otra simulación.

Corrección propuesta: entrada en la próxima observación ejecutable posterior a la señal, calendario de sesiones y ajuste consistente por splits/dividendos. Calcular equity y retornos diarios netos del portfolio con valoración a mercado; usar esa misma serie para riesgo y comparaciones. Hallazgo por inspección.

**12. P2 — El backtest puede detenerse ante scores ausentes**

Ubicación: app/backtesting/engine.py:502 y :561.

Si hay precio pero todos los pilares están ausentes/excluidos, calculate_smi retorna None. Compararlo con buy_threshold causa TypeError.

Reproducción: dos snapshots con ticker y precio, sin scores → “'>=' not supported between instances of 'NoneType' and 'float'”.

Corrección propuesta: descartar explícitamente observaciones no evaluables, registrar motivo y contabilizarlas en cobertura.

**13. P2 — Se pierden advertencias por sobrescritura**

Ubicación: app/scoring/signal.py:109, :117 y :123.

Los modificadores se acumulan para dilución pero luego se sustituyen por OVEREXTENDED o NO MKT DATA.

Reproducción: SMI=90, runway=3 meses y RSI=80 → BUY (OVEREXTENDED), sin DILUTION RISK en la etiqueta. La alerta fundamental separada sigue existiendo; el problema es la pérdida de información en la señal resumida.

Corrección propuesta: lista de modificadores independientes, ordenada por severidad, serializada sin sobrescrituras.

**14. P2 — El detalle puede quedar viejo y el arranque silencioso de alertas es incompleto**

Ubicación: frontend/src/components/TickerDetail.tsx:22; frontend/src/components/AlertsManager.tsx:169; frontend/src/App.tsx:16.

El modal carga solamente cuando cambia ticker; no se actualiza al completar un análisis ni con el refresco del dashboard. Puede mostrar una señal anterior mientras el ranking ya cambió.

AlertsManager consume el indicador de primer montaje aun si alerts está vacío. App comienza pasando una lista vacía mientras descarga el dashboard; la primera respuesta real puede tratar alertas existentes como nuevas, si no están en el registro local y cumplen los demás filtros.

Corrección propuesta: asociar el detalle a una versión de snapshot/refresco y sembrar notificaciones después de la primera carga exitosa, distinguiendo “cargando” de “sin alertas”. Mostrar errores HTTP, estado de reconexión y fin de espera de jobs.

**15. P2 — Persistencia parcial y exclusión mutua limitada a un proceso**

Ubicación: app/jobs/runner.py:236, :485, :535 y :556; app/database/repository.py:492.

Precios, alertas y snapshot de score se guardan en commits separados. Las alertas se persisten antes del snapshot; si falla este último, el error se captura y el job puede terminar SUCCESS. El dashboard también combina los últimos snapshots independientes.

asyncio.Lock protege el proceso actual; no coordina una CLI ejecutada aparte, otro worker o una segunda instancia del servidor.

Corrección propuesta: publicar atómicamente una generación consistente por ticker/job; rollback y estado PARTIAL/ERROR cuando corresponda. Usar bloqueo transaccional o lease persistente si existen varios procesos, y recuperación de jobs abandonados.

**Mejoras para aumentar calidad: orden sugerido**

1. Corregir primero integridad: vigencia de precios y contratos, ceros legítimos, atribución por entidad, alertas temporales y errores con None. Convertir las reproducciones en pruebas que exijan el comportamiento corregido.
2. Definir qué significa cada señal: horizonte, momento de entrada, salida y requisitos de evidencia. Mantener separados sentimiento, dirección, riesgo y ejecutabilidad.
3. Agrupar noticias por evento y origen. Las URLs distintas de una noticia sindicada hoy cuentan como noticias distintas; además, el runner pasa cantidad bruta al bono de confianza. Usar eventos independientes y noticias relevantes como tamaño efectivo. Limitar también concentración por autor en social, no solo contar autores.
4. Validar sentimiento en un conjunto etiquetado del sector, por empresa e idioma, midiendo errores críticos. Comparar heurística y FinBERT en ese conjunto; cambiar de modelo sin medición no garantiza mejora.
5. Rediseñar validación con precios ejecutables, costos, calendario y configuración congelada. Evaluar cronológicamente fuera de muestra, separar ventanas cuyos retornos se solapan y comparar con estrategias simples y con cada pilar eliminado. Informar tamaño de muestra, incertidumbre y resultados por activo/régimen.
6. Mantener la calibración automática desactivada hasta validar lo anterior. Una mejora debe demostrar estabilidad fuera de muestra y rendimiento neto, no solo más señales o mayor SMI.
7. Mostrar en interfaz peso efectivo, fuentes excluidas y motivo, hora real del dato, independencia de evidencias y trazabilidad de cada alerta a sus documentos.
8. Endurecer fundamentos: frescura y completitud por componente, períodos contables comparables y publicación conocida al momento de análisis. No equiparar “un campo disponible” con salud financiera completa; los datos faltantes aún producen algunas imputaciones neutrales en calculate_fundamental_score.
9. Mejorar operación: aislamiento de tests, dependencias reproducibles, errores visibles, tiempos límite de consultas/jobs, transacciones consistentes y documentación acorde al comportamiento real.

Antes de optimizar pesos o agregar indicadores, corregiría los puntos 1–11: afectan directamente qué evidencia entra, cómo se interpreta y cómo se mide si funciona. Una auditoría de código confirma estos mecanismos, pero no permite prometer un aumento específico de aciertos o rentabilidad.

