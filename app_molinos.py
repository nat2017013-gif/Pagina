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
st.session_state.setdefault("modo_carga", None)   # None | "excel" | "manual"
st.session_state.setdefault("df_manual_ok", False)
st.session_state.setdefault("df_manual_raw", None)

# ── Selector de modo ──────────────────────────────────────────────────────────
if st.session_state["modo_carga"] is None:
    st.markdown(render_alarm("info", (
        "<strong>📋 Carga de datos históricos (Fase I)</strong><br><br>"
        "Elige la opción que mejor se adapte a tu flujo de trabajo."
    )), unsafe_allow_html=True)
    _mc1, _mc2 = st.columns(2)
    with _mc1:
        if st.button("📂 Cargar Excel", type="primary", use_container_width=True,
                     help="Sube un .xlsx con columnas X1, X2, …, Xn"):
            st.session_state["modo_carga"] = "excel"
            st.rerun()
    with _mc2:
        if st.button("✍️ Ingreso Manual", type="secondary", use_container_width=True,
                     help="Escribe los datos directamente en una tabla editable"):
            st.session_state["modo_carga"] = "manual"
            st.rerun()
    st.stop()

# ── Botón para cambiar de modo ────────────────────────────────────────────────
_modo_label = "📂 Excel" if st.session_state["modo_carga"] == "excel" else "✍️ Manual"
if st.button(f"↩ Cambiar método de carga ({_modo_label})", key="btn_cambiar_modo"):
    st.session_state["modo_carga"]    = None
    st.session_state["df_manual_ok"]  = False
    st.session_state["df_manual_raw"] = None
    st.rerun()

# =============================================================================
# RAMA A — EXCEL (flujo original intacto)
# =============================================================================
if st.session_state["modo_carga"] == "excel":
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
        st.markdown(render_alarm("info", (
            "<strong>📋 Instrucciones de uso</strong><br><br>"
            "1. Descarga la <strong>plantilla de ejemplo</strong> con el botón de arriba<br>"
            "2. Completa con los datos de pesaje de tu línea (columnas X1\u2026Xn)<br>"
            "3. Carga el archivo Excel con el botón de arriba<br>"
            "4. El sistema calculará automáticamente CEP, capacidad, potencia y economía<br><br>"
            "<strong>Límites activos:</strong> LIE = 39.5 kg · LSE = 40.5 kg · Nominal = 40.0 kg"
        )), unsafe_allow_html=True)
        st.stop()

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

# =============================================================================
# RAMA B — INGRESO MANUAL
# =============================================================================
else:
    st.markdown(
        render_section_title("✍️ Ingreso Manual de Datos Históricos (Fase I)"),
        unsafe_allow_html=True,
    )

    # ── Controles de estructura ───────────────────────────────────────────────
    _mc_a, _mc_b = st.columns([1, 1])
    with _mc_a:
        _man_nsg = st.number_input("Nº de subgrupos (filas)", min_value=2, max_value=100,
                                   value=20, key="man_nsg")
    with _mc_b:
        _man_n = st.number_input("Tamaño de muestra n (columnas X)", min_value=2, max_value=10,
                                 value=5, key="man_n")

    _man_xcols = [f"X{i+1}" for i in range(int(_man_n))]

    # ── Inicializar / redimensionar tabla en session_state ────────────────────
    _man_key = f"man_df_{int(_man_nsg)}_{int(_man_n)}"
    if st.session_state.get("man_table_key") != _man_key:
        _man_data = {"Subgrupo": list(range(1, int(_man_nsg)+1)),
                     "Hora":     [""] * int(_man_nsg)}
        for xc in _man_xcols:
            _man_data[xc] = [None] * int(_man_nsg)
        st.session_state["man_df_edit"]   = pd.DataFrame(_man_data)
        st.session_state["man_table_key"] = _man_key

    # ── Tabla editable ────────────────────────────────────────────────────────
    st.markdown(f"**Ingresa los pesos (kg) — {int(_man_nsg)} subgrupos × n={int(_man_n)}:**")
    _man_edited = st.data_editor(
        st.session_state["man_df_edit"],
        width="stretch",
        num_rows="fixed",
        column_config={
            "Subgrupo": st.column_config.NumberColumn("Subgrupo", disabled=True),
            "Hora":     st.column_config.TextColumn("Hora"),
            **{xc: st.column_config.NumberColumn(
                xc, min_value=35.0, max_value=45.0, format="%.4f", step=0.001)
               for xc in _man_xcols}
        },
        key=f"man_editor_{_man_key}"
    )
    st.session_state["man_df_edit"] = _man_edited

    # ── Botón guardar ─────────────────────────────────────────────────────────
    if st.button("💾 Guardar datos iniciales", type="primary", key="btn_man_guardar"):
        _df_check = _man_edited[_man_xcols].apply(pd.to_numeric, errors="coerce")
        _n_nulls  = _df_check.isnull().any(axis=1).sum()
        if _n_nulls > 0:
            st.warning(f"⚠ {_n_nulls} subgrupo(s) tienen celdas vacías. "
                       "Completa todos los valores antes de guardar.")
        elif len(_df_check.dropna()) < 2:
            st.warning("⚠ Se necesitan al menos 2 subgrupos completos.")
        else:
            _df_save = _man_edited.copy()
            for xc in _man_xcols:
                _df_save[xc] = pd.to_numeric(_df_save[xc], errors="coerce")
            _df_save = _df_save.dropna(subset=_man_xcols, how="any").reset_index(drop=True)
            st.session_state["df_manual_raw"] = _df_save
            st.session_state["df_manual_ok"]  = True
            st.rerun()

    if not st.session_state["df_manual_ok"]:
        st.markdown(render_alarm("info", (
            "<strong>📋 Instrucciones</strong><br><br>"
            "1. Configura el número de subgrupos y el tamaño de muestra <strong>n</strong><br>"
            "2. Completa todos los valores de peso en la tabla (kg)<br>"
            "3. Pulsa <strong>💾 Guardar datos iniciales</strong> para activar el análisis<br><br>"
            "<strong>Límites activos:</strong> LIE = 39.5 kg · LSE = 40.5 kg · Nominal = 40.0 kg"
        )), unsafe_allow_html=True)
        st.stop()

    # Datos confirmados → construir df_raw / n / x_cols / s idénticos al flujo Excel
    _proc_ok = False
    try:
        df_raw = st.session_state["df_manual_raw"].copy()
        n, x_cols = detect_subgroups(df_raw)
        issues    = validate_data(df_raw, x_cols)
        s         = compute_spc(df_raw, x_cols, n)
        _proc_ok  = True
    except Exception as _e:
        st.error("❌ No se pudo procesar los datos manuales. Verifica que todos los valores sean numéricos.")
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

# ─────────────────────────────────────────────────────────────────────────────
# KPIs — solo se muestran en Fase I / Capacidad (página de carga inicial)
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.get("pagina", "capacidad") == "capacidad":
    st.markdown("<br>", unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4)

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
    global s, cpk_color, cpk_text, cpk_badge, freq_min, n_proposed

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
    global s, cpk_color, cpk_text, cpk_badge, freq_min, n_proposed

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
    global s, cpk_color, cpk_text, cpk_badge, freq_min, n_proposed

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

    for tipo, msg in alarmas:
        st.markdown(render_alarm(tipo, msg), unsafe_allow_html=True)


def page_potencia():
    global s, cpk_color, cpk_text, cpk_badge, freq_min, n_proposed


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
    global s, cpk_color, cpk_text, cpk_badge, freq_min, n_proposed

    import hashlib

    # ── Límites fijos desde Fase I ────────────────────────────────────────────
    UCL_fijo  = s["UCL_x"];    LCL_fijo  = s["LCL_x"]
    CL_fijo   = s["xbar_bar"]; UCLr_fijo = s["UCL_r"]
    LCLr_fijo = s["LCL_r"];   CLr_fijo  = s["R_bar"]
    sig_fijo  = s["sigma_st"]; n_fijo    = s["n"]

    # ── Inicializar session_state con arquitectura multi-bloque ──────────────
    def _make_bloque(n_muestra, n_sg=5):
        """Crea un bloque de monitoreo vacío con su propio tamaño de muestra."""
        xcols = [f"X{i+1}" for i in range(n_muestra)]
        data  = {"Subgrupo": list(range(1, n_sg + 1)), "Hora": [""]*n_sg}
        for xc in xcols:
            data[xc] = [None]*n_sg
        return {
            "n":           n_muestra,
            "n_sg":        n_sg,
            "df":          pd.DataFrame(data),
            "hash":        "",
            "fig_x":       None,
            "fig_r":       None,
            "new_signals":   [],
            "new_r_signals": [],
            "idx_new":     [],
            "df_nuevos":   None,
            "n_new":       0,
            "n_hist":      0,
        }

    if "mon_n_fijo" not in st.session_state:
        st.session_state["mon_n_fijo"] = n_fijo

    if st.session_state.get("mon_n_fijo") != n_fijo:
        # Archivo recargado con distinto n → resetear todo
        st.session_state["mon_bloques"]       = []
        st.session_state["mon_bloque_activo"] = 0
        st.session_state["mon_n_fijo"]        = n_fijo

    if "mon_bloques" not in st.session_state:
        st.session_state["mon_bloques"]       = []
        st.session_state["mon_bloque_activo"] = 0

    # Compatibilidad: si viene de versión anterior con mon_df suelto, migrar
    if "mon_df" in st.session_state and len(st.session_state.get("mon_bloques", [])) == 0:
        st.session_state["mon_bloques"]       = []
        st.session_state["mon_bloque_activo"] = 0

    # ── Si aún no hay bloques, mostrar controles de creación inicial ──────────
    if len(st.session_state["mon_bloques"]) == 0:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#1A3F5C 0%,#0F2A40 100%);
             color:white;padding:1.1rem 1.5rem 1rem;border-radius:12px;
             border-bottom:3px solid #2563A8;
             box-shadow:0 4px 16px rgba(26,63,92,.18);margin-bottom:.75rem;">
          <div style="display:flex;align-items:center;gap:.75rem;margin-bottom:.3rem">
            <span style="font-size:1.25rem;line-height:1">🔴</span>
            <span style="font-size:1.05rem;font-weight:700;letter-spacing:-.3px;line-height:1.2">
              Monitoreo en Tiempo Real — Fase II
            </span>
          </div>
          <p style="margin:0;opacity:.72;font-size:.78rem;padding-left:2rem;line-height:1.45">
            Configura el tamaño del bloque inicial y pulsa
            <strong style="color:#D6E8F7">Crear bloque inicial</strong> para comenzar.
          </p>
        </div>
        """, unsafe_allow_html=True)
        _ci1, _ci2, _ci3 = st.columns([1, 1, 1])
        with _ci1:
            _init_sg = st.number_input("Filas (subgrupos)", min_value=2, max_value=50,
                                       value=5, key="mon_init_n_sg")
        with _ci2:
            _init_n = st.number_input("Columnas n (tamaño muestra)", min_value=2, max_value=10,
                                      value=int(n_fijo), key="mon_init_n_n")
        with _ci3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("✅ Crear bloque inicial", type="primary", key="btn_crear_bloque_inicial"):
                st.session_state["mon_bloques"]       = [_make_bloque(int(_init_n), int(_init_sg))]
                st.session_state["mon_bloque_activo"] = 0
                st.rerun()
        return   # No renderizar nada más hasta que exista un bloque

    # Referencia corta al bloque activo
    _bi = st.session_state["mon_bloque_activo"]
    _bloques = st.session_state["mon_bloques"]

    # x_cols_mon → columnas del bloque activo
    x_cols_mon = [f"X{i+1}" for i in range(_bloques[_bi]["n"])]

    # ══════════════════════════════════════════════════════════════════════════
    # ENCABEZADO OPERATIVO — Bloque 1
    # ══════════════════════════════════════════════════════════════════════════

    # Inicializar metadatos del turno (claves únicas, sin colisión con estado CEP)
    from datetime import date as _date
    st.session_state.setdefault("mon_meta_operador", "")
    st.session_state.setdefault("mon_meta_turno",    "Mañana")
    st.session_state.setdefault("mon_meta_fecha",    _date.today())
    st.session_state.setdefault("mon_meta_lote",     "")
    st.session_state.setdefault("mon_meta_obs",      "")

    with st.container():
        # ── Banner superior ────────────────────────────────────────────────────
        st.markdown("""
        <div style="background:linear-gradient(135deg,#1A3F5C 0%,#0F2A40 100%);
             color:white;padding:1.1rem 1.5rem 1rem;border-radius:12px;
             border-bottom:3px solid #2563A8;
             box-shadow:0 4px 16px rgba(26,63,92,.18);margin-bottom:.75rem;">
          <div style="display:flex;align-items:center;gap:.75rem;margin-bottom:.3rem">
            <span style="font-size:1.25rem;line-height:1">🔴</span>
            <span style="font-size:1.05rem;font-weight:700;
                  letter-spacing:-.3px;line-height:1.2">
              Monitoreo en Tiempo Real — Fase II
            </span>
          </div>
          <p style="margin:0;opacity:.72;font-size:.78rem;padding-left:2rem;
               line-height:1.45">
            Límites de control <strong style="color:#D6E8F7">fijos</strong>
            desde la Fase I de estabilización.
            Ingresa los nuevos subgrupos y el sistema detectará
            automáticamente si el proceso sale de control estadístico.
          </p>
        </div>
        """, unsafe_allow_html=True)

        # ── Formulario operativo ───────────────────────────────────────────────
        st.markdown("""
        <div style="background:#EEF3F8;border:1px solid #D6E8F7;
             border-left:4px solid #2563A8;border-radius:8px;
             padding:.55rem 1rem .3rem;margin-bottom:.5rem;">
          <span style="font-size:.66rem;font-weight:700;color:#2563A8;
               text-transform:uppercase;letter-spacing:.85px;">
            📋 Datos del turno de muestreo
          </span>
        </div>
        """, unsafe_allow_html=True)

        _mc1, _mc2, _mc3, _mc4 = st.columns([2.2, 1.2, 1.2, 1.8])
        with _mc1:
            st.text_input(
                "👤 Operador / Responsable",
                placeholder="Nombre del operador...",
                key="mon_meta_operador",
            )
        with _mc2:
            st.selectbox(
                "🕐 Turno",
                options=["Mañana", "Tarde", "Noche"],
                key="mon_meta_turno",
            )
        with _mc3:
            st.date_input(
                "📅 Fecha",
                key="mon_meta_fecha",
            )
        with _mc4:
            st.text_input(
                "🏷️ Línea / Lote",
                placeholder="Ej: L-042 / Lote 2025-05",
                key="mon_meta_lote",
            )

        with st.expander("💬 Observaciones del turno (opcional)"):
            st.text_area(
                "Observaciones",
                placeholder="Novedades del turno, incidentes, cambios de operario...",
                height=72,
                label_visibility="collapsed",
                key="mon_meta_obs",
            )

    # ── Separador ──────────────────────────────────────────────────────────────
    st.markdown(
        "<hr style='border:none;border-top:1px solid #E2E8EE;margin:.5rem 0 .6rem'>",
        unsafe_allow_html=True,
    )

    # ── Límites fijos ──────────────────────────────────────────────────────────
    with st.container():
        st.markdown("""
        <div style="background:#EEF6FD;border:1px solid #BDD7EE;
             border-left:4px solid #2563A8;border-radius:8px;
             padding:.7rem 1.1rem .5rem;margin-bottom:.6rem;">
          <span style="font-size:.66rem;font-weight:700;color:#2563A8;
               text-transform:uppercase;letter-spacing:.85px;">
            🔒 Límites de Control Fijos — Fase I (Estabilización)
          </span>
        </div>
        """, unsafe_allow_html=True)
        lf1, lf2, lf3, lf4, lf5, lf6 = st.columns(6)
        for col, lbl, val in [
            (lf1, "LCS X̄ (fijo)",  f"{UCL_fijo:.4f} kg"),
            (lf2, "LC X̄ (fijo)",   f"{CL_fijo:.4f} kg"),
            (lf3, "LCI X̄ (fijo)",  f"{LCL_fijo:.4f} kg"),
            (lf4, "LCS R (fijo)",   f"{UCLr_fijo:.4f} kg"),
            (lf5, "R̄ (fijo)",      f"{CLr_fijo:.4f} kg"),
            (lf6, "n (fijo)",       str(n_fijo)),
        ]:
            with col:
                st.metric(lbl, val)

    st.divider()
    st.markdown(
        render_section_title("📝 Ingreso de Nuevos Subgrupos (Fase II — Monitoreo)"),
        unsafe_allow_html=True,
    )

    # ══ SELECTOR DE BLOQUE ACTIVO (solo si hay más de uno) ═══════════════════
    _bloque_actual = _bloques[_bi]
    if len(_bloques) > 1:
        _info_bloques = " · ".join(
            [f"Bloque {i+1}: n={b['n']}, {b['n_sg']} subgr."
             for i, b in enumerate(_bloques)]
        )
        st.markdown(
            f"<div style='background:#EEF6FD;border:1px solid #BDD7EE;"
            f"border-left:4px solid #2563A8;border-radius:8px;"
            f"padding:.5rem 1rem;margin-bottom:.5rem;font-size:.82rem;'>"
            f"📦 <strong>Bloques registrados:</strong> {_info_bloques}</div>",
            unsafe_allow_html=True
        )
        _opciones_bloque = [f"Bloque {i+1} (n={b['n']}, {b['n_sg']} subgr.)"
                            for i, b in enumerate(_bloques)]
        _bi_sel = st.selectbox(
            "✏️ Editar bloque:",
            options=list(range(len(_bloques))),
            format_func=lambda i: _opciones_bloque[i],
            index=_bi,
            key="mon_bloque_selector"
        )
        if _bi_sel != _bi:
            st.session_state["mon_bloque_activo"] = _bi_sel
            st.rerun()
        _bi = _bi_sel
        _bloque_actual = _bloques[_bi]

    # x_cols_mon → fijas del bloque activo, inmutables
    x_cols_mon = [f"X{i+1}" for i in range(_bloque_actual["n"])]
    _estructura_cambio = False   # bloques son inmutables en estructura

    # ══ MODO DUAL DE ENTRADA ═════════════════════════════════════════════════
    _tab_manual, _tab_excel = st.tabs(["✏️ Ingreso Manual", "📂 Cargar Excel"])

    with _tab_manual:
        with st.container():
            # KEY DINÁMICA: incluye índice de bloque para evitar colisión de keys
            _mon_editor_key = f"mon_editor_b{_bi}_{_bloque_actual['n']}_{_bloque_actual['n_sg']}"

            st.markdown(f"**Anota los pesos nuevos (kg) — Bloque {_bi+1} · n={_bloque_actual['n']}:**")
            mon_edited = st.data_editor(
                _bloque_actual["df"],
                width='stretch',
                num_rows="fixed",
                column_config={
                    "Subgrupo": st.column_config.NumberColumn("Subgrupo", disabled=True),
                    "Hora":     st.column_config.TextColumn("Hora"),
                    **{xc: st.column_config.NumberColumn(
                        xc, min_value=35.0, max_value=45.0, format="%.2f", step=0.1)
                       for xc in x_cols_mon}
                },
                key=_mon_editor_key
            )
            _bloque_actual["df"] = mon_edited

            btn_col1, btn_col2 = st.columns([1, 1])
            with btn_col1:
                if st.button("🗑 Limpiar tabla", type="secondary", key="btn_limpiar_mon"):
                    empty_mon = {"Subgrupo": list(range(1, _bloque_actual["n_sg"]+1)),
                                 "Hora":     [""]*_bloque_actual["n_sg"]}
                    for xc in x_cols_mon:
                        empty_mon[xc] = [None]*_bloque_actual["n_sg"]
                    _bloque_actual["df"]   = pd.DataFrame(empty_mon)
                    _bloque_actual["hash"] = ""

            with btn_col2:
                _df_export = _bloque_actual["df"].copy()
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
                    file_name=f"monitoreo_bloque{_bi+1}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="btn_download_mon"
                )

    with _tab_excel:
        with st.container():
            _mon_xl_file = st.file_uploader(
                "Sube un archivo Excel con columnas numéricas",
                type=["xlsx", "xls"],
                key="mon_excel_uploader"
            )
            if _mon_xl_file is not None:
                try:
                    _mon_xl_raw = pd.read_excel(_mon_xl_file)
                    # Detectar columnas numéricas y eliminar vacías
                    _mon_num_cols = []
                    for _c in _mon_xl_raw.columns:
                        _series = pd.to_numeric(_mon_xl_raw[_c], errors="coerce")
                        if _series.notna().sum() > 0:
                            _mon_xl_raw[_c] = _series
                            _mon_num_cols.append(_c)
                    _mon_xl_clean = _mon_xl_raw[_mon_num_cols].dropna(axis=1, how="all")
                    # Convertir a float
                    _mon_xl_clean = _mon_xl_clean.apply(pd.to_numeric, errors="coerce")

                    # Validar mínimos
                    if len(_mon_xl_clean) < 2:
                        st.warning("⚠ Se necesitan al menos 2 filas con datos numéricos.")
                    elif len(_mon_num_cols) < 2:
                        st.warning("⚠ Se necesitan al menos 2 columnas numéricas.")
                    else:
                        _prev_n = min(10, len(_mon_xl_clean))
                        st.markdown(
                            f"**Vista previa** — {len(_mon_xl_clean)} filas × "
                            f"{len(_mon_num_cols)} columnas numéricas"
                            + (f" &nbsp;·&nbsp; <span style='color:#888;font-size:.82rem'>"
                               f"Mostrando primeras {_prev_n} filas para vista previa.</span>"
                               if len(_mon_xl_clean) > 10 else ""),
                            unsafe_allow_html=True,
                        )
                        st.dataframe(
                            _mon_xl_clean.head(_prev_n),
                            use_container_width=True,
                            height=min(350, 38 + _prev_n * 35),
                            key="mon_excel_preview",
                        )

                        if st.button("✅ Usar estos datos", key="btn_mon_usar_excel"):
                            _bloque_actual["df"]   = _mon_xl_clean.reset_index(drop=True)
                            _bloque_actual["hash"] = ""   # invalida hash anterior
                except Exception as _xl_err:
                    st.error("❌ No se pudo leer el archivo. Verifica que contenga datos numéricos válidos.")
                    with st.expander("Ver detalle técnico"):
                        st.code(str(_xl_err))

    # ══ FORMULARIO NUEVO BLOQUE (debajo de la tabla del bloque activo) ════════
    st.divider()
    st.markdown(
        render_section_title("➕ Agregar Nuevo Bloque de Monitoreo"),
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='background:#EEF6FD;border:1px solid #BDD7EE;"
        "border-left:4px solid #2563A8;border-radius:8px;"
        "padding:.5rem 1rem;margin-bottom:.6rem;font-size:.82rem;'>"
        "Define la estructura del <strong>nuevo bloque</strong>. "
        "Los bloques existentes no se modifican.</div>",
        unsafe_allow_html=True
    )
    # Inicializar valores del formulario de nuevo bloque (desacoplados de cualquier bloque)
    st.session_state.setdefault("mon_new_rows", 5)
    st.session_state.setdefault("mon_new_n",    int(n_fijo))

    _nb_a, _nb_b, _nb_c, _nb_d = st.columns([1, 1, 1, 1])
    with _nb_a:
        _new_rows = st.number_input(
            "Nº de subgrupos (filas)",
            min_value=2, max_value=50,
            value=st.session_state["mon_new_rows"],
            key="mon_new_rows",
        )
    with _nb_b:
        _new_n = st.number_input(
            "Tamaño de muestra n (columnas X)",
            min_value=2, max_value=10,
            value=st.session_state["mon_new_n"],
            key="mon_new_n",
        )
    with _nb_c:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Crear nuevo bloque", type="primary", key="btn_nuevo_bloque"):
            _bloques.append(_make_bloque(int(_new_n), int(_new_rows)))
            st.session_state["mon_bloques"]       = _bloques
            st.session_state["mon_bloque_activo"] = len(_bloques) - 1
            st.rerun()
    with _nb_d:
        st.markdown("<br>", unsafe_allow_html=True)
        _puede_eliminar = len(_bloques) > 1
        if st.button(
            f"🗑 Eliminar Bloque {_bi+1}",
            key="btn_eliminar_bloque",
            type="secondary",
            disabled=not _puede_eliminar,
            help=("Elimina el bloque activo" if _puede_eliminar
                  else "No se puede eliminar el único bloque existente"),
        ):
            _bloques.pop(_bi)
            new_bi = min(_bi, len(_bloques) - 1)
            st.session_state["mon_bloques"]       = _bloques
            st.session_state["mon_bloque_activo"] = new_bi
            st.session_state.pop("mon_hash_global", None)
            st.rerun()

    # ══ BLOQUE 3 — PROCESAMIENTO (multi-bloque) ═══════════════════════════════
    # Procesar TODOS los bloques para concatenar en los gráficos.
    # Cada bloque tiene su propio n y columnas X; se calcula xbar/R independientemente.
    _cualquier_dato = False

    for _bk_idx, _bk in enumerate(_bloques):
        _bk_xcols = [f"X{i+1}" for i in range(_bk["n"])]
        _bk_raw   = _bk["df"].copy()
        _bk_raw[_bk_xcols] = _bk_raw[[c for c in _bk_xcols if c in _bk_raw.columns]].apply(
            pd.to_numeric, errors="coerce"
        )
        _bk_cols_ok  = [c for c in _bk_xcols if c in _bk_raw.columns]
        _bk_n_valids = _bk_raw[_bk_cols_ok].notna().sum(axis=1)
        _bk_filas    = _bk_raw[_bk_n_valids >= 2].index
        if len(_bk_filas) >= 2:
            _bk_clean = _bk_raw.loc[_bk_filas].reset_index(drop=True)
            _bk_num   = _bk_clean[_bk_cols_ok].apply(pd.to_numeric, errors="coerce")
            _bk_clean["xbar"] = _bk_num.mean(axis=1, skipna=True)
            _bk_clean["R"]    = _bk_num.max(axis=1, skipna=True) - _bk_num.min(axis=1, skipna=True)
            _bk["_df_proc"] = _bk_clean   # resultado temporal para este render
            _cualquier_dato = True
        else:
            _bk["_df_proc"] = None

    # El bloque activo también actualiza df_nuevos para la sección de resumen
    df_nuevos = _bloques[_bi].get("_df_proc")
    df_mon_raw = _bloque_actual["df"].copy()

    # Avisar si el bloque activo aún no tiene suficientes datos
    if not _estructura_cambio and not _cualquier_dato:
        st.warning("⚠ Se requieren al menos 2 subgrupos con datos para graficar. "
                   "Completa más filas en la tabla.")

    # ── HASH Y FIGURAS PERSISTENTES (concatena todos los bloques) ────────────
    # Construir hash global sobre todos los bloques con datos
    _global_hash_src = "".join(
        bk["_df_proc"].to_csv(index=False)
        for bk in _bloques if bk.get("_df_proc") is not None
    )

    if not _estructura_cambio and _cualquier_dato:
        nuevo_hash = hashlib.md5(_global_hash_src.encode()).hexdigest()

        # Usar una clave única por bloque activo para las figuras cacheadas
        _fig_hash_key = f"mon_hash_global"
        if nuevo_hash != st.session_state.get(_fig_hash_key, ""):
            # Datos cambiaron — reconstruir figuras concatenando todos los bloques
            st.session_state[_fig_hash_key] = nuevo_hash

            n_hist   = len(s["df"]); df_hist = s["df"].copy()
            idx_hist = list(range(1, n_hist+1))

            # Acumular todos los subgrupos nuevos de todos los bloques
            _all_xbar    = []
            _all_R       = []
            _all_idx_new = []
            _cursor      = n_hist + 1
            _bloque_boundaries = []   # (start_idx, end_idx, bloque_num)

            for _bk_idx, _bk in enumerate(_bloques):
                _bk_proc = _bk.get("_df_proc")
                if _bk_proc is None:
                    continue
                _bk_len = len(_bk_proc)
                _bk_idx_new = list(range(_cursor, _cursor + _bk_len))
                _all_xbar   += list(_bk_proc["xbar"])
                _all_R      += list(_bk_proc["R"])
                _all_idx_new += _bk_idx_new
                _bloque_boundaries.append((_cursor, _cursor + _bk_len - 1, _bk_idx + 1))
                _cursor += _bk_len

            n_new   = len(_all_xbar)
            idx_new = _all_idx_new

            new_signals = [i for i, xb_n in enumerate(_all_xbar)
                           if xb_n > UCL_fijo or xb_n < LCL_fijo]
            new_colors  = [CR if i in new_signals else "#E67E22" for i in range(n_new)]

            fig_mon = go.Figure()
            for y0, y1, col_bg in [
                (LCL_fijo, CL_fijo - (CL_fijo-LCL_fijo)*2/3, "rgba(231,76,60,.05)"),
                (CL_fijo + (UCL_fijo-CL_fijo)*2/3, UCL_fijo,  "rgba(231,76,60,.05)"),
                (CL_fijo - (CL_fijo-LCL_fijo)/3, CL_fijo + (UCL_fijo-CL_fijo)/3, "rgba(39,174,96,.05)"),
            ]:
                fig_mon.add_hrect(y0=y0, y1=y1, fillcolor=col_bg, line_width=0)
            _LC_COLOR  = "#1B4F72"
            _LIM_COLOR = "#C0392B"
            for y, lbl, col_ln, dash, lw in [
                (UCL_fijo, f"LCS = {UCL_fijo:.3f}", _LIM_COLOR, "dash",  2.5),
                (CL_fijo,  f"LC = {CL_fijo:.3f}",   _LC_COLOR,  "solid", 2.2),
                (LCL_fijo, f"LCI = {LCL_fijo:.3f}", _LIM_COLOR, "dash",  2.5),
            ]:
                fig_mon.add_hline(y=y, line_dash=dash, line_color=col_ln, line_width=lw,
                                  annotation_text=lbl, annotation_position="right",
                                  annotation_font_size=10, annotation_font_color=col_ln,
                                  annotation_bgcolor="rgba(255,255,255,.75)")
            fig_mon.add_vline(x=n_hist+0.5, line_dash="dot", line_color="#95A5A6", line_width=1.6,
                              annotation_text="▶ Fase II", annotation_font_size=10,
                              annotation_font_color="#5D6D7E",
                              annotation_bgcolor="rgba(255,255,255,.8)")
            # Líneas divisorias entre bloques
            for _bnd_start, _bnd_end, _bnd_num in _bloque_boundaries[1:]:
                fig_mon.add_vline(x=_bnd_start - 0.5, line_dash="dot",
                                  line_color="#8E44AD", line_width=1.2,
                                  annotation_text=f"B{_bnd_num}",
                                  annotation_font_size=9, annotation_font_color="#8E44AD",
                                  annotation_bgcolor="rgba(255,255,255,.7)")
            hist_colors_mon = [_LIM_COLOR if ix in set(s["signals_x"]) else _LC_COLOR
                               for ix in df_hist.index]
            fig_mon.add_trace(go.Scatter(
                x=idx_hist, y=df_hist["xbar"], mode="lines+markers", name="Histórico (Fase I)",
                line=dict(color=_LC_COLOR, width=1.6),
                marker=dict(color=hist_colors_mon, size=7, opacity=0.72,
                            line=dict(color="white", width=1.1)),
                hovertemplate=(
                    "<b>Subgrupo %{x}</b><br>"
                    "x̄ = %{y:.4f} kg<br>"
                    "<span style='color:#7F8C8D'>Fase I — Histórico</span>"
                    "<extra></extra>"
                )
            ))
            fig_mon.add_trace(go.Scatter(
                x=idx_new, y=_all_xbar, mode="lines+markers", name="Nuevos (Fase II)",
                line=dict(color="#E67E22", width=2.4),
                marker=dict(color=new_colors, size=11,
                            line=dict(color="white", width=2.0)),
                hovertemplate=(
                    "<b>Subgrupo %{x}</b><br>"
                    "x̄ = %{y:.4f} kg<br>"
                    "<span style='color:#E67E22'>Fase II — Nuevo</span>"
                    "<extra></extra>"
                )
            ))
            if new_signals:
                si_new = [idx_new[i] for i in new_signals]
                sv_new = [_all_xbar[i] for i in new_signals]
                fig_mon.add_trace(go.Scatter(
                    x=si_new, y=sv_new, mode="markers", name="🚨 SEÑAL",
                    marker=dict(color=_LIM_COLOR, size=18, symbol="x-open",
                                line=dict(color=_LIM_COLOR, width=3)),
                    hovertemplate=(
                        "<b>⚠ FUERA DE CONTROL</b><br>"
                        "Subgrupo %{x}<br>"
                        "x̄ = %{y:.4f} kg"
                        "<extra>🚨 Señal</extra>"
                    )
                ))
            # Rango Y fijo: basado en UCL/LCL + 10% padding — sin auto-scale
            _rng_pad = (UCL_fijo - LCL_fijo) * 0.10
            _y_lo    = LCL_fijo - _rng_pad
            _y_hi    = UCL_fijo + _rng_pad

            fig_mon.update_layout(
                template="plotly_white", height=400,
                plot_bgcolor="#FAFCFF",
                paper_bgcolor="white",
                title=dict(
                    text=(f"Carta X̄ de Monitoreo — {n_hist} históricos + {n_new} nuevos"
                          f"{'  |  🚨 ' + str(len(new_signals)) + ' señal(es)' if new_signals else '  |  ✅ Proceso estable'}"),
                    font=dict(size=13, color=_LIM_COLOR if new_signals else _LC_COLOR,
                              family="IBM Plex Sans, sans-serif"),
                    x=0, xanchor="left", pad=dict(l=4)
                ),
                xaxis=dict(
                    title=dict(text="Número de Subgrupo", font=dict(size=11)),
                    tickmode="linear", tickfont=dict(size=10),
                    range=[0, n_hist+n_new+1],
                    gridcolor="#E8EDF2", gridwidth=1, zeroline=False,
                ),
                yaxis=dict(
                    title=dict(text="Peso promedio x̄ (kg)", font=dict(size=11)),
                    tickfont=dict(size=10),
                    range=[_y_lo, _y_hi],
                    gridcolor="#E8EDF2", gridwidth=1, zeroline=False,
                ),
                legend=dict(orientation="h", y=1.07, x=0,
                            font=dict(size=10), bgcolor="rgba(255,255,255,0)"),
                hoverlabel=dict(bgcolor="white", bordercolor="#D5D8DC",
                                font=dict(size=11, family="IBM Plex Sans, sans-serif")),
                margin=dict(l=50, r=110, t=65, b=45),
            )

            # Carta R
            fig_mon_r = go.Figure()
            for y, lbl, col_ln, dash, lw in [
                (UCLr_fijo, f"LCS = {UCLr_fijo:.3f}", _LIM_COLOR, "dash",  2.5),
                (CLr_fijo,  f"R̄ = {CLr_fijo:.3f}",   "#1E8449",  "solid", 2.2),
            ]:
                fig_mon_r.add_hline(y=y, line_dash=dash, line_color=col_ln, line_width=lw,
                                    annotation_text=lbl, annotation_position="right",
                                    annotation_font_size=9, annotation_font_color=col_ln,
                                    annotation_bgcolor="rgba(255,255,255,.75)")
            if LCLr_fijo > 0:
                fig_mon_r.add_hline(y=LCLr_fijo, line_dash="dash", line_color=_LIM_COLOR,
                                    line_width=2.5,
                                    annotation_text=f"LCI = {LCLr_fijo:.3f}",
                                    annotation_position="right", annotation_font_size=9,
                                    annotation_font_color=_LIM_COLOR,
                                    annotation_bgcolor="rgba(255,255,255,.75)")
            fig_mon_r.add_vline(x=n_hist+0.5, line_dash="dot", line_color="#95A5A6",
                                line_width=1.6)
            new_r_signals = [i for i, rv in enumerate(_all_R) if rv > UCLr_fijo]
            new_r_colors  = [_LIM_COLOR if i in new_r_signals else "#E67E22"
                             for i in range(n_new)]
            fig_mon_r.add_trace(go.Scatter(
                x=idx_hist, y=df_hist["R"], mode="lines+markers", name="R Histórico",
                line=dict(color="#1E8449", width=1.6),
                marker=dict(
                    color=[_LIM_COLOR if ix in set(s["signals_r"]) else "#1E8449"
                           for ix in df_hist.index],
                    size=7, opacity=0.72, symbol="diamond",
                    line=dict(color="white", width=1.1)
                ),
                hovertemplate=(
                    "<b>Subgrupo %{x}</b><br>"
                    "R = %{y:.4f} kg<br>"
                    "<span style='color:#7F8C8D'>Fase I — Histórico</span>"
                    "<extra></extra>"
                )
            ))
            fig_mon_r.add_trace(go.Scatter(
                x=idx_new, y=_all_R, mode="lines+markers", name="R Nuevos",
                line=dict(color="#E67E22", width=2.4),
                marker=dict(color=new_r_colors, size=11, symbol="diamond",
                            line=dict(color="white", width=2.0)),
                hovertemplate=(
                    "<b>Subgrupo %{x}</b><br>"
                    "R = %{y:.4f} kg<br>"
                    "<span style='color:#E67E22'>Fase II — Nuevo</span>"
                    "<extra></extra>"
                )
            ))
            fig_mon_r.update_layout(
                template="plotly_white", height=300,
                plot_bgcolor="#FAFCFF",
                paper_bgcolor="white",
                title=dict(text="Carta R de Monitoreo — Variabilidad entre muestras",
                           font=dict(size=12, color=_LC_COLOR,
                                     family="IBM Plex Sans, sans-serif"),
                           x=0, xanchor="left", pad=dict(l=4)),
                xaxis=dict(
                    title=dict(text="Subgrupo", font=dict(size=11)),
                    tickmode="linear", tickfont=dict(size=10),
                    range=[0, n_hist+n_new+1],
                    gridcolor="#E8EDF2", gridwidth=1, zeroline=False,
                ),
                yaxis=dict(
                    title=dict(text="Rango (kg)", font=dict(size=11)),
                    tickfont=dict(size=10),
                    gridcolor="#E8EDF2", gridwidth=1, zeroline=False,
                ),
                legend=dict(orientation="h", y=1.1, x=0,
                            font=dict(size=10), bgcolor="rgba(255,255,255,0)"),
                hoverlabel=dict(bgcolor="white", bordercolor="#D5D8DC",
                                font=dict(size=11, family="IBM Plex Sans, sans-serif")),
                margin=dict(l=50, r=110, t=60, b=45),
            )

            # Guardar señales en session_state para las alertas y exportación
            # df_nuevos_ss = bloque activo (para resumen); _all_* para alertas globales
            _df_nuevos_para_export = (
                _bloques[_bi].get("_df_proc")
                if _bloques[_bi].get("_df_proc") is not None
                else pd.DataFrame(columns=x_cols_mon + ["xbar", "R"])
            )
            st.session_state["mon_fig_x"]       = fig_mon
            st.session_state["mon_fig_r"]       = fig_mon_r
            st.session_state["mon_new_signals"]  = new_signals
            st.session_state["mon_new_r_signals"]= new_r_signals
            st.session_state["mon_idx_new"]      = idx_new
            st.session_state["mon_df_nuevos"]    = _df_nuevos_para_export.copy()
            st.session_state["mon_n_new"]        = n_new
            st.session_state["mon_n_hist"]       = n_hist
            # Listas globales para alertas (índices coinciden con new_signals)
            st.session_state["mon_all_xbar"]     = list(_all_xbar)
            st.session_state["mon_all_R"]        = list(_all_R)

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
        n_new         = st.session_state["mon_n_new"]
        # Listas globales: índices de new_signals/new_r_signals apuntan aquí
        _all_xbar_ss  = st.session_state.get("mon_all_xbar", [])
        _all_R_ss     = st.session_state.get("mon_all_R",    [])

        st.markdown(render_section_title("🚨 Alertas de Monitoreo"), unsafe_allow_html=True)
        if not new_signals and not new_r_signals:
            st.markdown(render_alarm("ok",
                "✅ Todos los subgrupos nuevos están bajo control. "
                "El proceso se mantiene estable."), unsafe_allow_html=True)
        else:
            if new_signals:
                sgs_txt  = ", ".join([f"S{idx_new[i]}" for i in new_signals])
                vals_txt = ", ".join([f"{_all_xbar_ss[i]:.4f}" for i in new_signals
                                      if i < len(_all_xbar_ss)])
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
        st.divider()
        # ── Tablas por bloque ─────────────────────────────────────────────────
        st.markdown(render_section_title("📋 Tablas de Subgrupos por Bloque"),
                    unsafe_allow_html=True)
        for _tbl_bi, _tbl_bk in enumerate(_bloques):
            _tbl_proc = _tbl_bk.get("_df_proc")
            _is_active = (_tbl_bi == _bi)
            _border_color = "#2563A8" if _is_active else "#BDD7EE"
            _label_extra  = " (activo)" if _is_active else ""
            st.markdown(
                f"<div style='background:#EEF6FD;border:1px solid {_border_color};"
                f"border-left:4px solid {_border_color};border-radius:8px;"
                f"padding:.45rem 1rem;margin:.4rem 0 .25rem;font-size:.8rem;font-weight:600'>"
                f"📦 Bloque {_tbl_bi+1}{_label_extra} — n={_tbl_bk['n']} · "
                f"{_tbl_bk['n_sg']} subgrupos configurados</div>",
                unsafe_allow_html=True
            )
            if _tbl_proc is not None and len(_tbl_proc) > 0:
                _disp_cols = (
                    [c for c in _tbl_proc.columns
                     if c not in ("xbar", "R")]
                    + ["xbar", "R"]
                )
                _disp_cols = [c for c in _disp_cols if c in _tbl_proc.columns]
                st.dataframe(
                    _tbl_proc[_disp_cols].style.format(
                        {c: "{:.4f}" for c in _disp_cols
                         if c not in ("Subgrupo", "Hora", "xbar", "R")}
                        | {"xbar": "{:.4f}", "R": "{:.4f}"}
                    ),
                    use_container_width=True,
                    height=min(400, 38 + len(_tbl_proc) * 35),
                    key=f"tbl_bloque_{_tbl_bi}",
                )
            else:
                st.markdown(
                    "<span style='color:#95A5A6;font-size:.8rem'>— Sin datos suficientes aún —</span>",
                    unsafe_allow_html=True
                )

        with st.container():
            st.markdown(render_section_title("📊 Resumen de Nuevos Subgrupos"),
                        unsafe_allow_html=True)
            xb_new = sum(_all_xbar) / len(_all_xbar) if _all_xbar else 0.0
            r_new  = sum(_all_R)    / len(_all_R)    if _all_R    else 0.0
            rs1, rs2, rs3, rs4 = st.columns(4)
            with rs1:
                st.metric("x̄ nuevos", f"{xb_new:.4f} kg",
                          delta=f"{(xb_new-CL_fijo)*1000:+.1f} g vs LC")
            with rs2:
                st.metric("R̄ nuevos", f"{r_new:.4f} kg",
                          delta=f"{(r_new-CLr_fijo)*1000:+.1f} g vs R̄")
            with rs3:
                st.metric("Subgrupos bajo control",
                          f"{n_new - len(new_signals)}/{n_new}")
            with rs4:
                pct_ok   = (n_new - len(new_signals)) / n_new * 100
                color_ok = CG if pct_ok == 100 else CY if pct_ok >= 80 else CR
                st.markdown(f"""
                <div style="background:white;border-radius:10px;padding:.8rem 1rem;
                     box-shadow:0 1px 6px rgba(0,0,0,.08);
                     border-left:4px solid {color_ok};text-align:center;">
                  <div style="font-size:1.6rem;font-weight:700;
                       color:{color_ok};line-height:1.2">{pct_ok:.0f}%</div>
                  <div style="font-size:.72rem;color:#7F8C8D;
                       margin-top:.2rem">Tasa de conformidad</div>
                </div>""", unsafe_allow_html=True)

        # ══ PASO 5 — EXPORTACIÓN HTML ════════════════════════════════════════
        st.divider()
        with st.container():
            st.markdown(render_section_title("📄 Exportar Reporte de Monitoreo"),
                        unsafe_allow_html=True)

            # ── Campos del reporte ────────────────────────────────────────────
            _exp_c1, _exp_c2 = st.columns([3, 1])
            with _exp_c1:
                _exp_title = st.text_input(
                    "Título del reporte",
                    value="Reporte de Monitoreo CEP — Línea de Empaque Mogolla",
                    key="mon_export_title",
                )
            with _exp_c2:
                _exp_resp = st.text_input(
                    "Responsable del reporte",
                    value=st.session_state.get("mon_meta_operador", ""),
                    key="mon_export_responsable",
                )
            _exp_notes = st.text_input(
                "Notas finales (opcional)",
                placeholder="Acciones tomadas, conclusiones, firma...",
                key="mon_export_notes",
            )
            _exp_obs = st.text_area(
                "Observaciones adicionales (opcional)",
                placeholder="Contexto del turno, condiciones del equipo...",
                height=68,
                key="mon_export_obs",
            )

            # ── Construir HTML ────────────────────────────────────────────────
            import datetime as _dt

            _fig_x_html = st.session_state["mon_fig_x"].to_html(
                full_html=False, include_plotlyjs="cdn"
            )
            _fig_r_html = st.session_state["mon_fig_r"].to_html(
                full_html=False, include_plotlyjs=False   # cdn ya incluido arriba
            )

            _ts       = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
            _operador = st.session_state.get("mon_meta_operador", "—") or "—"
            _turno    = st.session_state.get("mon_meta_turno",    "—")
            _fecha    = str(st.session_state.get("mon_meta_fecha", "—"))
            _lote     = st.session_state.get("mon_meta_lote",     "—") or "—"
            _obs_tur  = st.session_state.get("mon_meta_obs",      "") or ""

            _n_h   = st.session_state.get("mon_n_hist", 0)
            _n_n   = st.session_state.get("mon_n_new",  0)
            _nsigs = len(st.session_state.get("mon_new_signals",   []))
            _rsigs = len(st.session_state.get("mon_new_r_signals", []))
            _pct_ok_exp = ((_n_n - _nsigs) / _n_n * 100) if _n_n > 0 else 0.0
            _estado_proceso = (
                "🚨 FUERA DE CONTROL" if (_nsigs + _rsigs) > 0 else "✅ BAJO CONTROL"
            )
            _estado_color = "#C0392B" if (_nsigs + _rsigs) > 0 else "#1E8449"

            # Tabla de subgrupos nuevos — construida desde listas globales
            _idx_new_ss   = st.session_state.get("mon_idx_new", list(range(1, _n_n+1)))
            _new_sigs_set = set(st.session_state.get("mon_new_signals", []))
            _all_xbar_exp = st.session_state.get("mon_all_xbar", [])
            _all_R_exp    = st.session_state.get("mon_all_R",    [])

            _trows = ""
            for _ri in range(_n_n):
                _bg    = "#FFF0F0" if _ri in _new_sigs_set else "white"
                _flag  = " 🚨" if _ri in _new_sigs_set else ""
                _sg_num = _idx_new_ss[_ri] if _ri < len(_idx_new_ss) else _ri + 1
                _xb_val = f"{_all_xbar_exp[_ri]:.4f}" if _ri < len(_all_xbar_exp) else "—"
                _r_val  = f"{_all_R_exp[_ri]:.4f}"    if _ri < len(_all_R_exp)    else "—"
                _trows += (
                    f"<tr style='background:{_bg}'>"
                    f"<td style='padding:.3rem .6rem;font-weight:600'>{_sg_num}{_flag}</td>"
                    f"<td style='padding:.3rem .6rem;text-align:right;font-family:monospace'>"
                    f"{_xb_val}</td>"
                    f"<td style='padding:.3rem .6rem;text-align:right;font-family:monospace'>"
                    f"{_r_val}</td>"
                    f"</tr>"
                )
            _thead_xcols = ""  # tabla simplificada: solo subgrupo, x̄, R (columnas X varían por bloque)

            # Alertas para el reporte
            _alerta_html = ""
            if _nsigs == 0 and _rsigs == 0:
                _alerta_html = (
                    "<div style='background:#EAFAF1;border-left:4px solid #1E8449;"
                    "padding:.6rem 1rem;border-radius:4px;margin:.4rem 0'>"
                    "✅ Todos los subgrupos nuevos están dentro de los límites de control.</div>"
                )
            else:
                if _nsigs > 0:
                    _sgs_t = ", ".join(
                        [f"S{_idx_new_ss[i]}" for i in st.session_state["mon_new_signals"]
                         if i < len(_idx_new_ss)]
                    )
                    _alerta_html += (
                        f"<div style='background:#FDEDEC;border-left:4px solid #C0392B;"
                        f"padding:.6rem 1rem;border-radius:4px;margin:.4rem 0'>"
                        f"🚨 <strong>SEÑAL CARTA X̄:</strong> Subgrupos {_sgs_t} fuera de límites.</div>"
                    )
                if _rsigs > 0:
                    _sgs_r = ", ".join(
                        [f"S{_idx_new_ss[i]}" for i in st.session_state["mon_new_r_signals"]
                         if i < len(_idx_new_ss)]
                    )
                    _alerta_html += (
                        f"<div style='background:#FDEDEC;border-left:4px solid #C0392B;"
                        f"padding:.6rem 1rem;border-radius:4px;margin:.4rem 0'>"
                        f"🚨 <strong>SEÑAL CARTA R:</strong> Variabilidad inestable en subgrupos {_sgs_r}.</div>"
                    )

            _notas_html  = f"<p style='margin:.3rem 0'>{_exp_notes}</p>" if _exp_notes.strip() else ""
            _obs_html    = (f"<p style='margin:.3rem 0;color:#555'>{_exp_obs}</p>"
                            if _exp_obs.strip() else "")
            _obs_tur_html = (f"<p style='margin:.3rem 0;font-style:italic;color:#666'>{_obs_tur}</p>"
                             if _obs_tur.strip() else "")

            _html_reporte = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_exp_title}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',Arial,sans-serif;font-size:13px;color:#1A1A2E;background:#F4F6F9;padding:0}}
  .page{{max-width:1100px;margin:0 auto;background:white;padding:2rem 2.5rem 3rem}}
  .header{{background:linear-gradient(135deg,#1B4F72,#154360);color:white;
            padding:1.4rem 2rem;border-radius:10px;margin-bottom:1.5rem}}
  .header h1{{font-size:1.25rem;font-weight:700;margin-bottom:.3rem}}
  .header .sub{{font-size:.8rem;opacity:.8}}
  .meta-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:.7rem;margin-bottom:1.2rem}}
  .meta-card{{background:#EEF3F8;border-radius:7px;padding:.55rem .8rem;
              border-left:3px solid #1B4F72}}
  .meta-card .lbl{{font-size:.65rem;font-weight:700;color:#5D6D7E;
                   text-transform:uppercase;letter-spacing:.6px}}
  .meta-card .val{{font-size:.88rem;font-weight:600;color:#1A1A2E;margin-top:.15rem}}
  .kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:.7rem;margin-bottom:1.2rem}}
  .kpi{{background:#F8F9FA;border-radius:7px;padding:.65rem .85rem;text-align:center;
         border-top:3px solid #1B4F72}}
  .kpi .v{{font-size:1.35rem;font-weight:700;line-height:1.2}}
  .kpi .l{{font-size:.68rem;color:#7F8C8D;margin-top:.2rem}}
  .section{{margin-bottom:1.3rem}}
  .section-title{{font-size:.72rem;font-weight:700;color:#1B4F72;text-transform:uppercase;
                  letter-spacing:.8px;padding:.4rem 0;border-bottom:2px solid #D6E8F7;
                  margin-bottom:.6rem}}
  table{{width:100%;border-collapse:collapse;font-size:.8rem}}
  th{{background:#1B4F72;color:white;padding:.4rem .6rem;text-align:left;font-weight:600}}
  td{{padding:.3rem .6rem;border-bottom:1px solid #EEF0F3}}
  tr:hover td{{background:#F8FBFF}}
  .estado{{display:inline-block;padding:.25rem .75rem;border-radius:20px;
            font-weight:700;font-size:.78rem;
            background:{_estado_color}18;color:{_estado_color};
            border:1px solid {_estado_color}44}}
  .footer{{margin-top:2rem;padding-top:1rem;border-top:1px solid #D5D8DC;
            font-size:.72rem;color:#95A5A6;display:flex;justify-content:space-between}}
  .fig-wrap{{margin:.6rem 0;border:1px solid #E8EDF2;border-radius:8px;overflow:hidden}}
</style>
</head>
<body>
<div class="page">

  <div class="header">
    <h1>{_exp_title}</h1>
    <div class="sub">
      Molinos Santa Marta S.A.S. &nbsp;·&nbsp;
      Control Estadístico de Procesos — Fase II &nbsp;·&nbsp;
      Generado: {_ts} &nbsp;·&nbsp;
      Estado: <span style="font-weight:700;color:{'#FF8C8C' if (_nsigs+_rsigs)>0 else '#A8F0C6'}">{_estado_proceso}</span>
    </div>
  </div>

  <div class="meta-grid">
    <div class="meta-card"><div class="lbl">Operador</div><div class="val">{_operador}</div></div>
    <div class="meta-card"><div class="lbl">Turno</div><div class="val">{_turno}</div></div>
    <div class="meta-card"><div class="lbl">Fecha</div><div class="val">{_fecha}</div></div>
    <div class="meta-card"><div class="lbl">Línea / Lote</div><div class="val">{_lote}</div></div>
  </div>

  <div class="kpi-row">
    <div class="kpi">
      <div class="v" style="color:#1B4F72">{_n_h}</div>
      <div class="l">Subgrupos históricos</div>
    </div>
    <div class="kpi">
      <div class="v" style="color:#E67E22">{_n_n}</div>
      <div class="l">Subgrupos nuevos</div>
    </div>
    <div class="kpi">
      <div class="v" style="color:{_estado_color}">{_nsigs + _rsigs}</div>
      <div class="l">Señales detectadas</div>
    </div>
    <div class="kpi">
      <div class="v" style="color:{_estado_color}">{_pct_ok_exp:.0f}%</div>
      <div class="l">Conformidad Fase II</div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Límites de Control Fijos — Fase I</div>
    <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:.5rem;font-size:.8rem">
      <div><strong>LCS X̄</strong><br>{UCL_fijo:.4f} kg</div>
      <div><strong>LC X̄</strong><br>{CL_fijo:.4f} kg</div>
      <div><strong>LCI X̄</strong><br>{LCL_fijo:.4f} kg</div>
      <div><strong>LCS R</strong><br>{UCLr_fijo:.4f} kg</div>
      <div><strong>R̄</strong><br>{CLr_fijo:.4f} kg</div>
      <div><strong>n (fijo)</strong><br>{n_fijo}</div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Alertas</div>
    {_alerta_html}
  </div>

  <div class="section">
    <div class="section-title">Tabla de Subgrupos Nuevos (Fase II)</div>
    <table>
      <thead>
        <tr>
          <th>Subgrupo</th>
          {_thead_xcols}
          <th style="text-align:right">x̄ (kg)</th>
          <th style="text-align:right">R (kg)</th>
        </tr>
      </thead>
      <tbody>{_trows}</tbody>
    </table>
  </div>

  <div class="section">
    <div class="section-title">Carta X̄ — Histórico + Nuevos Subgrupos</div>
    <div class="fig-wrap">{_fig_x_html}</div>
  </div>

  <div class="section">
    <div class="section-title">Carta R — Variabilidad</div>
    <div class="fig-wrap">{_fig_r_html}</div>
  </div>

  {"<div class='section'><div class='section-title'>Notas Finales</div>" + _notas_html + "</div>" if _exp_notes.strip() else ""}
  {"<div class='section'><div class='section-title'>Observaciones Adicionales</div>" + _obs_html + "</div>" if _exp_obs.strip() else ""}
  {"<div class='section'><div class='section-title'>Observaciones del Turno</div>" + _obs_tur_html + "</div>" if _obs_tur.strip() else ""}

  <div class="footer">
    <span>Responsable: <strong>{_exp_resp or "—"}</strong></span>
    <span>Molinos Santa Marta S.A.S. &nbsp;·&nbsp; CEP v2.1 &nbsp;·&nbsp; {_ts}</span>
  </div>

</div>
</body>
</html>"""

            st.download_button(
                label="📥 Descargar Reporte HTML de Monitoreo",
                data=_html_reporte.encode("utf-8"),
                file_name="reporte_monitoreo.html",
                mime="text/html",
                type="primary",
                key="btn_export_html_mon",
            )

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
    global s, cpk_color, cpk_text, cpk_badge, freq_min, n_proposed


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
