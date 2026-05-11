"""
=============================================================================
  SISTEMA DE CONTROL ESTADÍSTICO DE PROCESOS  v2.0
  Molinos Santa Marta S.A.S. — Línea de Empaque de Mogolla
  Universidad del Magdalena · Facultad de Ingeniería
  Asignatura: Control Estadístico de Procesos · Grupo 5
=============================================================================
  Instalación:
      pip install streamlit pandas numpy scipy plotly openpyxl
  Ejecución:
      python -m streamlit run app_molinos.py
=============================================================================
  Estructura del proyecto (todos en la misma carpeta):
      app_molinos.py       ← este archivo (punto de entrada)
      calculos_cep.py      ← funciones estadísticas y de exportación
      interfaz_estilos.py  ← CSS, paleta de colores, componentes HTML
      visualizaciones.py   ← figuras Plotly
=============================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import io
from scipy import stats
import plotly.graph_objects as go
import warnings
warnings.filterwarnings("ignore")

# ── Módulos del proyecto ──────────────────────────────────────────────────────
from interfaz_estilos import (
    CP, CR, CG, CY, CN,
    configurar_pagina, aplicar_estilos,
    render_encabezado, render_alarm, render_section_title
)
from calculos_cep import (
    LSL, USL, NOMINAL, CONTROL_CONSTANTS,
    detect_subgroups, validate_data,
    compute_spc, compute_eco, cpk_st,
    generate_sample_excel, export_excel,
)
from visualizaciones import (
    fig_histogram, fig_xbar, fig_r,
    fig_power, fig_gauge, fig_simulador_campanas,
    fig_campanas_potencia,
)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN E INICIALIZACIÓN
# ─────────────────────────────────────────────────────────────────────────────
configurar_pagina()
aplicar_estilos()
render_encabezado()

# ─────────────────────────────────────────────────────────────────────────────
# CARGA DE DATOS
# ─────────────────────────────────────────────────────────────────────────────
sample_bytes = generate_sample_excel()
upc, dlc = st.columns([4, 1])
with upc:
    uploaded = st.file_uploader(
        "📂 Cargar archivo Excel con datos de muestreo (.xlsx)",
        type=["xlsx", "xls"],
        help="Columnas obligatorias: X1, X2, ..., Xn (n entre 2 y 10). Opcionales: Subgrupo, Hora."
    )
with dlc:
    st.markdown("<br>", unsafe_allow_html=True)
    st.download_button(
        "⬇ Plantilla", sample_bytes, "plantilla_CEP.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width='stretch'
    )

if uploaded is None:
    st.markdown(render_alarm("info", """
        <strong>📋 Instrucciones de uso</strong><br><br>
        1. Descarga la <strong>plantilla de ejemplo</strong> con el botón de arriba<br>
        2. Completa con los datos de pesaje de tu línea (columnas X1…Xn)<br>
        3. Carga el archivo Excel con el botón de arriba<br>
        4. El sistema calculará automáticamente CEP, capacidad, potencia y economía<br><br>
        <strong>Límites activos:</strong> LIE = 39.5 kg · LSE = 40.5 kg · Nominal = 40.0 kg
    """), unsafe_allow_html=True)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# PROCESAMIENTO — limpieza silenciosa
# ─────────────────────────────────────────────────────────────────────────────
_proc_ok = False
with st.container():
    try:
        df_raw = pd.read_excel(uploaded)
        _xcand = sorted(
            [c for c in df_raw.columns
             if str(c).strip().upper().startswith("X") and str(c).strip()[1:].isdigit()],
            key=lambda c: int(str(c).strip()[1:])
        )
        if not _xcand:
            st.error("❌ No se encontraron columnas X1, X2,... en el archivo.")
            st.stop()
        df_raw[_xcand] = df_raw[_xcand].apply(pd.to_numeric, errors="coerce")
        df_raw = df_raw.dropna(subset=_xcand, how="all").reset_index(drop=True)
        df_raw = df_raw.dropna(subset=_xcand, how="any").reset_index(drop=True)
        _keep  = [c for c in df_raw.columns
                  if (str(c).strip().upper().startswith("X") and str(c).strip()[1:].isdigit())
                  or str(c).lower() in ("subgrupo", "hora", "fecha", "turno", "operario")]
        df_raw = df_raw[[c for c in df_raw.columns if c in _keep]]

        if len(df_raw) < 2:
            st.warning("⚠ Se necesitan al menos 2 subgrupos completos. Revisa el archivo.")
            st.stop()

        n, x_cols = detect_subgroups(df_raw)
        issues    = validate_data(df_raw, x_cols)
        s         = compute_spc(df_raw, x_cols, n)
        _proc_ok  = True
    except Exception as _e:
        st.error("❌ No se pudo procesar el archivo. Verifica que tenga columnas X1, X2,... con valores numéricos.")
        with st.expander("Ver detalle técnico"):
            st.code(str(_e))
        st.stop()

if _proc_ok:
    for iss in issues:
        st.warning(f"⚠ {iss}")

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE — parámetros económicos (persisten al cambiar de página)
# ─────────────────────────────────────────────────────────────────────────────
st.session_state.setdefault("eco_cost_kg",   25.0)
st.session_state.setdefault("eco_prod_h",    255)
st.session_state.setdefault("eco_hours_day", 16.0)
st.session_state.setdefault("eco_days_month",30)
st.session_state.setdefault("eco_lote",      200)
st.session_state.setdefault("eco_p_rechazo", 0.10)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN INLINE + KPIs — solo se ejecutan si el procesamiento fue exitoso
# ─────────────────────────────────────────────────────────────────────────────
# Protección explícita: s, n, x_cols solo existen cuando _proc_ok es True.
# (Los st.stop() en el bloque de carga ya detienen el script en caso de error,
#  pero este guard es una salvaguarda adicional ante cualquier re-run parcial.)
if not _proc_ok:
    st.stop()

# Los widgets de muestreo solo son relevantes en la página de Potencia/ARL.
_pagina_usa_muestreo = st.session_state.get("pagina", "capacidad") in ("potencia",)
if _pagina_usa_muestreo:
    st.markdown(render_section_title("⚙️ Parámetros de Muestreo"), unsafe_allow_html=True)
    c5, c6 = st.columns(2)
    with c5:
        n_proposed = st.slider(
            "n tamaño de muestra propuesto", 2, 10,
            value=min(n + 1, 10), key="slider_n_proposed"
        )
    st.session_state["n_proposed_val"] = n_proposed
    with c6:
        freq_min = st.number_input(
            "Frec. muestreo (min)", 1, value=20, key="input_freq_min"
        )
    st.session_state["freq_min_val"] = freq_min
else:
    # Valores por defecto silenciosos — los widgets no se renderizan
    n_proposed = st.session_state.get("n_proposed_val", 5)
    freq_min   = st.session_state.get("freq_min_val", 20)

# KPIs globales — s está garantizado definido aquí
_kpi_over_g    = max(0.0, s["xbar_bar"] - NOMINAL) * 1000
_kpi_sacos_mes = (st.session_state["eco_prod_h"]
                  * st.session_state["eco_hours_day"]
                  * st.session_state["eco_days_month"])
_kpi_over_kg   = max(0.0, s["xbar_bar"] - NOMINAL) * _kpi_sacos_mes
_kpi_costo_mes = _kpi_over_kg * st.session_state["eco_cost_kg"]
_kpi_costo_anio= _kpi_costo_mes * 12
_kpi_sacos_ext = (_kpi_over_kg * 12 / 40) if _kpi_over_g > 0 else 0.0

cpk_color, cpk_text, cpk_badge = cpk_st(s["Cpk"])
n_rules_hit = sum(1 for r in s["sens_rules"] if r["hits"])

# ─────────────────────────────────────────────────────────────────────────────
# KPIs
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
k1, k2, k3, k4, k5 = st.columns(5)

bord = "red" if s["Cpk"] < 1.0 else "yellow" if s["Cpk"] < 1.33 else "green"
with k1:
    st.markdown(f"""<div class="kpi-card {bord}">
    <div class="kpi-value" style="color:{cpk_color}">{s['Cpk']:.3f}</div>
    <div class="kpi-label">Índice Cpk</div>
    <div class="kpi-sub"><span class="badge {cpk_badge}">{cpk_text}</span></div></div>""",
    unsafe_allow_html=True)

pnc = s["pnc_total"]*100
pb  = "red" if pnc > 5 else "yellow" if pnc > 0.27 else "green"
pc  = CR if pnc > 5 else CY if pnc > 0.27 else CG
with k2:
    st.markdown(f"""<div class="kpi-card {pb}">
    <div class="kpi-value" style="color:{pc}">{pnc:.2f}%</div>
    <div class="kpi-label">% Producto No Conforme</div>
    <div class="kpi-sub">↓{s['pnc_low']*100:.2f}% LIE | ↑{s['pnc_high']*100:.2f}% LSE</div></div>""",
    unsafe_allow_html=True)

with k3:
    st.markdown(f"""<div class="kpi-card {'yellow' if _kpi_over_g > 0 else 'green'}">
    <div class="kpi-value" style="color:{CY if _kpi_over_g > 0 else CG}">{_kpi_over_g:+.1f} g</div>
    <div class="kpi-label">Sobrellenado promedio</div>
    <div class="kpi-sub">x̄ = {s['xbar_bar']:.4f} kg</div></div>""",
    unsafe_allow_html=True)

with k4:
    st.markdown(f"""<div class="kpi-card {'red' if _kpi_costo_mes > 0 else 'green'}">
    <div class="kpi-value" style="color:{CR if _kpi_costo_mes > 0 else CG}">${_kpi_costo_mes:,.0f}</div>
    <div class="kpi-label">Pérdida mensual (COP)</div>
    <div class="kpi-sub">${_kpi_costo_anio:,.0f}/año · {_kpi_sacos_ext:.0f} sacos extra</div></div>""",
    unsafe_allow_html=True)

rb = "red" if n_rules_hit >= 3 else "yellow" if n_rules_hit >= 1 else "green"
rc = CR if n_rules_hit >= 3 else CY if n_rules_hit >= 1 else CG
with k5:
    st.markdown(f"""<div class="kpi-card {rb}">
    <div class="kpi-value" style="color:{rc}">{n_rules_hit}/8</div>
    <div class="kpi-label">Reglas sensibilización</div>
    <div class="kpi-sub">{'⚠ Causas asignables' if n_rules_hit else '✅ Sin patrones anómalos'}</div></div>""",
    unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — NAVEGACIÓN SPA
# ─────────────────────────────────────────────────────────────────────────────

# Páginas disponibles agrupadas por fase
_PAGES = {
    "🏭 FASE I": [
        ("📊 Capacidad",      "capacidad"),
        ("📈 Cartas CEP",     "cartas_cep"),
        ("🔬 Diagnóstico",    "diagnostico"),
    ],
    "📊 FASE II": [
        ("⚡ Potencia",       "potencia"),
        ("🔴 Monitoreo",      "monitoreo"),
    ],
    "💰 ANÁLISIS ECONÓMICO": [
        ("💰 Análisis Económico", "eco_analisis"),
    ],
}

# Inicializar página por defecto
if "pagina" not in st.session_state:
    st.session_state["pagina"] = "capacidad"


def render_sidebar():
    """Construye el menú lateral de navegación SPA."""
    with st.sidebar:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#1B4F72,#154360);
             color:white;padding:1rem 1.2rem;border-radius:10px;margin-bottom:1.2rem;">
          <div style="font-size:1rem;font-weight:700;letter-spacing:-.3px">⚙️ CEP Menu</div>
          <div style="font-size:.72rem;opacity:.8;margin-top:.2rem">Molinos Santa Marta S.A.S.</div>
        </div>
        """, unsafe_allow_html=True)

        for grupo, items in _PAGES.items():
            st.markdown(
                f'<div style="font-size:.68rem;font-weight:700;color:#7F8C8D;'
                f'text-transform:uppercase;letter-spacing:.8px;'
                f'margin:.9rem 0 .3rem;padding-left:.2rem">{grupo}</div>',
                unsafe_allow_html=True
            )
            for label, key in items:
                activo = st.session_state["pagina"] == key
                if st.button(
                    label,
                    key=f"nav_{key}",
                    width='stretch',
                    type="primary" if activo else "secondary",
                ):
                    st.session_state["pagina"] = key
                    # No st.rerun() — Streamlit re-renders automatically on session_state change

        st.markdown("---")
        st.markdown(
            '<div style="font-size:.7rem;color:#95A5A6;text-align:center">'
            'v2.1 · Molinos Santa Marta S.A.S.</div>',
            unsafe_allow_html=True
        )


render_sidebar()
pagina_activa = st.session_state["pagina"]

# ─────────────────────────────────────────────────────────────────────────────
# ROUTER — muestra la sección activa
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE PÁGINA
# ─────────────────────────────────────────────────────────────────────────────

def page_capacidad():
    global s, n_rules_hit, cpk_color, cpk_text, cpk_badge, freq_min, n_proposed

    # ── Override manual de especificaciones ───────────────────────────────────
    st.markdown(render_section_title("⚙️ Especificaciones del Proceso"), unsafe_allow_html=True)
    esp_col1, esp_col2, esp_col3 = st.columns(3)
    with esp_col1:
        lsl_input = st.number_input("LSL — Límite inferior de especificación (kg)",
                                    value=float(LSL), format="%.4f",
                                    step=0.01, key="cap_lsl")
    with esp_col2:
        usl_input = st.number_input("USL — Límite superior de especificación (kg)",
                                    value=float(USL), format="%.4f",
                                    step=0.01, key="cap_usl")
    with esp_col3:
        st.metric("Tolerancia total", f"{usl_input - lsl_input:.4f} kg",
                  delta=f"{(usl_input-lsl_input - (USL-LSL))*1000:+.1f} g vs default")

    # Recalcular índices con los valores ingresados
    _sig  = s["sigma_st"]; _xb = s["xbar_bar"]
    _Cp   = (usl_input - lsl_input) / (6 * _sig)
    _Cpu  = (usl_input - _xb) / (3 * _sig)
    _Cpl  = (_xb - lsl_input) / (3 * _sig)
    _Cpk  = min(_Cpu, _Cpl)
    from scipy import stats as _stats
    _pnc_low  = _stats.norm.cdf(lsl_input, _xb, _sig)
    _pnc_high = 1 - _stats.norm.cdf(usl_input, _xb, _sig)
    _pnc_tot  = _pnc_low + _pnc_high
    _cpk_color, _cpk_txt, _cpk_badge = cpk_st(_Cpk)

    # Aviso si el usuario cambió los defaults
    if abs(lsl_input - LSL) > 1e-6 or abs(usl_input - USL) > 1e-6:
        st.markdown(render_alarm("warning",
            f"⚠ Usando especificaciones manuales: LSL = {lsl_input} kg | USL = {usl_input} kg. "
            f"Los índices de capacidad han sido recalculados."), unsafe_allow_html=True)

    ch, cg = st.columns([3, 1])
    with ch:
        st.plotly_chart(fig_histogram(s), key="chart_histogram")
    with cg:
        st.plotly_chart(fig_gauge(_Cpk), key="chart_gauge")
        st.markdown(f"""<div style="background:white;border-radius:8px;padding:.8rem;
            box-shadow:0 1px 6px rgba(0,0,0,.07);font-size:.82rem">
        <div class="section-title" style="margin-top:0">Índices</div>
        <table style="width:100%;border-collapse:collapse">
        <tr><td style="color:#7F8C8D;padding:3px 0">Cp</td><td style="text-align:right;font-family:monospace;font-weight:600">{_Cp:.4f}</td></tr>
        <tr><td style="color:#7F8C8D;padding:3px 0">Cpu</td><td style="text-align:right;font-family:monospace;font-weight:600">{_Cpu:.4f}</td></tr>
        <tr><td style="color:#7F8C8D;padding:3px 0">Cpl</td><td style="text-align:right;font-family:monospace;font-weight:600">{_Cpl:.4f}</td></tr>
        <tr style="border-top:2px solid #D5E8F3"><td style="font-weight:700;color:{_cpk_color};padding:5px 0">Cpk</td>
        <td style="text-align:right;font-family:monospace;font-weight:700;color:{_cpk_color}">{_Cpk:.4f}</td></tr>
        </table></div>""", unsafe_allow_html=True)

    st.markdown(render_section_title("Estadísticas"), unsafe_allow_html=True)
    sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)
    for col, lbl, val in [
        (sc1, "x̄ global",    f"{s['xbar_bar']:.4f} kg"),
        (sc2, "σ̂ (R̄/d₂)",   f"{s['sigma_st']:.4f} kg"),
        (sc3, "R̄",           f"{s['R_bar']:.4f} kg"),
        (sc4, "n",            str(s["n"])),
        (sc5, "Subgrupos",    str(len(s["df"]))),
        (sc6, "PNC total",    f"{_pnc_tot*100:.3f}%"),
    ]:
        with col: st.metric(lbl, val)

    sw = s["sw"]
    if sw["W"]:
        cls     = "alarm-ok" if sw["normal"] else "alarm-warning"
        verdict = "✅ Normalidad confirmada (p > 0.05)" if sw["normal"] else "⚠ Posible no normalidad (p ≤ 0.05)"
        st.markdown(f"""<div class="alarm-box {cls}">
        <strong>🔬 Test Shapiro-Wilk</strong> &nbsp;|&nbsp; W = {sw['W']:.5f} &nbsp;|&nbsp;
        p = {sw['p']:.5f} &nbsp;|&nbsp; {verdict}
        </div>""", unsafe_allow_html=True)

    with st.expander("📋 Tabla de subgrupos"):
        st.dataframe(s["df"].round(4), key="df_subgrupos")


def page_cartas_cep():
    global s, n_rules_hit, cpk_color, cpk_text, cpk_badge, freq_min, n_proposed

    ca, cb = st.columns(2)
    with ca:
        cls = "alarm-ok" if not s["signals_x"] else "alarm-critical"
        msg = (f"✅ Carta X̄: Sin puntos fuera de control." if not s["signals_x"]
               else f"❌ Carta X̄: {len(s['signals_x'])}/{len(s['df'])} fuera de límites.")
        st.markdown(f'<div class="alarm-box {cls}">{msg}</div>', unsafe_allow_html=True)
    with cb:
        cls = "alarm-ok" if not s["signals_r"] else "alarm-critical"
        msg = (f"✅ Carta R: Variabilidad bajo control." if not s["signals_r"]
               else f"❌ Carta R: {len(s['signals_r'])}/{len(s['df'])} fuera de control.")
        st.markdown(f'<div class="alarm-box {cls}">{msg}</div>', unsafe_allow_html=True)

    st.plotly_chart(fig_xbar(s), key="chart_xbar")
    st.plotly_chart(fig_r(s),    key="chart_r")

    with st.expander("📐 Constantes y límites"):
        co = s["consts"]
        st.markdown(f"""
        |Parámetro|Valor| |Parámetro|Valor|
        |---------|-----|-|---------|-----|
        |n|**{s['n']}**| |LCS X̄|**{s['UCL_x']:.4f} kg**|
        |d₂|**{co['d2']}**| |LC X̄|**{s['xbar_bar']:.4f} kg**|
        |A₂|**{co['A2']}**| |LCI X̄|**{s['LCL_x']:.4f} kg**|
        |D₃|**{co['D3']}**| |LCS R|**{s['UCL_r']:.4f} kg**|
        |D₄|**{co['D4']}**| |R̄|**{s['R_bar']:.4f} kg**|
        |σ̂|**{s['sigma_st']:.4f} kg**| |LCI R|**{s['LCL_r']:.4f} kg**|
        """)


def page_diagnostico():
    global s, n_rules_hit, cpk_color, cpk_text, cpk_badge, freq_min, n_proposed

    st.markdown(render_section_title("🚦 Diagnóstico Integral"), unsafe_allow_html=True)
    alarmas = []
    if s["Cpk"] < 1.0:     alarmas.append(("critical", f"🔴 Proceso INCAPAZ: Cpk={s['Cpk']:.3f}. Reducir variabilidad urgente."))
    elif s["Cpk"] < 1.33:  alarmas.append(("warning",  f"🟡 Proceso MARGINAL: Cpk={s['Cpk']:.3f}. Monitoreo intensivo."))
    else:                   alarmas.append(("ok",       f"🟢 Proceso CAPAZ: Cpk={s['Cpk']:.3f} ≥ 1.33."))

    des_g = (s["xbar_bar"] - NOMINAL) * 1000
    if abs(des_g) > 200:   alarmas.append(("warning", f"🟡 Descentrado {des_g:+.1f} g sobre nominal. Ajustar dosificador."))
    else:                   alarmas.append(("ok",      f"🟢 Centrado aceptable: desviación = {des_g:+.1f} g."))

    if s["signals_x"]:     alarmas.append(("critical", f"🔴 {len(s['signals_x'])} subgrupo(s) fuera de límites en carta X̄."))
    else:                   alarmas.append(("ok",       "🟢 Carta X̄: proceso bajo control estadístico."))

    if s["signals_r"]:     alarmas.append(("critical", f"🔴 {len(s['signals_r'])} subgrupo(s) con variabilidad fuera de control."))
    else:                   alarmas.append(("ok",       "🟢 Carta R: variabilidad estable."))

    pnc_t = s["pnc_total"]
    if pnc_t > 0.05:       alarmas.append(("critical", f"🔴 PNC={pnc_t*100:.2f}%. Riesgo legal y comercial elevado."))
    elif pnc_t > 0.0027:   alarmas.append(("warning",  f"🟡 PNC={pnc_t*100:.3f}%. Supera umbral 3σ."))
    else:                   alarmas.append(("ok",       f"🟢 PNC={pnc_t*100:.4f}% — dentro del estándar."))

    sw = s["sw"]
    if sw["W"]:
        if not sw["normal"]: alarmas.append(("warning", f"🟡 Shapiro-Wilk p={sw['p']:.4f} sugiere no normalidad."))
        else:                 alarmas.append(("ok",      f"🟢 Normalidad confirmada: p={sw['p']:.4f}."))

    if n_rules_hit:          alarmas.append(("warning", f"🟡 {n_rules_hit} regla(s) de sensibilización activada(s)."))
    else:                    alarmas.append(("ok",       "🟢 Ninguna regla de sensibilización activada."))

    for tipo, msg in alarmas:
        st.markdown(render_alarm(tipo, msg), unsafe_allow_html=True)

    st.markdown(render_section_title("🔎 Reglas de Sensibilización (Nelson / Western Electric)"),
                unsafe_allow_html=True)
    for r in s["sens_rules"]:
        css  = "rule-hit" if r["hits"] else "rule-ok"
        icon = "⚠️" if r["hits"] else "✅"
        sub  = f" → Subgrupos: {[h+1 for h in r['hits']]}" if r["hits"] else ""
        st.markdown(f'<div class="{css}">{icon} <strong>Regla {r["rule"]}:</strong> {r["desc"]}{sub}</div>',
                    unsafe_allow_html=True)


def page_potencia():
    global s, n_rules_hit, cpk_color, cpk_text, cpk_badge, freq_min, n_proposed


    # ── Variables de Fase I (autollenado desde s) ─────────────────────────────
    _mu0  = s["xbar_bar"]
    _sig  = s["sigma_st"]
    _n    = s["n"]
    _UCL  = s["UCL_x"]
    _LCL  = s["LCL_x"]
    _conf = 95.00

    # ── Inicializar session_state ─────────────────────────────────────────────
    if "pot_mu1_val"    not in st.session_state: st.session_state["pot_mu1_val"]    = ""
    if "pot_calculado"  not in st.session_state: st.session_state["pot_calculado"]  = False
    if "arl_mu1_val"    not in st.session_state: st.session_state["arl_mu1_val"]    = ""
    if "arl_calculado"  not in st.session_state: st.session_state["arl_calculado"]  = False

    # ══════════════════════════════════════════════════════════════════════════
    # BLOQUE A — ANÁLISIS DE POTENCIA
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1B4F72,#2E86C1);color:white;
         padding:1.1rem 1.5rem;border-radius:10px;margin-bottom:.8rem;">
    <h3 style="margin:0 0 .25rem;font-size:1.15rem;">🔬 Análisis de Potencia Estadística</h3>
    <p style="margin:0;opacity:.85;font-size:.82rem;">
    Los campos azules se autollenan desde la Fase I. Solo debes ingresar la Nueva Media (μ₁).</p>
    </div>
    """, unsafe_allow_html=True)

    pot_col1, pot_col2 = st.columns([1, 1])

    with pot_col1:
        st.markdown(render_section_title("📥 Parámetros de Fase I (automáticos)"),
                    unsafe_allow_html=True)
        pa1, pa2 = st.columns(2)
        with pa1:
            st.number_input("Media actual (μ₀)", value=float(f"{_mu0:.4f}"),
                            format="%.4f", disabled=True, key="pot_mu0")
            st.number_input("LCS", value=float(f"{_UCL:.4f}"),
                            format="%.4f", disabled=True, key="pot_UCL")
        with pa2:
            st.number_input("Sigma (σ)", value=float(f"{_sig:.6f}"),
                            format="%.6f", disabled=True, key="pot_sig")
            st.number_input("LCI", value=float(f"{_LCL:.4f}"),
                            format="%.4f", disabled=True, key="pot_LCL")
        pb1, pb2 = st.columns(2)
        with pb1:
            st.number_input("Tamaño de muestra (n)", value=int(_n),
                            disabled=True, key="pot_n")
        with pb2:
            st.number_input("Nivel de confianza (%)", value=_conf,
                            format="%.2f", disabled=True, key="pot_conf")

    with pot_col2:
        st.markdown(render_section_title("✏️ Parámetro manual"), unsafe_allow_html=True)
        _mu1_pot_txt = st.text_input(
            "Nueva Media (μ₁) en kg",
            value=st.session_state["pot_mu1_val"],
            placeholder=f"Ej: {_mu0 - _sig:.3f}",
            help="Ingresa la media desplazada que deseas evaluar (kg)",
            key="pot_mu1_txt"
        )
        st.session_state["pot_mu1_val"] = _mu1_pot_txt

        if st.button("🔬 Calcular Potencia", type="primary", key="btn_pot_calcular",
                     width='stretch'):
            if not _mu1_pot_txt.strip():
                st.warning("⚠ Ingresa un valor para μ₁ antes de calcular.")
                st.session_state["pot_calculado"] = False
            else:
                try:
                    float(_mu1_pot_txt.replace(",", "."))
                    st.session_state["pot_calculado"] = True
                except ValueError:
                    st.warning("⚠ Ingresa un número válido para μ₁ (usa punto como decimal).")
                    st.session_state["pot_calculado"] = False

    # ── Resultados de Potencia ─────────────────────────────────────────────────
    if st.session_state["pot_calculado"] and st.session_state["pot_mu1_val"].strip():
        try:
            mu1_pot = float(st.session_state["pot_mu1_val"].replace(",", "."))
            fig_pot, res_pot = fig_campanas_potencia(_mu0, _sig, _n, _UCL, _LCL, mu1_pot)

            beta_p  = res_pot["beta"]
            power_p = res_pot["power"]
            ARL0_p  = res_pot["ARL0"]
            ARL1_p  = res_pot["ARL1"]
            pc_     = res_pot["pow_color"]

            st.markdown("<br>", unsafe_allow_html=True)
            kp1, kp2, kp3, kp4 = st.columns(4)
            pow_bord = "green" if power_p >= 0.9 else "yellow" if power_p >= 0.5 else "red"

            with kp1:
                st.markdown(f"""<div class="kpi-card {pow_bord}">
                <div class="kpi-value" style="color:{pc_}">{power_p:.2%}</div>
                <div class="kpi-label">Potencia (1 − β)</div>
                <div class="kpi-sub">Probabilidad de detectar el cambio</div></div>""",
                unsafe_allow_html=True)

            with kp2:
                col_b = CR if beta_p > 0.5 else CY if beta_p > 0.1 else CG
                st.markdown(f"""<div class="kpi-card {'red' if beta_p>0.5 else 'yellow' if beta_p>0.1 else 'green'}">
                <div class="kpi-value" style="color:{col_b}">{beta_p:.4f}</div>
                <div class="kpi-label">Error Tipo II (β)</div>
                <div class="kpi-sub">P(no detectar el cambio)</div></div>""",
                unsafe_allow_html=True)

            with kp3:
                st.markdown(f"""<div class="kpi-card">
                <div class="kpi-value" style="color:{CP}">{ARL0_p:.0f}</div>
                <div class="kpi-label">ARL₀</div>
                <div class="kpi-sub">Muestras entre falsas alarmas</div></div>""",
                unsafe_allow_html=True)

            with kp4:
                col_arl = CG if ARL1_p <= 5 else CY if ARL1_p <= 20 else CR
                st.markdown(f"""<div class="kpi-card {'green' if ARL1_p<=5 else 'yellow' if ARL1_p<=20 else 'red'}">
                <div class="kpi-value" style="color:{col_arl}">{ARL1_p:.1f}</div>
                <div class="kpi-label">ARL₁</div>
                <div class="kpi-sub">Muestras para detectar el cambio</div></div>""",
                unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            st.plotly_chart(fig_pot, key="chart_pot_campanas")

            delta_g = (mu1_pot - _mu0) * 1000
            if power_p >= 0.9:
                css_i = "alarm-ok"
                msg_i = (f"✅ Con μ₁ = {mu1_pot:.4f} kg (desplazamiento {delta_g:+.1f} g), "
                         f"la carta detecta el cambio con <strong>{power_p:.1%} de potencia</strong>. "
                         f"En promedio se necesitan <strong>{ARL1_p:.1f} muestras</strong> para dar señal.")
            elif power_p >= 0.5:
                css_i = "alarm-warning"
                msg_i = (f"⚠️ Potencia moderada de <strong>{power_p:.1%}</strong> para μ₁ = {mu1_pot:.4f} kg. "
                         f"Se necesitan ~<strong>{ARL1_p:.1f} muestras</strong> para detectar el cambio. "
                         f"Considera aumentar el tamaño de subgrupo.")
            else:
                css_i = "alarm-critical"
                msg_i = (f"❌ Potencia muy baja (<strong>{power_p:.1%}</strong>) para μ₁ = {mu1_pot:.4f} kg. "
                         f"La carta tardaría ~<strong>{ARL1_p:.0f} muestras</strong> en detectar el cambio. "
                         f"Se recomienda aumentar n o reducir el intervalo de muestreo.")
            st.markdown(f'<div class="alarm-box {css_i}">{msg_i}</div>', unsafe_allow_html=True)

        except ValueError:
            st.warning("⚠ Valor de μ₁ inválido.")
    else:
        st.markdown(render_alarm("info",
            "👆 Ingresa una <strong>Nueva Media (μ₁)</strong> y pulsa <strong>Calcular Potencia</strong> "
            "para visualizar la gráfica de dos campanas y los indicadores de detección."
        ), unsafe_allow_html=True)

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # BLOQUE B — ARL y ATS
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("""
    <div style="background:linear-gradient(135deg,#154360,#1B4F72);color:white;
         padding:1.1rem 1.5rem;border-radius:10px;margin-bottom:.8rem;">
    <h3 style="margin:0 0 .25rem;font-size:1.15rem;">📊 ARL y ATS</h3>
    <p style="margin:0;opacity:.85;font-size:.82rem;">
    Calcula el tiempo promedio de alarma (ATS) dado un cambio en la media.</p>
    </div>
    """, unsafe_allow_html=True)

    arl_col1, arl_col2 = st.columns([1, 1])

    with arl_col1:
        arl_n    = st.number_input("Tamaño de muestra (n)", min_value=2, max_value=10,
                                   value=int(_n), key="arl_n")
        _arl_mu1_txt = st.text_input(
            "Media con cambio (μ₁) en kg",
            value=st.session_state["arl_mu1_val"],
            placeholder=f"Ej: {_mu0 - _sig:.3f}",
            help="Nueva media del proceso después del corrimiento",
            key="arl_mu1_txt"
        )
        st.session_state["arl_mu1_val"] = _arl_mu1_txt

        arl_alfa = st.number_input("Nivel de significancia (α)", value=0.0027,
                                   format="%.4f", min_value=0.0001, max_value=0.10,
                                   key="arl_alfa",
                                   help="0.0027 corresponde a límites 3-sigma")

    with arl_col2:
        arl_h    = st.number_input("Tiempo entre muestras",
                                   value=float(freq_min), min_value=0.1,
                                   format="%.1f", key="arl_h")
        arl_unit = st.selectbox("Unidad de tiempo", ["Minutos", "Horas"],
                                key="arl_unit")
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📊 Calcular ARL / ATS", type="primary", key="btn_arl_calcular",
                     width='stretch'):
            if not _arl_mu1_txt.strip():
                st.warning("⚠ Ingresa un valor para μ₁ antes de calcular.")
                st.session_state["arl_calculado"] = False
            else:
                try:
                    float(_arl_mu1_txt.replace(",", "."))
                    st.session_state["arl_calculado"] = True
                except ValueError:
                    st.warning("⚠ Ingresa un número válido para μ₁ (usa punto como decimal).")
                    st.session_state["arl_calculado"] = False

    # ── Resultados ARL/ATS ────────────────────────────────────────────────────
    if st.session_state["arl_calculado"] and st.session_state["arl_mu1_val"].strip():
        try:
            arl_mu1 = float(st.session_state["arl_mu1_val"].replace(",", "."))

            _co_arl   = CONTROL_CONSTANTS[int(arl_n)]
            _UCL_arl  = _mu0 + _co_arl["A2"] * s["R_bar"]
            _LCL_arl  = _mu0 - _co_arl["A2"] * s["R_bar"]
            _se_arl   = _sig / np.sqrt(arl_n)

            z_u_arl   = (_UCL_arl - arl_mu1) / _se_arl
            z_l_arl   = (_LCL_arl - arl_mu1) / _se_arl
            beta_arl  = max(0.0, min(stats.norm.cdf(z_u_arl) - stats.norm.cdf(z_l_arl), 1.0))
            power_arl = 1.0 - beta_arl

            ARL0_arl = 1.0 / max(arl_alfa, 1e-9)
            ARL1_arl = 1.0 / max(power_arl, 1e-9)
            ATS1_arl = ARL1_arl * arl_h
            ATS0_arl = ARL0_arl * arl_h

            unidad_lbl = "min" if arl_unit == "Minutos" else "h"

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(render_section_title("📋 Resultados ARL y ATS"), unsafe_allow_html=True)

            df_arl = pd.DataFrame({
                "Indicador": [
                    "ARL₀  (falsas alarmas — proceso en control)",
                    "ARL₁  (muestras para detectar el cambio)",
                    f"ATS₀  (tiempo entre falsas alarmas)",
                    f"ATS₁  (tiempo para detectar el cambio)",
                    "Potencia (1 − β)",
                    "Error Tipo II (β)",
                ],
                "Fórmula": [
                    "1 / α",
                    "1 / (1 − β)",
                    f"ARL₀ × h",
                    f"ARL₁ × h",
                    "1 − β",
                    "P(LCI < x̄ < LCS | μ₁)",
                ],
                "Valor": [
                    f"{ARL0_arl:.0f} muestras",
                    f"{ARL1_arl:.1f} muestras",
                    f"{ATS0_arl:.1f} {unidad_lbl}",
                    f"{ATS1_arl:.1f} {unidad_lbl}",
                    f"{power_arl:.4f}  ({power_arl:.2%})",
                    f"{beta_arl:.4f}  ({beta_arl:.2%})",
                ],
            })
            st.dataframe(df_arl, hide_index=True,
                         key="df_arl_resultados")

            ka, kb, kc, kd = st.columns(4)
            with ka:
                st.markdown(f"""<div class="kpi-card">
                <div class="kpi-value" style="color:{CP}">{ARL0_arl:.0f}</div>
                <div class="kpi-label">ARL₀ (muestras)</div>
                <div class="kpi-sub">α = {arl_alfa:.4f}</div></div>""",
                unsafe_allow_html=True)

            c_arl1 = CG if ARL1_arl <= 5 else CY if ARL1_arl <= 20 else CR
            b_arl1 = "green" if ARL1_arl <= 5 else "yellow" if ARL1_arl <= 20 else "red"
            with kb:
                st.markdown(f"""<div class="kpi-card {b_arl1}">
                <div class="kpi-value" style="color:{c_arl1}">{ARL1_arl:.1f}</div>
                <div class="kpi-label">ARL₁ (muestras)</div>
                <div class="kpi-sub">1 / (1−β)</div></div>""",
                unsafe_allow_html=True)

            with kc:
                st.markdown(f"""<div class="kpi-card">
                <div class="kpi-value" style="color:{CP}">{ATS0_arl:.1f}</div>
                <div class="kpi-label">ATS₀ ({unidad_lbl})</div>
                <div class="kpi-sub">ARL₀ × h</div></div>""",
                unsafe_allow_html=True)

            c_ats1 = CG if ATS1_arl <= arl_h*5 else CY if ATS1_arl <= arl_h*20 else CR
            b_ats1 = "green" if ATS1_arl <= arl_h*5 else "yellow" if ATS1_arl <= arl_h*20 else "red"
            with kd:
                st.markdown(f"""<div class="kpi-card {b_ats1}">
                <div class="kpi-value" style="color:{c_ats1}">{ATS1_arl:.1f}</div>
                <div class="kpi-label">ATS₁ ({unidad_lbl})</div>
                <div class="kpi-sub">ARL₁ × h</div></div>""",
                unsafe_allow_html=True)

            delta_g2 = (arl_mu1 - _mu0) * 1000
            st.markdown(render_alarm("info",
                f"Con un corrimiento de <strong>{delta_g2:+.1f} g</strong> "
                f"(μ₁ = {arl_mu1:.4f} kg), "
                f"la carta tarda en promedio <strong>{ATS1_arl:.1f} {unidad_lbl}</strong> en dar señal "
                f"(= {ARL1_arl:.1f} muestras × {arl_h:.1f} {unidad_lbl}/muestra). "
                f"El proceso en control genera una falsa alarma cada "
                f"<strong>{ATS0_arl:.0f} {unidad_lbl}</strong>."
            ), unsafe_allow_html=True)

        except ValueError:
            st.warning("⚠ Valor de μ₁ inválido.")
    else:
        st.markdown(render_alarm("info",
            "👆 Ingresa una <strong>Media con cambio (μ₁)</strong> y pulsa "
            "<strong>Calcular ARL / ATS</strong> para obtener los resultados."
        ), unsafe_allow_html=True)


def page_monitoreo():
    global s, n_rules_hit, cpk_color, cpk_text, cpk_badge, freq_min, n_proposed

    import hashlib

    # ── Límites fijos desde Fase I ────────────────────────────────────────────
    UCL_fijo  = s["UCL_x"];    LCL_fijo  = s["LCL_x"]
    CL_fijo   = s["xbar_bar"]; UCLr_fijo = s["UCL_r"]
    LCLr_fijo = s["LCL_r"];   CLr_fijo  = s["R_bar"]
    sig_fijo  = s["sigma_st"]; n_fijo    = s["n"]

    # ── Inicializar session_state SOLO una vez ────────────────────────────────
    x_cols_mon = [f"X{i+1}" for i in range(n_fijo)]
    if ("mon_df" not in st.session_state or
            st.session_state.get("mon_n_fijo") != n_fijo):
        empty_mon = {"Subgrupo": list(range(1, 6)), "Hora": [""]*5}
        for xc in x_cols_mon:
            empty_mon[xc] = [None]*5
        st.session_state["mon_df"]     = pd.DataFrame(empty_mon)
        st.session_state["mon_n_sg"]   = 5
        st.session_state["mon_n_fijo"] = n_fijo
        st.session_state["mon_hash"]   = ""
        st.session_state["mon_fig_x"]  = None
        st.session_state["mon_fig_r"]  = None

    st.markdown("""
    <div style="background:linear-gradient(135deg,#1B4F72,#154360);color:white;
         padding:1.2rem 1.5rem;border-radius:10px;margin-bottom:.8rem">
    <h3 style="margin:0 0 .3rem;font-size:1.15rem">🔴 Monitoreo en Tiempo Real</h3>
    <p style="margin:0;opacity:.85;font-size:.82rem">
    Los límites de control están <strong>fijos</strong> a partir del análisis de estabilización.
    Ingresa nuevos subgrupos y la carta mostrará si el proceso sigue bajo control.</p>
    </div>""", unsafe_allow_html=True)

    st.markdown(render_section_title("🔒 Límites de Control Fijos (Fase I — Estabilización)"),
                unsafe_allow_html=True)
    lf1, lf2, lf3, lf4, lf5, lf6 = st.columns(6)
    for col, lbl, val in [
        (lf1, "LCS X̄ (fijo)",  f"{UCL_fijo:.4f} kg"),
        (lf2, "LC X̄ (fijo)",   f"{CL_fijo:.4f} kg"),
        (lf3, "LCI X̄ (fijo)",  f"{LCL_fijo:.4f} kg"),
        (lf4, "LCS R (fijo)",   f"{UCLr_fijo:.4f} kg"),
        (lf5, "R̄ (fijo)",      f"{CLr_fijo:.4f} kg"),
        (lf6, "n (fijo)",       str(n_fijo)),
    ]:
        with col: st.metric(lbl, val)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(render_section_title("📝 Ingreso de Nuevos Subgrupos (Fase II — Monitoreo)"),
                unsafe_allow_html=True)

    # ══ BLOQUE 1 — INPUTS DE ESTRUCTURA ══════════════════════════════════════
    mon_a, mon_b = st.columns([1, 1])
    with mon_a:
        n_mon_sg = st.number_input("Nº de subgrupos (filas)",
                                   min_value=2, max_value=50, value=5,
                                   key="mon_n_sg_input")
    with mon_b:
        n_mon_n = st.number_input("Tamaño de muestra n (columnas X)",
                                  min_value=2, max_value=10, value=int(n_fijo),
                                  key="mon_n_n_input")

    x_cols_mon = [f"X{i+1}" for i in range(int(n_mon_n))]

    # Detectar si hubo cambio estructural en ESTE ciclo de render
    _estructura_cambio = (
        st.session_state.get("mon_n_sg") != int(n_mon_sg) or
        st.session_state.get("mon_n_n")  != int(n_mon_n)
    )

    if _estructura_cambio:
        # Estructura cambió: construir DF limpio con la nueva forma.
        # Se preservan valores de columnas que sigan existiendo.
        prev_df   = st.session_state.get("mon_df")
        prev_cols = list(prev_df.columns) if prev_df is not None else []
        new_rows  = int(n_mon_sg)
        empty_mon = {"Subgrupo": list(range(1, new_rows + 1)), "Hora": [""] * new_rows}
        for xc in x_cols_mon:
            if xc in prev_cols and prev_df is not None:
                vals = list(prev_df[xc])
                if len(vals) >= new_rows:
                    empty_mon[xc] = vals[:new_rows]
                else:
                    empty_mon[xc] = vals + [None] * (new_rows - len(vals))
            else:
                empty_mon[xc] = [None] * new_rows
        # Asignar ANTES de renderizar el editor — el editor toma el DF nuevo
        st.session_state["mon_df"]   = pd.DataFrame(empty_mon).copy()
        st.session_state["mon_n_sg"] = int(n_mon_sg)
        st.session_state["mon_n_n"]  = int(n_mon_n)
        st.session_state["mon_hash"] = ""   # invalida figuras anteriores

    # ══ BLOQUE 2 — EDITOR ════════════════════════════════════════════════════
    # KEY DINÁMICA: cambia junto con la estructura del DF.
    # Esto fuerza a React a montar un editor nuevo en lugar de intentar
    # mutar el DOM del editor anterior — causa raíz del removeChild / insertBefore.
    _mon_editor_key = f"mon_editor_{int(n_mon_n)}_{int(n_mon_sg)}"

    st.markdown("**Anota los pesos nuevos (kg):**")
    mon_edited = st.data_editor(
        st.session_state["mon_df"],
        width='stretch',
        num_rows="fixed",
        column_config={
            "Subgrupo": st.column_config.NumberColumn("Subgrupo", disabled=True),
            "Hora":     st.column_config.TextColumn("Hora"),
            **{xc: st.column_config.NumberColumn(
                xc, min_value=35.0, max_value=45.0, format="%.2f", step=0.1)
               for xc in x_cols_mon}
        },
        key=_mon_editor_key   # KEY DINÁMICA — monta editor nuevo cuando cambia estructura
    )
    # Persistir ediciones SOLO cuando la estructura no cambió en este ciclo.
    # Si _estructura_cambio es True, mon_df ya fue reemplazado con el DF limpio;
    # usar mon_edited en ese caso devolvería el shape del editor anterior.
    if not _estructura_cambio:
        st.session_state["mon_df"] = mon_edited

    # Botones de acción (sin st.rerun)
    btn_col1, btn_col2 = st.columns([1, 1])
    with btn_col1:
        if st.button("🗑 Limpiar tabla", type="secondary", key="btn_limpiar_mon"):
            empty_mon = {"Subgrupo": list(range(1, int(n_mon_sg)+1)),
                         "Hora":     [""]*int(n_mon_sg)}
            for xc in x_cols_mon:
                empty_mon[xc] = [None]*int(n_mon_sg)
            st.session_state["mon_df"]   = pd.DataFrame(empty_mon)
            st.session_state["mon_hash"] = ""
            # Sin st.rerun() — el editor se actualizará en el próximo ciclo natural

    with btn_col2:
        # Botón de descarga — exportar mon_df + columnas calculadas si existen
        _df_export = st.session_state["mon_df"].copy()
        # Añadir xbar y R si ya fueron calculados
        _xm_export = [c for c in _df_export.columns
                      if str(c).strip().upper().startswith("X")
                      and str(c).strip()[1:].isdigit()]
        if _xm_export:
            _df_num = _df_export[_xm_export].apply(pd.to_numeric, errors="coerce")
            _filas_ok = _df_num.dropna(how="any").index
            if len(_filas_ok) > 0:
                _df_export.loc[_filas_ok, "xbar"] = _df_num.loc[_filas_ok].mean(axis=1)
                _df_export.loc[_filas_ok, "R"]    = (_df_num.loc[_filas_ok].max(axis=1)
                                                      - _df_num.loc[_filas_ok].min(axis=1))
        _buf_export = io.BytesIO()
        _df_export.to_excel(_buf_export, index=False, engine="openpyxl")
        st.download_button(
            label="💾 Descargar datos de monitoreo",
            data=_buf_export.getvalue(),
            file_name="monitoreo_cep.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="btn_download_mon"
        )

    # ── CARGA EXCEL (desactivada — conservada como referencia) ────────────────
    # mon_file = st.file_uploader("📂 Subir nuevo Excel", type=["xlsx","xls"])
    # if mon_file:
    #     df_mon_raw = pd.read_excel(mon_file)
    #     st.session_state["mon_df"] = df_mon_raw.copy()

    # ══ BLOQUE 3 — PROCESAMIENTO ═════════════════════════════════════════════
    # Si hubo cambio estructural en este ciclo, no graficar — esperar próximo render
    df_nuevos  = None
    df_mon_raw = mon_edited.copy()

    if not _estructura_cambio and df_mon_raw is not None:
        try:
            _xm = x_cols_mon
            # Verificar columnas presentes
            cols_ok = [c for c in df_mon_raw.columns if c in _xm]
            if not cols_ok:
                st.error(f"❌ No se encontraron columnas {', '.join(_xm)} en los datos.")
            else:
                # Convertir a numérico
                df_mon_raw[_xm] = df_mon_raw[_xm].apply(pd.to_numeric, errors="coerce")

                # Filas válidas
                filas_validas = df_mon_raw[_xm].dropna(how="any")
                st.write("🔍 Filas válidas:", len(filas_validas))  # DEBUG temporal

                if len(filas_validas) < 2:
                    st.warning("⚠ Se requieren al menos 2 subgrupos completos para graficar. "
                               "Completa más filas en la tabla.")
                else:
                    n_antes   = len(df_mon_raw)
                    df_clean  = df_mon_raw.loc[filas_validas.index].reset_index(drop=True)
                    n_dropped = n_antes - len(df_clean)
                    if n_dropped > 0:
                        st.info(f"ℹ️ Se ignoraron {n_dropped} fila(s) incompletas.")
                    df_nuevos = df_clean.copy()
                    df_nuevos["xbar"] = df_nuevos[_xm].mean(axis=1)
                    df_nuevos["R"]    = df_nuevos[_xm].max(axis=1) - df_nuevos[_xm].min(axis=1)
        except Exception as e:
            st.error(f"❌ Error procesando datos: {e}")

    # ── HASH Y FIGURAS PERSISTENTES ───────────────────────────────────────────
    if df_nuevos is not None:
        nuevo_hash = hashlib.md5(
            df_nuevos.to_csv(index=False).encode()
        ).hexdigest()

        if nuevo_hash != st.session_state.get("mon_hash", ""):
            # Datos cambiaron — reconstruir figuras
            st.session_state["mon_hash"] = nuevo_hash

            n_hist  = len(s["df"]);   df_hist = s["df"].copy()
            n_new   = len(df_nuevos)
            idx_hist = list(range(1, n_hist+1))
            idx_new  = list(range(n_hist+1, n_hist+n_new+1))

            new_signals = [i for i, xb_n in enumerate(df_nuevos["xbar"])
                           if xb_n > UCL_fijo or xb_n < LCL_fijo]
            new_colors  = [CR if i in new_signals else "#E67E22" for i in range(n_new)]

            fig_mon = go.Figure()
            for y0, y1, col_bg in [
                (LCL_fijo, CL_fijo - (CL_fijo-LCL_fijo)*2/3, "rgba(231,76,60,.05)"),
                (CL_fijo + (UCL_fijo-CL_fijo)*2/3, UCL_fijo,  "rgba(231,76,60,.05)"),
                (CL_fijo - (CL_fijo-LCL_fijo)/3, CL_fijo + (UCL_fijo-CL_fijo)/3, "rgba(39,174,96,.05)"),
            ]:
                fig_mon.add_hrect(y0=y0, y1=y1, fillcolor=col_bg, line_width=0)
            for y, lbl, col_ln, dash in [
                (UCL_fijo, f"LCS={UCL_fijo:.3f}", CR, "dash"),
                (CL_fijo,  f"LC={CL_fijo:.3f}",  CP, "solid"),
                (LCL_fijo, f"LCI={LCL_fijo:.3f}", CR, "dash"),
            ]:
                fig_mon.add_hline(y=y, line_dash=dash, line_color=col_ln, line_width=2,
                                  annotation_text=lbl, annotation_position="right",
                                  annotation_font_size=10, annotation_font_color=col_ln)
            fig_mon.add_vline(x=n_hist+0.5, line_dash="dot", line_color=CN, line_width=2,
                              annotation_text="► Nuevos datos", annotation_font_size=11,
                              annotation_font_color=CN)
            hist_colors_mon = [CR if ix in set(s["signals_x"]) else CP for ix in df_hist.index]
            fig_mon.add_trace(go.Scatter(
                x=idx_hist, y=df_hist["xbar"], mode="lines+markers", name="Histórico (Fase I)",
                line=dict(color=CP, width=1.8),
                marker=dict(color=hist_colors_mon, size=8, line=dict(color="white", width=1.2)),
                hovertemplate="Subgrupo %{x}<br>x̄=%{y:.4f} kg<extra>Histórico</extra>"
            ))
            fig_mon.add_trace(go.Scatter(
                x=idx_new, y=df_nuevos["xbar"], mode="lines+markers", name="Nuevos (Fase II)",
                line=dict(color="#E67E22", width=2.2),
                marker=dict(color=new_colors, size=10, line=dict(color="white", width=1.5)),
                hovertemplate="Subgrupo %{x}<br>x̄=%{y:.4f} kg<extra>Nuevo</extra>"
            ))
            if new_signals:
                si_new = [idx_new[i] for i in new_signals]
                sv_new = [df_nuevos["xbar"].iloc[i] for i in new_signals]
                fig_mon.add_trace(go.Scatter(
                    x=si_new, y=sv_new, mode="markers", name="🚨 SEÑAL",
                    marker=dict(color=CR, size=16, symbol="x-open", line=dict(color=CR, width=3))
                ))
            # Rango Y fijo: basado en UCL/LCL + 10% padding — sin auto-scale
            _rng_pad = (UCL_fijo - LCL_fijo) * 0.10
            _y_lo    = LCL_fijo - _rng_pad
            _y_hi    = UCL_fijo + _rng_pad

            fig_mon.update_layout(
                template="plotly_white", height=380,
                title=dict(
                    text=(f"Carta X̄ de Monitoreo — {n_hist} históricos + {n_new} nuevos | "
                          f"{'🚨 ' + str(len(new_signals)) + ' señal(es) detectada(s)' if new_signals else '✅ Sin señales'}"),
                    font=dict(size=13, color=CR if new_signals else CP)
                ),
                xaxis=dict(title="Número de Subgrupo", tickmode="linear",
                           range=[0, n_hist+n_new+1]),
                yaxis=dict(title="Peso promedio x̄ (kg)",
                           range=[_y_lo, _y_hi]),
                legend=dict(orientation="h", y=1.08),
                margin=dict(l=40, r=100, t=60, b=40)
            )

            # Carta R
            fig_mon_r = go.Figure()
            for y, lbl, col_ln, dash in [
                (UCLr_fijo, f"LCS={UCLr_fijo:.3f}", CR,        "dash"),
                (CLr_fijo,  f"R̄={CLr_fijo:.3f}",  "#2ECC71", "solid"),
            ]:
                fig_mon_r.add_hline(y=y, line_dash=dash, line_color=col_ln, line_width=2,
                                    annotation_text=lbl, annotation_position="right",
                                    annotation_font_size=9)
            if LCLr_fijo > 0:
                fig_mon_r.add_hline(y=LCLr_fijo, line_dash="dash", line_color=CR, line_width=2,
                                    annotation_text=f"LCI={LCLr_fijo:.3f}",
                                    annotation_position="right", annotation_font_size=9)
            fig_mon_r.add_vline(x=n_hist+0.5, line_dash="dot", line_color=CN, line_width=2)
            new_r_signals = [i for i, rv in enumerate(df_nuevos["R"]) if rv > UCLr_fijo]
            new_r_colors  = [CR if i in new_r_signals else "#E67E22" for i in range(n_new)]
            fig_mon_r.add_trace(go.Scatter(
                x=idx_hist, y=df_hist["R"], mode="lines+markers", name="R Histórico",
                line=dict(color="#2ECC71", width=1.8),
                marker=dict(
                    color=[CR if ix in set(s["signals_r"]) else "#2ECC71" for ix in df_hist.index],
                    size=8, symbol="diamond", line=dict(color="white", width=1.2)
                )
            ))
            fig_mon_r.add_trace(go.Scatter(
                x=idx_new, y=df_nuevos["R"], mode="lines+markers", name="R Nuevos",
                line=dict(color="#E67E22", width=2.2),
                marker=dict(color=new_r_colors, size=10, symbol="diamond",
                            line=dict(color="white", width=1.5))
            ))
            fig_mon_r.update_layout(
                template="plotly_white", height=280,
                title=dict(text="Carta R de Monitoreo — Variabilidad",
                           font=dict(size=12, color=CP)),
                xaxis=dict(title="Subgrupo", tickmode="linear",
                           range=[0, n_hist+n_new+1]),
                yaxis_title="Rango (kg)",
                legend=dict(orientation="h", y=1.08),
                margin=dict(l=40, r=100, t=50, b=40)
            )

            # Guardar señales en session_state para las alertas
            st.session_state["mon_fig_x"]       = fig_mon
            st.session_state["mon_fig_r"]       = fig_mon_r
            st.session_state["mon_new_signals"]  = new_signals
            st.session_state["mon_new_r_signals"]= new_r_signals
            st.session_state["mon_idx_new"]      = idx_new
            st.session_state["mon_df_nuevos"]    = df_nuevos.copy()
            st.session_state["mon_n_new"]        = n_new
            st.session_state["mon_n_hist"]       = n_hist

        # ── Renderizar figuras (desde session_state) ──────────────────────────
        st.markdown(render_section_title("📈 Carta X̄ — Histórico + Nuevos Subgrupos"),
                    unsafe_allow_html=True)
        st.plotly_chart(st.session_state["mon_fig_x"],
                        width='stretch', key="chart_mon_xbar")
        st.plotly_chart(st.session_state["mon_fig_r"],
                        width='stretch', key="chart_mon_r")

        # ── Alertas ───────────────────────────────────────────────────────────
        new_signals   = st.session_state["mon_new_signals"]
        new_r_signals = st.session_state["mon_new_r_signals"]
        idx_new       = st.session_state["mon_idx_new"]
        df_nuevos_ss  = st.session_state["mon_df_nuevos"]
        n_new         = st.session_state["mon_n_new"]

        st.markdown(render_section_title("🚨 Alertas de Monitoreo"), unsafe_allow_html=True)
        if not new_signals and not new_r_signals:
            st.markdown(render_alarm("ok",
                "✅ Todos los subgrupos nuevos están bajo control. "
                "El proceso se mantiene estable."), unsafe_allow_html=True)
        else:
            if new_signals:
                sgs_txt  = ", ".join([f"S{idx_new[i]}" for i in new_signals])
                vals_txt = ", ".join([f"{df_nuevos_ss['xbar'].iloc[i]:.4f}" for i in new_signals])
                st.markdown(render_alarm("critical",
                    f"🚨 <strong>SEÑAL EN CARTA X̄:</strong> Subgrupos {sgs_txt} fuera de límites. "
                    f"x̄ = {vals_txt} kg. Investigar causa asignable inmediatamente."),
                    unsafe_allow_html=True)
            if new_r_signals:
                sgs_r = ", ".join([f"S{idx_new[i]}" for i in new_r_signals])
                st.markdown(render_alarm("critical",
                    f"🚨 <strong>SEÑAL EN CARTA R:</strong> Variabilidad inestable en "
                    f"subgrupos {sgs_r}. Posible problema en el dosificador o cambio de operario."),
                    unsafe_allow_html=True)

        # ── Resumen estadístico ───────────────────────────────────────────────
        st.markdown(render_section_title("📊 Resumen de Nuevos Subgrupos"),
                    unsafe_allow_html=True)
        xb_new = df_nuevos_ss["xbar"].mean()
        r_new  = df_nuevos_ss["R"].mean()
        rs1, rs2, rs3, rs4 = st.columns(4)
        with rs1: st.metric("x̄ nuevos", f"{xb_new:.4f} kg",
                            delta=f"{(xb_new-CL_fijo)*1000:+.1f} g vs LC")
        with rs2: st.metric("R̄ nuevos", f"{r_new:.4f} kg",
                            delta=f"{(r_new-CLr_fijo)*1000:+.1f} g vs R̄")
        with rs3: st.metric("Subgrupos bajo control",
                            f"{n_new - len(new_signals)}/{n_new}")
        with rs4:
            pct_ok   = (n_new - len(new_signals)) / n_new * 100
            color_ok = CG if pct_ok == 100 else CY if pct_ok >= 80 else CR
            borde_ok = "green" if pct_ok == 100 else "yellow" if pct_ok >= 80 else "red"
            st.markdown(f"""<div class="kpi-card {borde_ok}">
            <div class="kpi-value" style="color:{color_ok}">{pct_ok:.0f}%</div>
            <div class="kpi-label">Tasa de conformidad</div>
            </div>""", unsafe_allow_html=True)

    else:
        st.markdown(render_alarm("info", """
        <strong>📋 Cómo usar el Monitoreo:</strong><br><br>
        1. Los límites de arriba son <strong>fijos</strong> — vienen del análisis histórico<br>
        2. Selecciona el modo de ingreso (editor o Excel nuevo)<br>
        3. Ingresa los pesos de los nuevos subgrupos del turno actual<br>
        4. La gráfica mostrará los puntos nuevos a la derecha de los históricos<br>
        5. Si un punto se sale de los límites, aparece una <strong>🚨 alerta inmediata</strong>
        """), unsafe_allow_html=True)


def page_eco_analisis():
    global s, n_rules_hit, cpk_color, cpk_text, cpk_badge, freq_min, n_proposed


    # ══════════════════════════════════════════════════════════════════════════
    # SECCIÓN 1 — PARÁMETROS DEL PROCESO
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1B4F72,#154360);color:white;
         padding:1.1rem 1.5rem;border-radius:10px;margin-bottom:.8rem;">
    <h3 style="margin:0 0 .25rem;font-size:1.15rem;">💰 Análisis Económico del Sobrellenado</h3>
    <p style="margin:0;opacity:.85;font-size:.82rem;">
    Parámetros de Fase I (μ, σ) tomados automáticamente. Ajusta los parámetros de producción y costo.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(render_section_title("⚙️ Parámetros del Proceso"), unsafe_allow_html=True)
    ep1, ep2, ep3, ep4 = st.columns(4)
    with ep1:
        st.session_state["eco_cost_kg"] = st.number_input(
            "Costo mogolla ($/kg)", min_value=0.0, step=1.0,
            value=float(st.session_state["eco_cost_kg"]),
            key="eco_input_cost_kg",
            help="Costo unitario del producto en COP por kilogramo"
        )
    with ep2:
        st.session_state["eco_prod_h"] = st.number_input(
            "Producción (sacos/hora)", min_value=1, step=5,
            value=int(st.session_state["eco_prod_h"]),
            key="eco_input_prod_h",
            help="Velocidad de la línea en sacos por hora"
        )
    with ep3:
        st.session_state["eco_hours_day"] = st.number_input(
            "Horas productivas/día", min_value=1.0, max_value=24.0, step=0.5,
            value=float(st.session_state["eco_hours_day"]),
            key="eco_input_hours",
            help="Horas efectivas de producción por turno/día"
        )
    with ep4:
        st.session_state["eco_days_month"] = st.number_input(
            "Días productivos/mes", min_value=1, max_value=31,
            value=int(st.session_state["eco_days_month"]),
            key="eco_input_days",
            help="Días calendario con producción activa"
        )

    # Leer valores consolidados
    _e_cost  = st.session_state["eco_cost_kg"]
    _e_prod  = st.session_state["eco_prod_h"]
    _e_hours = st.session_state["eco_hours_day"]
    _e_days  = st.session_state["eco_days_month"]

    # Parámetros Fase I (solo lectura)
    _xb  = s["xbar_bar"]
    _sig = s["sigma_st"]

    # Referencia automática desde Fase I
    ep5, ep6, ep7, ep8 = st.columns(4)
    _des_g_nominal = round((_xb - NOMINAL) * 1000, 1)
    with ep5:
        st.metric("μ (Fase I)", f"{_xb:.4f} kg",
                  delta=_des_g_nominal,
                  delta_color="inverse" if _des_g_nominal > 0 else "normal",
                  help=f"Desviación sobre nominal: {_des_g_nominal:+.1f} g/saco")
    with ep6: st.metric("σ̂ (Fase I)", f"{_sig:.4f} kg",  help="Desviación estándar estimada R̄/d₂")
    with ep7: st.metric("LSL",         f"{LSL:.2f} kg")
    with ep8: st.metric("USL",         f"{USL:.2f} kg")

    st.markdown("<br>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # SECCIÓN 2 — SITUACIÓN ACTUAL
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown(render_section_title("📊 Situación Actual — Sobrellenado Anual"), unsafe_allow_html=True)

    eco = compute_eco(s, _e_cost, _e_prod, _e_hours, _e_days)

    sa1, sa2, sa3, sa4, sa5 = st.columns(5)
    with sa1:
        _ov_color = CY if eco["overfill_g"] > 0 else CG
        _ov_borde = "yellow" if eco["overfill_g"] > 0 else "green"
        st.markdown(f"""<div class="kpi-card {_ov_borde}">
        <div class="kpi-value" style="color:{_ov_color}">{eco['overfill_g']:+.1f} g</div>
        <div class="kpi-label">Sobrellenado/saco</div>
        <div class="kpi-sub">x̄ − nominal = {_xb:.4f} − {NOMINAL:.1f} kg</div></div>""",
        unsafe_allow_html=True)

    with sa2:
        st.markdown(f"""<div class="kpi-card">
        <div class="kpi-value" style="color:{CP}">{eco['sacos_mes']:,.0f}</div>
        <div class="kpi-label">Sacos/mes</div>
        <div class="kpi-sub">{eco['sacos_anio']:,.0f} sacos/año</div></div>""",
        unsafe_allow_html=True)

    with sa3:
        st.markdown(f"""<div class="kpi-card yellow">
        <div class="kpi-value" style="color:{CY}">{eco['kg_extra_mes']:,.1f} kg</div>
        <div class="kpi-label">kg extra/mes</div>
        <div class="kpi-sub">{eco['kg_extra_mes']*12:,.0f} kg extra/año</div></div>""",
        unsafe_allow_html=True)

    with sa4:
        st.markdown(f"""<div class="kpi-card red">
        <div class="kpi-value" style="color:{CR}">${eco['costo_mes']:,.0f}</div>
        <div class="kpi-label">Pérdida mensual (COP)</div>
        <div class="kpi-sub">${eco['costo_anio']:,.0f}/año</div></div>""",
        unsafe_allow_html=True)

    with sa5:
        st.markdown(f"""<div class="kpi-card red">
        <div class="kpi-value" style="color:{CR}">{eco['sacos_extra_anio']:.0f}</div>
        <div class="kpi-label">Sacos equivalentes/año</div>
        <div class="kpi-sub">kg extra ÷ 40 kg/saco</div></div>""",
        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # SECCIÓN 3 — SIMULACIÓN: probabilidad de rechazo de lote
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown(render_section_title("🎯 Simulación — Media Óptima por Probabilidad de Rechazo"),
                unsafe_allow_html=True)
    st.markdown(render_alarm("info",
        "Ajusta el <strong>tamaño del lote</strong> y la <strong>probabilidad máxima de rechazo</strong> "
        "aceptable. El sistema calculará la media óptima μ* que minimiza el sobrellenado "
        "sin superar ese riesgo usando <code>μ* = LSL + z(1−p) · σ/√n_lote</code>."
    ), unsafe_allow_html=True)

    sim1, sim2 = st.columns(2)
    with sim1:
        st.session_state["eco_lote"] = st.slider(
            "Tamaño del lote del cliente (sacos)",
            min_value=10, max_value=2000,
            value=int(st.session_state["eco_lote"]),
            step=10, key="eco_slider_lote",
            help="Número de sacos por lote de despacho al cliente"
        )
    with sim2:
        st.session_state["eco_p_rechazo"] = st.slider(
            "Probabilidad máxima de rechazo del lote (%)",
            min_value=0.01, max_value=5.0,
            value=float(st.session_state["eco_p_rechazo"]),
            step=0.01, format="%.2f",
            key="eco_slider_p",
            help="P(x̄_lote < LSL) que el cliente está dispuesto a tolerar"
        )

    _lote     = int(st.session_state["eco_lote"])
    _p_rec    = st.session_state["eco_p_rechazo"] / 100.0   # proporción
    _se_lote  = _sig / np.sqrt(_lote)                        # SE del promedio del lote
    _z_opt    = stats.norm.ppf(1.0 - _p_rec)                 # z tal que P(Z>z) = p_rechazo
    _mu_opt   = LSL + _z_opt * _se_lote                      # media óptima

    # Clamp: no puede superar USL − 3σ ni bajar de nominal
    _mu_opt = float(np.clip(_mu_opt, NOMINAL, USL - 3*_sig))

    # Capacidad con media óptima
    _Cpk_opt = min((USL - _mu_opt) / (3*_sig), (_mu_opt - LSL) / (3*_sig))
    _pnc_opt = (stats.norm.cdf(LSL, _mu_opt, _sig)
                + 1 - stats.norm.cdf(USL, _mu_opt, _sig))

    st.markdown("<br>", unsafe_allow_html=True)
    sr1, sr2, sr3, sr4 = st.columns(4)
    with sr1:
        st.markdown(f"""<div class="kpi-card green">
        <div class="kpi-value" style="color:{CG}">{_mu_opt:.4f} kg</div>
        <div class="kpi-label">Media óptima μ*</div>
        <div class="kpi-sub">{(_mu_opt-NOMINAL)*1000:+.1f} g sobre nominal</div></div>""",
        unsafe_allow_html=True)

    with sr2:
        _zc, _zt, _zb = cpk_st(_Cpk_opt)
        st.markdown(f"""<div class="kpi-card {'green' if _Cpk_opt>=1.33 else 'yellow' if _Cpk_opt>=1.0 else 'red'}">
        <div class="kpi-value" style="color:{_zc}">{_Cpk_opt:.3f}</div>
        <div class="kpi-label">Cpk con μ*</div>
        <div class="kpi-sub"><span class="badge {_zb}">{_zt}</span></div></div>""",
        unsafe_allow_html=True)

    with sr3:
        _pnc_opt_pct = _pnc_opt * 100
        _pc_opt = CR if _pnc_opt_pct > 5 else CY if _pnc_opt_pct > 0.27 else CG
        st.markdown(f"""<div class="kpi-card {'red' if _pnc_opt_pct>5 else 'yellow' if _pnc_opt_pct>0.27 else 'green'}">
        <div class="kpi-value" style="color:{_pc_opt}">{_pnc_opt_pct:.4f}%</div>
        <div class="kpi-label">PNC con μ*</div>
        <div class="kpi-sub">vs {s['pnc_total']*100:.4f}% actual</div></div>""",
        unsafe_allow_html=True)

    with sr4:
        _z_disp  = stats.norm.ppf(1.0 - _p_rec)
        st.markdown(f"""<div class="kpi-card">
        <div class="kpi-value" style="color:{CP}">{_z_disp:.3f}</div>
        <div class="kpi-label">z crítico</div>
        <div class="kpi-sub">P(rechazo) ≤ {st.session_state['eco_p_rechazo']:.2f}% · SE = {_se_lote*1000:.2f} g</div></div>""",
        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # SECCIÓN 4 — RESULTADO: media óptima vs actual
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown(render_section_title("📐 Resultado — Comparativa de Medias"), unsafe_allow_html=True)

    _des_actual = (_xb - NOMINAL) * 1000
    _des_opt    = (_mu_opt - NOMINAL) * 1000
    _reduccion_g = _des_actual - _des_opt

    comp1, comp2, comp3 = st.columns(3)
    with comp1:
        _cc = CY if _des_actual > 0 else CG
        st.markdown(f"""<div class="kpi-card {'yellow' if _des_actual>0 else 'green'}">
        <div class="kpi-value" style="color:{_cc}">{_xb:.4f} kg</div>
        <div class="kpi-label">Media actual (Fase I)</div>
        <div class="kpi-sub">Exceso: {_des_actual:+.1f} g/saco · Cpk = {s['Cpk']:.3f}</div></div>""",
        unsafe_allow_html=True)

    with comp2:
        st.markdown(f"""<div class="kpi-card green">
        <div class="kpi-value" style="color:{CG}">{_mu_opt:.4f} kg</div>
        <div class="kpi-label">Media óptima propuesta</div>
        <div class="kpi-sub">Exceso: {_des_opt:+.1f} g/saco · Cpk = {_Cpk_opt:.3f}</div></div>""",
        unsafe_allow_html=True)

    with comp3:
        _rc = CG if _reduccion_g > 0 else CY
        st.markdown(f"""<div class="kpi-card {'green' if _reduccion_g>0 else 'yellow'}">
        <div class="kpi-value" style="color:{_rc}">{_reduccion_g:.1f} g</div>
        <div class="kpi-label">Reducción de exceso/saco</div>
        <div class="kpi-sub">{_des_actual:.1f} g → {_des_opt:.1f} g por saco</div></div>""",
        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # SECCIÓN 5 — AHORRO ECONÓMICO COMPARATIVO
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown(render_section_title("💵 Ahorro Económico Comparativo"), unsafe_allow_html=True)

    # Cálculo escenario óptimo
    _sacos_anio   = eco["sacos_anio"]
    _over_opt_kg  = max(0.0, _mu_opt - NOMINAL)
    _costo_opt_mes  = _over_opt_kg * _e_prod * _e_hours * _e_days * _e_cost
    _costo_opt_anio = _costo_opt_mes * 12
    _sacos_opt_anio = (_over_opt_kg * _sacos_anio / 40) if _over_opt_kg > 0 else 0.0

    _ahorro_mes    = eco["costo_mes"]  - _costo_opt_mes
    _ahorro_anio   = eco["costo_anio"] - _costo_opt_anio
    _ahorro_sacos  = eco["sacos_extra_anio"] - _sacos_opt_anio
    _pct_ahorro    = (_ahorro_anio / max(eco["costo_anio"], 1e-9)) * 100

    # Tabla comparativa
    st.markdown(f"""
    <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:.85rem;font-family:'IBM Plex Sans',sans-serif">
      <thead>
        <tr style="background:#1B4F72;color:white">
          <th style="padding:.6rem .9rem;text-align:left">Escenario</th>
          <th style="padding:.6rem .9rem;text-align:right">Media (kg)</th>
          <th style="padding:.6rem .9rem;text-align:right">Exceso/saco (g)</th>
          <th style="padding:.6rem .9rem;text-align:right">Sacos extra/año</th>
          <th style="padding:.6rem .9rem;text-align:right">Costo mensual (COP)</th>
          <th style="padding:.6rem .9rem;text-align:right">Costo anual (COP)</th>
        </tr>
      </thead>
      <tbody>
        <tr style="background:#FEF9E7">
          <td style="padding:.55rem .9rem;font-weight:600;color:{CY}">⚠ Actual</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace">{_xb:.4f}</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace">{_des_actual:+.1f}</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace">{eco['sacos_extra_anio']:.0f}</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace">${eco['costo_mes']:,.0f}</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace">${eco['costo_anio']:,.0f}</td>
        </tr>
        <tr style="background:#EAFAF1">
          <td style="padding:.55rem .9rem;font-weight:600;color:{CG}">✅ Óptimo</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace">{_mu_opt:.4f}</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace">{_des_opt:+.1f}</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace">{_sacos_opt_anio:.0f}</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace">${_costo_opt_mes:,.0f}</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace">${_costo_opt_anio:,.0f}</td>
        </tr>
        <tr style="background:#EBF5FB;border-top:2px solid #1B4F72">
          <td style="padding:.55rem .9rem;font-weight:700;color:{CP}">💰 Ahorro</td>
          <td style="padding:.55rem .9rem;text-align:right;color:#7F8C8D">—</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace;font-weight:700;color:{CG}">{_reduccion_g:.1f} g menos</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace;font-weight:700;color:{CG}">{_ahorro_sacos:.0f}</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace;font-weight:700;color:{CG}">${_ahorro_mes:,.0f}</td>
          <td style="padding:.55rem .9rem;text-align:right;font-family:monospace;font-weight:700;color:{CG}">${_ahorro_anio:,.0f}</td>
        </tr>
      </tbody>
    </table>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # KPIs de ahorro
    ak1, ak2, ak3, ak4 = st.columns(4)
    with ak1:
        st.markdown(f"""<div class="kpi-card green">
        <div class="kpi-value" style="color:{CG}">${_ahorro_anio:,.0f}</div>
        <div class="kpi-label">Ahorro anual (COP)</div>
        <div class="kpi-sub">${_ahorro_mes:,.0f}/mes</div></div>""",
        unsafe_allow_html=True)

    with ak2:
        st.markdown(f"""<div class="kpi-card green">
        <div class="kpi-value" style="color:{CG}">{_pct_ahorro:.1f}%</div>
        <div class="kpi-label">Reducción de pérdida</div>
        <div class="kpi-sub">Vs. situación actual</div></div>""",
        unsafe_allow_html=True)

    with ak3:
        st.markdown(f"""<div class="kpi-card green">
        <div class="kpi-value" style="color:{CG}">{_ahorro_sacos:.0f}</div>
        <div class="kpi-label">Sacos recuperados/año</div>
        <div class="kpi-sub">{_ahorro_sacos*40:,.0f} kg de producto</div></div>""",
        unsafe_allow_html=True)

    with ak4:
        _roi_meses = (eco["costo_anio"] / max(_ahorro_anio, 1e-9)) * 12 if _ahorro_anio > 0 else float("inf")
        _roi_txt   = f"{_roi_meses:.1f} meses" if _roi_meses < 120 else "N/A"
        st.markdown(f"""<div class="kpi-card {'green' if _ahorro_anio>0 else 'yellow'}">
        <div class="kpi-value" style="color:{CG if _ahorro_anio>0 else CY}">{_roi_txt}</div>
        <div class="kpi-label">Payback implícito</div>
        <div class="kpi-sub">Pérdida actual / ahorro anual</div></div>""",
        unsafe_allow_html=True)

    # Alerta resumen
    if _ahorro_anio > 0:
        st.markdown(render_alarm("ok",
            f"<strong>📌 Recomendación:</strong> Ajustando la media de dosificación a "
            f"<strong>{_mu_opt:.4f} kg</strong> ({_des_opt:+.1f} g sobre nominal), "
            f"la probabilidad de rechazo del lote de <strong>{_lote} sacos</strong> "
            f"permanece ≤ <strong>{st.session_state['eco_p_rechazo']:.2f}%</strong>. "
            f"Esto representa un ahorro de <strong>${_ahorro_anio:,.0f} COP/año</strong> "
            f"equivalente a <strong>{_ahorro_sacos:.0f} sacos/año</strong> de producto recuperado."
        ), unsafe_allow_html=True)
    else:
        st.markdown(render_alarm("info",
            "ℹ️ La media actual ya está en o por debajo del óptimo para la probabilidad de rechazo configurada. "
            "Considera reducir la probabilidad de rechazo aceptable para encontrar margen de mejora."
        ), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Botón exportar reporte completo (aquí sí tenemos eco disponible)
    excel_rep = export_excel(s, eco)
    st.download_button(
        "📥 Exportar Reporte Completo a Excel", excel_rep,
        "reporte_CEP_Molinos.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )



# ─────────────────────────────────────────────────────────────────────────────
# ROUTER — muestra la sección activa
# ─────────────────────────────────────────────────────────────────────────────

if pagina_activa == "capacidad":
    page_capacidad()

elif pagina_activa == "cartas_cep":
    page_cartas_cep()

elif pagina_activa == "diagnostico":
    page_diagnostico()

elif pagina_activa == "potencia":
    page_potencia()

elif pagina_activa == "monitoreo":
    page_monitoreo()

elif pagina_activa == "eco_analisis":
    page_eco_analisis()