# 🚀 Space Market Intelligence Engine (SMIE v2.0)

**Motor cuantitativo multivariable de análisis e inteligencia de mercado para el sector espacial y aeroespacial.**

SMIE sintetiza de forma desacoplada la **narrativa social (X/Twitter)**, las **probabilidades implícitas en Prediction Markets (Polymarket)**, los **catalizadores sectoriales (Google News)** y la **acción técnica del precio (yfinance)** para generar índices no sesgados, señales cuantitativas explicables y detección temprana de divergencias tripartitas.

> 📖 **Documentación de arquitectura y contexto:** Consulta [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) y la especificación [`SPACE_MARKET_INTELLIGENCE_ENGINE_SPEC.md`](SPACE_MARKET_INTELLIGENCE_ENGINE_SPEC.md).

---

## 📐 Métricas Clave

- **`SMI` (Space Market Intelligence Index, 0–100):** Índice integral ponderado maestro con normalización adaptativa dinámica de pesos según disponibilidad y calidad de fuentes.
- **`SSI` (Space Sentiment Index, 0–100):** Mide exclusivamente el sentimiento social puro de X/Twitter con engagement logarítmico, decaimiento temporal, contracción bayesiana para muestras pequeñas ($N < 10$) y detección de negación sintáctica.
- **`PMS` (Prediction Market Score, 0–100):** Probabilidad agregada de éxito de eventos espaciales implícita en Polymarket (con regla de exclusión si `quality_score < 30` y filtrado por matriz de impacto de eventos sectoriales).
- **`Canonical Signals`:** Desacoplamiento estricto entre `base_signal` canónico (`STRONG BUY`, `BUY`, `WATCH`, `HOLD`, `AVOID`, `STRONG AVOID`) y `signal_modifier` (`OVEREXTENDED`, `NO MKT DATA`).
- **`Market Score` (0–100):** Confirmación técnica del precio basada en EMA200, RSI(14) con suavizado Wilder RMA, Bollinger Bands, MACD y ratio de volumen.
- **`Divergence Engine & Risk Hierarchy`:** Detecta desacoples estructurales (ej. *Bullish Divergence: Social/Polymarket Bullish vs. Price Bearish*, *Early Reversal* con $\Delta_{24\text{h}}$ dinámico) y alertas de severidad simétrica (`CRITICAL` para `STRONG BUY`, `STRONG AVOID` y `BEARISH_CONFIRMATION`).

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
  python -m app.cli run-all
  ```
- **Analizar un activo específico con explicaciones "WHY?":**
  ```bash
  python -m app.cli analyze ASTS
  ```
- **Generar el reporte diario del sector espacial:**
  ```bash
  python -m app.cli daily-report
  ```
- **Ejecutar motor de backtesting cuantitativo (Model A vs Model B):**
  ```bash
  python -m app.cli backtest
  ```
- **Ingerir contratos de Polymarket:**
  ```bash
  python -m app.cli collect-polymarket
  ```
- **Evaluar divergencias activas:**
  ```bash
  python -m app.cli calculate-divergences
  ```
- **Ejecutar suite de tests automatizados (58 tests unitarios):**
  ```bash
  python -m pytest tests/ -v
  ```

---

## 🛰️ Universo de Cobertura Inicial
- **ASTS** — AST SpaceMobile
- **RKLB** — Rocket Lab
- **SATL** — Satellogic
- **SPCE** — Virgin Galactic
- **SPCX** — Procure Space ETF / Proxy de Eventos Sectoriales (SpaceX Starship, Artemis, FCC)
