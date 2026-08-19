import React, { useState } from 'react';
import {
  X, Compass, Activity, Zap, Shield, HelpCircle,
  TrendingUp, Layers, CheckCircle2, AlertTriangle,
  Info, Cpu, BookOpen, Target, Scale, Award
} from 'lucide-react';

interface AboutModalProps {
  onClose: () => void;
}

export const AboutModal: React.FC<AboutModalProps> = ({ onClose }) => {
  const [activeSection, setActiveSection] = useState<'overview' | 'metrics' | 'divergences' | 'guide' | 'proscons'>('overview');

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: '920px',
          width: '95%',
          maxHeight: '88vh',
          display: 'flex',
          flexDirection: 'column',
          padding: '0',
          overflow: 'hidden'
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '20px 24px',
            borderBottom: '1px solid var(--border-color)',
            background: 'rgba(19, 28, 46, 0.95)'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                fontSize: '1.8rem',
                background: 'rgba(0, 242, 254, 0.1)',
                padding: '6px 12px',
                borderRadius: '10px',
                border: '1px solid rgba(0, 242, 254, 0.25)'
              }}
            >
              🚀
            </div>
            <div>
              <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.35rem', margin: 0, color: '#fff' }}>
                Space Market Intelligence Engine (SMIE v2.0)
              </h2>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '2px 0 0 0' }}>
                Manual de Operaciones, Arquitectura Cuantitativa & Guía del Usuario
              </p>
            </div>
          </div>

          <button className="btn-close" onClick={onClose} style={{ position: 'static' }}>
            <X size={18} />
          </button>
        </div>

        {/* Section Navigation Tabs */}
        <div
          style={{
            display: 'flex',
            background: 'rgba(11, 15, 25, 0.9)',
            borderBottom: '1px solid var(--border-color)',
            padding: '0 16px',
            overflowX: 'auto',
            gap: '8px'
          }}
        >
          <button
            onClick={() => setActiveSection('overview')}
            style={{
              background: 'none',
              border: 'none',
              borderBottom: activeSection === 'overview' ? '2px solid var(--accent-cyan)' : '2px solid transparent',
              color: activeSection === 'overview' ? 'var(--accent-cyan)' : 'var(--text-muted)',
              padding: '12px 14px',
              fontSize: '0.85rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              whiteSpace: 'nowrap'
            }}
          >
            <Target size={15} /> 1. Objetivo & Misión
          </button>

          <button
            onClick={() => setActiveSection('metrics')}
            style={{
              background: 'none',
              border: 'none',
              borderBottom: activeSection === 'metrics' ? '2px solid var(--accent-cyan)' : '2px solid transparent',
              color: activeSection === 'metrics' ? 'var(--accent-cyan)' : 'var(--text-muted)',
              padding: '12px 14px',
              fontSize: '0.85rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              whiteSpace: 'nowrap'
            }}
          >
            <Layers size={15} /> 2. Métricas Clave (SMI / SSI / PMS)
          </button>

          <button
            onClick={() => setActiveSection('divergences')}
            style={{
              background: 'none',
              border: 'none',
              borderBottom: activeSection === 'divergences' ? '2px solid var(--accent-cyan)' : '2px solid transparent',
              color: activeSection === 'divergences' ? 'var(--accent-cyan)' : 'var(--text-muted)',
              padding: '12px 14px',
              fontSize: '0.85rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              whiteSpace: 'nowrap'
            }}
          >
            <Zap size={15} /> 3. Divergencias Tripartitas
          </button>

          <button
            onClick={() => setActiveSection('guide')}
            style={{
              background: 'none',
              border: 'none',
              borderBottom: activeSection === 'guide' ? '2px solid var(--accent-cyan)' : '2px solid transparent',
              color: activeSection === 'guide' ? 'var(--accent-cyan)' : 'var(--text-muted)',
              padding: '12px 14px',
              fontSize: '0.85rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              whiteSpace: 'nowrap'
            }}
          >
            <BookOpen size={15} /> 4. Guía de Uso Paso a Paso
          </button>

          <button
            onClick={() => setActiveSection('proscons')}
            style={{
              background: 'none',
              border: 'none',
              borderBottom: activeSection === 'proscons' ? '2px solid var(--accent-cyan)' : '2px solid transparent',
              color: activeSection === 'proscons' ? 'var(--accent-cyan)' : 'var(--text-muted)',
              padding: '12px 14px',
              fontSize: '0.85rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              whiteSpace: 'nowrap'
            }}
          >
            <Scale size={15} /> 5. Ventajas & Riesgos
          </button>
        </div>

        {/* Scrollable Modal Body */}
        <div style={{ padding: '24px', overflowY: 'auto', flex: 1, fontSize: '0.9rem', lineHeight: '1.6' }}>

          {/* TAB 1: OBJETIVO & MISIÓN */}
          {activeSection === 'overview' && (
            <div>
              <div
                style={{
                  background: 'rgba(0, 242, 254, 0.06)',
                  border: '1px solid rgba(0, 242, 254, 0.2)',
                  borderRadius: '12px',
                  padding: '16px 20px',
                  marginBottom: '20px'
                }}
              >
                <h3 style={{ color: 'var(--accent-cyan)', fontSize: '1.05rem', margin: '0 0 8px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Compass size={18} /> ¿Qué es Space Market Intelligence Engine (SMIE)?
                </h3>
                <p style={{ margin: 0, color: 'var(--text-main)' }}>
                  <strong>SMIE</strong> es una plataforma de análisis cuantitativo e inteligencia de mercado diseñada específicamente para acciones de empresas de la industria aeroespacial y espacial cotizadas en mercados públicos (como <strong>ASTS</strong>, <strong>RKLB</strong>, <strong>SATL</strong>, <strong>SPCE</strong> y <strong>SPCX</strong>).
                </p>
              </div>

              <h4 style={{ color: '#fff', fontSize: '0.95rem', marginBottom: '8px' }}>🚀 El Problema del Sector Espacial</h4>
              <p style={{ color: 'var(--text-muted)', marginBottom: '16px' }}>
                La industria aeroespacial es única en el mercado financiero: depende fuertemente de <strong>eventos binarios</strong> (lanzamientos de cohetes, despliegue de constelaciones satelitales, aprobaciones de espectro por la FCC, contratos de defensa con el DoD/NASA). Los modelos tradicionales de análisis técnico o fundamental a menudo fallan al no capturar a tiempo las expectativas de eventos ni la narrativa social.
              </p>

              <h4 style={{ color: '#fff', fontSize: '0.95rem', marginBottom: '8px' }}>🧠 La Solución de SMIE v2.0: Cuatro Fuentes Desacopladas</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginTop: '12px' }}>
                <div style={{ background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
                  <div style={{ color: 'var(--bullish-green)', fontWeight: 700, fontSize: '0.85rem' }}>1. Narrativa Social (X)</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Sentimiento en tiempo real con ponderación logarítmica de engagement y relevancia.
                  </div>
                </div>

                <div style={{ background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
                  <div style={{ color: 'var(--accent-cyan)', fontWeight: 700, fontSize: '0.85rem' }}>2. Prediction Markets (Polymarket)</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Probabilidades financieras implícitas con filtro estricto de calidad de mercado.
                  </div>
                </div>

                <div style={{ background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
                  <div style={{ color: '#f59e0b', fontWeight: 700, fontSize: '0.85rem' }}>3. Noticias & Catalizadores</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Detección de contratos de defensa, lanzamientos, acuerdos y diluciones de capital.
                  </div>
                </div>

                <div style={{ background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
                  <div style={{ color: '#38bdf8', fontWeight: 700, fontSize: '0.85rem' }}>4. Acción Técnica del Precio</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Confirmación cuantitativa: EMA200, RSI(14), Bandas de Bollinger, MACD y volumen.
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: MÉTRICAS CLAVE */}
          {activeSection === 'metrics' && (
            <div>
              <p style={{ color: 'var(--text-muted)', marginBottom: '16px' }}>
                Para evitar confusiones, el sistema separa estrictamente el sentimiento social puro de las expectativas de mercados de predicción y del índice integral:
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '14px' }}>
                {/* SMI */}
                <div style={{ background: 'rgba(168, 85, 247, 0.08)', border: '1px solid rgba(168, 85, 247, 0.3)', borderRadius: '12px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: '#a855f7', fontWeight: 800, fontSize: '1.05rem' }}>
                      SMI — Space Market Intelligence Index (0 a 100)
                    </span>
                    <span style={{ fontSize: '0.75rem', background: '#a855f7', color: '#000', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
                      ÍNDICE MAESTRO
                    </span>
                  </div>
                  <p style={{ margin: '8px 0 0 0', color: 'var(--text-main)', fontSize: '0.85rem' }}>
                    Combina todas las fuentes disponibles mediante <strong>pesos adaptativos normalizados</strong> (Social 30%, Polymarket 15%, News 20%, Momentum 20%, Fundamentales 10%, Risk 5%). Si falta una fuente, las demás absorben su peso proporcionalmente sin inventar datos neutros ficticios.
                  </p>
                </div>

                {/* SSI */}
                <div style={{ background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: '12px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: 'var(--bullish-green)', fontWeight: 800, fontSize: '1.05rem' }}>
                      SSI — Space Sentiment Index (0 a 100)
                    </span>
                    <span style={{ fontSize: '0.75rem', background: 'var(--bullish-green)', color: '#000', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
                      SENTIMIENTO SOCIAL X
                    </span>
                  </div>
                  <p style={{ margin: '8px 0 0 0', color: 'var(--text-main)', fontSize: '0.85rem' }}>
                    Mide <strong>exclusivamente</strong> la narrativa y opinión pública en X/Twitter. Pondera cada publicación según su engagement logarítmico ("ln(1 + likes + 2·reposts)") y aplica un decaimiento temporal exponencial de 24 horas.
                  </p>
                </div>

                {/* PMS */}
                <div style={{ background: 'rgba(0, 229, 255, 0.08)', border: '1px solid rgba(0, 229, 255, 0.3)', borderRadius: '12px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, fontSize: '1.05rem' }}>
                      PMS — Prediction Market Score (0 a 100)
                    </span>
                    <span style={{ fontSize: '0.75rem', background: 'var(--accent-cyan)', color: '#000', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
                      POLYMARKET EXPECTATIONS
                    </span>
                  </div>
                  <p style={{ margin: '8px 0 0 0', color: 'var(--text-main)', fontSize: '0.85rem' }}>
                    Calcula la probabilidad agregada de éxito de eventos espaciales directos y sectoriales en Polymarket.
                    <br />
                    <em>Regla de Oro:</em> Si la calidad del mercado (liquidez, volumen, spread) es $&lt; 30$, su peso efectivo en SMI se anula ($0\%$).
                  </p>
                </div>

                {/* Market Score */}
                <div style={{ background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '12px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: '#f59e0b', fontWeight: 800, fontSize: '1.05rem' }}>
                      Market Score — Confirmación Técnica (0 a 100)
                    </span>
                    <span style={{ fontSize: '0.75rem', background: '#f59e0b', color: '#000', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
                      ANÁLISIS TÉCNICO
                    </span>
                  </div>
                  <p style={{ margin: '8px 0 0 0', color: 'var(--text-main)', fontSize: '0.85rem' }}>
                    Evalúa si la tendencia del precio acompaña la narrativa. Penaliza sobreextensiones alcistas ($RSI &gt; 75$) o cotizaciones por debajo de la media móvil de 200 días ($EMA200$).
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: DIVERGENCIAS TRIPARTITAS */}
          {activeSection === 'divergences' && (
            <div>
              <p style={{ color: 'var(--text-muted)', marginBottom: '16px' }}>
                Una de las ventajas competitivas más potentes de SMIE es que <strong>nunca promedia fuentes contradictorias a ciegas</strong>. Cuando X, Polymarket y el Precio no coinciden, el <em>Divergence Engine</em> emite alertas de régimen:
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div style={{ background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: '10px', padding: '14px' }}>
                  <div style={{ color: 'var(--bullish-green)', fontWeight: 700, fontSize: '0.9rem' }}>
                    🟢 BULLISH DIVERGENCE (Oportunidad)
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-main)', marginTop: '6px' }}>
                    El sentimiento social (SSI) y Polymarket (PMS) son fuertemente alcistas, pero el precio de la acción sigue deprimido o rezagado. Suele anticipar rebotes o infravaloración temporal.
                  </div>
                </div>

                <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '10px', padding: '14px' }}>
                  <div style={{ color: 'var(--bearish-red)', fontWeight: 700, fontSize: '0.9rem' }}>
                    🔴 BEARISH DIVERGENCE (Alerta de Trampa)
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-main)', marginTop: '6px' }}>
                    El precio de la acción está en máximos o subiendo, pero la comunidad social o las apuestas en Polymarket están colapsando. Alerta sobre alta probabilidad de corrección inminente.
                  </div>
                </div>

                <div style={{ background: 'rgba(0, 229, 255, 0.1)', border: '1px solid rgba(0, 229, 255, 0.3)', borderRadius: '10px', padding: '14px' }}>
                  <div style={{ color: 'var(--accent-cyan)', fontWeight: 700, fontSize: '0.9rem' }}>
                    ⚡ EARLY REVERSAL (Giro Temprano)
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-main)', marginTop: '6px' }}>
                    Las probabilidades de Polymarket giran drásticamente antes de que la noticia llegue a X o impacte en la cotización del mercado bursátil.
                  </div>
                </div>

                <div style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '14px' }}>
                  <div style={{ color: '#fff', fontWeight: 700, fontSize: '0.9rem' }}>
                    🛡️ CONFIRMATION (Alineación Estructural)
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '6px' }}>
                    Todas las fuentes (X + Polymarket + Noticias + Precio) se mueven en la misma dirección, otorgando la máxima puntuación de Confianza ($&gt; 80\%$).
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: GUÍA DE USO PASO A PASO */}
          {activeSection === 'guide' && (
            <div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
                  <div style={{ background: 'var(--accent-cyan)', color: '#000', fontWeight: 800, width: '28px', height: '28px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    1
                  </div>
                  <div>
                    <h4 style={{ margin: 0, color: '#fff', fontSize: '0.95rem' }}>Revisa el Termómetro del Sector</h4>
                    <p style={{ margin: '4px 0 0 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      En la barra superior del Dashboard verás el <strong>SMI Promedio del Sector</strong>, el activo más alcista y el estado de frescura en vivo de los proveedores.
                    </p>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
                  <div style={{ background: 'var(--accent-cyan)', color: '#000', fontWeight: 800, width: '28px', height: '28px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    2
                  </div>
                  <div>
                    <h4 style={{ margin: 0, color: '#fff', fontSize: '0.95rem' }}>Explora la Tabla Terminal de Posiciones</h4>
                    <p style={{ margin: '4px 0 0 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      Compara rápidamente qué empresas tienen puntuaciones <code>SMI &gt; 75</code> (Señales <strong>BUY / STRONG BUY</strong>) o advertencias de divergencia.
                    </p>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
                  <div style={{ background: 'var(--accent-cyan)', color: '#000', fontWeight: 800, width: '28px', height: '28px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    3
                  </div>
                  <div>
                    <h4 style={{ margin: 0, color: '#fff', fontSize: '0.95rem' }}>Haz Clic en Cualquier Ticker para Abrir el Análisis Detallado</h4>
                    <p style={{ margin: '4px 0 0 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      Podrás ver:
                      <br />• <strong>Pestaña Prediction Markets:</strong> Contratos de Polymarket, barras YES/NO, volumen y liquidez.
                      <br />• <strong>Pestaña X Social Feed:</strong> Tweets clasificados por sentimiento con tags de catalizador.
                      <br />• <strong>WHY THIS SIGNAL?:</strong> Razones explícitas generadas por el motor algorítmico.
                      <br />• <strong>Gráfico Multi-serie SVG:</strong> Activa o desactiva las curvas de Precio, SMI, SSI y PMS con los botones interactivos.
                    </p>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
                  <div style={{ background: 'var(--accent-cyan)', color: '#000', fontWeight: 800, width: '28px', height: '28px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    4
                  </div>
                  <div>
                    <h4 style={{ margin: 0, color: '#fff', fontSize: '0.95rem' }}>Ejecuta el Pipeline Manualmente o Consulta Reportes</h4>
                    <p style={{ margin: '4px 0 0 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      Usa el botón <strong>"Run SMIE Pipeline"</strong> en el header o los comandos CLI en tu consola:
                      <br />• <code>python -m app.cli daily-report</code>: Genera el resumen diario del sector.
                      <br />• <code>python -m app.cli backtest</code>: Evalúa el desempeño cuantitativo de los modelos.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: VENTAJAS & RIESGOS */}
          {activeSection === 'proscons' && (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                {/* Ventajas */}
                <div style={{ background: 'rgba(16, 185, 129, 0.06)', border: '1px solid rgba(16, 185, 129, 0.25)', borderRadius: '12px', padding: '16px' }}>
                  <h4 style={{ color: 'var(--bullish-green)', fontSize: '0.95rem', margin: '0 0 12px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <CheckCircle2 size={16} /> Ventajas Principales
                  </h4>
                  <ul style={{ paddingLeft: '18px', margin: 0, color: 'var(--text-main)', fontSize: '0.82rem', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <li><strong>Visión Multivariable Completa:</strong> No depende solo de gráficos técnicos ni solo de opiniones en redes.</li>
                    <li><strong>Expectativas Reales con Dinero (Polymarket):</strong> Incorpora probabilidades financieras donde los usuarios arriesgan capital real.</li>
                    <li><strong>Filtro Automático de Calidad:</strong> Elimina mercados de predicción ilíquidos o con spreads manipulables.</li>
                    <li><strong>Explicabilidad Total (Cero Cajas Negras):</strong> Cada señal explica detalladamente por qué se emitió.</li>
                    <li><strong>Aislamiento de Fallos:</strong> Si una red social falla, el motor sigue funcionando con las demás fuentes.</li>
                  </ul>
                </div>

                {/* Riesgos y Limitaciones */}
                <div style={{ background: 'rgba(239, 68, 68, 0.06)', border: '1px solid rgba(239, 68, 68, 0.25)', borderRadius: '12px', padding: '16px' }}>
                  <h4 style={{ color: 'var(--bearish-red)', fontSize: '0.95rem', margin: '0 0 12px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <AlertTriangle size={16} /> Desventajas y Riesgos del Sector
                  </h4>
                  <ul style={{ paddingLeft: '18px', margin: 0, color: 'var(--text-main)', fontSize: '0.82rem', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <li><strong>Riesgo Binario Extremo:</strong> Un fallo en el lanzamiento de un cohete puede provocar caídas inmediatas en el precio que ningún modelo predictivo puede anticipar antes del despegue.</li>
                    <li><strong>Spreads en Mercados de Nicho:</strong> Algunos contratos específicos pueden tener baja liquidez (SMIE los filtra si Quality &lt; 30).</li>
                    <li><strong>Retrasos en Redes Sociales:</strong> La velocidad de la narrativa en X puede incluir desinformación o euforia irracional.</li>
                  </ul>
                </div>
              </div>

              {/* Disclaimer */}
              <div style={{ marginTop: '16px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '12px 16px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                <strong>Aviso Legal (Financial Disclaimer):</strong> Space Market Intelligence Engine (SMIE) es una herramienta de investigación y análisis cuantitativo de datos públicos y probabilísticos. No constituye asesoramiento financiero ni recomendaciones personalizadas de inversión.
              </div>
            </div>
          )}

        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: '14px 24px',
            borderTop: '1px solid var(--border-color)',
            background: 'rgba(19, 28, 46, 0.95)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}
        >
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            SMIE v2.0 • Aerospace Market Intelligence Architecture
          </span>
          <button
            onClick={onClose}
            className="btn btn-primary"
            style={{ padding: '8px 20px', fontSize: '0.85rem', fontWeight: 700 }}
          >
            Entendido, ir al Dashboard
          </button>
        </div>
      </div>
    </div>
  );
};
