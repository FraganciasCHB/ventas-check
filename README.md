
# Perfumes Pedido Calc

Calcula **ingreso, costo, utilidad (balance neto)** y **margen ponderado** para un lote de pedido de perfumes a partir de tu catálogo en Excel.

## Estructura de datos
- **Catálogo**: `listas_de_precios_propios.xlsx` con hoja **PERFUMES** y columnas:
  - `producto`
  - `precio compra`
  - `precio venta`
- **Pedido**: `pedido.csv` con columnas:
  - `producto`
  - `cantidad`
  - `descuento_%` (usar 0..1, ej. 0.15 = 15%)

> Incluimos ejemplos en `examples/`.

## Uso rápido (local, Python)
```bash
pip install -r requirements.txt
python calc_pedido.py --catalogo listas_de_precios_propios.xlsx --pedido pedido.csv --dedup first --export
```
- `--dedup` resuelve duplicados en el catálogo por nombre normalizado:
  - `first` (default) | `max_venta` | `min_costo` | `avg`
- `--export` genera `salida_YYYYMMDD_HHMMSS.xlsx` y CSVs.

## Un clic (Windows)
Opcionalmente puedes crear un ejecutable:
```bash
pip install pyinstaller
pyinstaller --onefile calc_pedido.py --name calc_pedido
```
Luego coloca `calc_pedido.exe` junto a tu `listas_de_precios_propios.xlsx` y `pedido.csv` y ejecútalo:
```powershell
.\calc_pedido.exe --catalogo listas_de_precios_propios.xlsx --pedido pedido.csv --dedup max_venta --export
```

## GitHub Actions (build de .exe)
Este repo trae un workflow para generar el `.exe` en **Actions** (Windows):
- Ve a **Actions → Build EXE → Run workflow**.
- Descarga el artefacto `calc_pedido_win` (contiene `calc_pedido.exe`).

## Scripts de conveniencia
- `scripts/run_windows_auto.bat` — instala dependencias y ejecuta.
- `scripts/run_macos_auto.command` — instala dependencias y ejecuta (macOS).

## Ejemplos
- `examples/pedido_template.csv`
- `examples/listas_de_precios_propios_sample.xlsx`
