# 🚀 SPACE MARKET INTELLIGENCE ENGINE (SMIE v2.0) — CONTEXTO MAESTRO DEL PROYECTO

> **Documento de Continuidad Arquitectónica, Contexto Técnico y Hoja de Ruta**  
> *Diseñado para que cualquier desarrollador o IA (Claude Code, Cursor, Windsurf, Antigravity, etc.) comprenda inmediatamente el sistema, sus decisiones de diseño, estado actual, fórmulas cuantitativas y manual de operación.*

---

## 1. 🔭 Visión y Propósito del Proyecto

**Space Market Intelligence Engine (SMIE v2.0)** es una plataforma de análisis cuantitativo e inteligencia de mercado diseñada específicamente para el sector espacial y aeroespacial estadounidense ($ASTS, $RKLB, $SATL, $SPCE, $SPCX, etc.).

### El Problema que Resuelve
La industria aeroespacial se caracteriza por una extrema dependencia de **eventos binarios de alto impacto** (lanzamientos de cohetes, despliegue de constelaciones satelitales, aprobaciones de espectro por la FCC, contratos de defensa con NASA/DoD). Los modelos tradicionales de análisis técnico o fundamental a menudo fallan al no capturar a tiempo la narrativa social ni las probabilidades implícitas en mercados de predicción.

SMIE resuelve esto sintetizando **cuatro fuentes de información completamente desacopladas**:
1. **Narrativa Social (X / Twitter):** Sentimiento y euforia de la comunidad minorista e institucional.
2. **Prediction Markets (Polymarket):** Expectativas financieras donde los participantes arriesgan capital real sobre eventos concretos.
3. **Noticias & Catalizadores (Google News RSS):** Detección temprana de contratos, lanzamientos, acuerdos y diluciones de capital.
4. **Acción Técnica del Precio (yfinance):** Confirmación cuantitativa de tendencia, momentum y sobreextensión.

---

## 2. 🏗️ Arquitectura General del Sistema

El sistema está construido como un **Monolito Modular** en Python 3.11+ con interfaz web moderna en React 18 / TypeScript / Vite:

```text
                                ┌─────────────────────────────────────────────────────────┐
                                │                 DATA COLLECTORS LAYER                   │
                                │  - X/Twitter (Twikit / Mock Fallback)                  │
                                │  - Polymarket Gamma API (Mock Fallback)                 │
                                │  - News (Google News RSS Feed Parser)                   │
                                │  - Market Data (yfinance OHLCV 1Y)                     │
                                └────────────────────────────┬────────────────────────────┘
                                                             │
                                                             ▼
                                ┌─────────────────────────────────────────────────────────┐
                                │                 PROCESSORS & NLP LAYER                  │
                                │  - Sentiment Classifier (Lexical / FinBERT)            │
                                │  - Disambiguation: multi-word ATH vs negative metrics   │
                                │  - log1p Engagement Weight: ln(1+likes+2·rt+...)       │
                                │  - Exp Decay Recency Weight: exp(-lambda·age)          │
                                │  - Polymarket Quality Scorer (0-100 Quality Threshold)  │
                                │  - Catalyst Categorizer & Importance Assessor           │
                                │  - Technical Indicators (EMA200, RSI, BB, MACD, ATR)    │
                                └────────────────────────────┬────────────────────────────┘
                                                             │
                                                             ▼
                                ┌─────────────────────────────────────────────────────────┐
                                │                 QUANT SCORING ENGINES                   │
                                │  - SSI (Social Sentiment Score, 0-100)                  │
                                │  - PMS (Prediction Market Score, 0-100)                 │
                                │  - News Score (0-100)                                   │
                                │  - Price Momentum Score (0-100)                         │
                                │  - Fundamental Score (0-100)                           │
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
                                │  - Quantitative "WHY?" Explanation Engine               │
                                └────────────────────────────┬────────────────────────────┘
                                                             │
                                ┌────────────────────────────┴────────────────────────────┐
                                │                                                         │
                                ▼                                                         ▼
                 ┌─────────────────────────────┐                           ┌─────────────────────────────┐
                 │      PERSISTENCE LAYER      │                           │     PRESENTATION LAYER      │
                 │  - SQLite WAL (Auto-migrate)│                           │  - FastAPI REST API         │
                 │  - Immutable Snapshots      │                           │  - React 18 + TS Terminal UI│
                 │  - Sample Counts (P, N, M)  │                           │  - Multi-series SVG Charts  │
                 │  - Divergences & Job Runs   │                           │  - Silent Cold-Start Radar  │
                 │  - Introspective Migration  │                           │  - Desktop Notifications    │
                 └─────────────────────────────┘                           └─────────────────────────────┘
```

---

## 3. 📐 Nomenclatura Cuantitativa y Motores de Puntuación

### A. Distinción Estricta de Métricas

| Métrica | Nombre Completo | Rango | Definición y Rol |
| :--- | :--- | :---: | :--- |
| **`SMI`** | **Space Market Intelligence Index** | **$0\text{--}100$** | **Índice cuantitativo integral maestro.** Combina los 6 factores multivariables con pesos adaptativos dinámicos. |
| **`SSI`** | **Space Sentiment Index** | **$0\text{--}100$** | Mide **exclusivamente el sentimiento social puro de X/Twitter**, ponderado por engagement logarítmico y decaimiento temporal. |
| **`PMS`** | **Prediction Market Score** | **$0\text{--}100$** | Mide las **expectativas implícitas en Prediction Markets (Polymarket)** para eventos directos y sectoriales. |
| **`Risk Score`** | **Risk & Safety Score** | **$0\text{--}100$** | Mide la **seguridad del activo** (mayor = más seguro/menor volatilidad) combinando: ATR% sobre precio, volatilidad anualizada a 30 días y drawdown móvil a 30 días. |
| **`Market Score`** | **Technical Market Score** | **$0\text{--}100$** | Mide la **confirmación técnica del precio** (escalado desde el score técnico de 40 pts). |

---

### B. Fórmulas Matemáticas Clave

#### 1. Ponderación Social SSI & Bayesian Credibility Shrinkage:
- **Engagement Logarítmico:**
  $$\text{Engagement} = \ln\left(1 + \text{likes} + 2\cdot\text{reposts} + 1.5\cdot\text{replies} + \frac{\text{views}}{1000}\right)$$
  Multiplicador de peso parametrizado por `ENGAGEMENT_SCALE_DIVISOR = 10.0`:
  $$w_i = \text{relevance} \cdot \text{recency} \cdot \text{confidence} \cdot \left(1.0 + \frac{\text{engagement}}{10.0}\right)$$
- **Decaimiento Temporal Exponencial:**
  $$\text{Weight}_{\text{recency}} = e^{-\lambda \cdot \text{age\_hours}}, \quad \lambda = \frac{\ln(2)}{12.0\text{h}}$$
- **Contracción Bayesiana de Credibilidad (*Empirical Bayes Shrinkage*):** Ante muestras reducidas ($1 \le N < 10$ posts), el score social efectivo se contrae suavemente hacia el prior neutro ($\mu_0 = 50.0$) con piso mínimo de credibilidad ($10\%$):
  $$\text{effective\_social} = 50.0 + (\text{social\_score} - 50.0) \times \min\left(1.0, \max\left(0.10, \frac{\text{post\_count}}{10.0}\right)\right)$$
- **Exclusión Adaptativa sin Falsa Neutralidad:** Si $N = 0$ posts o no hay posts relevantes, el pilar social se excluye estrictamente ($w_{\text{social}} = 0$) y su peso se redistribuye proporcionalmente entre las fuentes activas.

#### 2. Polymarket Market Quality Scorer (0 a 100):
Calcula la confiabilidad del contrato para evitar manipulación en mercados ilíquidos:
$$\text{Quality} = 0.35 \cdot \text{Liquidity} + 0.30 \cdot \text{Volume} + 0.20 \cdot \text{Spread} + 0.15 \cdot \text{TimeToResolution}$$
> **Regla de Calidad:** Si $\text{Quality} < 30.0$ o `prediction_count == 0`, el peso de Polymarket se anula estrictamente ($w_{\text{prediction}} = 0$).

#### 3. Módulo de Análisis Fundamental del Sector Espacial (0 a 100):
Cuantifica la viabilidad financiera y solvencia de compañías espaciales de alto crecimiento:
$$\text{Fundamental\_Score} = 0.40 \cdot \text{Runway} + 0.25 \cdot \text{Solvency} + 0.20 \cdot \text{Growth} + 0.15 \cdot \text{Margin}$$
- **Cash Runway (40%):** Meses de caja operativa frente a quema de efectivo ($\text{Burn Rate}$). Flujo libre de caja positivo $\to 90$ pts; $>24$ meses $\to 85$ pts; $<6$ meses $\to 15$ pts (riesgo crítico de dilución).
- **Solvencia (25%):** Posición de caja neta frente a endeudamiento total (`total_debt / total_cash`).
- **Crecimiento YoY (20%):** Expansión anual de ingresos por contratos comerciales y de defensa.
- **Márgenes Unitarios (15%):** Margen bruto de hardware aeroespacial y payloads satelitales.

#### 4. Arquitectura de 6 Pilares y Normalización Adaptativa de SMI:
Pesos base canónicos:
- **Social (SSI):** $30\%$
- **Prediction Markets (PMS):** $15\%$
- **News / Catalysts:** $20\%$
- **Market Momentum:** $20\%$
- **Fundamentals:** $10\%$
- **Risk / Safety:** $5\%$

Ante fuentes no disponibles ($None$ o $N=0$):
$$w_i^{\text{active}} = \frac{w_i}{\sum_{j \in \text{active}} w_j}$$

- **Source Agreement ($\in [-1.0, +1.0]$) — Pairwise Directional Concordance:**
  $$\text{Agreement} = \frac{1}{\binom{N}{2}} \sum_{i < j} \text{Concordance}(d_i, d_j), \quad \text{Concordance}(d_i, d_j) = \text{sign}(d_i \cdot d_j) \cdot \min\left(1.0, \frac{|d_i| + |d_j|}{1.5}\right)$$
  *(donde $|d_k| < 0.10 \implies \text{Concordance} = 0$. Excluye la métrica de riesgo no direccional).*

---

### C. Ciclo Cerrado de Optimización (Backtesting $\to$ Pesos Dinámicos)

El sistema soporta retroalimentación adaptativa en ciclo cerrado (`ENABLE_DYNAMIC_WEIGHT_FEEDBACK`):
* **Compuerta Muestral Bilateral:** $\min(N_{\text{trades\_A}}, N_{\text{trades\_B}}) \ge 30$ en horizonte de $3\text{D}$.
* **Modulación por $\Delta\text{Sharpe}$:**
  $$\kappa = 1.0 + \text{clip}\left(\frac{\Delta\text{Sharpe}_{\text{3D}}}{2.0}, -0.5, +0.5\right)$$
  $$w_{\text{prediction}}^* = \text{clip}(0.15 \times \kappa, 0.05, 0.25)$$
* **Conservación de Suma:** Los 5 pilares restantes se re-escalan proporcionalmente garantizando que $\sum_{i=1}^6 w_i \equiv 1.0000$.

---

### D. Normalización Invariante a Escala (MACD & ATR)
El umbral de compresión y cruce del histograma MACD no es absoluto en dólares; se normaliza dinámicamente como:
$$\text{MACD\_Threshold} = \min(0.08 \times \text{ATR}, 0.0020 \times \text{Price})$$
Garantizando simetría cuantitativa entre activos de bajo precio ($SPCE $\approx \$3$) y alto precio ($ASTS/RKLB $\approx \$30\text{--}\$80$).

---

### E. Divergence Engine (Detección de Desacoples Tripartitos)

| Tipo de Divergencia | Condición Cuantitativa | Implicación de Mercado | Severidad |
| :--- | :--- | :--- | :---: |
| **`BULLISH_DIVERGENCE`** | $\text{SSI} \ge 70$ y $\text{PMS} \ge 60$, pero $\text{Price} < \text{EMA200}$ o Retorno $< -5\%$ | Oportunidad de compra por desacople / infravaloración temporal. | **`HIGH`** |
| **`BEARISH_DIVERGENCE`** | Precio en máximos / extendido, pero $\text{SSI} \le 40$ o $\text{PMS} \le 40$ | Alerta de trampa alcista; alto riesgo de corrección. | **`HIGH`** |
| **`BEARISH_CONFIRMATION`**| Todas las fuentes alineadas a la baja + alto volumen de venta | Confirmación multilateral bajista; liquidación institucional. | **`CRITICAL`** |
| **`EARLY_REVERSAL`** | $\Delta\text{PMS}_{24\text{h}} \ge +15\%$ mientras el precio y redes siguen neutros/bajistas | Giro temprano liderado por apostadores informados en Polymarket. | **`HIGH`** |
| **`BULLISH_CONFIRMATION`**| Todas las fuentes activas en la misma dirección ($\text{Agreement} \ge 0.70$) | Confirmación estructural; máxima certeza en la señal alcista. | **`HIGH`** |

---

### F. Señales de Trading y Explicabilidad "WHY?"

- **Estructura Desacoplada:**
  - `base_signal`: Enum canónico puro (`STRONG BUY`, `BUY`, `WATCH`, `HOLD`, `AVOID`, `STRONG AVOID`).
  - `signal_modifier`: Modificador cualitativo opcional (`OVEREXTENDED`, `NO MKT DATA`, `None`).
  - `signal`: String compuesto para presentación visual (ej. `"WATCH (OVEREXTENDED)"`, `"BUY (OVEREXTENDED)"`).
- **Umbrales del SMI y Gestión de Sobrecompra:**
  - **`85–100`**: **STRONG BUY** *(restringido preventivamente a `base_signal: WATCH` con `signal_modifier: OVEREXTENDED` si RSI > 75 por sobreextensión técnica)*.
  - **`75–84`**: **BUY** *(mantiene `base_signal: BUY` pero adjunta `signal_modifier: OVEREXTENDED` si RSI > 75)*.
  - **`65–74`**: **WATCH**
  - **`50–64`**: **HOLD**
  - **`35–49`**: **AVOID**
  - **`0–34`**: **STRONG AVOID** *(emite alerta `CRITICAL` para preservación de capital)*.

---

### G. Jerarquización de Prediction Markets (Directos vs Sectoriales)

En el endpoint `/api/tickers/{ticker}` y la pestaña modal de predicciones:
* **Prioridad #1 — Contratos Directos:** Contratos cuyo ticker coincide con el activo seleccionado (ej. `ASTS` $\to$ lanzamiento comercial de BlueBird). Se ordenan siempre en primer lugar.
* **Prioridad #2 — Catalizadores Sectoriales (SpaceX / NASA / Space Force):** Contratos macro que impactan al activo mediante la matriz `DEFAULT_EVENT_COMPANY_MAPPINGS`.
* **Metadatos:** Cada contrato incluye `is_direct: bool`, `event_role: "DIRECT" | "SECTOR_CATALYST"` e `impact_weight: float`.
* **Sub-Filtros en UI:** Pestañas para alternar entre `Todos`, `🎯 Directos $TICKER` y `🌐 Sectoriales / SpaceX`.

---

## 4. 🔔 Sistema de Alertas y Notificaciones de Escritorio (Windows Toast)

Reconstruido con arquitectura robusta en [`AlertsManager.tsx`](frontend/src/components/AlertsManager.tsx):
1. **Silent Cold-Start Seeding:** Al cargar o recargar la página ($F5$), las alertas existentes en el servidor se marcan como conocidas sin emitir ningún toast ni sonido.
2. **Disparo Exclusivo por Deltas:** Solo las alertas genuinamente nuevas generadas por ejecuciones posteriores del pipeline emiten notificación.
3. **Registro Persistente e Idempotente (`localStorage: smie_desktop_notified_v1`):** Con auto-pruning de 100 registros.
4. **Compuerta de Frescura:** Alertas con antigüedad $> 30\text{ min}$ o inactivas se suprimen del popup del SO.
5. **Panel de Preferencias:**
   - Toggle directo de Notificaciones de Windows.
   - Selector de severidad: *🔴 Solo Críticas* / *🟠 Críticas + Altas* / *⚪ Todas*.
   - Botón de prueba interactiva de sonido/toast.

---

## 5. 🧪 Motor de Backtesting Físico y Continuo

Módulo [`app/backtesting/engine.py`](file:///d:/Mis%20Cosas/test/Space%20Sentiment%20Index/app/backtesting/engine.py):
- **Horizonte Físico Continuo:** Búsqueda temporal basada en $t_{\text{target}} = t_{\text{entry}} + \text{timedelta}(\text{days}=H)$ con tolerancia acotada, resolviendo desfases en frecuencias horarias.
- **Paridad Bayesiana:** Reproduce fielmente el shrinkage ($N/10$) y exclusión de pilares vacíos ($N=0$) a partir de `post_count`, `news_count` y `prediction_count` persistidos en snapshots.
- **Model A vs Model B:**
  - **Model A (Control Baseline):** Sin Polymarket con redistribución adaptativa.
  - **Model B (SMIE Multi-Source):** Incorporando Prediction Markets.
- **Métricas:** Win Rate, Profit Factor, Expectancy, Max Drawdown, Sharpe Ratio anualizado, Sortino Ratio y $\Delta\text{Sharpe}$.

---

## 6. 💻 Endpoints REST API y CLI

### Endpoints REST (`FastAPI`)
- `GET /api/dashboard`: Ranking global con columnas de 6 factores, contadores muestrales (`post_count`, `news_count`, `prediction_count`), `risk_score`, alertas y divergencias.
- `GET /api/tickers/{ticker}`: Detalle completo con desglose de 6 pilares, `sample_counts`, datos técnicos (incluyendo ATR), catalizadores y prediction markets.
- `GET /api/tickers/{ticker}/prediction-markets`: Contratos de Polymarket clasificados en Directos vs Sectoriales con probabilidad YES/NO, $\Delta_{24\text{h}}$, volumen, liquidez, spread y calidad.
- `GET /api/tickers/{ticker}/divergences`: Historial de divergencias tripartitas.
- `GET /api/tickers/{ticker}/history`: Series temporales históricas multi-curva (`price`, `smi`, `ssi`, `pms`, `volume`, `risk_score`).
- `GET /api/reports/daily`: Reporte formal de inteligencia estructurado en JSON y Markdown.
- `GET /api/backtest`: Métricas comparativas y calibración adaptativa de pesos.
- `GET /api/health`: Diagnóstico de salud por subsistema.

### Comandos CLI (`python -m app.cli.commands <comando>`)
- `run-all`: Ejecuta el pipeline completo de SMIE y genera snapshots.
- `analyze <TICKER>`: Desglose analítico con árbol de razones "WHY?".
- `daily-report`: Imprime el reporte diario del sector espacial.
- `backtest`: Ejecuta el motor de backtesting comparativo.
- `collect-social` / `collect-polymarket` / `collect-news` / `collect-market`: Ingestión granular.
- `calculate-divergences`: Evaluación de divergencias activas.

---

## 7. 🌐 Frontend Terminal Web (React + TS + Vite)

- **Dashboard Principal:** Tabla terminal estilo Bloomberg con 6 pilares visibles (Social, PMS, News, Momentum, Tech, Risk/Safety), tarjetas informativas y badges de vigencia de datos.
- **Detalle de Ticker:** Modal interactivo con gráfico multi-curva SVG, desglose de 6 factores, barra de *Data Depth* (`xxP / xxN / xxM`), medidor ATR y pestañas especializadas.
- **Alertas & Radar:** Menú desplegable con filtro por categorías, indicador de no leídas, panel de ajustes de notificación y arranque silencioso en recargas.

---

## 8. 🛰️ Universo de Cobertura Inicial
1. **ASTS** — AST SpaceMobile Inc.
2. **RKLB** — Rocket Lab USA Inc.
3. **SATL** — Satellogic Inc.
4. **SPCE** — Virgin Galactic Holdings Inc.
5. **SPCX** — Procure Space ETF / Proxy Sectorial (SpaceX Starship, Artemis, FCC).

---

## 9. 🛡️ Suite de Pruebas Automatizadas

## 9. 🛡️ Suite de Pruebas Automatizadas

El proyecto cuenta con una suite completa de tests unitarios y de integración automatizados que cubren matemática cuantitativa, scoring multivariable de 6 pilares, fundamentales, divergencias, persistencia por lotes, gobernanza de datos en vivo vs mock, backtesting físico, exclusión mutua asíncrona con mutex, paridad determinista live/backtest sin sesgo de anticipación, invarianza de escala ATR, zonas horarias UTC, compuertas de profundidad de indicadores y NLP:
```powershell
python -m pytest tests/ -v
```
- Incluye el módulo `tests/test_strategy_parity.py` que certifica matemáticamente la paridad idéntica entre la ejecución en vivo y el cálculo histórico sin sesgo de anticipación (*Lookahead Bias*), invarianza de escala ATR, niveles de soporte/resistencia calculados sobre ventanas fijas de 100 velas independientes del tamaño del historial de red y puntuación anatómica de velas con precedencia de Doji corregida.
