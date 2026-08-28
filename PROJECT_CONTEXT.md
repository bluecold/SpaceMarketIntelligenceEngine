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

### D. Señales Canónicas y Preservación de Capital

- **Señal Base:** Enum canónico puro (`STRONG BUY`, `BUY`, `WATCH`, `HOLD`, `AVOID`, `STRONG AVOID`).
- **Modificadores:** `DILUTION RISK`, `CONFLICTING SOURCES`, `LOW DATA QUALITY`, `OVEREXTENDED`, `NO MKT DATA`.
- **Alertas de Catalizadores Críticos con Identidad Única:** Identificadores con categoría explícita `{ticker}:CATALYST:{category}` permitiendo la coexistencia de múltiples catalizadores simultáneos en el mismo activo.

---

### E. Ciclo de Notificaciones y Gestión de Episodios

1. **Silent Cold-Start:** En el arranque o recarga ($F5$), las alertas existentes se registran sin disparar notificaciones ruidosas.
2. **Identidad por Episodio (`baseId@opened_at`):** Si una alerta se resuelve y vuelve a abrirse semanas después con nuevo timestamp, el navegador dispara la notificación del nuevo episodio oportunamente.
3. **Sondeo Inteligente:** Cadencia periódica de 1 hora alineada con el programador backend y sondeo inmediato al enfocar la pestaña si estuvo inactiva $\ge 15$ minutos (`visibilitychange`).

---

## 4. 🧪 Suite de Pruebas Automatizadas

La suite de pruebas (`tests/`) está totalmente aislada de la red y la base de datos de producción mediante `tests/conftest.py`:
```powershell
python -m pytest tests/ -v
```
- **112 pruebas automatizadas** que se ejecutan en **~2.2 segundos**.
- Cobertura integral de: paridad de estrategias sin sesgo de anticipación, invarianza de escala ATR, concurrencia atómica HTTP 409, episodios de alertas, extracción de fundamentales vía DataFrames, contracción bayesiana, detección de catalizadores destructivos (`LAUNCH_FAILURE`) y normalización adaptativa de 6 pilares.
