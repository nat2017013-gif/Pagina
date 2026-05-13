"""
=============================================================================
  MÓDULO: calculos_cep.py
  Funciones de cálculo estadístico para el sistema CEP
  Molinos Santa Marta S.A.S.
=============================================================================
"""

import pandas as pd
import numpy as np
from scipy import stats
import io
import warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES CORPORATIVAS
# ─────────────────────────────────────────────────────────────────────────────
LSL     = 39.5
USL     = 40.5
NOMINAL = 40.0

CONTROL_CONSTANTS = {
    2:  {"d2": 1.128, "A2": 1.880, "D3": 0.000, "D4": 3.267},
    3:  {"d2": 1.693, "A2": 1.023, "D3": 0.000, "D4": 2.574},
    4:  {"d2": 2.059, "A2": 0.729, "D3": 0.000, "D4": 2.282},
    5:  {"d2": 2.326, "A2": 0.577, "D3": 0.000, "D4": 2.114},
    6:  {"d2": 2.534, "A2": 0.483, "D3": 0.000, "D4": 2.004},
    7:  {"d2": 2.704, "A2": 0.419, "D3": 0.076, "D4": 1.924},
    8:  {"d2": 2.847, "A2": 0.373, "D3": 0.136, "D4": 1.864},
    9:  {"d2": 2.970, "A2": 0.337, "D3": 0.184, "D4": 1.816},
    10: {"d2": 3.078, "A2": 0.308, "D3": 0.223, "D4": 1.777},
}


# ─────────────────────────────────────────────────────────────────────────────
# DETECCIÓN Y VALIDACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def detect_subgroups(df):
    x_cols = sorted(
        [c for c in df.columns if str(c).strip().upper().startswith("X") and str(c).strip()[1:].isdigit()],
        key=lambda c: int(str(c).strip()[1:])
    )
    n = len(x_cols)
    if n < 2 or n > 10:
        raise ValueError(f"Se detectaron {n} columnas X. Deben ser entre 2 y 10.")
    return n, x_cols


def validate_data(df, x_cols):
    issues = []
    for col in x_cols:
        bad = pd.to_numeric(df[col], errors="coerce").isna().sum()
        if bad: issues.append(f"Columna {col}: {bad} valor(es) no numérico(s).")
    vals = df[x_cols].values.flatten().astype(float)
    if vals.min() < 30 or vals.max() > 50:
        issues.append(f"Valores fuera de rango plausible ({vals.min():.2f}–{vals.max():.2f} kg).")
    if len(df) < 10:
        issues.append(f"Solo {len(df)} subgrupos — se recomiendan ≥20 para CEP robusto.")
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# PRUEBA DE NORMALIDAD
# ─────────────────────────────────────────────────────────────────────────────

def shapiro_test(vals):
    if len(vals) < 3: return {"W": None, "p": None, "normal": None}
    W, p = stats.shapiro(vals)
    return {"W": W, "p": p, "normal": bool(p > 0.05)}


# ─────────────────────────────────────────────────────────────────────────────
# CÁLCULO PRINCIPAL CEP
# ─────────────────────────────────────────────────────────────────────────────

def compute_spc(df, x_cols, n):
    co = CONTROL_CONSTANTS[n]
    d2, A2, D3, D4 = co["d2"], co["A2"], co["D3"], co["D4"]
    df = df.copy()
    for c in x_cols: df[c] = pd.to_numeric(df[c], errors="coerce")

    df["xbar"] = df[x_cols].mean(axis=1)
    df["R"]    = df[x_cols].max(axis=1) - df[x_cols].min(axis=1)

    xb = df["xbar"].mean(); Rb = df["R"].mean(); sig = Rb / d2

    UCLx = xb + A2*Rb; LCLx = xb - A2*Rb
    UCLr = D4*Rb;      LCLr = D3*Rb

    s1 = sig / np.sqrt(n)
    z1u = xb+s1; z1l = xb-s1; z2u = xb+2*s1; z2l = xb-2*s1

    Cp  = (USL-LSL) / (6*sig)
    Cpu = (USL-xb)  / (3*sig)
    Cpl = (xb-LSL)  / (3*sig)
    Cpk = min(Cpu, Cpl)

    pnc_low  = stats.norm.cdf(LSL, xb, sig)
    pnc_high = 1 - stats.norm.cdf(USL, xb, sig)

    all_vals = df[x_cols].values.flatten().astype(float)
    sw = shapiro_test(all_vals)

    sx = list(df[df["xbar"].gt(UCLx) | df["xbar"].lt(LCLx)].index)
    sr = list(df[df["R"].gt(UCLr) | ((LCLr > 0) & df["R"].lt(LCLr))].index)

    return {
        "df": df, "x_cols": x_cols, "n": n, "consts": co,
        "xbar_bar": xb, "R_bar": Rb, "sigma_st": sig,
        "UCL_x": UCLx, "LCL_x": LCLx, "UCL_r": UCLr, "LCL_r": LCLr,
        "z1u": z1u, "z1l": z1l, "z2u": z2u, "z2l": z2l,
        "Cp": Cp, "Cpu": Cpu, "Cpl": Cpl, "Cpk": Cpk,
        "pnc_low": pnc_low, "pnc_high": pnc_high, "pnc_total": pnc_low+pnc_high,
        "all_vals": all_vals, "sw": sw, "signals_x": sx, "signals_r": sr
    }


# ─────────────────────────────────────────────────────────────────────────────
# CÁLCULO ECONÓMICO
# ─────────────────────────────────────────────────────────────────────────────

def compute_eco(s, cost_per_kg, prod_hourly, hours_day, days_month):
    xb = s["xbar_bar"]
    over = max(0, xb - NOMINAL)
    sacos_mes  = prod_hourly * hours_day * days_month
    sacos_anio = sacos_mes * 12
    return {
        "overfill_g":      over * 1000,
        "sacos_mes":       sacos_mes,
        "sacos_anio":      sacos_anio,
        "kg_extra_mes":    over * sacos_mes,
        "costo_mes":       over * sacos_mes * cost_per_kg,
        "costo_anio":      over * sacos_anio * cost_per_kg,
        "sacos_extra_anio": (over * sacos_anio / 40) if over > 0 else 0
    }


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────────────────────────────────────

def cpk_st(cpk):
    """Retorna (color, texto, badge_css) según el valor de Cpk."""
    CP = "#1B4F72"; CR = "#E74C3C"; CG = "#27AE60"; CY = "#F39C12"
    if cpk >= 1.33: return CG, "CAPAZ ✓", "badge-green"
    if cpk >= 1.0:  return CY, "MARGINAL ⚠", "badge-yellow"
    return CR, "INCAPAZ ✗", "badge-red"


def generate_sample_excel():
    """Genera la plantilla de ejemplo en bytes para descarga."""
    data = {
        "Subgrupo": list(range(1, 13)),
        "Hora":     ["9:18","9:38","9:58","10:18","10:38","10:58","11:18","11:38","12:45","13:05","13:25","13:45"],
        "X1": [41.1, 39.2, 40.0, 39.8, 40.2, 40.5, 41.1, 39.9, 40.4, 39.1, 40.0, 40.6],
        "X2": [40.0, 40.7, 40.0, 40.3, 40.1, 40.7, 40.9, 40.2, 40.6, 40.0, 40.1, 39.8],
        "X3": [40.2, 39.6, 40.8, 40.9, 39.7, 41.1, 39.6, 41.4, 40.1, 39.8, 40.8, 40.8],
        "X4": [40.8, 40.2, 41.1, 40.8, 40.4, 39.3, 39.3, 41.0, 40.8, 40.8, 41.6, 41.1],
        "X5": [40.7, 40.1, 41.1, 40.3, 40.4, 40.5, 39.8, 40.2, 40.0, 40.2, 41.6, 41.5],
    }
    buf = io.BytesIO()
    pd.DataFrame(data).to_excel(buf, index=False, sheet_name="Muestreo_CEP", engine="openpyxl")
    return buf.getvalue()


def export_excel(s, eco):
    """Exporta el reporte completo a Excel con múltiples hojas."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        s["df"].round(4).to_excel(writer, sheet_name="Datos_Subgrupos", index=False)

        pd.DataFrame({
            "Indicador": ["x̄", "σ̂ (R̄/d₂)", "R̄", "n", "LCS X̄", "LCI X̄", "LCS R", "LCI R",
                          "LSL", "USL", "Nominal", "Cp", "Cpu", "Cpl", "Cpk",
                          "PNC bajo LIE (%)", "PNC sobre LSE (%)", "PNC total (%)",
                          "Shapiro-Wilk W", "Shapiro-Wilk p"],
            "Valor": [
                round(s["xbar_bar"], 5), round(s["sigma_st"], 5), round(s["R_bar"], 5), s["n"],
                round(s["UCL_x"], 5), round(s["LCL_x"], 5), round(s["UCL_r"], 5), round(s["LCL_r"], 5),
                LSL, USL, NOMINAL,
                round(s["Cp"], 4), round(s["Cpu"], 4), round(s["Cpl"], 4), round(s["Cpk"], 4),
                round(s["pnc_low"]*100, 4), round(s["pnc_high"]*100, 4), round(s["pnc_total"]*100, 4),
                round(s["sw"]["W"], 5) if s["sw"]["W"] else "N/A",
                round(s["sw"]["p"], 5) if s["sw"]["p"] else "N/A",
            ]
        }).to_excel(writer, sheet_name="Capacidad", index=False)

        pd.DataFrame({
            "Concepto": ["Sobrellenado promedio (g)", "Sacos/mes", "Sacos/año",
                         "kg extra/mes", "Costo mensual (COP)", "Costo anual (COP)", "Sacos extra/año"],
            "Valor": [
                round(eco["overfill_g"], 2), int(eco["sacos_mes"]), int(eco["sacos_anio"]),
                round(eco["kg_extra_mes"], 2), round(eco["costo_mes"], 0),
                round(eco["costo_anio"], 0), round(eco["sacos_extra_anio"], 1)
            ]
        }).to_excel(writer, sheet_name="Economico", index=False)
    return buf.getvalue()
if __name__ == "__main__":
    main()
