
import argparse
import pandas as pd
import re
from pathlib import Path

def norm_text(s: str) -> str:
    """Normaliza nombres de producto: quita espacios dobles, recorta y pone mayúsculas."""
    if pd.isna(s):
        return ""
    s = str(s)
    s = s.strip()
    s = re.sub(r"\s+", " ", s)  # colapsar espacios
    return s.upper()

def deduplicate_catalog(df_cat: pd.DataFrame, policy: str = "first") -> pd.DataFrame:
    """
    El catálogo puede tener productos repetidos.
    - Si están repetidos pero con los mismos precios, conservamos 1 y seguimos.
    - Si tienen precios distintos, aplicamos 'policy':
        'first'      -> se queda la primera aparición.
        'max_venta'  -> tomar mayor 'precio venta' (y su 'precio compra' asociado si hay empates; si no, el menor costo).
        'min_costo'  -> tomar menor 'precio compra' (y su 'precio venta' asociado si hay empates; si no, el mayor PV).
        'avg'        -> promediar precios.
    """
    cols = ["producto", "precio compra", "precio venta"]
    base = df_cat.copy()

    # Detección de duplicados por nombre normalizado
    base["_key"] = base["producto"].apply(norm_text)

    # Separar duplicados y únicos
    dup_mask = base.duplicated("_key", keep=False)
    dups = base[dup_mask]
    uniques = base[~dup_mask]

    if dups.empty:
        res = uniques.drop(columns=["_key"])
        return pd.concat([res], ignore_index=True)

    # Agrupar duplicados
    agg_rows = []
    for key, g in dups.groupby("_key", as_index=False):
        # Si todos los precios coinciden, conserva uno
        if g["precio compra"].nunique(dropna=False) == 1 and g["precio venta"].nunique(dropna=False) == 1:
            agg_rows.append(g.iloc[[0]].drop(columns=["_key"]))
            continue

        # Políticas
        if policy == "first":
            agg_rows.append(g.iloc[[0]].drop(columns=["_key"]))

        elif policy == "max_venta":
            # fila(s) con mayor PV
            idx = g["precio venta"].astype(float).idxmax()
            agg_rows.append(g.loc[[idx]].drop(columns=["_key"]))

        elif policy == "min_costo":
            idx = g["precio compra"].astype(float).idxmin()
            agg_rows.append(g.loc[[idx]].drop(columns=["_key"]))

        elif policy == "avg":
            # Promediar precios y reconstruir una fila
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

def main(catalog_xlsx, pedido_csv, dedup_policy="first"):
    # 1) Cargar datos
    df_cat = pd.read_excel(catalog_xlsx, sheet_name="PERFUMES")
    df_cat.columns = [c.strip().lower() for c in df_cat.columns]  # 'producto','precio compra','precio venta'

    df_ped = pd.read_csv(pedido_csv)
    df_ped.columns = [c.strip().lower() for c in df_ped.columns]  # 'producto','cantidad','descuento_%'

    # 2) Normalizar textos para unir sin fallas por espacios / mayúsculas
    df_cat["producto_norm"] = df_cat["producto"].apply(norm_text)
    df_ped["producto_norm"] = df_ped["producto"].apply(norm_text)

    # 3) Deduplicar catálogo si hay repetidos
    df_cat_clean = deduplicate_catalog(df_cat[["producto","precio compra","precio venta"]].copy(), policy=dedup_policy)
    df_cat_clean["producto_norm"] = df_cat_clean["producto"].apply(norm_text)

    # 4) Merge m:1 (pedido puede repetir, catálogo debería ser único después del paso anterior)
    df = df_ped.merge(df_cat_clean.drop_duplicates("producto_norm"),
                      on="producto_norm", how="left", validate="m:1",
                      suffixes=("", "_cat"))

    # 5) Verificar faltantes del catálogo
    missing = df[df["precio venta"].isna() | df["precio compra"].isna()]["producto"].unique().tolist()
    if missing:
        print("\n[ADVERTENCIA] Algunos productos del pedido no se encontraron en el catálogo (revisa nombres):")
        for m in missing:
            print(" -", m)

    # 6) Calcular métricas
    df["descuento_%"] = df["descuento_%"].fillna(0.0).astype(float)
    df["cantidad"]    = df["cantidad"].fillna(0).astype(float)

    df["precio_venta_aplicado"] = df["precio venta"] * (1 - df["descuento_%"])
    df["ingreso_linea"] = df["cantidad"] * df["precio_venta_aplicado"]
    df["costo_linea"]   = df["cantidad"] * df["precio compra"]
    df["utilidad_linea"]= df["ingreso_linea"] - df["costo_linea"]
    df["margen_linea"]  = df["utilidad_linea"] / df["ingreso_linea"].replace({0: pd.NA})

    total_ingreso = df["ingreso_linea"].sum(skipna=True)
    total_costo   = df["costo_linea"].sum(skipna=True)
    total_util    = df["utilidad_linea"].sum(skipna=True)
    margen_pond   = (total_util / total_ingreso) if total_ingreso else 0.0

    # 7) Salida legible
    print("\n=== RESUMEN DEL PEDIDO ===")
    print(f"Ingreso total: ${total_ingreso:,.2f}")
    print(f"Costo total:   ${total_costo:,.2f}")
    print(f"Utilidad total (Balance neto): ${total_util:,.2f}")
    print(f"Margen ponderado: {margen_pond:.1%}")

    print("\n=== DETALLE ===")
    cols = ["producto","cantidad","descuento_%","precio venta","precio_venta_aplicado",
            "precio compra","ingreso_linea","costo_linea","utilidad_linea","margen_linea"]
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    print(df[cols].to_string(index=False))

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Calcula ganancias por lote de pedido basadas en un catálogo.")
    p.add_argument("--catalogo", required=True, help="Ruta al XLSX con hoja PERFUMES (producto, precio compra, precio venta)")
    p.add_argument("--pedido",   required=True, help="CSV con columnas: producto,cantidad,descuento_% (descuento 0 a 1)")
    p.add_argument("--dedup",    default="first", choices=["first","max_venta","min_costo","avg"],
                   help="Política cuando hay productos duplicados en el catálogo (default: first)")
    args = p.parse_args()
    main(args.catalogo, args.pedido, args.dedup)
