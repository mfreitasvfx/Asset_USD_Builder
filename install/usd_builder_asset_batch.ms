-- USD_Builder_Asset : lote -- pasta de .max -> um FBX por arquivo
-- Rode com: fileIn @"C:\dev\USD_Builder_Asset\install\usd_builder_asset_batch.ms"
python.Execute "import sys"
python.Execute "p = r'C:/dev/USD_Builder_Asset/src'"
python.Execute "if p not in sys.path: sys.path.insert(0, p)"
-- recarrega a cada execucao, pra editar no VS Code sem reiniciar o Max
python.Execute "for _m in [k for k in list(sys.modules) if k.startswith('usd_builder_asset')]: del sys.modules[_m]"
python.Execute "import usd_builder_asset.ui.batch_window as _b; _b.show()"
