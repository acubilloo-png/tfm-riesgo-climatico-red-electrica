# ============================================================================
# 06_extremos_observados.py
# ----------------------------------------------------------------------------
# TAREA 2 DEL ENCARGO, en su forma original: ajuste de la distribucion de
# extremos sobre series temporales reales.
#
# El atlas de Pryor y Barthelmie no lo permitia, porque distribuye el nivel de
# retorno ya ajustado y no las series anuales. Las rachas observadas de AEMET si
# son series temporales, de modo que aqui se ajustan los tres metodos pedidos y
# se comparan:
#
#   1. Gumbel por L-momentos      robusta con n del orden de 40
#   2. GEV, tambien por L-momentos, informando el parametro de forma
#   3. Picos sobre umbral (POT) con Pareto generalizada, como control
#
# mas intervalos de confianza al 95 % por bootstrap de 500 replicas.
#
# ----------------------------------------------------------------------------
# DOS DECISIONES METODOLOGICAS QUE NO ESTABAN EN EL ENCARGO
# ----------------------------------------------------------------------------
# a) DESAGRUPAMIENTO PARA POT. Las rachas diarias no son independientes: una
#    borrasca produce rachas altas varios dias seguidos. Si se ajusta la Pareto
#    a todas las excedencias, la tasa de excedencias queda inflada y el nivel de
#    retorno sesgado. Se desagrupa por rachas de episodios: dentro de cada grupo
#    de excedencias separadas por menos de 3 dias se conserva solo el maximo.
#
# b) CONVENIO DE SIGNO DE LA FORMA. Se informa el parametro de forma en el
#    convenio estandar de Coles, donde la funcion de distribucion de la GEV es
#    exp(-(1+xi*z)^(-1/xi)) y xi>0 corresponde a cola pesada (Frechet), xi<0 a
#    cola acotada (Weibull inversa) y xi=0 al caso Gumbel. Los L-momentos de
#    Hosking dan k = -xi, y la conversion se hace explicita en el codigo para
#    que sea auditable.
# ============================================================================

import json
import os

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import gamma as fgamma

CARPETA = os.path.dirname(os.path.abspath(__file__))
CSV_RACHAS = os.path.join(CARPETA, "rachas_aemet_cv.csv")
CSV_EST = os.path.join(CARPETA, "estaciones_aemet_cv.csv")
SALIDA = os.path.join(CARPETA, "extremos_observados.json")
SALIDA_CSV = os.path.join(CARPETA, "v50_estaciones.csv")

T_RETORNO = 50
MIN_DIAS_ANIO = 300      # un ano cuenta si tiene al menos 300 dias con racha
MIN_ANIOS = 20           # una estacion entra si tiene al menos 20 anos utiles
UMBRAL_POT = 99.5        # percentil para el umbral de picos sobre umbral
HUECO_DIAS = 3           # separacion minima entre episodios independientes
N_BOOTSTRAP = 500
SEMILLA = 42
EULER = 0.5772156649015329

rng = np.random.default_rng(SEMILLA)


# ---------------------------------------------------------------------------
# L-momentos por momentos ponderados por probabilidad (estimadores no sesgados)
# ---------------------------------------------------------------------------
def l_momentos(x):
    x = np.sort(np.asarray(x, dtype="float64"))
    n = len(x)
    j = np.arange(1, n + 1)
    b0 = x.mean()
    b1 = np.sum((j - 1) / (n - 1) * x) / n
    b2 = np.sum((j - 1) * (j - 2) / ((n - 1) * (n - 2)) * x) / n
    lam1 = b0
    lam2 = 2 * b1 - b0
    lam3 = 6 * b2 - 6 * b1 + b0
    return lam1, lam2, lam3


def gumbel_lmom(x, T):
    """Gumbel por L-momentos. Devuelve (nivel_retorno, loc, escala)."""
    lam1, lam2, _ = l_momentos(x)
    escala = lam2 / np.log(2.0)
    loc = lam1 - escala * EULER
    nivel = loc - escala * np.log(-np.log(1.0 - 1.0 / T))
    return nivel, loc, escala


def gev_lmom(x, T):
    """
    GEV por L-momentos (Hosking). Devuelve (nivel, loc, escala, xi_estandar).
    k de Hosking equivale a -xi en el convenio de Coles.
    """
    lam1, lam2, lam3 = l_momentos(x)
    tau3 = lam3 / lam2
    c = 2.0 / (3.0 + tau3) - np.log(2.0) / np.log(3.0)
    k = 7.8590 * c + 2.9554 * c ** 2
    if abs(k) < 1e-6:                      # degenera en Gumbel
        nivel, loc, escala = gumbel_lmom(x, T)
        return nivel, loc, escala, 0.0
    escala = lam2 * k / ((1.0 - 2.0 ** (-k)) * fgamma(1.0 + k))
    loc = lam1 - escala * (1.0 - fgamma(1.0 + k)) / k
    y = -np.log(1.0 - 1.0 / T)
    nivel = loc + escala * (1.0 - y ** k) / k
    return nivel, loc, escala, -k          # xi estandar


def desagrupar(fechas, valores, umbral, hueco_dias):
    """
    Conserva solo el maximo de cada episodio de excedencias. Dos excedencias
    separadas por menos de 'hueco_dias' se consideran del mismo episodio.
    """
    mask = valores > umbral
    if not mask.any():
        return np.array([]), np.array([])
    f = np.asarray(fechas)[mask]
    v = np.asarray(valores)[mask]
    orden = np.argsort(f)
    f, v = f[orden], v[orden]
    picos_f, picos_v = [], []
    ini = 0
    for i in range(1, len(f) + 1):
        corta = (i == len(f)) or ((f[i] - f[i - 1]).astype("timedelta64[D]").astype(int)
                                  > hueco_dias)
        if corta:
            j = ini + int(np.argmax(v[ini:i]))
            picos_f.append(f[j])
            picos_v.append(v[j])
            ini = i
    return np.array(picos_f), np.array(picos_v)


def pot_gpd(fechas, valores, n_anios, T, percentil, hueco):
    """Picos sobre umbral con Pareto generalizada. Devuelve (nivel, u, xi, sigma, n_picos)."""
    u = float(np.percentile(valores, percentil))
    _, picos = desagrupar(fechas, valores, u, hueco)
    if len(picos) < 10:
        return np.nan, u, np.nan, np.nan, len(picos)
    excesos = picos - u
    xi, _, sigma = stats.genpareto.fit(excesos, floc=0)
    tasa = len(picos) / n_anios          # excedencias por ano
    if abs(xi) < 1e-6:
        nivel = u + sigma * np.log(T * tasa)
    else:
        nivel = u + (sigma / xi) * ((T * tasa) ** xi - 1.0)
    return float(nivel), u, float(xi), float(sigma), len(picos)


def bootstrap_ic(maximos, T, n_rep, funcion):
    """Intervalo de confianza al 95 % remuestreando los maximos anuales."""
    vals = []
    for _ in range(n_rep):
        m = rng.choice(maximos, size=len(maximos), replace=True)
        try:
            r = funcion(m, T)
            v = r[0] if isinstance(r, tuple) else r
            if np.isfinite(v):
                vals.append(v)
        except Exception:
            continue
    if len(vals) < 50:
        return None, None
    return (round(float(np.percentile(vals, 2.5)), 2),
            round(float(np.percentile(vals, 97.5)), 2))


# ---------------------------------------------------------------------------
print("Cargando rachas observadas...")
df = pd.read_csv(CSV_RACHAS, sep=";", encoding="utf-8-sig", low_memory=False)
df["fecha"] = pd.to_datetime(df["fecha"])
df = df.dropna(subset=["racha"])
est = pd.read_csv(CSV_EST, sep=";", encoding="utf-8-sig")
nombres = dict(zip(est["indicativo"], est["nombre"]))
print(f"  {len(df)} registros con racha, {df['indicativo'].nunique()} estaciones")
print(f"  periodo {df['fecha'].min():%Y-%m-%d} a {df['fecha'].max():%Y-%m-%d}")
print(f"  racha maxima observada: {df['racha'].max():.1f} m/s "
      f"({df['racha'].max() * 3.6:.0f} km/h)")

df["anio"] = df["fecha"].dt.year

# Maximos anuales, solo de anos suficientemente completos
cob = df.groupby(["indicativo", "anio"]).agg(dias=("racha", "size"),
                                             maximo=("racha", "max")).reset_index()
cob = cob[cob["dias"] >= MIN_DIAS_ANIO]
n_anios = cob.groupby("indicativo").size()
validas = n_anios[n_anios >= MIN_ANIOS].index.tolist()
print(f"\n  estaciones con >={MIN_ANIOS} anos completos: {len(validas)}")

# ---------------------------------------------------------------------------
print(f"\n=== AJUSTE DE EXTREMOS (retorno {T_RETORNO} anos) ===")
filas = []
for ide in sorted(validas):
    sub = cob[cob["indicativo"] == ide]
    maximos = sub["maximo"].values.astype("float64")
    n_a = len(maximos)

    v50_gum, loc_g, esc_g = gumbel_lmom(maximos, T_RETORNO)
    v50_gev, loc_e, esc_e, xi = gev_lmom(maximos, T_RETORNO)

    diario = df[df["indicativo"] == ide]
    v50_pot, u, xi_gpd, sigma, n_picos = pot_gpd(
        diario["fecha"].values, diario["racha"].values.astype("float64"),
        n_a, T_RETORNO, UMBRAL_POT, HUECO_DIAS)

    ic_gum = bootstrap_ic(maximos, T_RETORNO, N_BOOTSTRAP, gumbel_lmom)
    ic_gev = bootstrap_ic(maximos, T_RETORNO, N_BOOTSTRAP, gev_lmom)

    fila = {
        "indicativo": ide, "nombre": nombres.get(ide, ""),
        "n_anios": int(n_a),
        "anio_ini": int(sub["anio"].min()), "anio_fin": int(sub["anio"].max()),
        "maximo_observado_ms": round(float(maximos.max()), 2),
        "V50_gumbel_ms": round(float(v50_gum), 2),
        "V50_gumbel_ic95": ic_gum,
        "V50_gev_ms": round(float(v50_gev), 2),
        "V50_gev_ic95": ic_gev,
        "xi_gev": round(float(xi), 4),
        "V50_pot_ms": round(float(v50_pot), 2) if np.isfinite(v50_pot) else None,
        "umbral_pot_ms": round(u, 2),
        "xi_gpd": round(float(xi_gpd), 4) if np.isfinite(xi_gpd) else None,
        "n_picos_pot": int(n_picos),
    }
    filas.append(fila)
    print(f"  {ide:<7} {n_a:>2} anos  max obs {fila['maximo_observado_ms']:>5.1f}   "
          f"Gumbel {fila['V50_gumbel_ms']:>5.1f}  GEV {fila['V50_gev_ms']:>5.1f} "
          f"(xi={xi:>+6.3f})  POT {str(fila['V50_pot_ms']):>5}   "
          f"{str(nombres.get(ide, ''))[:26]}")

res = pd.DataFrame(filas)
res.to_csv(SALIDA_CSV, index=False, sep=";", encoding="utf-8-sig")

# ---------------------------------------------------------------------------
print("\n=== COMPARACION DE LOS TRES METODOS ===")
med = {
    "gumbel": float(res["V50_gumbel_ms"].median()),
    "gev": float(res["V50_gev_ms"].median()),
    "pot": float(res["V50_pot_ms"].dropna().median()),
}
for k_, v in med.items():
    print(f"  mediana entre estaciones, {k_:<7} {v:>6.2f} m/s "
          f"({v * 3.6:>5.1f} km/h)")
ref = med["gumbel"]
desv = {k_: 100 * (v - ref) / ref for k_, v in med.items()}
print(f"\n  desviacion frente a Gumbel:")
for k_, v in desv.items():
    print(f"    {k_:<7} {v:>+7.2f} %")
max_desv = max(abs(v) for v in desv.values())
print(f"\n  desviacion maxima {max_desv:.2f} %  "
      f"(criterio del encargo: investigar si supera el 15 %)")
print("  " + ("*** SUPERA EL 15 %: hay que investigarlo ***" if max_desv > 15
              else "dentro del criterio: los tres metodos concuerdan"))

# Parametro de forma: justifica o no el uso de Gumbel
xis = res["xi_gev"].values
print(f"\n  parametro de forma de la GEV: mediana {np.median(xis):+.4f}, "
       f"rango {xis.min():+.3f} a {xis.max():+.3f}")
n_cerca = int((np.abs(xis) < 0.1).sum())
print(f"    estaciones con |xi| < 0,1: {n_cerca} de {len(xis)}")
if np.abs(np.median(xis)) < 0.1:
    print("    la forma es proxima a cero: el uso de Gumbel queda justificado")
else:
    print("    la forma NO es proxima a cero: la Gumbel no es el modelo adecuado")

with open(SALIDA, "w", encoding="utf-8") as fh:
    json.dump({
        "fuente": "AEMET OpenData, rachas maximas diarias observadas",
        "periodo": f"{int(df['anio'].min())}-{int(df['anio'].max())}",
        "T_retorno": T_RETORNO,
        "criterios": {"min_dias_anio": MIN_DIAS_ANIO, "min_anios": MIN_ANIOS,
                      "percentil_umbral_pot": UMBRAL_POT,
                      "hueco_desagrupamiento_dias": HUECO_DIAS,
                      "n_bootstrap": N_BOOTSTRAP},
        "convenio_forma": ("Coles: F(z)=exp(-(1+xi*z)^(-1/xi)); xi>0 cola pesada, "
                           "xi<0 cola acotada, xi=0 Gumbel. k de Hosking = -xi"),
        "n_estaciones_validas": len(validas),
        "estaciones": filas,
        "medianas_entre_estaciones": {k_: round(v, 3) for k_, v in med.items()},
        "desviacion_pct_frente_a_gumbel": {k_: round(v, 2) for k_, v in desv.items()},
        "desviacion_maxima_pct": round(max_desv, 2),
        "criterio_15pct_superado": bool(max_desv > 15),
        "xi_gev": {"mediana": round(float(np.median(xis)), 4),
                   "min": round(float(xis.min()), 4),
                   "max": round(float(xis.max()), 4),
                   "n_cerca_de_cero": n_cerca,
                   "gumbel_justificada": bool(abs(np.median(xis)) < 0.1)},
    }, fh, ensure_ascii=False, indent=2)

print(f"\nGuardados: {os.path.basename(SALIDA)} y {os.path.basename(SALIDA_CSV)}")
