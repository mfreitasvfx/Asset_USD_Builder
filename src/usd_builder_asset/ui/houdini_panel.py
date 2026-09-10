"""Janela do USD_Builder_Asset dentro do Houdini.

    import sys; sys.path.insert(0, r"C:/dev/USD_Builder_Asset/src")
    from usd_builder_asset.ui import houdini_panel
    houdini_panel.show()

Etapas numeradas, como no Asset_USD_Builder do Carlo:
    1 - SCAN          le a pasta e lista os objetos (KitBash)
    2 - BUILD ASSETS  monta a rede em /stage SEM escrever -- da' para
                      abrir o subnet USD_Builder_Asset_* e alterar antes
    3 - EXPORT USD's  aperta o execute dos componentoutput montados

A janela nao contem regra nenhuma: scanner/perfis/builder fazem o trabalho,
entao tudo que ela faz tambem roda headless via tools/build_lops.py.
"""
import os
import traceback

try:
    from PySide6 import QtCore, QtWidgets       # Houdini 21+
except ImportError:                             # 20.5 e anteriores
    from PySide2 import QtCore, QtWidgets

import hou

TITULO = "USD_Builder_Asset"
RENDERERS = ("karma", "arnold", "renderman", "vray")


def _reload_core():
    """Recarrega os modulos de logica (editar no VS Code -> Scan de novo)."""
    import sys
    for m in [k for k in list(sys.modules)
              if k.startswith("usd_builder_asset") and ".ui." not in k
              and not k.endswith(".ui")]:
        del sys.modules[m]


class Panel(QtWidgets.QWidget):

    def __init__(self, parent=None):
        if parent is None:
            try:
                parent = hou.qt.mainWindow()   # inexistente no hython
            except AttributeError:
                parent = None
        super(Panel, self).__init__(parent)
        self.setWindowFlag(QtCore.Qt.Window, True)
        self.setWindowTitle(TITULO)
        self.resize(560, 760)
        self._asset = None
        self._profile = None
        self._builds = []          # Results da etapa 2, para a etapa 3
        self._modo = "pasta"       # pasta | objetos | multifbx
        self._montar()

    # ------------------------------------------------------------------

    def _montar(self):
        raiz = QtWidgets.QVBoxLayout(self)

        # fonte
        gF = QtWidgets.QGroupBox("Fonte")
        fF = QtWidgets.QFormLayout(gF)
        linha = QtWidgets.QHBoxLayout()
        self.edFonte = QtWidgets.QLineEdit()
        bt = QtWidgets.QPushButton("...")
        bt.setFixedWidth(30)
        bt.clicked.connect(lambda: self._escolher(self.edFonte))
        linha.addWidget(self.edFonte)
        linha.addWidget(bt)
        wrap = QtWidgets.QWidget()
        wrap.setLayout(linha)
        fF.addRow("Pasta do asset", wrap)
        self.btScan = QtWidgets.QPushButton("1 — SCAN")
        self.btScan.clicked.connect(self._scan)
        fF.addRow(self.btScan)
        self.lbResumo = QtWidgets.QLabel("—")
        self.lbResumo.setWordWrap(True)
        fF.addRow(self.lbResumo)
        raiz.addWidget(gF)

        # objetos (kitbash) ou arquivos (set multi-FBX)
        gO = QtWidgets.QGroupBox("Objetos / arquivos (KitBash)")
        vO = QtWidgets.QVBoxLayout(gO)
        self.edFiltro = QtWidgets.QLineEdit()
        self.edFiltro.setPlaceholderText("filtrar…")
        self.edFiltro.textChanged.connect(self._filtrar)
        vO.addWidget(self.edFiltro)
        self.lista = QtWidgets.QListWidget()
        self.lista.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        vO.addWidget(self.lista)
        raiz.addWidget(gO, 1)

        # opcoes
        gR = QtWidgets.QGroupBox("Renderers e saida")
        fR = QtWidgets.QFormLayout(gR)
        hb = QtWidgets.QHBoxLayout()
        self.cks = {}
        for r in RENDERERS:
            ck = QtWidgets.QCheckBox(r)
            ck.setChecked(True)
            self.cks[r] = ck
            hb.addWidget(ck)
        wrapR = QtWidgets.QWidget()
        wrapR.setLayout(hb)
        fR.addRow("Renderers", wrapR)

        linha2 = QtWidgets.QHBoxLayout()
        self.edSaida = QtWidgets.QLineEdit(
            "C:/Users/Matheus/Downloads/MaxToLama/Testes/lops_ui")
        bt2 = QtWidgets.QPushButton("...")
        bt2.setFixedWidth(30)
        bt2.clicked.connect(lambda: self._escolher(self.edSaida))
        linha2.addWidget(self.edSaida)
        linha2.addWidget(bt2)
        wrap2 = QtWidgets.QWidget()
        wrap2.setLayout(linha2)
        fR.addRow("Pasta de saida", wrap2)

        self.ckTexShared = QtWidgets.QCheckBox(
            "Texturas compartilhadas (UMA copia em <saida>/textures)")
        self.ckTexShared.setChecked(True)
        fR.addRow(self.ckTexShared)
        raiz.addWidget(gR)

        # settings do Asset_USD_Builder (aba IMG SETTINGS)
        gS = QtWidgets.QGroupBox("Settings")
        fS = QtWidgets.QFormLayout(gS)

        def spin(valor, passo=0.01, dec=4):
            sp = QtWidgets.QDoubleSpinBox()
            sp.setDecimals(dec)
            sp.setRange(0.0, 100.0)
            sp.setSingleStep(passo)
            sp.setValue(valor)
            return sp

        self.spDisp = spin(0.01)
        self.spGamma = spin(1.0)
        self.spNormal = spin(1.0)
        self.spSss = spin(1.0)
        fS.addRow("Displacement Scale", self.spDisp)
        fS.addRow("BaseColor Gamma", self.spGamma)
        fS.addRow("Normal Scale", self.spNormal)
        fS.addRow("SubSurface", self.spSss)

        hbP = QtWidgets.QHBoxLayout()
        self.ckProxy = QtWidgets.QCheckBox("proxy (GL)")
        self.ckSimproxy = QtWidgets.QCheckBox("simproxy (fisica)")
        hbP.addWidget(self.ckProxy)
        hbP.addWidget(self.ckSimproxy)
        wrapP = QtWidgets.QWidget()
        wrapP.setLayout(hbP)
        fS.addRow("Branches", wrapP)
        raiz.addWidget(gS)

        linha3 = QtWidgets.QHBoxLayout()
        self.btBuild = QtWidgets.QPushButton("2 — BUILD ASSETS")
        self.btBuild.setMinimumHeight(34)
        self.btBuild.clicked.connect(self._build)
        linha3.addWidget(self.btBuild)
        self.btExport = QtWidgets.QPushButton("3 — EXPORT USD's")
        self.btExport.setMinimumHeight(34)
        self.btExport.clicked.connect(self._export)
        linha3.addWidget(self.btExport)
        wrap3 = QtWidgets.QWidget()
        wrap3.setLayout(linha3)
        raiz.addWidget(wrap3)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        raiz.addWidget(self.log, 1)

    # ------------------------------------------------------------------

    def _escolher(self, campo):
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Pasta", campo.text() or os.path.expanduser("~"))
        if d:
            campo.setText(d.replace("\\", "/"))

    def _diz(self, txt):
        self.log.appendPlainText(txt)
        print(txt)                 # espelha no console do Houdini
        QtWidgets.QApplication.processEvents()

    def _filtrar(self, txt):
        txt = txt.lower()
        for i in range(self.lista.count()):
            it = self.lista.item(i)
            it.setHidden(bool(txt) and txt not in it.text().lower())

    def _scan(self):
        self.log.clear()
        self.lista.clear()
        _reload_core()
        from usd_builder_asset import library, profiles
        from usd_builder_asset.lops import builder
        pasta = self.edFonte.text().strip()
        if not os.path.isdir(pasta):
            self._diz("pasta invalida: %r" % pasta)
            return
        self._diz("-" * 10 + " START SCANNING " + "-" * 10)
        try:
            self._asset = library.scan(pasta)
            self._profile, _etapas, avisos = profiles.plan(self._asset)
        except Exception:
            self._diz(traceback.format_exc())
            return
        self.lbResumo.setText(self._asset.resumo().replace("   ", "  "))
        self._diz(self._asset.resumo())
        for a in avisos:
            self._diz("! " + a)

        if self._asset.multi_fbx:
            # set multi-FBX com atlas (Post Apocalypse): a lista mostra os
            # ARQUIVOS; o Build abre cada um e monta os assets de dentro
            self._modo = "multifbx"
            for c in self._asset.geo_files:
                self.lista.addItem(os.path.basename(c))
            variantes = library.atlas_variants(self._asset)
            self._diz("✓ %d arquivos no set, atlas %s. Selecione e "
                      "2 — BUILD ASSETS."
                      % (self.lista.count(),
                         "com variantes " + "/".join(v for v, _p in variantes)
                         if variantes else "sem variantes"))
        elif self._profile.asset_grain == "object":
            self._modo = "objetos"
            self._diz("lendo objetos do arquivo…")
            try:
                for nome in builder.list_assets_in_file(
                        self._asset.default_geo):
                    self.lista.addItem(nome)
                self._diz("✓ %d objetos. Selecione e 2 — BUILD ASSETS."
                          % self.lista.count())
            except Exception:
                self._diz(traceback.format_exc())
        else:
            self._modo = "pasta"
            self._diz("perfil %s: Build monta a pasta inteira como 1 asset."
                      % self._profile.label)
        self._diz("-" * 10 + " FINISHED SCANNING " + "-" * 10)

    def _build(self):
        """Etapa 2: monta a rede em /stage SEM escrever.

        Da' para abrir o subnet USD_Builder_Asset_* e mexer no que quiser
        antes do export -- o pedido do Matheus: 'chegar e alterar'.
        """
        if self._asset is None:
            self._diz("faca o 1 — SCAN primeiro.")
            return
        _reload_core()
        from usd_builder_asset import library, log, profiles
        from usd_builder_asset.lops import builder
        # re-scan barato: garante que edicoes de codigo valem ja
        self._asset = library.scan(self._asset.root)
        self._profile, _e, _a = profiles.plan(self._asset)

        renderers = tuple(r for r, ck in self.cks.items() if ck.isChecked())
        out = self.edSaida.text().strip() or None
        tex_dir = None
        if out and self.ckTexShared.isChecked():
            tex_dir = out.rstrip("/") + "/textures"
        settings = {"basecolor_gamma": self.spGamma.value(),
                    "normal_scale": self.spNormal.value(),
                    "subsurface": self.spSss.value()}
        over = {"proxy": self.ckProxy.isChecked(),
                "simproxy": self.ckSimproxy.isChecked()}

        # alvos: (geo_path|None, asset_name|None, variants|None)
        alvos = []
        if self._modo == "multifbx":
            arquivos = [i.text() for i in self.lista.selectedItems()]
            if not arquivos:
                self._diz("selecione ao menos um arquivo da lista.")
                return
            caminhos = {os.path.basename(c): c
                        for c in self._asset.geo_files}
            variantes = library.atlas_variants(self._asset)
            perfil = profiles.custom("kitbash", **over)
            for nome_arq in arquivos:
                f = caminhos[nome_arq]
                try:
                    tops = builder.list_assets_in_file(f)
                except Exception:
                    self._diz(traceback.format_exc())
                    continue
                self._diz("PROCESSING FILE: %s (%d assets)"
                          % (nome_arq, len(tops)))
                for top in tops:
                    alvos.append((f, top, variantes))
        elif self._modo == "objetos":
            perfil = profiles.custom(self._profile.key, **over)
            sel = [i.text() for i in self.lista.selectedItems()]
            if not sel:
                self._diz("selecione ao menos um objeto da lista.")
                return
            alvos = [(None, nome, None) for nome in sel]
        else:
            perfil = profiles.custom(self._profile.key, **over)
            alvos = [(None, None, None)]

        self._builds = []
        t = log.Tempo()
        self._diz("\n" + "-" * 10 + " START BUILDING ASSET SUBNETWORK "
                  + "-" * 10)
        with hou.InterruptableOperation("USD_Builder_Asset build",
                                        open_interrupt_dialog=True) as op:
            for i, (geo, alvo, variantes) in enumerate(alvos):
                op.updateProgress(float(i) / max(1, len(alvos)))
                try:
                    res = builder.build_asset(
                        self._asset, perfil, out_dir=out,
                        asset_name=alvo, renderers=renderers, write=False,
                        geo_path=geo, variants=variantes,
                        tex_dir=tex_dir, disp_scale=self.spDisp.value(),
                        settings=settings)
                    self._builds.append(res)
                    self._diz("✓ Building Asset SubNet: %s ........... %d/%d"
                              % (res.asset_name, i + 1, len(alvos)))
                    for av in res.avisos:
                        self._diz("   ! " + av)
                except Exception:
                    self._diz(traceback.format_exc())
        self._diz(t.build_time())
        self._diz("-" * 10 + " FINISHED BUILDING (%d) " % len(self._builds)
                  + "-" * 10)
        self._diz("Confira/altere os subnets USD_Builder_Asset_* em /stage "
                  "e aperte 3 — EXPORT USD's.")

    def _export(self):
        """Etapa 3: executa os componentoutput montados na etapa 2."""
        _reload_core()
        from usd_builder_asset import log
        vivos = [r for r in self._builds
                 if r.nodes.get("componentoutput") is not None]
        if not vivos:
            self._diz("nada montado — rode o 2 — BUILD ASSETS antes.")
            return
        t = log.Tempo()
        self._diz("-" * 10 + " START EXPORTING USD's " + "-" * 10)
        escritos = 0
        with hou.InterruptableOperation("USD_Builder_Asset export",
                                        open_interrupt_dialog=True) as op:
            for i, res in enumerate(vivos):
                op.updateProgress(float(i) / max(1, len(vivos)))
                co = res.nodes["componentoutput"]
                try:
                    co.parm("execute").pressButton()
                    ok = res.usd_path and os.path.isfile(res.usd_path)
                    escritos += 1 if ok else 0
                    self._diz("✓ EXPORT: %s ........... %d/%d%s"
                              % (res.asset_name, i + 1, len(vivos),
                                 "" if ok else "  (NAO escrito!)"))
                except Exception:
                    self._diz(traceback.format_exc())
        self._diz(t.build_time())
        self._diz("-" * 10 + " FINISHED EXPORTING (%d/%d) " %
                  (escritos, len(vivos)) + "-" * 10)


_painel = None


def show():
    global _painel
    try:
        if _painel is not None:
            _painel.close()
            _painel.deleteLater()
    except Exception:
        pass
    _painel = Panel()
    _painel.show()
    _painel.raise_()
    return _painel
