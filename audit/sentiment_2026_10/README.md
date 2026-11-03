# Estudios de sentimiento y momentum — octubre 2026 (v2.2)

Estudios reproducibles que respaldan los cambios de scoring de la v2.2. Todos son **de solo lectura** sobre `data/space_sentiment.db` y se corren desde la raíz del repo:

```bash
python -m audit.sentiment_2026_10.<script>
```

Las salidas que pueden contener datos de posts van a `audit/output/` (ignorado por git). Este directorio solo versiona IDs de tweets y etiquetas, nunca textos ni usuarios de terceros.

| Script | Pregunta | Resultado (oct-2026) |
|---|---|---|
| `compare_sentiment_models.py` | ¿Cómo etiquetan FinBERT y FinTwitBERT los mismos 9.173 tweets? (~20 min en CPU) | FinBERT: 77% neutral. FinTwitBERT con umbral 0.20: 68% alcista (98.6% en tweets no ingleses). Coinciden en el 31%. |
| `score_model_review.py` + `model_review_labels.csv` | Revisión manual a ciegas de 150 desacuerdos (137 en inglés), ponderada por estrato | FinTwitBERT con umbral 0.90: 73% de aciertos vs 63% de FinBERT (IC 95% de la diferencia [-2, +23] pts); precisión de opiniones 64% vs 17%; polaridad invertida 0.5% vs 2.8%. La combinación "FinBERT filtra / FinTwit dirige" solo llega a 64%. |
| `momentum_study.py` | ¿El pilar de momentum predice retornos a 1/3/5 días? (2 años de precios diarios, sin lookahead) | No. Los retornos de 1–5 días tienen IC ≈ 0; la distancia a la EMA200 y el filtro binario tienen IC negativo (-0.09 a -0.13 a 3–5 días). Por eso en v2.2 el pilar es un filtro de tendencia de baja varianza con peso 0.10. |
| `pillar_ic_and_composition.py` + `_ic_stats.py` | ¿Qué mueve el SMI y qué pilar anticipa retornos? (reproduce cada snapshot con el código actual; desde 3/11 da un veredicto `ALIVE`/`REVERSED`/`DEAD`/`INSUFFICIENT_DATA` por pilar y horizonte, sobre retorno en exceso desde el primer cierre posterior) | v2.2: social 57%, noticias 28%, fundamentales 13%, momentum 3%, Polymarket 0% del movimiento del SMI (antes: momentum 58%, social 4%). IC a 72h dentro de ticker: social -0.13, noticias +0.05, fundamentales +0.17, SMI -0.10 (antes -0.29). **Muestra de 19 días con etiquetas mixtas: no concluyente.** Ese +0.17 de fundamentales salía de un solo ticker (en los otros cuatro el score nunca varió). |
| `sector_selloff_study.py` | ¿Una caída conjunta del sector anticipa los retornos de 1–10 días? (cesta a pesos iguales, 5 y 2 años, episodios sin solapamiento) | No. IC de la caída de la cesta a 3–5 días entre -0.03 y +0.09 con \|t\| ≤ 1; en el estudio de eventos (cesta ≤ -5/-8/-12% en 3 días, por desvíos, con amplitud o solo sectorial) todos los IC 95% del retorno medio cruzan el cero y el signo cambia según horizonte y periodo. Una caída de -5% en 3 días ocurre ~cada 2 semanas en este sector (la del 8/10/2026 fue -0.8 desvíos). Por eso no se agregó un modificador `SECTOR SELLOFF`. |
| `spam_pattern_check.py` | ¿Cuánto tráfico y cuántas opiniones descarta el filtro de spam? | 15% de los posts y 69 opiniones (todas alcistas, todas spam en la revisión manual). SPCE: 25% de sus opiniones eran campañas de bots. |

## Cómo usarlos más adelante

- **Antes de rebalancear pesos** (tarea pendiente): correr `pillar_ic_and_composition.py` (por defecto filtra `rules_version` ≥ 2.2.2; `--min-rules-version all` mezcla fórmulas viejas y solo sirve para probar el código) con al menos 3–4 semanas de datos a cadencia fija. Un pilar merece peso solo si sale `ALIVE` en 1 y 3 sesiones. La tabla queda en `audit/output/pillar_ic_verdicts_<fecha>.json`.
- **Reglas del veredicto** (`_ic_stats.py`, umbrales como constantes al inicio del módulo): al menos 20 observaciones independientes (fechas / horizonte), 4 semanas y 3 tickers cuyo score varíe; IC 95% por bootstrap por bloques que excluya el 0 y \|t\| de Newey-West ≥ 2; el signo se mantiene en ≥ 60% de las semanas y de los tickers; y quitando cualquier ticker el resto sigue con t ≥ 2 en la misma dirección. Los tests de `tests/test_ic_stats.py` fijan el comportamiento con datos sintéticos.
- **Si se cambia el modelo social**: correr `compare_sentiment_models.py`, revisar una muestra estratificada de desacuerdos y puntuarla con la lógica de `score_model_review.py`.
- **Si aparecen nuevos estilos de spam** en la pestaña "Excluded" del feed: agregar el patrón en `app/scoring/social.py` y verificar con `spam_pattern_check.py` que no descarta opiniones genuinas.
