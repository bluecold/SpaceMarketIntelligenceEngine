# 🚀 Space Market Intelligence Engine (SMIE v2.1)

**Motor cuantitativo multivariable de análisis e inteligencia de mercado para el sector espacial y aeroespacial.**

SMIE sintetiza de forma desacoplada la **narrativa social (X/Twitter)**, las **probabilidades implícitas en Prediction Markets (Polymarket)**, los **catalizadores sectoriales (Google News)**, los **factores fundamentales y de supervivencia de caja** y la **acción técnica del precio y riesgo (yfinance)** para generar índices cuantitativos no sesgados, señales explicables y detección temprana de divergencias tripartitas.

> 📖 **Documentación de arquitectura y contexto:** Consulta [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) y la especificación [`SPACE_MARKET_INTELLIGENCE_ENGINE_SPEC.md`](SPACE_MARKET_INTELLIGENCE_ENGINE_SPEC.md).

---

## 📐 Métricas y Capacidades Clave

- **`SMI` (Space Market Intelligence Index, 0–100):** Índice integral ponderado maestro con arquitectura multivariable de 6 pilares y normalización adaptativa dinámica de pesos según disponibilidad y calidad de fuentes.
- **`SSI` (Space Sentiment Index, 0–100):** Mide exclusivamente el sentimiento social puro de X/Twitter con engagement logarítmico, decaimiento temporal, ponderación por confianza del clasificador, contracción bayesiana para muestras pequeñas ($1 \le N < 10$) y exclusión estricta en $N=0$.
- **`PMS` (Prediction Market Score, 0–100):** Expectativa cuantitativa en Polymarket rebalanceada con dominancia de Momentum ($\Delta P_{24h}$ 60%) y Nivel calibrado (40%) anclado a la media móvil de 7 días del propio contrato (o tasa base $P_0 = 0.20$), convirtiendo el nivel en una medida de sorpresa real y anulando el peso si `quality_score < 30`.
- **`Prediction Markets Categorization`:** Clasificación y jerarquización de contratos de Polymarket en *🎯 Contratos Directos del Activo* (primer orden de prioridad) y *🌐 Catalizadores Sectoriales (SpaceX / NASA / Space Force)* con sub-filtros interactivos en la UI.
- **`Risk / Safety Score` (0–100):** Métrica cuantitativa de seguridad y compresión de riesgo calculada a partir de ATR normalizado, posición frente a bandas de Bollinger y drawdown, desacoplada como Compuerta de Preservación de Capital.
- **`Canonical Signals & Symmetric Bands`:** Desacoplamiento estricto entre `base_signal` canónico simétrico (`STRONG BUY ≥ 85`, `BUY ≥ 70`, `WATCH ≥ 55`, `HOLD 45–55`, `AVOID 20–45`, `STRONG AVOID < 20`) y `signal_modifier` (`OVEREXTENDED`, `DILUTION RISK`, `HIGH RISK`, `CONFLICTING SOURCES`, `LOW DATA QUALITY`, `NO MKT DATA`).
- **`Market Confirmation Gating & Opening Tape Guard`:** Bloqueo operativo estricto ante ausencia de cotización (`WATCH (NO MKT DATA)`), guarda de vela diaria (`is_today_candle` para evitar descartar sesiones previas) y compuerta horaria hasta las 10:00 ET neutralizando el desfase de cinta de volumen.
- **`Catalyst NLP Disambiguation & Dilution Protection`:** Detección sintáctica de negaciones (evita falsos bajistas ante *"no delay"*), desambiguación regex de lanzamientos aeroespaciales vs productos comerciales, y cobertura exhaustiva de ampliaciones de capital (`CAPITAL_RAISE`), separando ofertas de acciones de misiones operativas.
- **`Tripartite Divergence Engine with 50/50 Momentum`:** Detección de divergencias tripartitas (X ↔ Polymarket ↔ Precio) integrando un 50% de retorno de corto plazo con un 50% de momentum estructural de tendencia.
- **`Market Score` (0–100):** Confirmación técnica del precio basada en EMA200, RSI(14) con suavizado Wilder RMA, Bollinger Bands, MACD normalizado por ATR/Precio y ratio de volumen.
- **`Fundamental Health & Anti-Flapping Resolution`:** Salud financiera sectorial con normalización adaptativa sin imputaciones artificiales. Resolución protegida contra aleteo: las alertas de dilución (`CAPITAL_RAISE_RISK`, `DILUTION_WATCH`) solo se resuelven si la consulta de estados financieros fue exitosa (`fund_success`).
- **`Local FinBERT NLP Pipeline (100% Local Inference)`:** Inferencia neuronal de sentimiento financiero basada en `ProsusAI/finbert` ejecutada localmente en CPU/GPU (`transformers` + `torch`), sin llamadas a APIs externas ni costes en la nube. Supera la compresión estática del clasificador léxico proporcionando probabilidades graduadas y confianza contextual.
- **`Calibrated Divergence Engine`:** Detección de discrepancias tripartitas (X ↔ Polymarket ↔ Precio) con umbrales calibrados empíricamente ($\pm 0.18$ para sentimiento social y mercados de predicción, $\pm 0.10$ para divergencias de precio y RSI 70), manteniendo contracción bayesiana ante muestras pequeñas ($N < 3$).
- **`Actionable Alerts & 24h Momentum Shifts`:** Generador de alertas enriquecido con eventos para señales estándar `BUY`, regímenes bajistas `AVOID`, zonas de vigilancia alcista temprana (`WATCH_BULLISH` con SMI $\ge 60$), aceleración o caída abrupta de momentum en 24h (`MOMENTUM_ACCELERATION` $\ge +5$ pts / `MOMENTUM_BREAKDOWN` $\le -5$ pts) y catalizadores de importancia `HIGH` (lanzamientos, satélites, contratos de defensa).
- **`Catalyst Retention & Anti-Churn Grace Period`:** Ventana de gracia de 5 días para alertas de tipo `CATALYST`, impidiendo que eventos reales desaparezcan prematuramente cuando las noticias rotan en los feeds RSS.
- **`Single-Source Confidence Gating`:** Eliminación del acuerdo artificial ($1.0$); si existe solo 1 fuente activa aislada, se exige corroboración cruzada y se omite el bono de confianza ($+15\%$) para evitar sobreponderar publicaciones aisladas.
- **`Paired Block Bootstrap Backtesting & Parity`:** Remuestreo por bloques temporales emparejados y sincronizados (*Paired Block Bootstrap*) con paridad absoluta de filtros de riesgo (`risk_score`, `fundamental_score`) entre los Modelos A y B y el motor en vivo.
- **`Effective Weights Vector Persistence`:** Exportación y persistencia inmutable del vector normalizado de pesos efectivos (`effective_weights`) por snapshot y versión de estrategia.
- **`Catastrophic Catalyst Coverage`:** Categoría dedicada `LAUNCH_FAILURE` con importancia `CRITICAL` y sesgo `BEARISH` para explosiones, fallos de lanzamiento, anomalías de cohetes y pérdidas de payload, con ranking estricto para evitar contradicciones entre razones.
- **`Data Provenance & Live Data Governance`:** Trazabilidad estricta a nivel de fila (`source` en `social_posts` y `prediction_markets`), cálculo dinámico de procedencia (`LIVE`, `DEGRADED`, `MOCK`), integridad referencial en cascada y purga automática de datos sintéticos.
- **`Timing-Safe API Security, Atomic DB Lock & Heartbeat Worker`:** Mitigación de timing attacks con `secrets.compare_digest`, exclusión concurrente garantizada a nivel de base de datos con índice único parcial `uq_job_runs_single_running`, retorno atómico HTTP 409 Conflict y worker de heartbeat en segundo plano cada 30s.
- **`Episode-Based Desktop Notifications`:** Notificaciones de escritorio en tiempo real (Windows Toast) con arranque en frío silencioso, claves por episodio (`{alert_id}@{opened_at}`) que permiten alertar oportunamente sobre reaperturas sin duplicados intermedios.
- **`Intraday Reversals & Technical Alerts Engine`:** Monitoreo intradiario cuantitativo de agotamiento y rechazo de precios respecto a los máximos de la sesión (`intraday_reversal_pct` y `range_location`). Alerta temprana `INTRADAY_BEARISH_DIVERGENCE` ("Fade the Open / Sell the News") cuando la euforia matutina o catalizadores constructivos son contrarrestados por venta institucional agresiva ($\le -4.0\%$ del máximo con volumen $\ge 1.15\times$). Nueva categoría de alertas de escritorio y radar (`TECHNICAL`): `INTRADAY_REVERSAL_EXHAUSTION`, `RSI_OVERBOUGHT` ($\ge 75$), `RSI_OVERSOLD` ($\le 30$), `EMA200_BREAKDOWN` y `BOLLINGER_LOWER_BREACH`, con pestaña dedicada "📈 Técnicas" en la interfaz.
- **`196 Tests Automatizados`:** Cobertura exhaustiva de integridad, seguridad, paridad de estrategias, inferencia local FinBERT, no-anticipación temporal, desambiguación semántica, alertas técnicas y convergencia matemática (100% PASS).

---

## ⚡ Inicio Rápido

### 1. Instalación
```bash
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
```

### 2. Iniciar el Servidor Web
```bash
python -m app.main
```
Abre tu navegador en: **`http://localhost:8000`**

*(💡 Tip: Haz clic en el logo del cohete `🚀` o en el botón "Manual de Uso" dentro de la app para ver el manual interactivo).*

---

## 💻 Comandos CLI

- **Ejecutar pipeline completo:**
  ```bash
  python -m app.cli.commands run-all
  ```
- **Analizar un activo específico con explicaciones "WHY?":**
  ```bash
  python -m app.cli.commands analyze ASTS
  ```
- **Generar el reporte diario del sector espacial:**
  ```bash
  python -m app.cli.commands daily-report
  ```
- **Ejecutar motor de backtesting cuantitativo (Model A vs Model B con calibración de pesos):**
  ```bash
  python -m app.cli.commands backtest
  ```
- **Ingerir contratos de Polymarket:**
  ```bash
  python -m app.cli.commands collect-polymarket
  ```
- **Recolectar publicaciones de redes sociales (X) de forma aislada:**
  ```bash
  python -m app.cli.commands collect-social
  ```
- **Recolectar noticias del sector espacial:**
  ```bash
  python -m app.cli.commands collect-news
  ```
- **Evaluar divergencias activas:**
  ```bash
  python -m app.cli.commands calculate-divergences
  ```
- **Ejecutar suite completa de tests automatizados:**
  ```bash
  python -m pytest tests/ -v
  ```

---

## 🛰️ Universo de Cobertura Inicial
- **ASTS** — AST SpaceMobile
- **RKLB** — Rocket Lab
- **SATL** — Satellogic
- **SPCE** — Virgin Galactic
- **SPCX** — SpaceX (Space Exploration Technologies Corp.)
