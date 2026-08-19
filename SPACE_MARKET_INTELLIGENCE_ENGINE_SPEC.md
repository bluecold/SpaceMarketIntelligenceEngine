# 🚀 Space Market Intelligence Engine

## Especificación Funcional y Técnica

**Versión:** 2.0  
**Estado:** Especificación para desarrollo  
**Fecha:** 19/08/2026  
**Proyecto:** Space Market Intelligence Engine  
**Nombre corto:** SMIE  
**Idioma de desarrollo:** Inglés  
**Idioma inicial de UI:** Inglés  
**Tipo:** Aplicación Web + Motor de análisis cuantitativo  
**Mercado objetivo:** Acciones estadounidenses del sector espacial/aeroespacial

---

# 1. RESUMEN EJECUTIVO

Space Market Intelligence Engine (SMIE) es una aplicación web orientada al análisis cuantitativo del sentimiento, expectativas y comportamiento de mercado de empresas relacionadas con el sector espacial.

El sistema combinará múltiples fuentes de información:

1. X / Twitter
2. Prediction Markets, inicialmente Polymarket
3. Noticias
4. Datos de mercado
5. Indicadores técnicos
6. Catalizadores
7. Datos fundamentales
8. Historial propio del sistema

El objetivo no es simplemente clasificar publicaciones como bullish o bearish.

El objetivo es detectar:

- cambios de sentimiento;
- cambios de expectativas;
- cambios de probabilidad;
- divergencias entre narrativa y precio;
- convergencias entre distintas fuentes;
- posibles catalizadores;
- situaciones de sobreextensión;
- señales tempranas de cambio de tendencia.

---

# 2. CONCEPTO CENTRAL

El sistema debe distinguir tres tipos de información:

## 2.1 Social Intelligence

Pregunta:

> ¿Qué está diciendo la gente?

Fuente principal:

X.

Variables:

- sentimiento;
- volumen de conversación;
- engagement;
- relevancia;
- autores;
- velocidad de cambio;
- narrativas;
- catalizadores mencionados.

---

## 2.2 Prediction Market Intelligence

Pregunta:

> ¿Qué probabilidad le asigna el mercado a que ocurra un evento?

Fuente inicial:

Polymarket.

Variables:

- probabilidad actual;
- cambio de probabilidad;
- volumen;
- liquidez;
- spread;
- actividad;
- tiempo hasta resolución;
- calidad del mercado;
- dirección del cambio.

---

## 2.3 Market Intelligence

Pregunta:

> ¿Qué está haciendo realmente el capital?

Fuentes:

Market Data Provider.

Variables:

- precio;
- volumen;
- momentum;
- RSI;
- EMA;
- Bollinger Bands;
- MACD;
- ATR;
- volatilidad;
- beta;
- comportamiento relativo.

---

# 3. PRINCIPIO FUNDAMENTAL

El sistema debe analizar la interacción entre:

```text
                SOCIAL
                   │
                   ▼
              Narrativa
                   │
                   │
PREDICTION ────────┼──────── MARKET
 MARKET            │          DATA
                   ▼
              EXPECTATIONS
                   │
                   ▼
              SIGNAL ENGINE
```

La hipótesis principal del proyecto es:

> Una señal tiene mayor valor cuando diferentes fuentes independientes apuntan en la misma dirección.

Ejemplo:

```text
X Sentiment             BULLISH
Polymarket Probability  BULLISH
Price Momentum          BULLISH
Volume                  HIGH
```

Esto debería producir una mayor confianza que:

```text
X Sentiment             BULLISH
Polymarket              UNAVAILABLE
Price Momentum          BEARISH
```

---

# 4. OBJETIVO PRINCIPAL

Construir un sistema capaz de responder automáticamente:

> ¿Qué está ocurriendo hoy en el sentimiento y expectativas del sector espacial?

Y para cada acción:

> ¿Es bullish o bearish?

> ¿Por qué?

> ¿Qué está impulsando el sentimiento?

> ¿Existe confirmación mediante dinero/mercado?

> ¿Existe divergencia?

> ¿Qué nivel de confianza tiene la señal?

> ¿Cómo se comportó históricamente una situación similar?

---

# 5. TICKERS INICIALES

El MVP debe analizar:

| Ticker | Empresa |
|---|---|
| ASTS | AST SpaceMobile |
| RKLB | Rocket Lab |
| SATL | Satellogic |
| SPCE | Virgin Galactic |
| SPCX | Instrumento a validar |

---

# 6. VALIDACIÓN DE TICKERS

El sistema NO debe asumir que todos los símbolos son instrumentos negociables válidos.

Especialmente:

```text
SPCX
```

debe ser validado contra el proveedor de datos.

Si no existe:

```text
market_status = DATA_UNAVAILABLE
```

Esto no debe impedir el análisis de otras fuentes.

---

# 7. ARQUITECTURA GENERAL

```text
                         SMIE
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
      SOCIAL          PREDICTION          MARKET
       DATA             MARKETS            DATA
        │                 │                 │
        ▼                 ▼                 ▼
       X              Polymarket       Market Provider
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                          ▼
                   DATA NORMALIZATION
                          │
             ┌────────────┼────────────┐
             │            │            │
             ▼            ▼            ▼
        SENTIMENT      CATALYST      TECHNICAL
          ENGINE         ENGINE        ENGINE
             │            │            │
             └────────────┼────────────┘
                          ▼
                    SCORE ENGINE
                          │
             ┌────────────┼────────────┐
             │            │            │
             ▼            ▼            ▼
        SOCIAL SCORE   PMS SCORE   MARKET SCORE
             │            │            │
             └────────────┼────────────┘
                          ▼
                     SSI / SMI
                          │
                          ▼
                  DIVERGENCE ENGINE
                          │
                          ▼
                    SIGNAL ENGINE
                          │
                          ▼
                    WEB DASHBOARD
```

---

# 8. STACK TECNOLÓGICO

## Backend

Python 3.11+

FastAPI

## Frontend

React

TypeScript

Vite

## Database

SQLite para MVP.

PostgreSQL posteriormente.

## ORM

SQLAlchemy

## HTTP

httpx

## Scheduler

APScheduler

## Configuration

python-dotenv

## Testing

pytest

## Optional

Pandas

NumPy

scikit-learn

Transformers

PyTorch

---

# 9. PRINCIPIO DE ARQUITECTURA

El proyecto debe ser:

- modular;
- extensible;
- testeable;
- auditable;
- observable;
- explicable.

No implementar microservicios inicialmente.

Utilizar:

> Modular Monolith

---

# 10. ESTRUCTURA DEL PROYECTO

```text
space-market-intelligence/
│
├── README.md
├── ARCHITECTURE.md
├── CONFIGURATION.md
├── API.md
├── DEVELOPMENT.md
├── SSI_ALGORITHM.md
├── POLYMARKET.md
├── BACKTESTING.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── app/
│   ├── main.py
│   ├── config.py
│
│   ├── api/
│   │   ├── dashboard.py
│   │   ├── tickers.py
│   │   ├── sentiment.py
│   │   ├── polymarket.py
│   │   ├── market.py
│   │   ├── signals.py
│   │   └── history.py
│
│   ├── collectors/
│   │   ├── base.py
│   │   ├── twikit_provider.py
│   │   ├── polymarket_provider.py
│   │   ├── news_provider.py
│   │   └── market_provider.py
│
│   ├── social/
│   │   ├── analyzer.py
│   │   ├── classifier.py
│   │   ├── weighting.py
│   │   └── relevance.py
│
│   ├── prediction/
│   │   ├── analyzer.py
│   │   ├── probability.py
│   │   ├── liquidity.py
│   │   └── quality.py
│
│   ├── catalysts/
│   │   ├── detector.py
│   │   └── categories.py
│
│   ├── technical/
│   │   ├── indicators.py
│   │   └── scorer.py
│
│   ├── scoring/
│   │   ├── social.py
│   │   ├── prediction.py
│   │   ├── news.py
│   │   ├── momentum.py
│   │   ├── fundamentals.py
│   │   ├── risk.py
│   │   ├── ssi.py
│   │   └── signal.py
│
│   ├── divergence/
│   │   └── detector.py
│
│   ├── database/
│   │   ├── connection.py
│   │   ├── models.py
│   │   └── repository.py
│
│   ├── jobs/
│   │   ├── collect_social.py
│   │   ├── collect_polymarket.py
│   │   ├── collect_news.py
│   │   ├── collect_market.py
│   │   ├── calculate_scores.py
│   │   ├── calculate_divergences.py
│   │   └── daily_snapshot.py
│
│   ├── ml/
│   │   ├── features.py
│   │   ├── train.py
│   │   ├── predict.py
│   │   └── backtest.py
│
│   └── cli/
│       └── commands.py
│
├── frontend/
│   ├── package.json
│   └── src/
│
├── tests/
│
└── data/
```

---

# 11. X DATA SOURCE

## Provider

Twikit será el proveedor inicial.

IMPORTANTE:

Twikit debe estar completamente encapsulado.

Únicamente:

```text
collectors/twikit_provider.py
```

debe conocer Twikit.

El resto de la aplicación utilizará:

```python
XProvider
```

---

# 12. X PROVIDER INTERFACE

```python
class XProvider:

    async def search(
        self,
        query: str,
        max_results: int = 100
    ) -> list[SocialPost]:
        ...
```

Implementación inicial:

```text
TwikitProvider
```

Futuras:

```text
OfficialXProvider
AlternativeXProvider
MockXProvider
```

---

# 13. X QUERIES

Las consultas deben ser configurables.

ASTS:

```text
$ASTS
"AST SpaceMobile"
```

RKLB:

```text
$RKLB
"Rocket Lab"
"Neutron"
```

SATL:

```text
$SATL
"Satellogic"
```

SPCE:

```text
$SPCE
"Virgin Galactic"
```

SPCX:

```text
$SPCX
"SpaceX"
```

---

# 14. X TIME WINDOW

El análisis principal utilizará:

```text
NOW - 24 HOURS
```

No utilizar:

```text
current calendar day
```

Guardar:

```text
created_at
collected_at
analysis_timestamp
```

---

# 15. X DEDUPLICATION

La clave primaria de deduplicación:

```text
tweet_id
```

Una publicación encontrada mediante varias búsquedas debe almacenarse una sola vez.

---

# 16. SOCIAL POST MODEL

```text
SocialPost
-----------
id
external_id
ticker
created_at
collected_at
username
text
url
likes
reposts
replies
views
sentiment_score
sentiment_label
sentiment_confidence
relevance_score
engagement_score
recency_weight
catalyst
catalyst_direction
catalyst_importance
```

---

# 17. SENTIMENT MODEL

Score:

```text
-1.0 ... +1.0
```

Interpretación:

```text
-1.00 = extremely bearish
 0.00 = neutral
+1.00 = extremely bullish
```

Thresholds iniciales:

```text
>= +0.20 → BULLISH
<= -0.20 → BEARISH
otherwise → NEUTRAL
```

---

# 18. NLP

Utilizar inicialmente un modelo especializado en lenguaje financiero.

Preferencia:

```text
FinBERT
```

Crear abstracción:

```python
class SentimentClassifier:

    def analyze(self, text: str) -> SentimentResult:
        ...
```

---

# 19. SENTIMENT CONFIDENCE

Cada clasificación debe incluir:

```text
0–1
```

Ejemplo:

```json
{
  "score": 0.72,
  "label": "BULLISH",
  "confidence": 0.91
}
```

---

# 20. RELEVANCE

No todo tweet que menciona un ticker es relevante.

Crear:

```text
relevance_score
```

Rango:

```text
0–1
```

Threshold:

```text
0.40
```

Posts inferiores pueden descartarse del cálculo principal.

---

# 21. ENGAGEMENT

Considerar:

- likes;
- reposts;
- replies;
- views.

Usar normalización logarítmica.

Ejemplo conceptual:

```text
engagement =
log1p(likes)
+
2 * log1p(reposts)
+
1.5 * log1p(replies)
+
log1p(views)
```

Normalizar posteriormente a 0–1.

---

# 22. RECENCY WEIGHT

Utilizar decay temporal:

```text
weight = exp(-lambda * age_hours)
```

Los parámetros deben ser configurables.

---

# 23. SOCIAL SCORE

Inicial:

```text
Sentiment       50%
Engagement      20%
Relevance       15%
Catalyst        10%
Recency          5%
```

Resultado:

```text
0–100
```

---

# 24. SOCIAL SENTIMENT MOMENTUM

Calcular:

```text
SSS_current
SSS_previous
```

y:

```text
SSS Momentum =
current - previous
```

También:

```text
1D
3D
5D
```

cuando exista histórico.

---

# 25. POLYMARKET

Polymarket será tratado como una fuente de:

> Prediction Market Intelligence

No debe ser tratado simplemente como "sentiment".

---

# 26. CONCEPTO POLYMARKET

La variable principal será:

```text
market_probability
```

Por ejemplo:

```text
YES = 0.72
```

significa aproximadamente:

```text
72%
```

de probabilidad implícita según el mercado.

---

# 27. IMPORTANTE: NO ASUMIR MERCADOS

El sistema no debe asumir que existe un mercado Polymarket para cada ticker.

Puede existir:

```text
ASTS-specific market
```

o:

```text
SpaceX event
NASA event
launch event
regulatory event
contract event
```

sin existir un mercado directo sobre la acción.

---

# 28. EVENT MAPPING

Crear una capa:

```text
Event → Companies
```

Ejemplo:

```text
EVENT:
SpaceX launch succeeds

RELATED:
SPCX
ASTS
RKLB
```

La relación debe poder configurarse.

---

# 29. POLYMARKET PROVIDER

Crear:

```python
class PredictionMarketProvider:

    async def get_markets(
        self,
        query: str | None = None
    ) -> list[PredictionMarket]:
        ...

    async def get_market(
        self,
        market_id: str
    ) -> PredictionMarket:
        ...

    async def get_history(
        self,
        market_id: str
    ) -> list[MarketProbabilityPoint]:
        ...
```

---

# 30. PREDICTION MARKET MODEL

```text
PredictionMarket
----------------
id
external_id
title
description
category
status
created_at
end_date
resolution_date
yes_probability
no_probability
volume
liquidity
spread
url
```

---

# 31. POLYMARKET PROBABILITY

Guardar:

```text
current_probability
previous_probability
probability_change_1h
probability_change_6h
probability_change_24h
```

La variación es tan importante como el valor absoluto.

---

# 32. EJEMPLO

```text
Yesterday:
YES = 54%

Today:
YES = 71%
```

Entonces:

```text
probability_change_24h = +17 percentage points
```

Esto debe ser considerado un movimiento significativo.

---

# 33. PREDICTION MARKET MOMENTUM

Calcular:

```text
PM Momentum
```

basado en:

```text
probability_change
volume_change
liquidity_change
```

---

# 34. MARKET QUALITY SCORE

No confiar ciegamente en mercados pequeños.

Crear:

```text
Market Quality Score
```

Rango:

```text
0–100
```

Componentes:

```text
Liquidity
Volume
Spread
Activity
Time to Resolution
Market Stability
Historical Calibration
```

---

# 35. MARKET QUALITY RULE

Si:

```text
Market Quality < 30
```

entonces:

```text
Prediction Market Weight = 0
```

El mercado puede mostrarse en UI pero no debe influir significativamente en SSI.

---

# 36. PREDICTION MARKET SCORE

El PMS debe representar la información proveniente de prediction markets.

Componentes iniciales:

```text
Probability Level       40%
Probability Momentum    35%
Market Quality          15%
Volume/Liquidity        10%
```

Resultado:

```text
0–100
```

---

# 37. POLYMARKET CONFIDENCE

PMS debe tener una confianza independiente.

Ejemplo:

```text
PMS = 82
Confidence = 91%
```

si el mercado es líquido.

Otro:

```text
PMS = 82
Confidence = 32%
```

si existe poca liquidez.

---

# 38. EVENT IMPACT

Un mercado Polymarket puede estar relacionado indirectamente con varias empresas.

Cada relación debe tener:

```text
impact_score
```

Rango:

```text
-1 ... +1
```

Ejemplo:

```text
SpaceX successful launch

ASTS = +0.20
RKLB = +0.30
SPCE = +0.05
```

Estos mappings deben ser configurables y posteriormente aprendibles.

---

# 39. NEWS ENGINE

Crear:

```python
class NewsProvider:
    async def search(...):
        ...
```

La implementación concreta queda desacoplada.

---

# 40. NEWS MODEL

```text
NewsItem
--------
id
ticker
published_at
title
summary
source
url
sentiment
confidence
relevance
catalyst
importance
```

---

# 41. CATALYST ENGINE

Categorías:

```text
EARNINGS
REVENUE
GUIDANCE
CONTRACT
GOVERNMENT_CONTRACT
PARTNERSHIP
LAUNCH
LAUNCH_DELAY
SATELLITE_DEPLOYMENT
PRODUCT
REGULATORY
FINANCING
DILUTION
CAPITAL_RAISE
ANALYST_UPGRADE
ANALYST_DOWNGRADE
SHORT_INTEREST
INSIDER
ACQUISITION
TECHNICAL_MILESTONE
COMPETITOR
MACRO
OTHER
```

Cada catalizador:

```text
direction:
BULLISH
BEARISH
NEUTRAL
```

e:

```text
importance:
LOW
MEDIUM
HIGH
CRITICAL
```

---

# 42. MARKET DATA

El sistema debe soportar:

```text
5m
15m
1h
1d
```

MVP:

```text
1d
```

---

# 43. TECHNICAL INDICATORS

Calcular:

```text
Price
EMA200
RSI14
Bollinger Bands 20/2
MACD
Volume
Volume MA20
Volume Ratio
ATR
```

---

# 44. TECHNICAL SCORE

Inicial:

```text
EMA200       10
RSI          10
Bollinger    10
MACD          5
Volume        5
----------------
TOTAL        40
```

---

# 45. RSI

Reglas iniciales:

```text
50–70 = bullish
45–50 = moderately bullish
70–75 = bullish but extended
<45   = weak
>75   = overextended
```

No considerar:

```text
RSI > 70 = automatically bearish
```

---

# 46. MOMENTUM SCORE

Considerar:

```text
1D return
3D return
5D return
distance from EMA200
volume ratio
ATR
```

Normalizar:

```text
0–100
```

---

# 47. RISK SCORE

Variables:

```text
Beta
ATR
Volatility
Drawdown
Short Interest
Liquidity
```

IMPORTANTE:

```text
High Risk ≠ Bearish
```

Una acción puede ser:

```text
SSI = 85
Risk = HIGH
```

---

# 48. FUNDAMENTAL SCORE

Variables futuras:

```text
Revenue Growth
Earnings Surprise
Guidance
Cash
Debt
Profitability
Dilution
Analyst Revisions
```

Datos faltantes:

```text
NULL
```

Nunca inventar.

---

# 49. SPACE SENTIMENT INDEX

El SSI original se amplía.

Para evitar confusión entre sentimiento y market intelligence, el sistema puede utilizar:

```text
SSI = Space Sentiment Index
SMI = Space Market Intelligence Index
```

Se recomienda utilizar:

### SSI

para sentimiento social.

### SMI

para el score integral.

---

# 50. SPACE SENTIMENT INDEX

```text
SSI = Social Sentiment
```

Resultado:

```text
0–100
```

---

# 51. SPACE MARKET INTELLIGENCE INDEX

El índice integral será:

```text
Social Sentiment
+
Prediction Markets
+
News/Catalysts
+
Market Momentum
+
Fundamentals
+
Risk
```

---

# 52. SMI INITIAL WEIGHTS

MVP ampliado:

```text
Social Sentiment       30%
Prediction Markets     15%
News/Catalysts         20%
Market/Momentum        20%
Fundamentals           10%
Risk                    5%
```

Total:

```text
100%
```

---

# 53. ADAPTIVE WEIGHTS

No todos los componentes estarán siempre disponibles.

Ejemplo:

```text
Social = available
Prediction = unavailable
News = available
Market = available
Fundamental = available
Risk = available
```

Los pesos disponibles deben redistribuirse proporcionalmente.

Nunca utilizar silenciosamente:

```text
missing = 50
```

---

# 54. POLYMARKET WEIGHT ADJUSTMENT

El peso efectivo del prediction market depende de:

```text
Market Quality
```

Ejemplo:

```text
Base weight = 15%

Quality = 90
Effective weight ≈ 15%

Quality = 50
Effective weight ≈ 7.5%

Quality = 20
Effective weight = 0%
```

La fórmula exacta debe ser configurable.

---

# 55. CONFIDENCE

Confidence es independiente de SMI.

Considerar:

```text
Social data quantity
Social data quality
Prediction market quality
News availability
Technical availability
Fundamental availability
Source agreement
Sentiment dispersion
```

Resultado:

```text
0–100%
```

---

# 56. DATA QUALITY

Separar:

```text
Confidence
```

de:

```text
Data Quality
```

Ejemplo:

```text
SMI = 84

Confidence = 72%

Data Quality = 91%
```

---

# 57. SOURCE AGREEMENT

Calcular el grado de coincidencia:

```text
X
Polymarket
News
Price
```

Ejemplo:

```text
X             +0.80
Polymarket    +0.72
News          +0.60
Price         +0.55
```

High Agreement.

---

# 58. SOURCE DISAGREEMENT

Ejemplo:

```text
X             +0.80
Polymarket    +0.70
Price         -0.40
```

Esto no debe promediarse y desaparecer.

Debe generar:

```text
DIVERGENCE
```

---

# 59. DIVERGENCE ENGINE

El sistema debe detectar:

```text
X ↔ Polymarket
X ↔ Price
Polymarket ↔ Price
X ↔ Polymarket ↔ Price
```

---

# 60. BULLISH DIVERGENCE

Ejemplo:

```text
X sentiment       ↑
Polymarket        ↑
Price             ↓
```

Interpretación:

```text
Bullish divergence
```

---

# 61. BEARISH DIVERGENCE

```text
X sentiment       ↓
Polymarket        ↓
Price             ↑
```

Interpretación:

```text
Bearish divergence
```

---

# 62. STRONG BULLISH CONFIRMATION

```text
X                   ↑
Polymarket          ↑
News                bullish
Price               ↑
Volume              ↑
```

Esto aumenta:

```text
Signal Confidence
```

---

# 63. STRONG BEARISH CONFIRMATION

```text
X                   ↓
Polymarket          ↓
News                bearish
Price               ↓
Volume              ↑
```

Aumenta:

```text
Bearish confidence
```

---

# 64. EARLY REVERSAL

Detectar:

```text
X                 bearish
Polymarket        bullish
Price             stabilizing
```

o:

```text
X                 bullish
Polymarket        bearish
Price             stabilizing
```

Marcar:

```text
EARLY REVERSAL WATCH
```

No convertir automáticamente en BUY.

---

# 65. SIGNAL ENGINE

Inicial:

```text
0–34     STRONG AVOID
35–49    AVOID
50–64    HOLD
65–74    WATCH
75–84    BUY
85–100   STRONG BUY
```

Estos thresholds deben ser configurables y posteriormente optimizados mediante backtesting.

---

# 66. SIGNAL ≠ SENTIMENT

Ejemplo:

```text
SSI = 90
Technical = 20
```

No necesariamente:

```text
BUY
```

Debe existir:

```text
BULLISH SENTIMENT
BUT WEAK TECHNICAL CONFIRMATION
```

---

# 67. OVEREXTENSION

No generar automáticamente:

```text
STRONG BUY
```

cuando:

```text
RSI > 75
```

o:

```text
price move > configured threshold
```

Marcar:

```text
OVEREXTENDED
```

---

# 68. EXPLANATION ENGINE

Toda señal debe incluir explicación.

Ejemplo:

```text
ASTS — BUY

Reasons:
+ Social sentiment increased 9%
+ 71% of relevant posts are bullish
+ Prediction market probability increased 12pp
+ Price above EMA200
+ Volume 42% above average

Risks:
- RSI elevated
- High volatility
```

Nunca inventar razones.

---

# 69. DASHBOARD

La pantalla principal:

```text
SPACE MARKET INTELLIGENCE

Last Update
Market Status

Ticker
SMI
SSI
PMS
Market Score
Signal
Confidence
```

Ejemplo:

```text
ASTS   82   78   81   76   BUY
RKLB   69   74   63   70   WATCH
SATL   58   61   --   55   HOLD
SPCE   46   43   --   49   AVOID
SPCX   --   --   58   --   N/A
```

---

# 70. TICKER DETAIL

Debe mostrar:

```text
Ticker
Company
SMI
SSI
PMS
Signal
Confidence
Data Quality
```

Después:

```text
Score Breakdown
```

Después:

```text
Social
Prediction Markets
News
Technical
Fundamentals
Risk
```

---

# 71. SOCIAL PANEL

Mostrar:

```text
Bullish %
Neutral %
Bearish %

Total posts
Relevant posts

Engagement

SSI
SSI Momentum
```

---

# 72. POLYMARKET PANEL

Mostrar:

```text
Related Markets

Market
Probability
Δ1h
Δ6h
Δ24h
Volume
Liquidity
Spread
Quality
```

Ejemplo:

```text
Space launch event

YES       72%
Δ24h      +14pp
Volume    $2.4M
Liquidity High
Quality   91
```

---

# 73. EVENT IMPACT PANEL

Mostrar:

```text
Event
Probability
Related companies
Expected impact
```

Ejemplo:

```text
Event:
Successful launch

Probability:
72%

Potential impact:

RKLB  +++
ASTS  ++
SPCE  +
SATL  +
```

---

# 74. DIVERGENCE PANEL

Mostrar:

```text
ACTIVE DIVERGENCES
```

Ejemplo:

```text
RKLB

X              BULLISH ↑
Polymarket     BULLISH ↑
Price          BEARISH ↓

Potential bullish divergence
Confidence: 72%
```

---

# 75. HISTORICAL CHART

Mostrar:

```text
Price
SSI
SMI
PMS
Social Score
```

con posibilidad de activar/desactivar cada serie.

---

# 76. FRESHNESS

Mostrar:

```text
X data: 5 min ago
Polymarket: 2 min ago
News: 10 min ago
Market: 1 min ago
SMI: 3 min ago
```

---

# 77. DATABASE

Tablas:

```text
tickers
social_posts
prediction_markets
prediction_market_snapshots
prediction_market_events
news_items
catalysts
market_snapshots
technical_snapshots
score_snapshots
ssi_snapshots
smi_snapshots
divergences
signals
job_runs
```

---

# 78. PREDICTION MARKET SNAPSHOT

```text
prediction_market_snapshots
----------------------------
id
market_id
timestamp
yes_probability
no_probability
volume
liquidity
spread
quality_score
probability_change_1h
probability_change_6h
probability_change_24h
```

---

# 79. SMI SNAPSHOT

```text
smi_snapshots
-------------
id
ticker
timestamp

social_score
prediction_score
news_score
momentum_score
fundamental_score
risk_score

ssi
smi

confidence
data_quality

signal

price
volume
```

---

# 80. DIVERGENCE MODEL

```text
divergences
-----------
id
ticker
timestamp
type
source_a
source_b
source_c
direction
strength
confidence
description
resolved_at
```

Tipos:

```text
BULLISH_DIVERGENCE
BEARISH_DIVERGENCE
BULLISH_CONFIRMATION
BEARISH_CONFIRMATION
EARLY_REVERSAL
```

---

# 81. JOBS

Jobs independientes:

```text
collect_social
collect_polymarket
collect_news
collect_market
calculate_sentiment
calculate_prediction_scores
calculate_technical
calculate_smi
calculate_divergences
generate_signals
daily_snapshot
```

---

# 82. JOB FAILURE ISOLATION

Un fallo de Polymarket:

```text
must NOT stop:
X
Market
News
```

Un fallo de X:

```text
must NOT stop:
Polymarket
Market
News
```

---

# 83. SCHEDULER

Durante mercado:

```text
every 30–60 minutes
```

configurable.

Prediction markets:

```text
more frequent updates may be enabled
```

si existe suficiente utilidad.

Daily snapshot:

```text
after market close
```

---

# 84. CLI

```bash
python -m app.cli collect-social
```

```bash
python -m app.cli collect-polymarket
```

```bash
python -m app.cli collect-news
```

```bash
python -m app.cli collect-market
```

```bash
python -m app.cli calculate-scores
```

```bash
python -m app.cli calculate-divergences
```

```bash
python -m app.cli calculate-smi
```

```bash
python -m app.cli analyze ASTS
```

```bash
python -m app.cli snapshot
```

---

# 85. API

```text
GET /api/health

GET /api/tickers

GET /api/dashboard

GET /api/tickers/{ticker}

GET /api/tickers/{ticker}/social

GET /api/tickers/{ticker}/prediction-markets

GET /api/tickers/{ticker}/news

GET /api/tickers/{ticker}/technical

GET /api/tickers/{ticker}/history

GET /api/tickers/{ticker}/divergences

GET /api/tickers/{ticker}/signal
```

---

# 86. HEALTH API

```json
{
  "status": "ok",
  "database": "ok",
  "x_provider": "ok",
  "polymarket_provider": "ok",
  "market_provider": "ok",
  "news_provider": "ok",
  "last_update": "2026-08-19T19:00:00Z"
}
```

---

# 87. ERROR HANDLING

Provider failures deben registrar:

```text
provider_status
error
timestamp
retry_count
```

No convertir errores en datos neutrales.

Nunca:

```text
provider failed → score = 50
```

---

# 88. NULL POLICY

Si no existe información:

```text
NULL
```

No:

```text
0
```

y tampoco:

```text
50
```

porque ambos podrían interpretarse como datos reales.

---

# 89. RATE LIMITING

Implementar:

```text
retry
exponential backoff
jitter
rate limiting
```

Configuración:

```text
MAX_REQUESTS_PER_MINUTE
MAX_RETRIES
BACKOFF_FACTOR
```

---

# 90. CACHE

Deduplicar y cachear:

```text
tweet_id
news_id
market_id
```

Evitar requests innecesarios.

---

# 91. SECURITY

Nunca almacenar:

```text
passwords
API keys
cookies
tokens
```

en Git.

Usar:

```text
.env
```

y:

```text
.env.example
```

---

# 92. LOGGING

Ejemplo:

```text
INFO Starting social collection
INFO ASTS posts=182
INFO ASTS relevant=121
INFO Sentiment completed
INFO Polymarket markets=14
INFO Prediction score calculated
INFO SMI ASTS=78.4
INFO Signal=BUY
```

---

# 93. AUDITABILITY

Cada SMI debe poder explicarse.

Ejemplo:

```text
SMI = 81

Social             86
Prediction Market  79
News               82
Momentum            75
Fundamental         80
Risk                55
```

La aplicación debe permitir reconstruir cómo se obtuvo el valor.

---

# 94. NO FABRICATION RULE

El sistema nunca debe inventar:

- tweets;
- precios;
- probabilidades;
- noticias;
- volumen;
- liquidez;
- fundamentals;
- scores derivados de datos inexistentes.

Si no existe:

```text
NULL
```

---

# 95. LOOK-AHEAD BIAS

Una señal solo puede utilizar información disponible en el timestamp de la señal.

Nunca utilizar:

```text
future tweet
future news
future price
future probability
```

---

# 96. BACKTESTING

Guardar todos los snapshots necesarios para responder:

> ¿Qué ocurrió después de una señal?

Evaluar:

```text
1 hour
1 day
3 days
5 days
```

cuando los datos estén disponibles.

---

# 97. BACKTEST METRICS

```text
Win Rate
Average Return
Median Return
Profit Factor
Expectancy
Max Drawdown
Sharpe
Sortino
Average Holding Time
```

Por:

```text
ticker
signal
SMI range
divergence type
prediction-market availability
```

---

# 98. ESPECIAL INTERÉS: POLYMARKET VALUE

El backtesting debe responder específicamente:

> ¿Agregar Polymarket mejora el modelo?

Comparar:

```text
MODEL A

X + Market
```

contra:

```text
MODEL B

X + Market + Polymarket
```

Y evaluar:

```text
return
win rate
profit factor
drawdown
Sharpe
```

---

# 99. ABLATION TESTING

Realizar pruebas:

```text
Without X
Without Polymarket
Without News
Without Technical
Without Fundamentals
```

Esto permitirá saber qué componente realmente agrega valor.

---

# 100. MACHINE LEARNING

NO implementar inicialmente.

Primero acumular histórico.

Features futuras:

```text
SSI
SMI
SSI momentum
SMI momentum

Social sentiment
Bullish ratio
Bearish ratio

Prediction probability
Probability change
Prediction market quality
Prediction market volume

News score
Catalyst score

RSI
EMA distance
Bollinger position
MACD
Volume ratio
ATR

Beta
Volatility

SPY return
QQQ return
Sector return
```

---

# 101. ML TARGETS

```text
return_1d
return_3d
return_5d
```

y:

```text
direction_1d
direction_3d
direction_5d
```

También:

```text
P(return > +3%)
```

---

# 102. ML ALGORITHMS

Evaluar:

```text
Logistic Regression
Random Forest
XGBoost
LightGBM
```

No seleccionar modelo por accuracy únicamente.

---

# 103. ML OBJECTIVE

El objetivo no es predecir exactamente:

```text
future_price
```

sino:

```text
probability of positive return
```

y:

```text
expected return
```

---

# 104. WALK-FORWARD VALIDATION

```text
TRAIN
 ↓
VALIDATE
 ↓
TEST
 ↓
WALK FORWARD
```

Nunca optimizar utilizando todo el histórico.

---

# 105. ALERTS

Fase futura:

```text
SMI > 75
SMI crosses 75
SSI Momentum > +3
SSI Momentum < -3

PMS probability change > threshold

Bullish divergence
Bearish divergence

Strong Buy
Strong Avoid

Major catalyst
```

Canales:

```text
Telegram
Email
Discord
Webhook
```

---

# 106. MARKET EVENT INTELLIGENCE

El sistema debe poder relacionar un evento de prediction market con varias compañías.

Modelo:

```text
Event
 ↓
Probability
 ↓
Impact Mapping
 ↓
Companies
 ↓
SMI adjustment
```

Ejemplo:

```text
Event:
Major launch success

Probability:
82%

Impact:

RKLB +0.30
ASTS +0.20
SATL +0.10
SPCE +0.05
```

Los mappings inicialmente serán manuales.

Posteriormente podrán aprenderse mediante histórico.

---

# 107. SECTOR SENTIMENT

Además del análisis individual, calcular:

```text
SPACE SECTOR SENTIMENT
```

Agregando:

```text
ASTS
RKLB
SATL
SPCE
SPCX
```

Ponderación:

```text
equal weight
```

inicialmente.

Posteriormente:

```text
market cap
liquidity
volume
```

pueden utilizarse.

---

# 108. SECTOR ROTATION

Detectar:

```text
Sector SMI ↑
ASTS ↑
RKLB ↓
SPCE ↑
SATL ↓
```

Esto puede indicar:

```text
capital rotation
```

y debe visualizarse.

---

# 109. SPACE SENTIMENT MAP

Dashboard futuro:

```text
             BULLISH
                ↑
                │
        ASTS    │
                │
        RKLB    │
                │
────────────────┼────────────
                │
        SATL    │
                │
        SPCE    │
                │
                ↓
             BEARISH
```

---

# 110. DAILY REPORT

El sistema debe poder generar automáticamente:

```text
SPACE MARKET DAILY REPORT
```

Contenido:

```text
Sector sentiment
Top bullish
Top bearish
Largest sentiment change
Largest prediction-market change
Major catalysts
Divergences
Price movers
Volume anomalies
Signals
Risks
```

---

# 111. EJEMPLO DE DAILY REPORT

```text
SPACE MARKET INTELLIGENCE
19 AUG 2026

Sector:
NEUTRAL / BEARISH

Top Bullish:
ASTS

Largest SSI increase:
SATL +7

Largest Prediction Market move:
RKLB-related event +14pp

Strongest bullish divergence:
RKLB

Strongest bearish divergence:
SPCE

Signals:

ASTS   BUY
RKLB   WATCH
SATL   HOLD
SPCE   AVOID
SPCX   N/A
```

---

# 112. TESTING

Tests obligatorios:

```text
test_sentiment
test_relevance
test_engagement
test_social_score

test_prediction_probability
test_prediction_quality
test_prediction_score

test_technical_score
test_momentum

test_smi
test_confidence
test_data_quality

test_divergence
test_signal

test_missing_data
test_provider_failure
test_deduplication
```

---

# 113. TEST DE DIVERGENCE

```python
def test_bullish_divergence():

    result = detect_divergence(
        social=0.80,
        prediction=0.75,
        price=-0.40
    )

    assert result.type == "BULLISH_DIVERGENCE"
```

---

# 114. TEST DE POLYMARKET QUALITY

```python
def test_low_quality_market():

    quality = calculate_market_quality(
        liquidity=low,
        volume=low,
        spread=high
    )

    assert quality < 30
```

---

# 115. TEST DE WEIGHT ADJUSTMENT

```python
def test_prediction_weight_disabled():

    effective_weight = calculate_prediction_weight(
        base_weight=0.15,
        quality=20
    )

    assert effective_weight == 0
```

---

# 116. TEST DE MISSING DATA

```python
def test_missing_prediction_market():

    result = calculate_smi(
        social=80,
        prediction=None,
        news=70,
        momentum=75,
        fundamentals=80,
        risk=60
    )

    assert result is not None
```

---

# 117. DEPLOYMENT

Preparar Dockerfile.

MVP:

```text
Backend
Frontend
SQLite
```

No requiere inicialmente:

```text
Kubernetes
Kafka
Redis cluster
Microservices
```

---

# 118. FUTURE DATABASE

Migración:

```text
SQLite
   ↓
PostgreSQL
```

Debe realizarse sin modificar la lógica de negocio.

---

# 119. OBSERVABILITY

Guardar:

```text
job_runs
provider_status
last_success
last_failure
records_processed
processing_time
```

Dashboard administrativo futuro:

```text
X Provider       OK
Polymarket       OK
Market Data      OK
News             ERROR
```

---

# 120. CONFIGURATION

Ejemplo:

```yaml
tickers:
  - ASTS
  - RKLB
  - SATL
  - SPCE
  - SPCX

social:
  lookback_hours: 24
  relevance_threshold: 0.40

prediction_market:
  enabled: true
  min_quality: 30
  lookback_hours: 24

technical:
  rsi_period: 14
  ema_period: 200
  bollinger_period: 20
  bollinger_std: 2
  volume_period: 20

scheduler:
  intraday_minutes: 60
```

---

# 121. WEIGHT CONFIGURATION

```yaml
weights:
  social: 0.30
  prediction_market: 0.15
  news: 0.20
  momentum: 0.20
  fundamentals: 0.10
  risk: 0.05
```

Nunca hardcodear estos valores en múltiples módulos.

---

# 122. IMPORTANT ARCHITECTURAL RULE

Todos los scores deben ser independientes.

No hacer:

```text
Polymarket → directly modifies price
```

ni:

```text
X → directly generates BUY
```

Cada fuente produce información.

Después:

```text
Score Engine
```

combina.

---

# 123. SOURCE INDEPENDENCE

El sistema debe intentar identificar cuando dos fuentes probablemente están reaccionando a la misma noticia.

Ejemplo:

```text
News
 ↓
X posts
 ↓
Polymarket
 ↓
Price
```

No asumir que son cuatro señales independientes.

Esto será importante para futuras versiones.

---

# 124. INFORMATION CASCADE

Futuro módulo:

```text
Information Cascade Detector
```

Detectar:

```text
NEWS
 ↓
X
 ↓
POLYMARKET
 ↓
PRICE
```

y estimar:

```text
information propagation speed
```

---

# 125. LEAD-LAG ANALYSIS

Con suficiente histórico, estudiar:

```text
Does X lead price?
Does Polymarket lead price?
Does price lead X?
Does Polymarket lead X?
```

Esto debe ser empírico.

No asumir de antemano que Polymarket es mejor.

---

# 126. CORE RESEARCH QUESTION

Una de las preguntas principales del proyecto será:

> ¿Qué fuente detecta antes los cambios relevantes del sector espacial?

Comparar:

```text
X
Polymarket
News
Price
```

---

# 127. SECOND RESEARCH QUESTION

> ¿Polymarket aporta información incremental respecto de X?

Comparar:

```text
Model A:
X + Market

Model B:
X + Market + Polymarket
```

Si Model B no mejora:

```text
performance
```

el peso de Polymarket debe reducirse.

---

# 128. THIRD RESEARCH QUESTION

> ¿Las divergencias X ↔ Polymarket ↔ Price anticipan reversals?

Esto será uno de los experimentos más importantes del proyecto.

---

# 129. ROADMAP

## V1 — MVP

```text
X / Twikit
Market Data
Sentiment
Technical Indicators
Social Score
Technical Score
SSI
Dashboard
```

---

## V1.1

```text
News
Catalysts
Daily Reports
Historical charts
```

---

## V1.2

```text
Polymarket
Prediction Market Score
Market Quality
Event Mapping
```

---

## V1.3

```text
Divergence Engine
Source Agreement
Confidence
Data Quality
```

---

## V2

```text
Backtesting
Signal tracking
Alerts
Daily automation
```

---

## V3

```text
ML
Lead/Lag
Event impact learning
Adaptive weights
```

---

## V4

```text
Sector expansion
More stocks
Crypto
Integration with existing trading platform
```

---

# 130. MVP ACCEPTANCE CRITERIA

El MVP ampliado se considera funcional cuando:

- [ ] Backend inicia.
- [ ] Frontend inicia.
- [ ] SQLite funciona.
- [ ] Tickers configurables.
- [ ] X provider funciona.
- [ ] Tweets son recolectados.
- [ ] Tweets son deduplicados.
- [ ] Sentiment funciona.
- [ ] Social Score funciona.
- [ ] Market data funciona.
- [ ] Technical Score funciona.
- [ ] SSI funciona.
- [ ] Polymarket provider funciona.
- [ ] Markets pueden almacenarse.
- [ ] Probability changes se calculan.
- [ ] Market Quality se calcula.
- [ ] Prediction Market Score funciona.
- [ ] SMI funciona.
- [ ] Divergences funcionan.
- [ ] Signal funciona.
- [ ] Confidence funciona.
- [ ] Data Quality funciona.
- [ ] Dashboard funciona.
- [ ] Histórico funciona.
- [ ] Errores de providers están aislados.
- [ ] No se inventan datos.
- [ ] No existe look-ahead bias.
- [ ] Tests principales pasan.

---

# 131. DEFINITION OF DONE

El sistema estará listo cuando pueda ejecutar:

```bash
python -m app.cli collect-social
```

```bash
python -m app.cli collect-polymarket
```

```bash
python -m app.cli collect-market
```

```bash
python -m app.cli calculate-smi
```

y abrir:

```text
http://localhost:8000
```

para visualizar:

```text
ASTS
RKLB
SATL
SPCE
SPCX
```

con:

```text
SSI
SMI
Social Score
Prediction Market Score
Market Score
News Score
Momentum
Signal
Confidence
Data Quality
Divergences
```

---

# 132. PRINCIPIOS FUNDAMENTALES DEL PROYECTO

## 1. Measure before predicting

Primero medir.

Después predecir.

---

## 2. No source is always right

X puede equivocarse.

Polymarket puede equivocarse.

El precio puede equivocarse temporalmente.

---

## 3. Independent confirmation is valuable

Cuando múltiples fuentes coinciden:

```text
confidence ↑
```

---

## 4. Divergence is information

Cuando las fuentes divergen:

```text
do not average it away
```

Debe analizarse explícitamente.

---

## 5. Money matters

Prediction markets agregan una dimensión diferente:

```text
opinion
+
capital at risk
```

---

## 6. Quality matters

Una predicción de un mercado ilíquido no tiene el mismo valor que una de un mercado altamente líquido.

---

## 7. Historical validation is mandatory

Ningún score debe considerarse útil simplemente porque "parece lógico".

Debe probarse.

---

## 8. No fabrication

Nunca inventar información faltante.

---

## 9. No look-ahead

Nunca utilizar información futura.

---

## 10. Explainability

Toda señal debe responder:

> Why?

---

# 133. CONCEPTO FINAL

El producto final NO debe ser:

```text
Twitter Sentiment Bot
```

ni:

```text
Polymarket Tracker
```

Debe ser:

# SPACE MARKET INTELLIGENCE ENGINE

Un sistema que intenta detectar:

```text
NARRATIVE
   ↓
EXPECTATIONS
   ↓
CAPITAL
   ↓
PRICE
```

y especialmente detectar cuándo esos elementos:

```text
AGREE
```

o:

```text
DIVERGE
```

---

# 134. HIPÓTESIS CENTRAL DEL PROYECTO

La hipótesis que debe probarse empíricamente es:

> Los cambios coordinados en sentimiento social, probabilidades de prediction markets y comportamiento del precio pueden proporcionar información incremental sobre el comportamiento futuro de acciones del sector espacial.

Esta es una **hipótesis de investigación**, no una premisa asumida como verdadera.

---

# 135. OBJETIVO DE INVESTIGACIÓN

Determinar mediante datos históricos si:

```text
X
+
Polymarket
+
News
+
Market Data
```

pueden generar una señal con capacidad predictiva superior a:

```text
Market Data alone
```

y si:

```text
X + Market
```

es mejor o peor que:

```text
X + Polymarket + Market
```

---

# 136. VISIÓN A LARGO PLAZO

La aplicación debería evolucionar desde:

```text
Data Collection
```

hacia:

```text
Market Intelligence
```

y finalmente:

```text
Predictive Intelligence
```

Pipeline:

```text
COLLECT
   ↓
NORMALIZE
   ↓
ANALYZE
   ↓
SCORE
   ↓
COMPARE SOURCES
   ↓
DETECT DIVERGENCES
   ↓
GENERATE SIGNAL
   ↓
TRACK OUTCOME
   ↓
BACKTEST
   ↓
LEARN
   ↓
IMPROVE
```

---

# 137. INSTRUCCIÓN PARA LA IA DE DESARROLLO

Antes de escribir código:

1. Leer toda esta especificación.
2. Identificar todos los módulos.
3. Crear estructura del proyecto.
4. Implementar primero interfaces y modelos.
5. Implementar providers.
6. Implementar persistencia.
7. Implementar scoring.
8. Implementar divergences.
9. Implementar API.
10. Implementar dashboard.
11. Ejecutar tests.
12. Documentar cualquier desviación.

No implementar inicialmente:

- Machine Learning;
- microservicios;
- Kubernetes;
- sistemas distribuidos;
- optimización avanzada;
- trading automático;
- ejecución de órdenes.

El objetivo inicial es construir un sistema de **inteligencia y análisis**, no un sistema de ejecución automática de operaciones.

---

# 138. REGLA FINAL

La aplicación nunca debe responder solamente:

```text
"Bullish"
```

Debe poder responder:

```text
ASTS

SMI: 82
SSI: 87
Prediction Market Score: 76
Market Score: 79

Confidence: 84%

WHY?

+ Social sentiment accelerating
+ Prediction probability increased 11pp
+ Positive catalyst
+ Price above EMA200
+ Volume above average

DIVERGENCES:

None

RISK:

High volatility

SIGNAL:

BUY
```

El valor del proyecto está en explicar **por qué** se llegó a esa conclusión y posteriormente comprobar si esa conclusión tenía valor predictivo real.

---

# END OF SPECIFICATION

Space Market Intelligence Engine
Version 2.0
