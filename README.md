# 🚀 Space Market Intelligence Engine (SMIE v2.0)

**Motor cuantitativo multivariable de análisis e inteligencia de mercado para el sector espacial y aeroespacial.**

SMIE sintetiza de forma desacoplada la **narrativa social (X/Twitter)**, las **probabilidades implícitas en Prediction Markets (Polymarket)**, los **catalizadores sectoriales (Google News)**, los **factores fundamentales** y la **acción técnica del precio y riesgo (yfinance)** para generar índices cuantitativos no sesgados, señales explicables y detección temprana de divergencias tripartitas.

> 📖 **Documentación de arquitectura y contexto:** Consulta [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) y la especificación [`SPACE_MARKET_INTELLIGENCE_ENGINE_SPEC.md`](SPACE_MARKET_INTELLIGENCE_ENGINE_SPEC.md).

---

## 📐 Métricas Clave

- **`SMI` (Space Market Intelligence Index, 0–100):** Índice integral ponderado maestro con arquitectura multivariable de 6 pilares y normalización adaptativa dinámica de pesos según disponibilidad y calidad de fuentes.
- **`SSI` (Space Sentiment Index, 0–100):** Mide exclusivamente el sentimiento social puro de X/Twitter con engagement logarítmico, decaimiento temporal, contracción bayesiana para muestras pequeñas ($1 \le N < 10$) y exclusión estricta en $N=0$.
- **`PMS` (Prediction Market Score, 0–100):** Probabilidad agregada de éxito de eventos espaciales implícita en Polymarket (con regla de exclusión si `quality_score < 30` o sin mercados activos y filtrado por matriz de impacto de eventos sectoriales).
- **`Prediction Markets Categorization`:** Clasificación y jerarquización de contratos de Polymarket en *🎯 Contratos Directos del Activo* (primer orden de prioridad) y *🌐 Catalizadores Sectoriales (SpaceX / NASA / Space Force)* con sub-filtros interactivos en la UI.
- **`Risk / Safety Score` (0–100):** Métrica cuantitativa de seguridad y compresión de riesgo calculada a partir de ATR normalizado, posición frente a bandas de Bollinger y drawdown.
- **`Canonical Signals`:** Desacoplamiento estricto entre `base_signal` canónico (`STRONG BUY`, `BUY`, `WATCH`, `HOLD`, `AVOID`, `STRONG AVOID`) y `signal_modifier` (`OVEREXTENDED`, `NO MKT DATA`).
- **`Market Score` (0–100):** Confirmación técnica del precio basada en EMA200, RSI(14) con suavizado Wilder RMA, Bollinger Bands, MACD normalizado por ATR/Precio y ratio de volumen.
- **`Divergence Engine & Risk Hierarchy`:** Detecta desacoples estructurales (ej. *Bullish Divergence: Social/Polymarket Bullish vs. Price Bearish*, *Early Reversal* con $\Delta_{24\text{h}}$ dinámico) y alertas de severidad simétrica (`CRITICAL` para `STRONG BUY`, `STRONG AVOID` y `BEARISH_CONFIRMATION`).
- **`Closed-Loop Dynamic Weight Calibration`:** Retroalimentación empírica en ciclo cerrado desde el motor de backtesting hacia las ponderaciones del SMI basada en $\Delta\text{Sharpe}$ y compuertas de significancia estadística ($N \ge 30$).
- **`Desktop Notifications with Silent Cold-Start`:** Notificaciones de escritorio en tiempo real (Windows Toast) con arranque en frío silencioso, registro persistente anti-duplicados y panel de preferencias de severidad.

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
- **Evaluar divergencias activas:**
  ```bash
  python -m app.cli.commands calculate-divergences
  ```
- **Ejecutar suite de tests automatizados (74 tests unitarios):**
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

