
import argparse
import pandas as pd
import re
from datetime import datetime
from pathlib import Path

def norm_text(s: str) -> str:
    """Normaliza nombres de producto: recorta, colapsa espacios y pone mayúsculas."""
    if pd.isna(s):
        return ""
    s = str(s).strip()
    s = re.sub(r"\s+", " ", s)
    return s.upper()

def deduplicate_catalog(df_cat: pd.DataFrame, policy: str = "first") -> pd.DataFrame:
    """
    Deduplica productos por nombre normalizado.
    Políticas:
      - first (default): toma la primera aparición.
      - max_venta: precio venta máximo.
      - min_costo: precio compra mínimo.
      - avg: promedia precios.
    """
    base = df_cat.copy()
    base["_key"] = base["producto"].apply(norm_text)

    dup_mask = base.duplicated("_key", keep=False)
    dups = base[dup_mask]
    uniques = base[~dup_mask]

    if dups.empty:
        return pd.concat([uniques.drop(columns=["_key"])], ignore_index=True)

    agg_rows = []
    for _, g in dups.groupby("_key", as_index=False):
        if g["precio compra"].nunique(dropna=False) == 1 and g["precio venta"].nunique(dropna=False) == 1:
            agg_rows.append(g.iloc[[0]].drop(columns=["_key"]))
            continue

        if policy == "first":
            agg_rows.append(g.iloc[[0]].drop(columns=["_key"]))
        elif policy == "max_venta":
            idx = g["precio venta"].astype(float).idxmax()
            agg_rows.append(g.loc[[idx]].drop(columns=["_key"]))
        elif policy == "min_costo":
            idx = g["precio compra"].astype(float).idxmin()
            agg_rows.append(g.loc[[idx]].drop(columns=["_key"]))
        elif policy == "avg":
            row = g.iloc[0].copy()
            row["precio compra"] = g["precio compra"].astype(float).mean()
            row["precio venta"]  = g["precio venta"].astype(float).mean()
            row = row.drop(labels=["_key"])
            agg_rows.append(pd.DataFrame([row]))
        else:
            raise ValueError(f"Política de deduplicación desconocida: {policy}")

    agg = pd.concat(agg_rows, ignore_index=True)
    result = pd.concat([uniques.drop(columns=["_key"]), agg], ignore_index=True)
    return result

def calcular(catalog_xlsx: Path, pedido_csv: Path, dedup_policy: str = "first"):
    # Cargar catálogo
    df_cat = pd.read_excel(catalog_xlsx, sheet_name="PERFUMES")
    df_cat.columns = [c.strip().lower() for c in df_cat.columns]
    for col in ("producto","precio compra","precio venta"):
        if col not in df_cat.columns:
            raise ValueError(f"Columna faltante en catálogo: {col}")

    # Cargar pedido
    df_ped = pd.read_csv(pedido_csv)
    df_ped.columns = [c.strip().lower() for c in df_ped.columns]
    for col in ("producto","cantidad","descuento_%"):
        if col not in df_ped.columns:
            raise ValueError(f"Columna faltante en pedido: {col}")

    # Normalizar y deduplicar catálogo
    df_cat_clean = deduplicate_catalog(df_cat[["producto","precio compra","precio venta"]], policy=dedup_policy)
    df_cat_clean["producto_norm"] = df_cat_clean["producto"].apply(norm_text)

    # Normalizar pedido
    df_ped["producto_norm"] = df_ped["producto"].apply(norm_text)

    # Merge many-to-one
    right_unique = df_cat_clean.drop_duplicates("producto_norm")
    df = df_ped.merge(right_unique, on="producto_norm", how="left", validate="m:1")

    # Advertir faltantes
    missing = df[df["precio venta"].isna() | df["precio compra"].isna()]["producto"].dropna().unique().tolist()
    if missing:
        print("\n[ADVERTENCIA] Estos productos no se encontraron en el catálogo (revisa nombres):")
        for m in missing:
            print(" -", m)

    # Cálculos
    df["descuento_%"] = df["descuento_%"].fillna(0.0).astype(float)
    df["cantidad"]    = df["cantidad"].fillna(0).astype(float)

    df["precio_venta_aplicado"] = df["precio venta"] * (1 - df["descuento_%"])
    df["ingreso_linea"] = df["cantidad"] * df["precio_venta_aplicado"]
    df["costo_linea"]   = df["cantidad"] * df["precio compra"]
    df["utilidad_linea"]= df["ingreso_linea"] - df["costo_linea"]
    df["margen_linea"]  = df["utilidad_linea"] / df["ingreso_linea"].replace({0: pd.NA})

    total_ingreso = float(df["ingreso_linea"].sum(skipna=True))
    total_costo   = float(df["costo_linea"].sum(skipna=True))
    total_util    = float(df["utilidad_linea"].sum(skipna=True))
    margen_pond   = (total_util / total_ingreso) if total_ingreso else 0.0

    resumen = pd.DataFrame([{
        "ingreso_total": total_ingreso,
        "costo_total": total_costo,
        "utilidad_total_balance_neto": total_util,
        "margen_ponderado": margen_pond
    }])

    # Orden de columnas detalle
    detalle_cols = ["producto","cantidad","descuento_%","precio venta","precio_venta_aplicado",
                    "precio compra","ingreso_linea","costo_linea","utilidad_linea","margen_linea"]
    detalle = df[detalle_cols].copy()

    return detalle, resumen

def main():
    p = argparse.ArgumentParser(description="Calcula ganancias por lote de pedido basadas en un catálogo PERFUMES.")
    p.add_argument("--catalogo", required=True, help="XLSX con hoja PERFUMES (columnas: producto, precio compra, precio venta)")
    p.add_argument("--pedido", required=True, help="CSV con columnas: producto,cantidad,descuento_% (descuento 0..1)")
    p.add_argument("--dedup", default="first", choices=["first","max_venta","min_costo","avg"],
                   help="Política cuando hay productos duplicados en el catálogo")
    p.add_argument("--export", action="store_true", help="Exporta archivos detalle/resumen en CSV y XLSX")
    args = p.parse_args()

    detalle, resumen = calcular(Path(args.catalogo), Path(args.pedido), args.dedup)

    # Print resumen
    print("\n=== RESUMEN DEL PEDIDO ===")
    print(resumen.to_string(index=False, formatters={"margen_ponderado": "{:.1%}".format}))

    # Print detalle
    print("\n=== DETALLE ===")
    print(detalle.to_string(index=False))

    # Export
    if args.export:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = Path(f"salida_{ts}")
        detalle.to_csv(base.with_suffix("_detalle.csv"), index=False)
        resumen.to_csv(base.with_suffix("_resumen.csv"), index=False)
        # XLSX combinado
        with pd.ExcelWriter(base.with_suffix(".xlsx")) as xw:
            detalle.to_excel(xw, sheet_name="detalle", index=False)
            resumen.to_excel(xw, sheet_name="resumen", index=False)
        print(f"\n[OK] Archivos exportados con prefijo: {base} (.csv/.xlsx)")

if __name__ == "__main__":
    main()
