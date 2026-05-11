"""
=============================================================================
  MÓDULO: interfaz_estilos.py  v3.0
  Sistema de Diseño Industrial — Molinos Santa Marta S.A.S.
  Control Estadístico de Procesos
=============================================================================
  ARQUITECTURA DEL SISTEMA DE DISEÑO:
  ┌─────────────────────────────────────────────────────────────────┐
  │  TOKENS          paleta, tipografía, espaciado, sombras         │
  │  COMPONENTES     kpi_card, alarm_box, section_title, badge      │
  │  LAYOUT          header, sidebar, page scaffold                 │
  │  UTILIDADES      cpk_status, render_*                           │
  └─────────────────────────────────────────────────────────────────┘

  Importación en app_molinos.py:
      from interfaz_estilos import (
          CP, CR, CG, CY, CN,
          configurar_pagina, aplicar_estilos,
          render_encabezado, render_alarm, render_section_title,
          render_kpi, render_kpi_row,
          kpi_card_html, badge_html, alarm_html,
      )
=============================================================================
"""

import streamlit as st

# =============================================================================
# TOKENS — Design System Foundation
# =============================================================================

# ── Paleta primaria ────────────────────────────────────────────────────────────
# Azul industrial: profundo, serio, corporativo.
# Acento: ámbar cálido (no el amarillo genérico de advertencia) para highlights.
# Semántica: rojo contenido, verde contenido, sin saturaciones agresivas.

CP  = "#1A3F5C"   # Azul primario profundo
CP2 = "#2563A8"   # Azul secundario (hover, acciones)
CP3 = "#D6E8F7"   # Azul tenue (fondos, highlights suaves)

CR  = "#C0392B"   # Rojo (alerta crítica / fuera de control)
CR2 = "#FDECEA"   # Rojo tenue (fondo de alarma)

CG  = "#1A7A4A"   # Verde (conforme / OK)
CG2 = "#E8F8EF"   # Verde tenue

CY  = "#B7620A"   # Ámbar oscuro (advertencia — más industrial que amarillo)
CY2 = "#FEF3E2"   # Ámbar tenue

CN  = "#5D6B7A"   # Gris neutro medio
CN2 = "#8FA3B3"   # Gris claro
CN3 = "#F2F5F8"   # Gris casi blanco (fondos de página)
CN4 = "#E2E8EE"   # Gris borde

# Tokens semánticos de superficie
SURFACE_0 = "#FFFFFF"    # Blanco puro (cards)
SURFACE_1 = "#F7FAFC"    # Fondo de página
SURFACE_2 = "#EEF3F8"    # Fondo alternado (zebra)

# ── Espaciado ─────────────────────────────────────────────────────────────────
# Base: 4px. Escala multiplicativa x2 por nivel.
SP_XS  = "4px"
SP_SM  = "8px"
SP_MD  = "16px"
SP_LG  = "24px"
SP_XL  = "40px"

# ── Bordes y radios ───────────────────────────────────────────────────────────
RADIUS_SM = "6px"
RADIUS_MD = "10px"
RADIUS_LG = "14px"

# ── Sombras ───────────────────────────────────────────────────────────────────
SHADOW_SM  = "0 1px 4px rgba(0,0,0,.06)"
SHADOW_MD  = "0 3px 12px rgba(0,0,0,.08)"
SHADOW_LG  = "0 6px 24px rgba(26,63,92,.12)"
SHADOW_FOCUS = "0 0 0 3px rgba(37,99,168,.25)"


# =============================================================================
# CONFIGURACIÓN DE PÁGINA
# =============================================================================

def configurar_pagina():
    """st.set_page_config — debe ser la PRIMERA instrucción Streamlit del script."""
    st.set_page_config(
        page_title="CEP · Molinos Santa Marta",
        page_icon="⚙️",
        layout="wide",
        initial_sidebar_state="expanded",
    )


# =============================================================================
# CSS GLOBAL — Sistema de Diseño Completo
# =============================================================================

_CSS = """
<style>
/* ══════════════════════════════════════════════════════════════════════════
   TIPOGRAFÍA
   Fuente: DM Sans (moderna, legible, profesional, sin las connotaciones
   genéricas de Inter/Roboto). Mono: JetBrains Mono para valores numéricos.
══════════════════════════════════════════════════════════════════════════ */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=JetBrains+Mono:wght@400;500;600&family=DM+Serif+Display&display=swap');

:root {
  /* Paleta */
  --c-primary:      #1A3F5C;
  --c-primary-2:    #2563A8;
  --c-primary-3:    #D6E8F7;
  --c-danger:       #C0392B;
  --c-danger-2:     #FDECEA;
  --c-success:      #1A7A4A;
  --c-success-2:    #E8F8EF;
  --c-warning:      #B7620A;
  --c-warning-2:    #FEF3E2;
  --c-neutral:      #5D6B7A;
  --c-neutral-2:    #8FA3B3;
  --c-neutral-3:    #F2F5F8;
  --c-neutral-4:    #E2E8EE;
  --c-surface:      #FFFFFF;
  --c-surface-1:    #F7FAFC;
  --c-surface-2:    #EEF3F8;
  --c-text:         #1A2733;
  --c-text-2:       #3D5166;
  --c-text-3:       #8FA3B3;

  /* Tipografía */
  --font-body:  'DM Sans', system-ui, sans-serif;
  --font-mono:  'JetBrains Mono', 'Fira Code', monospace;
  --font-serif: 'DM Serif Display', Georgia, serif;

  /* Espaciado */
  --sp-xs: 4px; --sp-sm: 8px; --sp-md: 16px;
  --sp-lg: 24px; --sp-xl: 40px;

  /* Radios */
  --r-sm: 6px; --r-md: 10px; --r-lg: 14px;

  /* Sombras */
  --shadow-sm:  0 1px 4px rgba(0,0,0,.06);
  --shadow-md:  0 3px 12px rgba(0,0,0,.08);
  --shadow-lg:  0 6px 24px rgba(26,63,92,.12);
}

/* ── Reset global Streamlit ── */
html, body, [class*="css"] {
  font-family: var(--font-body);
  color: var(--c-text);
  -webkit-font-smoothing: antialiased;
}
#MainMenu, footer, header { visibility: hidden; }

/* ── Fondo de página ── */
.stApp { background: var(--c-surface-1); }
section.main > div { padding-top: 0.75rem; }

/* ══════════════════════════════════════════════════════════════════════════
   HEADER CORPORATIVO
══════════════════════════════════════════════════════════════════════════ */
.corp-header {
  background: linear-gradient(120deg, #1A3F5C 0%, #0F2A40 60%, #122035 100%);
  border-bottom: 3px solid #2563A8;
  padding: 0;
  margin-bottom: 1.25rem;
  border-radius: var(--r-lg);
  overflow: hidden;
  box-shadow: var(--shadow-lg);
  position: relative;
}
/* Textura sutil — patrón de grilla industrial */
.corp-header::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(37,99,168,.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(37,99,168,.08) 1px, transparent 1px);
  background-size: 28px 28px;
  pointer-events: none;
}
.corp-header-inner {
  position: relative;
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 1.1rem 1.6rem;
}
.corp-header-logo {
  width: 44px; height: 44px;
  background: rgba(37,99,168,.25);
  border: 1.5px solid rgba(37,99,168,.5);
  border-radius: var(--r-md);
  display: flex; align-items: center; justify-content: center;
  font-size: 1.4rem;
  flex-shrink: 0;
}
.corp-header-text { flex: 1; min-width: 0; }
.corp-header-title {
  font-size: 1.15rem; font-weight: 700; color: #FFFFFF;
  letter-spacing: -.3px; line-height: 1.2; margin: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.corp-header-sub {
  font-size: .72rem; color: rgba(255,255,255,.6);
  margin-top: 2px; letter-spacing: .2px;
}
.corp-header-pill {
  display: flex; align-items: center; gap: 6px;
  background: rgba(26,122,74,.2);
  border: 1px solid rgba(26,122,74,.45);
  border-radius: 20px;
  padding: 5px 12px;
  font-size: .72rem; font-weight: 600;
  color: #5DDBA3;
  flex-shrink: 0;
}
.corp-header-pill.inactive {
  background: rgba(176,176,176,.15);
  border-color: rgba(176,176,176,.3);
  color: rgba(255,255,255,.5);
}
.corp-header-pill-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #5DDBA3;
  animation: pulse-dot 2s ease-in-out infinite;
}
.corp-header-pill.inactive .corp-header-pill-dot {
  background: rgba(255,255,255,.4);
  animation: none;
}
@keyframes pulse-dot {
  0%,100% { opacity: 1; transform: scale(1); }
  50%      { opacity: .5; transform: scale(.85); }
}

/* ══════════════════════════════════════════════════════════════════════════
   SIDEBAR PROFESIONAL
══════════════════════════════════════════════════════════════════════════ */
[data-testid="collapsedControl"]     { display: none !important; }
[data-testid="stSidebarCollapseButton"] { display: none !important; }

section[data-testid="stSidebar"] {
  background: #101E2B !important;
  min-width: 220px !important;
  border-right: 1px solid #1E3448;
}
section[data-testid="stSidebar"] > div {
  padding: 0 !important;
  overflow-x: hidden;
}

.sidebar-brand {
  padding: 1.1rem 1rem .9rem;
  border-bottom: 1px solid #1E3448;
  background: linear-gradient(135deg, #0F2236, #1A3F5C);
}
.sidebar-brand-name {
  font-size: .9rem; font-weight: 700; color: #FFFFFF;
  letter-spacing: -.2px; line-height: 1.2;
}
.sidebar-brand-sub {
  font-size: .65rem; color: rgba(255,255,255,.45);
  margin-top: 2px; letter-spacing: .3px; text-transform: uppercase;
}
.sidebar-section-label {
  font-size: .6rem; font-weight: 700; letter-spacing: 1.2px;
  text-transform: uppercase; color: #3D5A73;
  padding: 1rem 1rem .4rem;
}
.sidebar-divider {
  height: 1px; background: #1E3448; margin: .4rem .75rem;
}
.sidebar-footer {
  padding: .75rem 1rem;
  border-top: 1px solid #1E3448;
  font-size: .63rem; color: #3D5A73;
  letter-spacing: .3px;
}

/* Botones del sidebar — override Streamlit */
section[data-testid="stSidebar"] button[kind="secondary"] {
  background: transparent !important;
  border: none !important;
  color: #8FA3B3 !important;
  font-size: .82rem !important;
  font-weight: 500 !important;
  text-align: left !important;
  padding: .48rem .9rem !important;
  border-radius: var(--r-sm) !important;
  width: 100% !important;
  transition: background .15s, color .15s !important;
  margin: 1px 0 !important;
}
section[data-testid="stSidebar"] button[kind="secondary"]:hover {
  background: rgba(37,99,168,.15) !important;
  color: #C8DCF0 !important;
}
section[data-testid="stSidebar"] button[kind="primary"] {
  background: rgba(37,99,168,.2) !important;
  border: 1px solid rgba(37,99,168,.5) !important;
  border-left: 3px solid #2563A8 !important;
  color: #C8DCF0 !important;
  font-weight: 600 !important;
  font-size: .82rem !important;
  text-align: left !important;
  padding: .48rem .9rem !important;
  border-radius: var(--r-sm) !important;
  width: 100% !important;
  margin: 1px 0 !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   KPI CARDS — Sistema completo
══════════════════════════════════════════════════════════════════════════ */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
  margin: .5rem 0 1.1rem;
}
.kpi-card {
  background: var(--c-surface);
  border-radius: var(--r-md);
  padding: .85rem 1rem .8rem;
  box-shadow: 0 1px 3px rgba(0,0,0,.05), 0 1px 8px rgba(26,63,92,.06);
  border: 1px solid var(--c-neutral-4);
  border-top: 3px solid var(--c-primary);
  position: relative;
  overflow: hidden;
  transition: box-shadow .18s ease, transform .18s ease;
}
/* Acento de color en esquina superior derecha */
.kpi-card::after {
  content: '';
  position: absolute;
  top: -8px; right: -8px;
  width: 52px; height: 52px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(37,99,168,.07), transparent 68%);
  pointer-events: none;
}
.kpi-card:hover {
  box-shadow: 0 4px 14px rgba(26,63,92,.12);
  transform: translateY(-1px);
}

/* Variantes semánticas — borde superior */
.kpi-card.danger  { border-top-color: var(--c-danger); }
.kpi-card.warning { border-top-color: var(--c-warning); }
.kpi-card.success { border-top-color: var(--c-success); }
.kpi-card.neutral { border-top-color: var(--c-neutral-2); }

/* Línea sutil de color en el fondo inferior — refuerzo semántico */
.kpi-card.danger::before  { content:''; position:absolute; bottom:0; left:0; right:0; height:2px; background:rgba(192,57,43,.15); }
.kpi-card.warning::before { content:''; position:absolute; bottom:0; left:0; right:0; height:2px; background:rgba(183,98,10,.15); }
.kpi-card.success::before { content:''; position:absolute; bottom:0; left:0; right:0; height:2px; background:rgba(26,122,74,.15); }

.kpi-icon {
  font-size: .95rem;
  opacity: .55;
  margin-bottom: .28rem;
  display: block;
  line-height: 1;
}
.kpi-value {
  font-family: var(--font-mono);
  font-size: 1.55rem; font-weight: 600;
  line-height: 1.05; letter-spacing: -.4px;
  color: var(--c-text);
  white-space: nowrap;
}
/* Colores semánticos del valor numérico */
.kpi-value.danger  { color: var(--c-danger); }
.kpi-value.warning { color: var(--c-warning); }
.kpi-value.success { color: var(--c-success); }

.kpi-label {
  font-size: .63rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 1px;
  color: var(--c-text-3);
  margin-top: .32rem;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  line-height: 1.3;
}
.kpi-sub {
  font-size: .69rem; color: var(--c-neutral);
  margin-top: .22rem; line-height: 1.45;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* ══════════════════════════════════════════════════════════════════════════
   BADGES
══════════════════════════════════════════════════════════════════════════ */
.badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: .22rem .65rem;
  border-radius: 20px;
  font-size: .67rem; font-weight: 700;
  letter-spacing: .5px; text-transform: uppercase;
}
.badge::before {
  content: ''; width: 5px; height: 5px;
  border-radius: 50%; flex-shrink: 0;
}
.badge-green  { background: var(--c-success-2); color: var(--c-success); border: 1px solid rgba(26,122,74,.25); }
.badge-green::before  { background: var(--c-success); }
.badge-yellow { background: var(--c-warning-2); color: var(--c-warning); border: 1px solid rgba(183,98,10,.25); }
.badge-yellow::before { background: var(--c-warning); }
.badge-red    { background: var(--c-danger-2);  color: var(--c-danger);  border: 1px solid rgba(192,57,43,.25); }
.badge-red::before    { background: var(--c-danger); }

/* ══════════════════════════════════════════════════════════════════════════
   ALARM BOXES — mensajes de estado del proceso
══════════════════════════════════════════════════════════════════════════ */
.alarm-box {
  padding: .75rem 1rem .75rem 1.2rem;
  border-radius: var(--r-sm);
  margin: .4rem 0;
  font-size: .83rem; line-height: 1.55;
  border-left: 4px solid;
  position: relative;
}
.alarm-critical {
  background: var(--c-danger-2);
  border-left-color: var(--c-danger);
  color: #7B1A13;
}
.alarm-warning {
  background: var(--c-warning-2);
  border-left-color: var(--c-warning);
  color: #7A3D05;
}
.alarm-info {
  background: var(--c-primary-3);
  border-left-color: var(--c-primary-2);
  color: var(--c-primary);
}
.alarm-ok {
  background: var(--c-success-2);
  border-left-color: var(--c-success);
  color: #0E4D2B;
}

/* ══════════════════════════════════════════════════════════════════════════
   SECTION TITLES — jerarquía visual interna
══════════════════════════════════════════════════════════════════════════ */
.section-title {
  display: flex; align-items: center; gap: 8px;
  font-size: .78rem; font-weight: 700;
  color: var(--c-primary);
  text-transform: uppercase; letter-spacing: .7px;
  padding-bottom: .45rem;
  border-bottom: 1.5px solid var(--c-primary-3);
  margin: 1.1rem 0 .75rem;
}

/* ══════════════════════════════════════════════════════════════════════════
   TABLAS PROFESIONALES — override Streamlit dataframe
══════════════════════════════════════════════════════════════════════════ */

/* ── Contenedor general ── */
[data-testid="stDataFrame"] { border-radius: var(--r-md); overflow: hidden; }

/* ── Encabezados ── */
[data-testid="stDataFrame"] th,
.stDataFrame th,
[data-testid="stDataFrame"] [role="columnheader"] {
  background: #1A3F5C !important;
  color: #FFFFFF !important;
  font-size: .70rem !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: .6px !important;
  padding: .5rem .7rem !important;
  border: none !important;
  white-space: nowrap !important;
  text-align: center !important;
}

/* ── Celdas de datos ── */
[data-testid="stDataFrame"] td,
.stDataFrame td,
[data-testid="stDataFrame"] [role="gridcell"] {
  font-family: var(--font-mono) !important;
  font-size: .80rem !important;
  padding: .38rem .7rem !important;
  border-color: #E8EEF3 !important;
  color: var(--c-text-2) !important;
  text-align: center !important;
  vertical-align: middle !important;
}

/* ── Primera columna — texto izquierda (labels) ── */
[data-testid="stDataFrame"] td:first-child,
.stDataFrame td:first-child {
  font-family: var(--font-body) !important;
  font-weight: 600 !important;
  color: var(--c-primary) !important;
  text-align: left !important;
  background: #F7FAFC !important;
}

/* ── Zebra striping suave ── */
[data-testid="stDataFrame"] tr:nth-child(even) td,
.stDataFrame tr:nth-child(even) td {
  background: #F2F6FA !important;
}
[data-testid="stDataFrame"] tr:nth-child(odd) td,
.stDataFrame tr:nth-child(odd) td {
  background: #FFFFFF !important;
}

/* ── Hover de fila ── */
[data-testid="stDataFrame"] tr:hover td,
.stDataFrame tr:hover td {
  background: #D6E8F7 !important;
  transition: background .12s ease !important;
}

/* ── Bordes suaves entre celdas ── */
[data-testid="stDataFrame"] td,
.stDataFrame td {
  border-bottom: 1px solid #E8EEF3 !important;
  border-right: none !important;
}

/* ── Tablas de resumen (st.dataframe en expanders) ── */
.stDataFrame table {
  border-collapse: collapse !important;
  width: 100% !important;
}

/* ── data_editor — editor de monitoreo ── */
[data-testid="stDataEditor"] th {
  background: #243B55 !important;
  color: #FFFFFF !important;
  font-size: .70rem !important;
  font-weight: 700 !important;
  letter-spacing: .5px !important;
  text-transform: uppercase !important;
  padding: .45rem .65rem !important;
  text-align: center !important;
}
[data-testid="stDataEditor"] td {
  font-family: var(--font-mono) !important;
  font-size: .81rem !important;
  text-align: center !important;
  padding: .35rem .6rem !important;
  border-color: #E8EEF3 !important;
}
[data-testid="stDataEditor"] tr:nth-child(even) td { background: #F2F6FA !important; }
[data-testid="stDataEditor"] tr:hover td { background: #D6E8F7 !important; }

/* ══════════════════════════════════════════════════════════════════════════
   REGLAS DE SENSIBILIZACIÓN
══════════════════════════════════════════════════════════════════════════ */
.rule-hit {
  background: var(--c-warning-2);
  border-left: 3px solid var(--c-warning);
  padding: .45rem .85rem;
  border-radius: var(--r-sm);
  margin: .25rem 0;
  font-size: .81rem; color: #7A3D05;
}
.rule-ok {
  background: var(--c-success-2);
  border-left: 3px solid var(--c-success);
  padding: .45rem .85rem;
  border-radius: var(--r-sm);
  margin: .25rem 0;
  font-size: .81rem; color: #0E4D2B;
}

/* ══════════════════════════════════════════════════════════════════════════
   MÉTRICAS STREAMLIT — refinamiento
══════════════════════════════════════════════════════════════════════════ */
[data-testid="stMetric"] {
  background: var(--c-surface);
  border-radius: var(--r-md);
  padding: .75rem 1rem;
  border: 1px solid var(--c-neutral-4);
  box-shadow: var(--shadow-sm);
}
[data-testid="stMetricLabel"] {
  font-size: .67rem !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: .7px !important;
  color: var(--c-text-3) !important;
}
[data-testid="stMetricValue"] {
  font-family: var(--font-mono) !important;
  font-size: 1.45rem !important;
  font-weight: 600 !important;
  color: var(--c-primary) !important;
}
[data-testid="stMetricDelta"] {
  font-size: .72rem !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   FORMULARIOS & WIDGETS STREAMLIT
══════════════════════════════════════════════════════════════════════════ */
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] [data-baseweb="select"],
[data-testid="stSlider"] {
  font-family: var(--font-body) !important;
  font-size: .84rem !important;
}
[data-testid="stNumberInput"] label,
[data-testid="stTextInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stSlider"] label {
  font-size: .74rem !important;
  font-weight: 600 !important;
  color: var(--c-text-2) !important;
  letter-spacing: .2px !important;
}
/* Botones principales */
[data-testid="baseButton-primary"] {
  font-weight: 600 !important;
  letter-spacing: .2px !important;
  font-size: .83rem !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   EXPANDERS
══════════════════════════════════════════════════════════════════════════ */
[data-testid="stExpander"] {
  border: 1px solid var(--c-neutral-4) !important;
  border-radius: var(--r-md) !important;
  box-shadow: none !important;
}
[data-testid="stExpander"] summary {
  font-size: .82rem !important;
  font-weight: 600 !important;
  color: var(--c-primary) !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   TABS (si se usan)
══════════════════════════════════════════════════════════════════════════ */
[data-testid="stTabs"] [data-baseweb="tab"] {
  font-size: .8rem !important;
  font-weight: 600 !important;
  letter-spacing: .2px !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   UTILIDADES
══════════════════════════════════════════════════════════════════════════ */
.mt-sm { margin-top: .5rem; }
.mt-md { margin-top: 1rem; }
.mt-lg { margin-top: 1.5rem; }
.mb-sm { margin-bottom: .5rem; }
.mb-md { margin-bottom: 1rem; }

/* Divisor elegante */
.divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--c-neutral-4), transparent);
  margin: 1.25rem 0;
  border: none;
}

/* Info chip — tags de metadatos */
.chip {
  display: inline-block;
  padding: .18rem .6rem;
  background: var(--c-surface-2);
  border: 1px solid var(--c-neutral-4);
  border-radius: 20px;
  font-size: .68rem; font-weight: 600;
  color: var(--c-neutral); letter-spacing: .3px;
}
</style>
"""


def aplicar_estilos():
    """Inyecta el CSS del sistema de diseño en la página de Streamlit."""
    st.markdown(_CSS, unsafe_allow_html=True)


# =============================================================================
# COMPONENTES — HTML Builders
# =============================================================================

def render_encabezado(dataset_nombre: str = None):
    """
    Header corporativo fijo.
    dataset_nombre: nombre del archivo cargado (None = sin datos).
    """
    if dataset_nombre:
        pill_cls  = "corp-header-pill"
        dot_html  = '<span class="corp-header-pill-dot"></span>'
        pill_text = f"{dot_html} {dataset_nombre}"
    else:
        pill_cls  = "corp-header-pill inactive"
        dot_html  = '<span class="corp-header-pill-dot"></span>'
        pill_text = f"{dot_html} Sin datos"

    st.markdown(f"""
    <div class="corp-header">
      <div class="corp-header-inner">
        <div class="corp-header-logo">⚙️</div>
        <div class="corp-header-text">
          <div class="corp-header-title">SISTEMA CEP — Línea de Empaque de Mogolla</div>
          <div class="corp-header-sub">
            Molinos Santa Marta S.A.S. &nbsp;·&nbsp; Control Estadístico de Procesos
            &nbsp;·&nbsp; Sacos 40 kg &nbsp;·&nbsp; v3.0
          </div>
        </div>
        <div class="{pill_cls}">{pill_text}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── KPI Card ──────────────────────────────────────────────────────────────────

def kpi_card_html(valor, label, sub="", estado="", icono="", badge_html_str=""):
    """
    Retorna HTML de una tarjeta KPI.

    estado: '' | 'danger' | 'warning' | 'success' | 'neutral'
    icono:  emoji o texto corto mostrado como decorador superior
    badge_html_str: HTML de badge opcional (resultado de badge_html())
    """
    val_cls   = estado if estado in ("danger", "warning", "success") else ""
    icon_html = (f'<span class="kpi-icon" aria-hidden="true">{icono}</span>'
                 if icono else "")
    sub_html  = (f'<div class="kpi-sub" title="{sub}">{sub}</div>'
                 if sub else "")
    bdg_html  = (f'<div style="margin-top:.28rem">{badge_html_str}</div>'
                 if badge_html_str else "")

    return (
        f'<div class="kpi-card {estado}">'
        f'{icon_html}'
        f'<div class="kpi-value {val_cls}">{valor}</div>'
        f'<div class="kpi-label">{label}</div>'
        f'{sub_html}'
        f'{bdg_html}'
        f'</div>'
    )


def render_kpi(valor, label, sub="", borde="", color=""):
    """
    API de compatibilidad con v2.0.
    borde mapea a estado: red→danger, yellow→warning, green→success.
    """
    _map = {"red": "danger", "yellow": "warning", "green": "success", "": ""}
    estado = _map.get(borde, "")
    return kpi_card_html(valor=valor, label=label, sub=sub, estado=estado)


def render_kpi_row(cards: list):
    """
    Renderiza una fila de KPI cards en un div grid.
    cards: lista de strings HTML (resultado de kpi_card_html).
    """
    inner = "\n".join(cards)
    return f'<div class="kpi-grid">{inner}</div>'


# ── Badge ─────────────────────────────────────────────────────────────────────

def badge_html(texto, tipo=""):
    """
    tipo: 'green' | 'yellow' | 'red' | ''
    """
    return f'<span class="badge badge-{tipo}">{texto}</span>'


# ── Alarm box ─────────────────────────────────────────────────────────────────

def alarm_html(tipo, mensaje):
    """
    tipo: 'critical' | 'warning' | 'info' | 'ok'
    Alias: render_alarm (compatibilidad v2.0).
    """
    return f'<div class="alarm-box alarm-{tipo}">{mensaje}</div>'


def render_alarm(tipo, mensaje):
    """Alias de compatibilidad v2.0."""
    return alarm_html(tipo, mensaje)


# ── Section title ─────────────────────────────────────────────────────────────

def section_title_html(titulo):
    return f'<div class="section-title">{titulo}</div>'


def render_section_title(titulo):
    """Alias de compatibilidad v2.0."""
    return section_title_html(titulo)


# ── Divider ───────────────────────────────────────────────────────────────────

def divider_html():
    return '<hr class="divider">'


# ── Info chip ─────────────────────────────────────────────────────────────────

def chip_html(texto):
    return f'<span class="chip">{texto}</span>'


# =============================================================================
# SIDEBAR — Renderizador profesional
# =============================================================================

def render_sidebar(pages_dict: dict, pagina_activa: str, dataset_info: str = ""):
    """
    Construye el sidebar de navegación SPA con diseño industrial.

    pages_dict: { "GRUPO LABEL": [("Label página", "key"), ...], ... }
    pagina_activa: key de la página activa actual
    dataset_info: texto informativo del dataset cargado
    """
    with st.sidebar:
        # ── Brand ──────────────────────────────────────────────────────────
        st.markdown("""
        <div class="sidebar-brand">
          <div class="sidebar-brand-name">⚙️ CEP Navigator</div>
          <div class="sidebar-brand-sub">Molinos Santa Marta S.A.S.</div>
        </div>
        """, unsafe_allow_html=True)

        # ── Dataset status ─────────────────────────────────────────────────
        if dataset_info:
            st.markdown(f"""
            <div style="padding:.6rem 1rem;background:rgba(26,122,74,.12);
                 border-bottom:1px solid #1E3448;">
              <div style="font-size:.65rem;color:#5DDBA3;font-weight:700;
                   text-transform:uppercase;letter-spacing:.8px">
                ● Dataset activo
              </div>
              <div style="font-size:.72rem;color:rgba(255,255,255,.55);
                   margin-top:2px;white-space:nowrap;overflow:hidden;
                   text-overflow:ellipsis">{dataset_info}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="padding:.6rem 1rem;background:rgba(176,176,176,.08);
                 border-bottom:1px solid #1E3448;">
              <div style="font-size:.65rem;color:rgba(255,255,255,.3);
                   font-weight:700;text-transform:uppercase;letter-spacing:.8px">
                ○ Sin datos cargados
              </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Navegación ─────────────────────────────────────────────────────
        for grupo, items in pages_dict.items():
            st.markdown(f'<div class="sidebar-section-label">{grupo}</div>',
                        unsafe_allow_html=True)
            for label, key in items:
                activo = pagina_activa == key
                if st.button(
                    label,
                    key=f"nav_{key}",
                    width="stretch",
                    type="primary" if activo else "secondary",
                ):
                    st.session_state["pagina"] = key

            st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

        # ── Footer ─────────────────────────────────────────────────────────
        st.markdown("""
        <div class="sidebar-footer">
          v3.0 &nbsp;·&nbsp; Molinos Santa Marta S.A.S.<br>
          CEP · Línea Empaque Mogolla
        </div>
        """, unsafe_allow_html=True)


# =============================================================================
# UTILIDADES DE STATUS
# =============================================================================

def cpk_status(cpk: float) -> tuple:
    """
    Retorna (estado_css, texto_badge, clase_badge) según Cpk.
    Reemplaza cpk_st() de calculos_cep para la capa visual.
    (La lógica de colores hex queda en calculos_cep para compatibilidad.)
    """
    if cpk >= 1.33:
        return "success", "CAPAZ",    "green"
    if cpk >= 1.0:
        return "warning", "MARGINAL", "yellow"
    return "danger", "INCAPAZ", "red"