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
                                │  - log1p Engagement Weight: ln(1+likes+2·rt+...)       │
                                │  - Exp Decay Recency Weight: exp(-lambda·age)          │
                                │  - Polymarket Quality Scorer (0-100 Quality Threshold)  │
                                │  - Catalyst Categorizer & Importance Assessor           │
                                │  - Technical Indicators (EMA200, RSI, BB, MACD, Vol)    │
                                └────────────────────────────┬────────────────────────────┘
                                                             │
                                                             ▼
                                ┌─────────────────────────────────────────────────────────┐
                                │                 QUANT SCORING ENGINES                   │
                                │  - SSI (Social Sentiment Score, 0-100)                  │
                                │  - PMS (Prediction Market Score, 0-100)                 │
                                │  - News Score (0-100)                                   │
                                │  - Price Momentum Score (0-100)                         │
                                │  - Technical Score (0-40)                               │
                                │  - Risk & Safety Score (0-100)                          │
                                └────────────────────────────┬────────────────────────────┘
                                                             │
                                                             ▼
                                ┌─────────────────────────────────────────────────────────┐
                                │                 SMI & DIVERGENCE ENGINE                 │
                                │  - SMI (Space Market Intelligence Index, 0-100)         │
                                │  - Adaptive Weight Normalization (No Fake Imputation)   │
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
                 │  - Prediction Market History│                           │  - Multi-series SVG Charts  │
                 │  - Divergences & Job Runs   │                           │  - Interactive Guide Modal  │
                 └─────────────────────────────┘                           └─────────────────────────────┘
```

---

## 3. 📐 Nomenclatura Cuantitativa y Motores de Puntuación

### A. Distinción Estricta de Métricas

| Métrica | Nombre Completo | Rango | Definición y Rol |
| :--- | :--- | :---: | :--- |
| **`SMI`** | **Space Market Intelligence Index** | **$0\text{--}100$** | **Índice cuantitativo integral maestro.** Combina todas las fuentes multivariables con pesos adaptativos dinámicos. |
| **`SSI`** | **Space Sentiment Index** | **$0\text{--}100$** | Mide **exclusivamente el sentimiento social puro de X/Twitter**, ponderado por engagement logarítmico y decaimiento temporal. |
| **`PMS`** | **Prediction Market Score** | **$0\text{--}100$** | Mide las **expectativas implícitas en Prediction Markets (Polymarket)** para eventos directos y sectoriales. |
| **`Market Score`** | **Technical Market Score** | **$0\text{--}100$** | Mide la **confirmación técnica del precio** (escalado desde el score técnico de 40 pts). |

---

### B. Fórmulas Matemáticas Clave

#### 1. Ponderación Social SSI:
- **Engagement Logarítmico:**
  $$\text{Engagement} = \ln\left(1 + \text{likes} + 2\cdot\text{reposts} + 1.5\cdot\text{replies} + \frac{\text{views}}{1000}\right)$$
- **Decaimiento Temporal Exponencial:**
  $$\text{Weight}_{\text{recency}} = e^{-\lambda \cdot \text{age\_hours}}, \quad \lambda = \frac{\ln(2)}{12.0\text{h}}$$
- **Score Social:** $\text{SSI} = 50 + 50 \cdot \text{Weighted\_Sentiment} \in [0, 100]$.

#### 2. Polymarket Market Quality Scorer (0 a 100):
Calcula la confiabilidad del contrato para evitar manipulación en mercados ilíquidos:
$$\text{Quality} = 0.30 \cdot \text{Liquidity} + 0.30 \cdot \text{Volume} + 0.20 \cdot \text{Spread} + 0.20 \cdot \text{TimeToExpiry}$$
> **Regla de Oro de Calidad:** Si $\text{Quality} < 30.0$, el peso efectivo de Polymarket en el cálculo de SMI se anula estrictamente ($w_{\text{prediction}} = 0$).

#### 3. Cálculo Adaptativo de SMI:
Pesos base: Social ($30\%$), Polymarket ($15\%$), News ($20\%$), Momentum ($20\%$), Fundamentales ($10\%$), Risk ($5\%$).
Ante fuentes faltantes ($None$) o anuladas por baja calidad:
$$w_i^{\text{active}} = \frac{w_i}{\sum_{j \in \text{active}} w_j}$$
- **Source Agreement ($\in [-1.0, +1.0]$) — Pairwise Directional Concordance:**
  $$\text{Agreement} = \frac{1}{\binom{N}{2}} \sum_{i < j} \text{Concordance}(d_i, d_j), \quad \text{Concordance}(d_i, d_j) = \text{sign}(d_i \cdot d_j) \cdot \min\left(1.0, \frac{|d_i| + |d_j|}{1.5}\right)$$
  *(donde $|d_k| < 0.10 \implies \text{Concordance} = 0$; garantiza concordancia direccional estricta $[-1.0, +1.0]$ y descarta la dispersión de $\sigma$ que penalizaba intensidades dispares en la misma dirección).*
- Si $\text{Agreement} < 0.30$, la **Confianza** del sistema se penaliza proporcionalmente por dispersión o contradicción entre fuentes.

---

### C. Divergence Engine (Detección de Desacoples Tripartitos)

El sistema nunca promedia a ciegas señales contradictorias:

| Tipo de Divergencia | Condición Cuantitativa | Implicación de Mercado |
| :--- | :--- | :--- |
| **`BULLISH_DIVERGENCE`** | $\text{SSI} \ge 70$ y $\text{PMS} \ge 60$, pero $\text{Price} < \text{EMA200}$ o Retorno $< -5\%$ | Oportunidad de compra por desacople / infravaloración temporal. |
| **`BEARISH_DIVERGENCE`** | Precio en máximos / extendido, pero $\text{SSI} \le 40$ o $\text{PMS} \le 40$ | Alerta de trampa alcista; alto riesgo de corrección. |
| **`EARLY_REVERSAL`** | $\Delta\text{PMS}_{24\text{h}} \ge +15\%$ mientras el precio y redes siguen neutros/bajistas | Giro temprano liderado por apostadores informados en Polymarket. |
| **`CONFIRMATION`** | Todas las fuentes activas en la misma dirección ($\text{Agreement} \ge 0.70$) | Confirmación estructural; máxima certeza en la señal. |

---

### D. Señales de Trading y Explicabilidad "WHY?"

- **Estructura Desacoplada:**
  - `base_signal`: Enum canónico puro (`STRONG BUY`, `BUY`, `WATCH`, `HOLD`, `AVOID`, `STRONG AVOID`).
  - `signal_modifier`: Modificador cualitativo opcional (`OVEREXTENDED`, `NO MKT DATA`, `None`).
  - `signal`: String compuesto formateado para presentación visual (ej. `"WATCH (OVEREXTENDED)"`, `"STRONG BUY (NO MKT DATA)"`).
- **Umbrales del SMI:**
  - **`80–100`**: **STRONG BUY** *(restringido automáticamente a `base_signal: WATCH` con `signal_modifier: OVEREXTENDED` si RSI > 75 por sobreextensión técnica)*.
  - **`70–79`**: **BUY**
  - **`60–69`**: **WATCH**
  - **`45–59`**: **HOLD**
  - **`35–44`**: **AVOID**
  - **`0–34`**: **STRONG AVOID**
- **NLP Heurístico con Detección de Negación e Idiomas Afirmativos:**
  - Control sintáctico de tokens (0-2 palabras de ventana).
  - Reconocimiento de modismos de certeza (`"no doubt"`, `"without doubt"`, `"no question"`) y barreras infranqueables de puntuación (`,`, `.`, `;`, `!`, `?`).

---

## 4. 🧪 Motor de Backtesting y Validación de Hipótesis

Módulo [`app/backtesting/engine.py`](file:///d:/Mis%20Cosas/test/Space%20Sentiment%20Index/app/backtesting/engine.py) diseñado para responder a la pregunta de investigación central:
> *¿Aporta la incorporación de Polymarket valor predictivo incremental sobre X + Mercado?*

- **Model A (Control Baseline):** `Model A (X Social + Technical + News Baseline)` — Evaluación sin Polymarket con redistribución adaptativa del 25% entre los pilares de Social, Noticias, Momentum, Riesgo y Análisis Técnico.
- **Model B (Tratamiento SMIE):** `Model B (Multi-Source with Polymarket PMS)` — Incorporación de los mercados de predicción de Polymarket.
- **Aislamiento Multi-Ticker:** Agrupación estricta por ticker antes del cálculo de retornos futuros a 1D, 3D y 5D para prevenir contaminación cruzada de precios.
- **Métricas calculadas:**
  - **Win Rate (%)**
  - **Profit Factor** ($\frac{\sum \text{Gains}}{\sum \text{Losses}}$)
  - **Expectancy ($E$)**
  - **Max Drawdown (%)**
  - **Sharpe Ratio** (anualizado $\times \sqrt{252}$)
  - **Sortino Ratio** (desviación a la baja)

---

## 5. 💻 Endpoints REST API y Comandos CLI

### Endpoints REST (`FastAPI`)
- `GET /api/dashboard`: Ranking global con columnas `smi`, `ssi`, `pms`, `market_score`, `signal`, `base_signal`, `signal_modifier`, `confidence`, `data_quality`, `is_stale`, `data_age_hours`, `divergence`.
- `GET /api/tickers/{ticker}`: Detalle exhaustivo con desglose de 6 pilares, tweets, noticias, prediction markets filtrados por matriz de impacto y divergencias.
- `GET /api/tickers/{ticker}/prediction-markets`: Lista de contratos de Polymarket asociados con YES/NO %, $\Delta_{24\text{h}}$, volumen, liquidez, spread y calidad.
- `GET /api/tickers/{ticker}/divergences`: Historial de divergencias tripartitas.
- `GET /api/tickers/{ticker}/history`: Series temporales multi-curva (`price`, `smi`, `ssi`, `pms`, `volume`).
- `GET /api/reports/daily`: Reporte diario estructurado en JSON y Markdown.
- `GET /api/backtest`: Métricas comparativas del backtest entre Model A y Model B.
- `GET /api/health`: Diagnóstico granular por proveedor (`database`, `x_provider`, `polymarket_provider`, `market_provider`, `news_provider`).

### Comandos CLI (`python -m app.cli <comando>`)
- `run-all`: Ejecuta el pipeline completo de SMIE y muestra el ranking.
- `analyze <TICKER>`: Desglose analítico completo de un ticker con explicaciones "WHY?".
- `daily-report`: Genera e imprime el reporte diario del sector espacial.
- `backtest`: Ejecuta el análisis comparativo cuantitativo entre Model A y Model B.
- `collect-social` / `collect-polymarket` / `collect-news` / `collect-market`: Ingestión granular por fuente.
- `calculate-divergences`: Evaluación de divergencias activas.

---

## 6. 🌐 Frontend Terminal Web (React + TS + Vite)

- **Dashboard Principal:** Tabla terminal interactiva estilo Bloomberg y vista alternativa en tarjetas con badges de frescura/obsolescencia de datos.
- **Detalle de Ticker:** Modal con medidores `SMI`, `SSI` y `PMS`, pestañas para **Prediction Markets** (filtrados por relevancia semántica), **X Social Feed**, **Noticias** y **Divergencias**.
- **Gráfico Multi-Serie Interactivo SVG:** Toggles interactivos para encender/apagar curvas individuales (Price, SMI, SSI, PMS) y tooltip sincronizado.
- **Modal de Inducción y Manual de Uso (`AboutModal.tsx`):** Accesible al hacer clic en el logo del cohete (`🚀`) o en el botón *"Manual de Uso"*.

---

## 7. 🛰️ Universo de Cobertura Inicial

1. **ASTS** — AST SpaceMobile Inc.
2. **RKLB** — Rocket Lab USA Inc.
3. **SATL** — Satellogic Inc.
4. **SPCE** — Virgin Galactic Holdings Inc.
5. **SPCX** — Procure Space ETF / Proxy de Eventos Sectoriales (SpaceX Starship, Artemis, FCC).

---

## 8. 🛡️ Suite de Pruebas Automatizadas

El proyecto cuenta con **53 tests unitarios automatizados** que validan la matemática, algoritmos y estabilidad:
```powershell
python -m pytest tests/ -v
```
*(Resultados: 53 passed en 1.50s, 0 warnings).*
