# 🚀 SPACE MARKET INTELLIGENCE ENGINE (SMIE v2.2) — CONTEXTO MAESTRO DEL PROYECTO

> **Documento de Continuidad Arquitectónica, Contexto Técnico y Hoja de Ruta**  
> *Diseñado para que cualquier desarrollador o IA (Claude Code, Cursor, Windsurf, Antigravity, etc.) comprenda inmediatamente el sistema, sus decisiones de diseño, estado actual, fórmulas cuantitativas y manual de operación.*

---

## 1. 🔭 Visión y Propósito del Proyecto

**Space Market Intelligence Engine (SMIE v2.2)** es una plataforma de análisis cuantitativo e inteligencia de mercado diseñada específicamente para el sector espacial y aeroespacial estadounidense ($ASTS, $RKLB, $SATL, $SPCE, $SPCX, etc.).

### El Problema que Resuelve
La industria aeroespacial se caracteriza por una extrema dependencia de **eventos binarios de alto impacto** (lanzamientos de cohetes, anomalías de vuelo, despliegue de constelaciones satelitales, aprobaciones de espectro por la FCC, contratos de defensa con NASA/DoD y rondas de dilución por quema de caja). Los modelos tradicionales de análisis técnico o fundamental a menudo fallan al no capturar a tiempo la narrativa social ni las probabilidades implícitas en mercados de predicción ni el riesgo de solvencia.

SMIE resuelve esto sintetizando **cinco fuentes de información completamente desacopladas**:
1. **Narrativa Social (X / Twitter):** Sentimiento y euforia de la comunidad minorista e institucional con ponderación por confianza y contracción bayesiana.
2. **Prediction Markets (Polymarket):** Expectativas financieras donde los participantes arriesgan capital real sobre eventos concretos.
3. **Noticias & Catalizadores (Google News RSS):** Detección temprana de contratos, lanzamientos, acuerdos, anomalías de vuelo y fallos de misión (`LAUNCH_FAILURE`).
4. **Factores Fundamentales & Supervivencia de Caja (yfinance DataFrames):** Detección de quema de caja y alertas por umbral de dilución (`CAPITAL_RAISE_RISK` para runway $<6$ meses).
5. **Acción Técnica del Precio & Medición de Riesgo (yfinance):** Contexto de tendencia, volatilidad (ATR/Bollinger) y sobreextensión. Desde v2.2 es un **complemento**: el SMI lo mueven los pilares de sentimiento (80% del peso) y el técnico enmarca y frena señales.

---

## 2. 🏗️ Arquitectura General del Sistema

El sistema está construido como un **Monolito Modular** en Python 3.11+ con interfaz web moderna en React 18 / TypeScript / Vite:

```text
                                ┌─────────────────────────────────────────────────────────┐
                                │                 DATA COLLECTORS LAYER                   │
                                │  - X/Twitter (Twikit / Mock Fallback con Provenance)    │
                                │  - Polymarket Gamma API (Mock Fallback con Provenance)  │
                                │  - News (Google News RSS Feed Parser)                   │
                                │  - Market Data (yfinance OHLCV 1Y con asyncio.to_thread)│
                                │  - Balance Sheet / Cashflow DataFrames (Cache 24h)      │
                                └────────────────────────────┬────────────────────────────┘
                                                             │
                                                             ▼
                                ┌─────────────────────────────────────────────────────────┐
                                │                 PROCESSORS & NLP LAYER                  │
                                │  - Sentiment: FinBERT (news) / FinTwitBERT (X posts)   │
                                │  - Disambiguation: multi-word ATH vs negative metrics   │
                                │  - log1p Engagement Weight: ln(1+likes+2·rt+...)       │
                                │  - Exp Decay Recency Weight: exp(-lambda·age)          │
                                │  - Confidence Multiplier Weighting                      │
                                │  - Polymarket Quality Scorer (0-100 Quality Threshold)  │
                                │  - Catalyst Categorizer & Hierarchy (LAUNCH_FAILURE)    │
                                │  - Technical Indicators (EMA200, RSI, BB, MACD, ATR)    │
                                └────────────────────────────┬────────────────────────────┘
                                                             │
                                                             ▼
                                ┌─────────────────────────────────────────────────────────┐
                                │                 QUANT SCORING ENGINES                   │
                                │  - SSI (Social Sentiment Score, 0-100, Null-Safe)       │
                                │  - PMS (Prediction Market Score, 0-100)                 │
                                │  - News Score (0-100)                                   │
                                │  - Price Momentum Score (0-100)                         │
                                │  - Fundamental Health Score (0-100 & Runway Months)     │
                                │  - Technical Score (0-40)                               │
                                │  - Risk & Safety Score (0-100)                          │
                                └────────────────────────────┬────────────────────────────┘
                                                             │
                                                             ▼
                                ┌─────────────────────────────────────────────────────────┐
                                │                 SMI & DIVERGENCE ENGINE                 │
                                │  - SMI (Space Market Intelligence Index, 0-100)         │
                                │  - Adaptive Weight Normalization (No Fake Imputation)   │
                                │  - Dynamic Closed-Loop Weight Calibration (Backtest)    │
                                │  - Source Agreement & Directional Cohesion Metric       │
                                │  - Tripartite Divergence Engine (X vs Poly vs Price)    │
                                │  - Signal Generator (STRONG BUY, BUY, WATCH, HOLD, etc) │
                                │  - Capital Preservation Gates (Dilution, Quality, Conf) │
                                │  - Quantitative "WHY?" Explanation Engine               │
                                └────────────────────────────┬────────────────────────────┘
                                                             │
                                ┌────────────────────────────┴────────────────────────────┐
                                │                                                         │
                                ▼                                                         ▼
                 ┌─────────────────────────────┐                           ┌─────────────────────────────┐
                 │      PERSISTENCE LAYER      │                           │     PRESENTATION LAYER      │
                 │  - SQLite WAL (Auto-migrate)│                           │  - FastAPI REST API (Async) │
                 │  - Immutable Snapshots      │                           │  - Atomic Lock Mutex (409)  │
                 │  - Sample Counts (P, N, M)  │                           │  - React 18 + TS Terminal UI│
                 │  - Stateful Alert Episodes  │                           │  - Smart Visibility Polling │
                 │  - Row-Level Data Provenance│                           │  - Desktop Notifications    │
                 └─────────────────────────────┘                           └─────────────────────────────┘
```

---

## 3. 📐 Nomenclatura Cuantitativa y Motores de Puntuación

### A. Distinción Estricta de Métricas

| Métrica | Nombre Completo | Rango | Definición y Rol |
| :--- | :--- | :---: | :--- |
| **`SMI`** | **Space Market Intelligence Index** | **$0\text{--}100$** | **Índice cuantitativo integral maestro.** Combina los 6 factores multivariables con pesos adaptativos dinámicos. |
| **`SSI`** | **Space Sentiment Index** | **$0\text{--}100$** | Mide **exclusivamente el sentimiento social puro de X/Twitter**: polaridad entre posts con opinión (FinTwitBERT), centrada en la norma de 14 días del ticker (50 = sentimiento normal del ticker), sin otros idiomas ni spam. Nulo cuando no hay opiniones. |
| **`Momentum Score`** | **Market Momentum (contexto técnico)** | **$0\text{--}100$** | Filtro de tendencia EMA200 (±10), confirmación de volumen según la dirección del día y penalización por RSI > 75. Baja varianza y peso 0.10 (ver B.4). |
| **`PMS`** | **Prediction Market Score** | **$0\text{--}100$** | Mide las **expectativas implícitas en Prediction Markets (Polymarket)** para eventos directos y sectoriales. |
| **`Risk Score`** | **Risk & Safety Score** | **$0\text{--}100$** | Mide la **seguridad del activo** (mayor = más seguro/menor volatilidad) combinando: ATR% sobre precio, volatilidad anualizada a 30 días y drawdown móvil a 30 días. |
| **`Market Score`** | **Technical Market Score** | **$0\text{--}100$** | Mide la **confirmación técnica del precio** (escalado desde el score técnico de 40 pts). |
| **`Fundamental Score`** | **Fundamental Health Score**| **$0\text{--}100$** | Salud financiera basada en Runway (40%), Solvencia (25%), Crecimiento (20%) y Márgenes (15%). |

---

### B. Fórmulas Matemáticas Clave

#### 1. Ponderación Social SSI & Bayesian Credibility Shrinkage:
- **Ponderación Multivariable por Publicación:**
  $$w_i = \text{relevance}_i \cdot \text{recency}_i \cdot \text{confidence}_i \cdot \left(1.0 + \frac{\text{engagement}_i}{10.0}\right)$$
- **Decaimiento Temporal Exponencial:**
  $$\text{Weight}_{\text{recency}} = e^{-\lambda \cdot \text{age\_hours}}, \quad \lambda = \frac{\ln(2)}{12.0\text{h}}$$
- **Contracción Bayesiana de Credibilidad (*Empirical Bayes Shrinkage*):** Ante muestras reducidas ($1 \le N < 10$ posts), el score social efectivo se contrae suavemente hacia el prior neutro ($\mu_0 = 50.0$):
  $$\text{effective\_social} = 50.0 + (\text{social\_score} - 50.0) \times \min\left(1.0, \max\left(0.10, \frac{\text{post\_count}}{10.0}\right)\right)$$
- **Exclusión Adaptativa sin Falsa Neutralidad:** Si $N = 0$ posts o no hay posts relevantes, el pilar social se excluye estrictamente ($w_{\text{social}} = 0$, `social_score = None`) y su peso se redistribuye proporcionalmente.
- **Polaridad solo entre opiniones:** La media ponderada usa únicamente posts `BULLISH`/`BEARISH`. Los `NEUTRAL` (~80% del tráfico de X: links, preguntas, charla) cuentan en la distribución y en `total_posts`, pero no en la polaridad; antes arrastraban todos los tickers hacia 50 (desvío del SSI de ±1–3 pts). Sin opiniones, `social_score = None`. `post_count` / `effective_sample_size` cuenta opiniones únicas acotadas por autores distintos.
  $$\text{raw} = 50 + 50 \cdot \frac{\sum_{i \in \text{opinión}} w_i s_i}{\sum_{i \in \text{opinión}} w_i}$$
- **Modelo de Sentimiento para X (FinTwitBERT, umbral 0.90):** Las noticias siguen con FinBERT, pero los posts de X usan `StephanAkkerman/FinTwitBERT-sentiment` (MIT, local, preentrenado con 10M de tweets financieros). Con el umbral de FinBERT (0.20) marcaba el 68% de los tweets como alcistas (y el 98.6% de los no ingleses): sus probabilidades están sobreconfiadas. Revisión manual a ciegas de 137 desacuerdos (oct-2026), ponderada por estrato: aciertos 73% vs 63% de FinBERT (IC 95% de la diferencia [-2, +23] pts), precisión de opiniones 64% vs 17%, polaridad invertida 0.5% vs 2.8%; la combinación "FinBERT filtra / FinTwit dirige" solo llegó a 64%. Configurable con `SOCIAL_SENTIMENT_MODEL` y `SOCIAL_SENTIMENT_THRESHOLD`; tras cambiarlos, `reclassify-social` reetiqueta la ventana de la línea base.
- **Filtro de Idioma:** Los modelos de sentimiento solo entienden inglés, así que los posts en otros idiomas (~6,5% de los relevantes: coreano, japonés, español, árabe...) se excluyen del SSI y de la línea base en vez de clasificarse mal (`non_english_post_count`). Se usa el idioma que detecta X (`social_posts.lang`, `SOCIAL_ALLOWED_LANGUAGES = ["en"]`); si falta o es indeterminado (`und`, solo cashtags/emojis), se decide por alfabeto. Traducir no compensa: aportarían < 2% de las opiniones.
- **Filtro de Spam Promocional (`SOCIAL_EXCLUDE_SPAM`):** Se excluyen del SSI, del volumen de menciones, de la línea base y de las alertas de catalizador los posts de bots de promoción: invitaciones a grupos de WhatsApp/Telegram/Discord, señales pagas y copy trading, testimonios ("I made $80,000 by following..."), cebos de notificaciones y campañas que secuestran hashtags de reality shows (#BBNaija, #bb28, #smno...) pegando cashtags ajenos. Revisión de 4.791 posts (oct-2026): 15% del tráfico y 69 opiniones, todas alcistas y todas spam en la revisión manual. Pesa sobre todo en SPCE (24% de sus opiniones; su norma bajó de 81.8 a 76.3); 1–5% en el resto.
- **Línea Base por Ticker (14 días):** El retail en X es estructuralmente alcista (polaridad media 55–61 en los 5 tickers), así que el SSI mide el desvío respecto de la norma propia del ticker, calculada sobre $[t-14d, t-24h)$ sin decaimiento temporal y contraída hacia neutral con un pseudo-peso $k = 10$ (`SOCIAL_BASELINE_PRIOR_WEIGHT`):
  $$\text{baseline} = 50 + 50 \cdot \frac{\sum w_j s_j}{\sum w_j + k}, \qquad \text{SSI} = \text{clamp}(50 + \text{raw} - \text{baseline})$$
  Se persisten `social_polarity_raw` y `social_baseline` por snapshot.
- **Volumen de Menciones (`mention_volume_ratio`):** Posts relevantes únicos en la ventana de 24h dividido por la mediana diaria del ticker en la línea base (deduplicando dentro de cada día y saltando días sin recolección). Requiere ≥ 3 días de historial. Desde 2× (`SOCIAL_ATTENTION_SPIKE_RATIO`) emite `ATTENTION_SPIKE` (`HIGH` si el SSI se inclina a un lado, `WARNING` si es mixto). No pondera en el SMI hasta validarse.

#### 2. Módulo de Análisis Fundamental y Alertas por Umbral:
Calcula los meses exactos de supervivencia operativa:
$$\text{Runway (meses)} = \frac{\text{Total Cash}}{\text{Annualized Burn Rate}} \times 12$$
- Si $\text{Runway} < 6.0 \text{ meses}$: Genera alerta crítica `CAPITAL_RAISE_RISK` (`CRITICAL`), modifica la señal a `[DILUTION RISK]` y degrada preventivamente `STRONG BUY` $\to$ `BUY`.
- Si $6.0 \le \text{Runway} < 12.0 \text{ meses}$ con alta deuda: Emite alerta de vigilancia `DILUTION_WATCH` (`HIGH`).

#### 3. Arquitectura de 6 Pilares y Normalización Adaptativa de SMI:
Pesos base v2.2 (`WEIGHT_*` en `app/config.py`). Los tres pilares de sentimiento suman el 80%:
- **Social (SSI):** $35\%$
- **News / Catalysts:** $30\%$
- **Prediction Markets (PMS):** $15\%$
- **Market Momentum:** $10\%$
- **Fundamentals:** $10\%$
- **Risk / Safety:** $0\%$ (fuera del promedio; actúa como compuerta `HIGH RISK` en la señal)

Motivo del cambio (v2.1 → v2.2): con social 30% / momentum 25%, el momentum explicaba el **58%** del movimiento del SMI y el social apenas el **4%** (el SSI casi no variaba). Con el SSI reformulado, el momentum de baja varianza y estos pesos, la composición medida sobre los 693 snapshots es: social 57%, noticias 28%, fundamentales 13%, momentum 3%, Polymarket 0% (`audit/sentiment_2026_10/pillar_ic_and_composition.py`).

Ante fuentes no disponibles ($None$ o $N=0$):
$$w_i^{\text{active}} = \frac{w_i}{\sum_{j \in \text{active}} w_j}$$

#### 3b. News Score (v2.2.1):
Mismo criterio que el SSI: polaridad solo entre titulares BULLISH/BEARISH (los neutrales, ~60% del feed, siguen contando en `total_news` pero no diluyen hacia 50); copias sindicadas del mismo titular ("... - Yahoo Finance", "... - The Motley Fool") se cuentan una vez (`normalize_headline_for_dedup`, se queda la copia de mayor confianza); vida media de 12h (`NEWS_HALF_LIFE_HOURS`, antes 24h, que mantenía dominante el rally del 6/10 hasta el 8/10); y contracción hacia 50 hasta que la evidencia (suma de recencia × importancia de los titulares con opinión) llega a `NEWS_MIN_OPINION_EVIDENCE = 2` (sin ella, un único titular de hace 3 días fijaba SATL en 2/100). Sobre 5–8 oct: RKLB 46 → 31 y ASTS 57 → 45 el 8/10; los tickers con pocas noticias (SATL, SPCE) quedan cerca de 50.

#### 4. Momentum como Contexto Técnico (v2.2):
$$\text{Momentum} = 50 \pm 10_{\,\text{precio vs EMA200}} \pm \min\left(10,\ 8(\text{vol\_ratio}-1)\right)_{\,\text{signo del día}} - 1.5\,\max(0, \text{RSI}-75)$$
- Sin el término de retornos de 1/3/5 días ni la distancia lineal a la EMA200 (en ATR) de v2.1.
- Evidencia (`audit/sentiment_2026_10/momentum_study.py`, 2 años de precios diarios, 1.756 barras, sin lookahead): los retornos de 1–5 días tienen IC ≈ 0 con el retorno futuro a 1–5 días; la distancia a la EMA200 y el filtro binario tienen IC negativo (-0.09 a -0.13 a 3–5 días). Ninguna variante predijo subas, así que el pilar quedó de baja varianza (desvío ~9 pts en vez de ~22) y peso 0.10: enmarca al sentimiento en vez de dominarlo. El volumen con signo y el RSI siguen protegiendo contra distribución y sobreextensión.

---

### C. Gobernanza de Datos y Trazabilidad de Procedencia

1. **Procedencia a Nivel de Fila:** Columnas `source` en `social_posts` y `prediction_markets` (`LIVE`, `MOCK`, `DEGRADED`).
2. **Evaluación Dinámica de Procedencia:** La procedencia del snapshot y de las alertas se deduce del origen real de las filas contenidas en la ventana de análisis.
3. **Purga Automática de Datos Sintéticos:** Si `ALLOW_MOCK_FALLBACK=False`, el inicio del sistema purga automáticamente registros mock heredados.
4. **Distintivos Visuales:** El frontend y las notificaciones de escritorio muestran etiquetas claras `[MOCK]` o `[DEGRADED]` cuando la procedencia no es 100% en vivo.

---

### D. Señales Canónicas, Calibración Simétrica y Bloqueo Operativo

- **Señal Base Simétrica:** Enum canónico puro con calibración balanceada alrededor de 50.0 (`STRONG BUY ≥ 85`, `BUY ≥ 70`, `WATCH ≥ 55`, `HOLD 45–55`, `CAUTION ≤ 45`, `AVOID ≤ 30`, `STRONG AVOID ≤ 15`; cada banda bajista es el espejo exacto de la alcista respecto de 50).
- **Modificadores Acumulativos:** `DILUTION RISK`, `CONFLICTING SOURCES`, `LOW DATA QUALITY`, `OVEREXTENDED`, `HIGH RISK`, `NO MKT DATA`, `CATALYST RISK`.
- **Compuerta de Catalizador Bajista (`CATALYST RISK`):** Un catalizador `BEARISH` de importancia `CRITICAL` (fallo de lanzamiento, cancelación de contrato, competidor seleccionado) o un `CAPITAL_RAISE` confirmado limita `STRONG BUY`/`BUY` a `WATCH`.
- **Reconciliación Catalizador–Sentimiento:** Si el clasificador marca NEUTRAL un texto con catalizador `CRITICAL`/`HIGH` (excepto `LAUNCH` genérico), el sentimiento del ítem toma el prior del catalizador (±0.60 / ±0.40); si lo contradice, se promedian ambos.
- **Bloqueo Operativo por Falta de Cotización:** Si `market_status != 'AVAILABLE'` o `price is None` o `price <= 0`, las compras se restringen obligatoriamente a `WATCH (NO MKT DATA)`, alineando la ejecución en vivo con el motor de backtesting y evitando órdenes ciegas.
- **Guarda de Vela Diaria y Filtro de Apertura:** Comprobación estricta `is_today_candle` antes de descartar la última barra intradía (evita descartar días completos en cierres de mercado) y neutralización del volumen inicial (ratio 1.0) hasta las 10:00 ET para amortiguar los 15 minutos de retraso de la cinta pública.
- **Alertas de Catalizadores Críticos y Altos con Identidad Única:** Identificadores con categoría explícita `{ticker}:CATALYST:{category}` permitiendo la coexistencia de múltiples catalizadores simultáneos en el mismo activo. Soporte tanto para catalizadores `CRITICAL` (fallos de misión, explosiones) como `HIGH` (lanzamientos orbitales, despliegues satelitales, contratos gubernamentales).
- **Ventana de Persistencia de Catalizadores (5-Day Grace Period):** Período de gracia de 5 días para alertas de categoría `CATALYST` en `save_alerts`, impidiendo la auto-resolución prematura cuando las noticias rotan fuera del top 20 RSS.
- **Alertas Accionables Ampliadas & Shifts de Momentum en 24h:** Generación proactiva de alertas para señales `BUY`, regímenes de advertencia `AVOID`, transiciones alcistas tempranas `WATCH_BULLISH` (SMI $\ge 60$) y desplazamientos bruscos de momentum (`MOMENTUM_ACCELERATION` $\ge +5$ pts / `MOMENTUM_BREAKDOWN` $\le -5$ pts).
- **Detección Sintáctica y Desambiguación NLP:** Detección de negaciones contextuales (`"no delay"`, `"no failure"`), cobertura exhaustiva de `CAPITAL_RAISE`, y desambiguación regex con hasta 4 modificadores intermediarios diferenciando lanzamientos de cohetes (`LAUNCH`) de anuncios corporativos de líneas de productos comerciales.

---

### E. Predicción Cuantitativa (PMS), Divergencias y Resolución Robusta

1. **Calibración con Anclaje Dinámico de Consenso (Media Móvil 7 Días):** Si el mercado no provee una tasa base explícita, se ancla a la media móvil histórica de 7 días de ese mismo contrato (acotada entre 0.005 y 0.995, `PMS_MIN_BASE_RATE`), midiendo la sorpresa real en lugar de sesgos estructurales de contratos muy asimétricos. Hasta v2.2.0 el piso era 0.05: cualquier mercado improbable (p. ej. 3.5% estable) puntuaba ~43, un sesgo bajista sin información.
5. **Sin PMS por proxies sectoriales (v2.2.1):** un ticker sin mercados directos válidos no recibe PMS (pilar excluido y pesos renormalizados) salvo `PMS_ALLOW_SECTOR_ONLY=True`. En oct-2026 ASTS, RKLB, SATL y SPCE solo tenían mercados de Starship vía `DEFAULT_EVENT_COMPANY_MAPPINGS`, y su PMS quedaba fijo en 47–49 todos los días: un ancla hacia 50 con el 11% del peso. Los eventos sectoriales siguen sumando cuando hay al menos un mercado directo.
6. **Tramos numéricos excluidos (v2.2.1):** los mercados que son un tramo de un evento excluyente de Polymarket (`negRisk` con `groupItemTitle` numérico: "<5", "5-6", "200+") no entran al PMS (`outcome_group`/`outcome_label`, propiedad `is_range_bucket`). Cada tramo tenía polaridad +1, así que "menos de 5 lanzamientos" contaba como alcista y cada tramo improbable como bajista (SPCX PMS 43 por 8 tramos con p≈0.001). Los resultados con nombre de un evento excluyente ("SpaceX" en "Largest IPO") sí cuentan.
7. **Event keys con límites de palabra (v2.2.1):** `match_event_key_from_text` usaba subcadenas, y "sda" dentro de "Wednesday"/"Thursday" mapeaba mercados de tormentas geomagnéticas a contratos de Space Force.
2. **Dominancia de Momentum ($\Delta P_{24h}$ 60% / Nivel 40%):** Ponderación prioritaria al flujo de capital informado y sorpresas de corto plazo.
3. **Divergencias Calibradas con Blend 50/50:** El motor de divergencias tripartitas combina 50% de retorno de corto plazo con 50% de momentum estructural de tendencia. Los umbrales de discrepancia se calibran empíricamente a $\pm 0.18$ para narrativa social y prediction markets, $\pm 0.10$ para divergencias de precio y RSI 70 para sobreextensión, manteniendo contracción bayesiana ante muestras pequeñas ($N < 3$).
4. **Protección Anti-Aleteo (Flapping) ante Fallo de Fuentes:** La resolución de alertas de dilución queda condicionada al éxito real de obtención de fundamentales (`fund_success == True`) y las divergencias al éxito de ingesta de Polymarket, previniendo cierres y reaperturas espurias ante cortes temporales de red.

---

### F. Seguridad, Concurrencia y Visualización Institucional

1. **Seguridad Timing-Safe:** Verificación de claves mediante `secrets.compare_digest`, mitigando ataques de canal lateral.
2. **Same-Origin Dashboard Authorization:** Verificación criptográfica segura para invocaciones internas sin exponer secretos en el cliente Vite y fail-secure (HTTP 503) en entornos productivos si la clave no está configurada.
3. **Bloqueo Distribuido Garantizado por Base de Datos:** Exclusión mutua garantizada a nivel de SQLite mediante índice único parcial `uq_job_runs_single_running` sobre `status='RUNNING'`. Las inserciones concurrentes fallan atómicamente con HTTP 409 Conflict.
4. **Heartbeat en Hilo Autónomo (30s):** Un worker en segundo plano renueva el heartbeat cada 30 segundos mientras el pipeline procesa modelos pesados (FinBERT, scraping o cómputo técnico), evitando que jobs legítimos sean declarados zombis por el timeout de 120s.
5. **Visualización Institucional de Historial (HistoryChart):** Conexión continua de series sorteando cierres bursátiles de fin de semana (`maxGapHours = 96`), sombreado visual de receso bursátil (`WEEKEND / MKT CLOSED`) y marcas de calendario inteligentes no superpuestas en el eje temporal.
6. **Silent Cold-Start & Episodios:** Identidad única por episodio `{baseId}@{opened_at}` con inicio silencioso para evitar ráfagas de notificaciones al recargar el navegador.
7. **Feed Social Ordenado por Influencia (v2.2):** La ficha del ticker muestra primero las opiniones con mayor peso en el SSI (con su % del voto), luego los neutrales que cuentan y al final los excluidos con su motivo (idioma, spam, baja relevancia, duplicado). Vistas "Most influential" / "Latest" / "Excluded" y lista completa con scroll. El peso y el motivo salen de la misma pasada de `calculate_social_score(post_details=...)`, así que la pantalla no puede contradecir al score. Los catalizadores de la ficha ignoran posts de spam u otros idiomas.

### G. Inteligencia Intradiaria, Fade The Open & Alertas Técnicas

1. **Métricas de Dinámica Intradiaria (`indicators.py`):** Extracción matemática rigurosa de las componentes de vela OHLCV:
   - `intraday_reversal_pct`: $(\text{price} - \text{day\_high}) / \text{day\_high} \times 100$, mide el porcentaje de caída desde el punto álgido de la sesión.
   - `range_location`: $(\text{price} - \text{day\_low}) / (\text{day\_high} - \text{day\_low})$, oscilador normalizado $[0.0, 1.0]$ que ubica el precio dentro del rango de la sesión actual.
   - `intraday_change`: $(\text{price} - \text{day\_open}) / \text{day\_open} \times 100$.
2. **Divergencia Intradiaria "Fade the Open / Sell the News" (`INTRADAY_BEARISH_DIVERGENCE`):** Detecta cuando la apertura o la narrativa matutina es constructiva (Social $\ge 0.08$ o Noticias $\ge 55.0$), pero el precio sufre un rechazo intradiario severo ($\le -4.0\%$ del máximo de la sesión con volumen $\ge 1.15\times$ cerrando en el 40% inferior del rango). Emite alerta de alta prioridad (`level='HIGH'`).
3. **Categoría de Alertas Técnicas Estructurales (`TECHNICAL`):**
   - `INTRADAY_REVERSAL_EXHAUSTION`: Caída $\le -4.5\%$ (nivel `WARNING`) o $\le -7.0\%$ (nivel `HIGH`) desde el máximo con volumen $\ge 1.15\times$ cerrando cerca de mínimos.
   - `RSI_OVERBOUGHT` ($\ge 75$) & `RSI_OVERSOLD` ($\le 30$): Alertas de compresión extrema y riesgo inminente de reversión a la media.
   - `EMA200_BREAKDOWN`: Pérdida de la media móvil institucional de 200 periodos con caída $\le -2.0\%$ en volumen $\ge 1.2\times$.
   - `BOLLINGER_LOWER_BREACH`: Ruptura del envelope de $2\sigma$ inferior.
4. **Ciclo de Vida y Auto-Resolución:** Las alertas de categoría `TECHNICAL` se auto-resuelven únicamente si la obtención de datos de mercado fue exitosa (`mkt_success == True`), previniendo aleteos por caídas de red.
5. **Visualización y Filtrado en Frontend:** Pestaña dedicada "📈 Técnicas" en `AlertsManager.tsx` con conteo en vivo e insignia visual cyan (`#38bdf8`) para distinguir eventos técnicos de catalizadores noticiosos o señales canónicas.

---

## 4. 🧪 Suite de Pruebas Automatizadas

La suite de pruebas (`tests/`) está totalmente aislada de la red y la base de datos de producción mediante `tests/conftest.py`:
```powershell
python -m pytest tests/ -v
```
- **232 pruebas automatizadas** que se ejecutan de forma reproducible y con 100% de éxito.
- Cobertura integral de:
  - **Inferencia Local FinBERT y Robustez NLP:** Clasificación local neuronal con `ProsusAI/finbert`, compatibilidad HuggingFace transformers 5.x (`top_k=None`) y sanitización de lotes vacíos/nulos.
  - **Modelo Social FinTwitBERT:** Vocabulario `BULLISH/BEARISH/NEUTRAL`, umbral 0.90, fallback al léxico reportado como `heuristic-lexicon`, reclasificación del historial que aborta sin escribir si el modelo no carga.
  - **Paridad de Estrategias y Cero Sesgo de Anticipación:** Validación matemática idéntica entre ejecución live y backtesting, incluyendo compuertas de `risk_score` y `fundamental_score` en Modelos A y B.
  - **Dinámica Intradiaria y Alertas Técnicas:** Verificación de cálculo de `intraday_reversal_pct`, `range_location`, alertas de sobrecompra/sobreventa de RSI, pérdida de EMA200 y divergencias intradiarias bajistas.
  - **Invarianza de Escala del Momentum & MACD Normalizado:** Filtro de tendencia binario y volumen con signo, idénticos para acciones de alta o baja volatilidad.
  - **SSI v2.2:** Polaridad solo entre opiniones, línea base por ticker, volumen de menciones, filtros de idioma y spam, y detalle por post (`post_details`) coherente con el score y con el feed de la API.
  - **Correcciones de Interpretación:** Conteo único de palabras anidadas, explosiones literales vs figuradas, rivalidades solo entre empresas conocidas, retrasos corporativos vs de lanzamiento, compuerta `CATALYST RISK` y bandas espejo.
  - **Gobernanza de Datos y Procedencia (Data Provenance):** Trazabilidad estricta (`LIVE`, `DEGRADED`, `MOCK`), integridad referencial en cascada y purga segura.
  - **Seguridad de API & Bloqueo Atómico Distribuido:** Pruebas contra timing attacks, fallos seguros en producción, índice único parcial `uq_job_runs_single_running` y worker autónomo de heartbeats.
  - **Calibración de Señales Simétricas & Inoperabilidad de Precios Nulos:** Verificación de bandas simétricas y degradación a `WATCH (NO MKT DATA)`.
  - **Calibración de Prediction Markets (PMS):** Validación de simetría de formulación y anclaje a media móvil de 7 días.
  - **Single-Source Confidence Gating & Anti-Flapping:** Eliminación de bonificación indebida (+15%) cuando solo existe una fuente activa y preservación de alertas ante degradación de proveedores.
  - **Normalización Fundamental Adaptativa:** Reescalado dinámico sobre componentes observados sin imputación artificial neutra de 50.0.
  - **Paired Block Bootstrap:** Remuestreo por bloques temporalmente sincronizados entre Model A y Model B para cálculo de significancia estadística.
  - **Persistencia de Pesos Efectivos:** Serialización completa del vector `effective_weights` por snapshot.
  - **Episodios de Alertas y Mutex Atómico HTTP 409:** Notificaciones silenciosas en arranque y prevención de carreras concurrentes en pipeline.
  - **Cobertura de Catalizadores Catastróficos y Negaciones:** Detección de `CAPITAL_RAISE`, `LAUNCH_FAILURE`, filtrado de productos comerciales y desambiguación sintáctica de negaciones.

---

## 5. 📋 Estado v2.2 y Tareas Pendientes

### Qué cambió en v2.2 (octubre 2026)
- **Interpretación de texto:** correcciones del léxico y de la detección de catalizadores, reconciliación catalizador–sentimiento y compuerta `CATALYST RISK` (sección 3.D).
- **Señales:** bandas espejo alrededor de 50 con la nueva banda `CAUTION` (sección 3.D).
- **SSI:** polaridad solo entre opiniones, línea base de 14 días por ticker, volumen de menciones con alerta `ATTENTION_SPIKE`, filtros de idioma y spam (sección 3.B.1).
- **Modelo social:** FinTwitBERT con umbral 0.90 para X, FinBERT para noticias; comando `reclassify-social` y columna `sentiment_model` por post.
- **SMI:** momentum de baja varianza y pesos con el sentimiento al 80% (secciones 3.B.3 y 3.B.4).
- **UI:** feed social ordenado por influencia con vistas y motivos de exclusión (sección 3.F.7).
- `RULES_VERSION = 2.2.0` en cada snapshot, para separar datos antiguos de los nuevos al analizar.
- **v2.2.1:** noticias con polaridad solo de opiniones, deduplicación de titulares sindicados, vida media 12h y contracción por evidencia (sección 3.B.3b); PMS sin proxies sectoriales ni tramos numéricos, piso de tasa base 0.005 y event keys con límites de palabra (sección 3.E.5–7). Con datos del 8/10 el PMS desaparece en ASTS/RKLB/SATL/SPCE y el SMI de RKLB pasa de 46.6 (HOLD) a ~41 (CAUTION).
- Estudios reproducibles en `audit/sentiment_2026_10/` (README con resultados).

Descartado tras medirlo: **sentimiento por empresa** (recortar el texto a las frases sobre cada ticker). Cambiaba el 1.9% de las etiquetas sin mejorar la precisión en dos revisiones a ciegas (30 vs 29 aciertos de 67); los casos de comparación reales eran 5 en 14 días.

### Tareas pendientes (por prioridad)

**Validar con datos del sistema nuevo (a partir de 3–4 semanas desde el despliegue de v2.2):**
1. **Verificar el signo predictivo del sentimiento social.** En los 19 días disponibles (etiquetas mixtas FinBERT/FinTwitBERT) el SSI tuvo IC **negativo** con el retorno a 72h (-0.13 dentro de ticker): la euforia de X precedió caídas. Ahora el social explica el 57% del SMI. Correr `python -m audit.sentiment_2026_10.pillar_ic_and_composition --since <fecha v2.2>`. Si el IC sigue negativo y estable, evaluar leerlo como indicador contrario o reducir su peso.
2. **Rebalancear pesos con evidencia** (paso 5 del plan de sentimiento): asignar peso según IC positivo y estable de cada pilar. Fundamentales mostró el IC más alto (+0.17 dentro de ticker); Polymarket explica 0% del movimiento del SMI porque su score casi no varía.
3. **Usar el cambio de sentimiento además del nivel** (paso 4): el SSI ya mide el desvío respecto de la norma de 14 días; evaluar si su variación a 24–72h aporta información adicional.
4. **Recalibrar los umbrales de divergencia social (±0.18).** Se fijaron cuando el SSI variaba ±1–3 pts; ahora varía ±6–15, así que las divergencias sociales disparan con más frecuencia.
5. **Vigilar la asimetría de FinTwitBERT:** en RKLB y SATL la norma de polaridad ronda 88, lo que deja poco margen para detectar euforia (el SSI puede subir ~12 pts pero caer mucho más). Si se confirma, usar umbrales distintos para alcista y bajista.
6. **Validar `ATTENTION_SPIKE`** (volumen de menciones ≥ 2×) antes de darle peso en el SMI.

**Descartado tras medirlo (oct-2026):** modificador `SECTOR SELLOFF` por caída conjunta de la cesta. `audit/sentiment_2026_10/sector_selloff_study.py` no encontró capacidad predictiva a 1–10 días (5 y 2 años; ver su README). Si se quiere mostrar la caída sectorial, que sea como contexto informativo en la UI, sin mover la señal.

**Mantenimiento continuo:**
7. **Ampliar el filtro de spam** con estilos que todavía se escapan ("$1,000 to $100,000…", "track record speaks for itself…"), juntando ejemplos desde la vista "Excluded" del feed y verificando con `spam_pattern_check.py` que no descarta opiniones genuinas.
8. **Tras cambiar `SOCIAL_SENTIMENT_MODEL`/`SOCIAL_SENTIMENT_THRESHOLD`:** correr `python -m app.cli reclassify-social` para no mezclar modelos en la línea base.

**Limitaciones conocidas:**
- El backtest no aplica la compuerta `CATALYST RISK` porque no hay historial de catalizadores por snapshot.
- Los posts guardados antes de capturar `lang` (≤ 2026-10-02) solo se filtran por alfabeto: el español y el portugués pasan hasta salir de la ventana de 14 días.
- Los snapshots con `rules_version < 2.2.0` usan la fórmula anterior del SSI y del momentum: no mezclarlos al medir. Los de `2.2.0` usan el News Score y el PMS anteriores a 2.2.1.
- `outcome_group`/`outcome_label` solo viven en memoria durante la corrida (no hay columna): la exclusión de tramos depende de que Polymarket siga enviando `negRisk` y `groupItemTitle`.
