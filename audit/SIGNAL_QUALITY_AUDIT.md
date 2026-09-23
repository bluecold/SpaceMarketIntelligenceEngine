Auditoría de calidad de señales — segunda revisión, 22/09/2026

**Conclusión actual**

Hay correcciones efectivas, pero no corresponde cerrar toda la auditoría. De los 15 puntos originales, considero 3 corregidos dentro del alcance revisado, 10 parcialmente corregidos y 2 pendientes. Las nuevas pruebas también revelan regresiones en el cálculo de momentum y limitaciones nuevas en la comparación A/B.

Se revisó el árbol de trabajo con 15 archivos de aplicación modificados y todavía sin commit, sobre HEAD 0cce8d2. Ese commit por sí solo NO identifica la versión corregida. En esta revisión se modificaron únicamente los artefactos de audit/; se conservaron las modificaciones de aplicación existentes.

La primera auditoría queda preservada en [SIGNAL_QUALITY_AUDIT_round1.md](SIGNAL_QUALITY_AUDIT_round1.md). Este documento reemplaza sus conclusiones como evaluación vigente.

**Comprobaciones realizadas**

- python -m pytest tests/ -q: 171 passed, 19.07 s. El fallo de collect-news observado en la primera revisión no se reprodujo esta vez.
- python -m audit.verify_signal_audit_fixed: las 11 verificaciones pasan. Esto no demuestra que todos los problemas estén resueltos; algunas aserciones son demasiado débiles y no ejercitan la integración real.
- python -m audit.review_round2: contraejemplos adicionales reproducidos, con SQLite en memoria, HTTP simulado y precios sintéticos. No usa la base productiva ni realiza solicitudes de red.
- npm run build en frontend/: correcto, TypeScript y Vite.
- Revisión estática de integración backend/frontend, persistencia y configuración. No se realizó una prueba visual de navegador ni una evaluación de rentabilidad real.
- El script review_round2.py verifica el comportamiento defectuoso observado; no sustituye a tests de regresión que exijan el comportamiento corregido.
- reproduce_signal_audit.py se conserva como evidencia histórica de la primera ronda; contiene asercciones sobre defectos antiguos y ya no debe utilizarse como prueba de aceptación.

**Estado de los 15 puntos originales**

| ID original | Estado | Resultado de la segunda revisión |
|---|---|---|
| 1. Frescura de precios | Parcial | Detecta datos de hace años, pero acepta hasta 120 h y sigue utilizando velas diarias provisionales. La frescura difiere entre ranking, detalle y alertas. |
| 2. Contratos cerrados en PMS | Corregido | Directos y sectoriales excluyen estados cerrados/resueltos, resolución y vencimiento. El ejemplo original ahora devuelve PMS=None. |
| 3. Ceros sustituidos en Polymarket | Parcial | El parser conserva volumen/liquidez/cambio cero y no hereda esos datos del evento. El repositorio todavía reemplaza delta=0 por un delta calculado. |
| 4. Atribución por empresa | Parcial | Se pasa ticker y baja la relevancia genérica a 0.25. Otro patrón de competencia invierte ganador/perdedor; sentimiento y catalizador pueden discrepar. |
| 5. Noticias antiguas y cierre de alertas | Parcial | Noticias de 90 días ya no generan catalizadores activos. Los errores HTTP absorbidos por el proveedor siguen interpretándose como ingestas exitosas. |
| 6. Volumen alcista durante caídas | Parcial | Corregido en momentum: el caso original pasa de 41 a 31 con volumen alto. Sigue el bono alcista en technical_score. |
| 7. Momentum por cambios de cobertura | Parcial | El ejemplo de fuente desaparecida queda en 0 para 1D. La integración compara scores brutos con ajustados y produce +27 falso; 3D/5D siguen con +60. |
| 8. Compra sin confirmación de mercado | Parcial | STRONG BUY se degrada a BUY cuando status indica ausencia. No se exige precio válido; un status omitido elude el control. |
| 9. Emparejamiento del bootstrap | Parcial | Rechaza muestras sin ninguna fecha común; una sola fecha basta para volver a emparejar todo por índice. |
| 10. Reconstrucción histórica | Parcial | B ejecuta señales guardadas, pero A usa reglas actuales. En reconstrucción se vuelven a modular los pesos finales. |
| 11. Ejecución y métricas de portfolio | Pendiente | Sin cambio sustancial: entrada al precio del snapshot, horizontes calendario, sin valoración diaria a mercado y significancia sobre trades brutos. |
| 12. None en backtest | Corregido | Se comprueba smi is not None antes de comparar umbrales. El caso de snapshots con solo precio ya no falla. |
| 13. Modificadores sobrescritos | Corregido | Se conservan DILUTION RISK y OVEREXTENDED simultáneamente; también se acumula NO MKT DATA. |
| 14. Actualización UI/notificaciones | Parcial | El detalle depende de lastUpdate y verifica HTTP. La detección de primera respuesta todavía se infiere de renders; faltan protección contra respuestas atrasadas y revisión de last_update. |
| 15. Atomicidad y bloqueo | Pendiente | Agrupar las llamadas en try/rollback no anula sus commits internos. El mutex sigue siendo local al proceso y los errores de persistencia pueden acabar en SUCCESS. |

“Corregido” se refiere al defecto delimitado y revisado, no a la certificación completa del módulo.

**R2-01 · P1 · El bootstrap sigue sin un emparejamiento temporal válido**

Referencias: app/backtesting/engine.py:309–314 y :350–364.

La nueva comprobación solo verifica que la intersección de fechas no esté vacía. No alinea ni filtra las series antes del remuestreo. Si hay 40 operaciones por brazo y solo una fecha común, se comparan las 40 posiciones como si fueran pares.

Reproducción: desplazar 39 de las 40 operaciones B diez años, manteniendo una fecha común, produce exactamente el mismo resultado que las series alineadas: significancia positiva, p=0.0 e intervalo [0.5, 0.5].

Además, str(timestamp).split()[0] no normaliza ISO: una lista con datetime y otra con los mismos instantes serializados con “T” se rechaza como sin fechas comunes.

Consecuencia: persiste el riesgo de atribuir una ventaja estadística a Polymarket por comparaciones mal alineadas. Corrección: normalizar a UTC y construir ambos retornos de portfolio sobre un calendario común antes de remuestrear bloques de fechas. No basta con exigir una intersección no vacía.

**R2-02 · P1 · La corrección de momentum introduce una comparación de escalas distintas**

Referencias: app/jobs/runner.py:392–406; app/scoring/smi.py:268–288.

El runner reconstruye previous_scores con los valores brutos persistidos, incluido social_score. El cálculo actual compara esos datos con active_scores, cuyo componente social ya incorpora contracción por tamaño muestral.

Reproducción siguiendo la integración del runner: social bruto=0, un autor/post efectivo y noticias=50, sin cambios en estas evidencias. Al desaparecer el pilar fundamental, el social actual efectivo es 45 y el anterior utilizado en la comparación es 0: aparece momentum 1D de +27.0.

La prueba nueva que pasa previous_smi_1d como el diccionario completo del scorer no reproduce este camino: ese diccionario sí contiene active_scores ajustados. En producción se reconstruyen desde columnas distintas.

Adicionalmente:
- El ejemplo original de desaparición de social devuelve 1D=0, pero 3D=+60 y 5D=+60.
- Si siguen los mismos pilares, un cambio de pesos o calidad de PMS aún cambia el delta aunque no cambien scores.
- is_mom_comparable_1d no se persiste ni se consulta en generate_signal_and_explanation.

Corrección: persistir scores efectivos y pesos/versiones comparables, o reconstruirlos con la muestra histórica. Aplicar la misma política a 1D/3D/5D y bloquear alertas de aceleración cuando el índice no sea comparable.

**R2-03 · P1 · Se mezclan dos estrategias en A/B y se reaplican pesos finales**

Referencias: app/backtesting/engine.py:491–551; app/scoring/smi.py:117 y :156.

El brazo B usa base_signal y SMI de producción cuando existen; A se recalcula con las reglas actuales. Esto puede medir cambios de versión, umbrales o restricciones, además de la presencia de Polymarket.

Reproducción con prediction_score=None en todos los snapshots: una señal histórica BUY y RSI=80 permiten 2 entradas en B, mientras A obtiene 0 porque las reglas actuales degradan su score alto a WATCH. No había información de Polymarket que explicara la diferencia.

En la rama de reconstrucción sin señal almacenada, effective_weights se pasa como custom_weights y el scorer vuelve a aplicar prediction_quality. Reproducción sobre exactamente las mismas entradas: SMI original=91.9; con sus propios pesos finales reutilizados, SMI=95.8.

También los pesos omitidos en custom_weights se completan con configuración actual, por lo que un vector final incompleto no necesariamente representa los mismos pilares de origen.

Corrección: separar expresamente:
- Evaluación de lo efectivamente publicado, usando señales almacenadas.
- Experimento A/B, con idéntica versión, ejecución y configuración en ambos brazos, variando solamente Polymarket.

Persistir pesos base y finales con semántica diferente. Verificar igualdad de scores reconstruidos y que A y B coincidan cuando no existe el pilar retirado.

**R2-04 · P1 · La unidad de persistencia todavía no es atómica**

Referencias: app/jobs/runner.py:554–568 y :586; app/database/repository.py, commits en save_divergences, save_alerts y save_ssi_snapshot.

El bloque rotulado Atomic Unit of Work llama funciones que ya ejecutan db.commit(). Un rollback posterior no revierte esas escrituras.

Reproducción con SQLite en memoria: guardar una alerta, simular fallo al guardar el snapshot y ejecutar rollback deja la alerta persistida. El runner captura ese fallo y continúa hacia finish_job_run(..., status=SUCCESS).

El riesgo es una alerta nueva junto a un score viejo, sin error operativo visible. Además, asyncio.Lock no coordina otra CLI, otro worker ni otra instancia.

Corrección: los repositorios deben permitir flush sin commit; una sola transacción debe publicar la generación. Ante fallos, conservar la generación anterior completa y devolver PARTIAL/ERROR. Añadir una prueba de fallo entre cada escritura y un bloqueo persistente si hay varios procesos.

**R2-05 · P1 · Un fallo del proveedor todavía puede cerrar alertas**

Referencias: app/collectors/news_provider.py:43–47 y :84–87; app/jobs/runner.py:323–330 y :562.

GoogleRSSNewsProvider transforma HTTP no exitosos y excepciones en una lista vacía. ingest_news_for_ticker retorna normalmente; el runner pone news_success=True y habilita resolve_missing.

Reproducción: respuesta HTTP 503 simulada → ingesta (0, [], []) sin excepción → al aplicar la misma política de guardado se resuelve una alerta existente.

Además, la autorización para resolver todas las categorías depende solo de noticias: no refleja el éxito de social, mercado y fundamentales. A la inversa, un fallo de noticias que sí propague excepción puede impedir resolver señales ajenas a esa fuente.

Corrección: resultado de colección estructurado con estado, hora, cobertura y error. Resolver episodios con evidencia vigente de las fuentes de esa categoría, no con un booleano global. Mantener “desconocido por fallo” separado de “no hay evento” y “evento resuelto”.

**R2-06 · P1 · El repositorio sigue sustituyendo delta=0 por movimiento histórico**

Referencia: app/database/repository.py:270–288.

La condición todavía incluye probability_change_24h == 0.0. El cambio del comentario no elimina el comportamiento original.

Reproducción: snapshot de hace 24 h a 0.50; nuevo precio 0.70 con delta explícito=0.0 → el repositorio cambia el dato a +20.0 pp. La calidad temporal de esa comparación local puede ser diferente de la del proveedor.

La suite contiene una prueba que exige justamente esa sustitución (tests/test_prediction_market.py:261). Es necesario actualizar el contrato del dato y el test; conservar un test antiguo en verde no acredita corrección semántica.

Corrección: recurrir al historial únicamente para None, conservar el cero publicado y registrar divergencias entre proveedor y estimación local por separado. No convertir lo desconocido automáticamente en estabilidad.

**R2-07 · P1 · La frescura y la ejecutabilidad siguen siendo insuficientes**

Referencias: app/collectors/market_provider.py:213–234; app/scoring/signal.py:121 aproximadamente; app/api/dashboard.py:48–57 y :220–235; app/api/tickers.py:153–160.

El límite fijo de 120 horas evita el caso extremo de años, pero no detecta sesiones omitidas.

Reproducción determinista: consulta del jueves 24/09/2026 a las 16:00 UTC con última vela del lunes 21/09 → AVAILABLE. Ya faltaban sesiones, aunque la edad era menor que cinco días.

El control de señal sigue devolviendo BUY (NO MKT DATA) ante ausencia explícita. Con indicators={} se asume status=AVAILABLE y puede retornar STRONG BUY sin precio. El segundo caso es un defecto de la función compartida; el runner principal normalmente proporciona status, por lo que no implica que todas las ejecuciones live sigan ese camino.

Inconsistencia adicional por inspección: el ranking ahora revisa frescura de mercado, pero las alertas persistidas y el encabezado del detalle siguen consultando solamente la fecha del snapshot de análisis. Una cotización STALE puede convivir con alerta is_active=True y detalle is_stale=False. No se realizó una prueba de interfaz para este caso.

Corrección: una política común por sesión, dato y tipo de señal; exigir precio positivo, finito y vigente para recomendaciones operables. Usar estado no operable cuando falta. Distinguir datos intradía/provisionales y garantizar coherencia de frescura en todas las respuestas API.

**R2-08 · P1 · Persisten errores semánticos en eventos de competencia**

Referencias: app/sentiment/weighting.py:185–198 y calculate_news_score; app/sentiment/classifier.py.

Pasar ticker corrige la frase “selects X over Y”, pero la segunda expresión regular para “X beats Y” toma group(1) como derrotado; ese grupo representa al ganador. Tampoco todas las empresas están resueltas mediante sus aliases en esa rama.

Reproducción: “Rocket Lab beats SpaceX for NASA contract” produce RKLB=BEARISH y SPCX=BULLISH, ambos invertidos.

Otro caso: “NASA cancels Rocket Lab contract” produce sentimiento NEUTRAL, score=0.0 y confianza=0.7. El detector de catalizadores sí reconoce la cancelación, pero news_score consume el sentimiento y no la dirección del catalizador. Pueden coexistir alerta crítica y puntuación neutra.

Corrección: normalizar ganador/perdedor por entidad y cláusula, con pruebas para cada patrón y empresa. Añadir ejemplos etiquetados de cancelaciones/negación. Establecer una política explícita para desacuerdos entre sentimiento y evento, sin imponer indiscriminadamente una dirección al texto entero.

**R2-09 · P2 · El Market Score aún premia el volumen vendedor**

Referencia: app/technical/scorer.py, bloque Volume Ratio.

El ajuste direccional fue aplicado a momentum.py, pero no al score técnico. En una configuración bajista con precio debajo de EMA, RSI=40, MACD negativo y caída del 5%, pasar de volumen 1x a 3x aumenta technical_score de 9 a 13 sobre 40 (Market Score de 22.5 a 32.5).

Esto afecta la lectura técnica y los caminos que usan technical_score como fallback. No invalida la corrección del momentum principal, que sí fue comprobada.

Corrección: coherencia de dirección entre ambos motores y pruebas que cubran momentum, técnico, divergencias y fallback. Volumen neutral tampoco demuestra por sí solo acumulación institucional.

**R2-10 · P2 · La corrección de UI aún depende de estados ambiguos**

Referencias: frontend/src/components/AlertsManager.tsx:119, :170–188 y :249; frontend/src/components/TickerDetail.tsx:22–43; app/api/dashboard.py:246.

El segundo efecto con lista vacía se interpreta como respuesta del servidor sin alertas, pero puede deberse a setPermission o a un render anterior a finalizar el fetch. La primera respuesta real podría seguir notificando alertas preexistentes. Falta una señal explícita de carga terminada.

El detalle se refresca con lastUpdate, pero last_update es la fecha del ticker primero en el ranking, no una versión global ni la del activo seleccionado. Una actualización parcial de otro ticker puede no refrescarlo. Las solicitudes no se cancelan ni se comprueba a qué ticker/version corresponde la respuesta: una respuesta lenta anterior puede sobrescribir una más nueva.

Estos son hallazgos de revisión estática, no reproducción en navegador.

Corrección: pasar estado de primera carga exitosa y snapshot_id/job_id; sembrar notificaciones en ese momento. Invalidar por activo y cancelar/ignorar respuestas antiguas. Añadir pruebas de carreras, arranque con permiso concedido y actualizaciones parciales.

**R2-11 · P2 · Las verificaciones de cierre dan una seguridad excesiva**

Referencia: audit/verify_signal_audit_fixed.py:139.

La prueba del bootstrap evalúa diff_decade.get('date_overlap_count', 0) == 0, pero la función no retorna date_overlap_count. La aserción pasa por el valor por defecto, aun si se elimina la comprobación temporal. La propia salida muestra overlap=None seguido de PASS.

Otras limitaciones:
- La prueba de contexto usa una noticia vieja que se descarta; no comprueba qué dirección produce la ingesta con una noticia actual.
- La prueba de momentum pasa un diccionario de scores efectivos, diferente de la integración real del runner.
- La prueba de falta de mercado exige solamente que no haya STRONG BUY; acepta BUY.
- No hay fallo inyectado que compruebe atomicidad real.

Corrección: pruebas con expectativas de dominio, no solamente con el resultado del ejemplo inicial. Incluir integración runner/repositorio, fechas parcialmente solapadas, serialización de timestamps, tamaños muestrales pequeños y fallos de proveedores. Reemplazar los mensajes globales de “todos los problemas corregidos” por el alcance que realmente verifica cada prueba.

**Limitación cuantitativa que permanece abierta (original 11)**

No se corrigió la entrada al mismo precio del snapshot, el horizonte en días calendario ni la falta de valoración a mercado de posiciones abiertas. Sharpe y significancia siguen basados en retornos de trades brutos, separados de los costos/límites de la simulación del portfolio. Estas métricas no deben interpretarse todavía como evidencia suficiente de ventaja operable ni utilizarse para activar automáticamente la calibración.

**Plan priorizado de mejora**

1. Corregir transacciones y propagación de estados de proveedores; impedir alertas con estados inconsistentes y devolver PARTIAL/ERROR.
2. Persistir un contrato de snapshot reproducible: scores brutos/efectivos, tamaños efectivos, pesos base/finales, versión de reglas, tiempos de observación y disponibilidad.
3. Reconstruir momentum comparable para todos los horizontes y alinear el bootstrap por calendario. Separar reproducción histórica de experimento A/B.
4. Unificar elegibilidad/frescura/ejecutabilidad entre scorer, API y UI; mantener velas provisionales identificadas.
5. Corregir atribución semántica, deduplicar noticias por evento y medir desempeño del clasificador con un conjunto etiquetado del sector. No asumir que más artículos equivalen a más evidencia independiente.
6. Evaluar con precios posteriores ejecutables, costos y equity diario neto. Calibrar en un período y validar en otro posterior, evitando solapamiento de objetivos.
7. Añadir pruebas de integración y de fallos que cubran estas condiciones antes de optimizar pesos. Mantener la calibración automática desactivada hasta demostrar coherencia y resultados fuera de muestra.

Las correcciones mejoraron casos concretos y la suite está verde. Los contraejemplos de esta revisión muestran por qué ese resultado todavía no equivale a validar la calidad predictiva o la confiabilidad operativa del sistema.

