# 🚀 SPACE MARKET INTELLIGENCE ENGINE (SMIE v2.0) — CONTEXTO MAESTRO DEL PROYECTO

> **Documento de Continuidad Arquitectónica, Contexto Técnico y Hoja de Ruta**  
> *Diseñado para que cualquier desarrollador o IA (Claude Code, Cursor, Windsurf, Antigravity, etc.) comprenda inmediatamente el sistema, sus decisiones de diseño, estado actual, fórmulas cuantitativas y manual de operación.*

---

## 1. 🔭 Visión y Propósito del Proyecto

**Space Market Intelligence Engine (SMIE v2.0)** es una plataforma de análisis cuantitativo e inteligencia de mercado diseñada específicamente para el sector espacial y aeroespacial estadounidense ($ASTS, $RKLB, $SATL, $SPCE, $SPCX, etc.).

### El Problema que Resuelve
La industria aeroespacial se caracteriza por una extrema dependencia de **eventos binarios de alto impacto** (lanzamientos de cohetes, anomalías de vuelo, despliegue de constelaciones satelitales, aprobaciones de espectro por la FCC, contratos de defensa con NASA/DoD y rondas de dilución por quema de caja). Los modelos tradicionales de análisis técnico o fundamental a menudo fallan al no capturar a tiempo la narrativa social ni las probabilidades implícitas en mercados de predicción ni el riesgo de solvencia.

SMIE resuelve esto sintetizando **cinco fuentes de información completamente desacopladas**:
1. **Narrativa Social (X / Twitter):** Sentimiento y euforia de la comunidad minorista e institucional con ponderación por confianza y contracción bayesiana.
2. **Prediction Markets (Polymarket):** Expectativas financieras donde los participantes arriesgan capital real sobre eventos concretos.
3. **Noticias & Catalizadores (Google News RSS):** Detección temprana de contratos, lanzamientos, acuerdos, anomalías de vuelo y fallos de misión (`LAUNCH_FAILURE`).
4. **Factores Fundamentales & Supervivencia de Caja (yfinance DataFrames):** Detección de quema de caja y alertas por umbral de dilución (`CAPITAL_RAISE_RISK` para runway $<6$ meses).
5. **Acción Técnica del Precio & Medición de Riesgo (yfinance):** Confirmación cuantitativa de tendencia, volatilidad (ATR/Bollinger) y sobreextensión.

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
                                │  - Sentiment Classifier (Lexical / FinBERT)            │
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
| **`SSI`** | **Space Sentiment Index** | **$0\text{--}100$** | Mide **exclusivamente el sentimiento social puro de X/Twitter**, ponderado por engagement logarítmico, decaimiento temporal y confianza del clasificador. Soporta valores nulos cuando no hay posts. |
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

#### 2. Módulo de Análisis Fundamental y Alertas por Umbral:
Calcula los meses exactos de supervivencia operativa:
$$\text{Runway (meses)} = \frac{\text{Total Cash}}{\text{Annualized Burn Rate}} \times 12$$
- Si $\text{Runway} < 6.0 \text{ meses}$: Genera alerta crítica `CAPITAL_RAISE_RISK` (`CRITICAL`), modifica la señal a `[DILUTION RISK]` y degrada preventivamente `STRONG BUY` $\to$ `BUY`.
- Si $6.0 \le \text{Runway} < 12.0 \text{ meses}$ con alta deuda: Emite alerta de vigilancia `DILUTION_WATCH` (`HIGH`).

#### 3. Arquitectura de 6 Pilares y Normalización Adaptativa de SMI:
Pesos base canónicos:
- **Social (SSI):** $30\%$
- **Prediction Markets (PMS):** $15\%$
- **News / Catalysts:** $20\%$
- **Market Momentum:** $20\%$
- **Fundamentals:** $10\%$
- **Risk / Safety:** $5\%$

Ante fuentes no disponibles ($None$ o $N=0$):
$$w_i^{\text{active}} = \frac{w_i}{\sum_{j \in \text{active}} w_j}$$

---

### C. Gobernanza de Datos y Trazabilidad de Procedencia

1. **Procedencia a Nivel de Fila:** Columnas `source` en `social_posts` y `prediction_markets` (`LIVE`, `MOCK`, `DEGRADED`).
2. **Evaluación Dinámica de Procedencia:** La procedencia del snapshot y de las alertas se deduce del origen real de las filas contenidas en la ventana de análisis.
3. **Purga Automática de Datos Sintéticos:** Si `ALLOW_MOCK_FALLBACK=False`, el inicio del sistema purga automáticamente registros mock heredados.
4. **Distintivos Visuales:** El frontend y las notificaciones de escritorio muestran etiquetas claras `[MOCK]` o `[DEGRADED]` cuando la procedencia no es 100% en vivo.

---

### D. Señales Canónicas, Calibración Simétrica y Bloqueo Operativo

- **Señal Base Simétrica:** Enum canónico puro con calibración balanceada alrededor de 50.0 (`STRONG BUY ≥ 85`, `BUY ≥ 70`, `WATCH ≥ 55`, `HOLD 45–55`, `AVOID 20–45`, `STRONG AVOID < 20`).
- **Modificadores Acumulativos:** `DILUTION RISK`, `CONFLICTING SOURCES`, `LOW DATA QUALITY`, `OVEREXTENDED`, `HIGH RISK`, `NO MKT DATA`.
- **Bloqueo Operativo por Falta de Cotización:** Si `market_status != 'AVAILABLE'` o `price is None` o `price <= 0`, las compras se restringen obligatoriamente a `WATCH (NO MKT DATA)`, alineando la ejecución en vivo con el motor de backtesting y evitando órdenes ciegas.
- **Guarda de Vela Diaria y Filtro de Apertura:** Comprobación estricta `is_today_candle` antes de descartar la última barra intradía (evita descartar días completos en cierres de mercado) y neutralización del volumen inicial (ratio 1.0) hasta las 10:00 ET para amortiguar los 15 minutos de retraso de la cinta pública.
- **Alertas de Catalizadores Críticos y Altos con Identidad Única:** Identificadores con categoría explícita `{ticker}:CATALYST:{category}` permitiendo la coexistencia de múltiples catalizadores simultáneos en el mismo activo. Soporte tanto para catalizadores `CRITICAL` (fallos de misión, explosiones) como `HIGH` (lanzamientos orbitales, despliegues satelitales, contratos gubernamentales).
- **Ventana de Persistencia de Catalizadores (5-Day Grace Period):** Período de gracia de 5 días para alertas de categoría `CATALYST` en `save_alerts`, impidiendo la auto-resolución prematura cuando las noticias rotan fuera del top 20 RSS.
- **Alertas Accionables Ampliadas & Shifts de Momentum en 24h:** Generación proactiva de alertas para señales `BUY`, regímenes de advertencia `AVOID`, transiciones alcistas tempranas `WATCH_BULLISH` (SMI $\ge 60$) y desplazamientos bruscos de momentum (`MOMENTUM_ACCELERATION` $\ge +5$ pts / `MOMENTUM_BREAKDOWN` $\le -5$ pts).
- **Detección Sintáctica y Desambiguación NLP:** Detección de negaciones contextuales (`"no delay"`, `"no failure"`), cobertura exhaustiva de `CAPITAL_RAISE`, y desambiguación regex con hasta 4 modificadores intermediarios diferenciando lanzamientos de cohetes (`LAUNCH`) de anuncios corporativos de líneas de productos comerciales.

---

### E. Predicción Cuantitativa (PMS), Divergencias y Resolución Robusta

1. **Calibración con Anclaje Dinámico de Consenso (Media Móvil 7 Días):** Si el mercado no provee una tasa base explícita, se ancla a la media móvil histórica de 7 días de ese mismo contrato (acotada entre 0.05 y 0.95), midiendo la sorpresa real en lugar de sesgos estructurales de contratos muy asimétricos.
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
- **196 pruebas automatizadas** que se ejecutan de forma reproducible y con 100% de éxito.
- Cobertura integral de:
  - **Inferencia Local FinBERT y Robustez NLP:** Clasificación local neuronal con `ProsusAI/finbert`, compatibilidad HuggingFace transformers 5.x (`top_k=None`) y sanitización de lotes vacíos/nulos.
  - **Paridad de Estrategias y Cero Sesgo de Anticipación:** Validación matemática idéntica entre ejecución live y backtesting, incluyendo compuertas de `risk_score` y `fundamental_score` en Modelos A y B.
  - **Dinámica Intradiaria y Alertas Técnicas:** Verificación de cálculo de `intraday_reversal_pct`, `range_location`, alertas de sobrecompra/sobreventa de RSI, pérdida de EMA200 y divergencias intradiarias bajistas.
  - **Invarianza de Escala ATR & Macd Normalizado:** Preservación de escalas relativas ante acciones de alta o baja volatilidad.
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

