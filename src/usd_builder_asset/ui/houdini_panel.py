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
        # duas abas como o HDA: USD BUILDER (fluxo) e SETTINGS (ajustes +
        # UPDATE MATERIALS) -- pedido do Matheus
        abas = QtWidgets.QTabWidget()
        raiz.addWidget(abas, 2)

        # ============ aba USD BUILDER ============
        w1 = QtWidgets.QWidget()
        v1 = QtWidgets.QVBoxLayout(w1)

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

        # perfil: Auto (o scanner decide) ou o usuario MARCA -- "nao seria
        # melhor eu indicar isso marcando?" (Matheus). Evermotion/SpeedTree/
        # Fab entram quando houver pasta real para medir.
        self.cbPerfil = QtWidgets.QComboBox()
        self.cbPerfil.addItem("Auto — o scanner decide", "auto")
        for chave, rotulo in (("megascans", "Megascans"),
                              ("maxtree", "Maxtree (plantas)"),
                              ("kitbash", "KitBash3D"),
                              ("construido", "Ja construido"),
                              ("generico", "Generico")):
            self.cbPerfil.addItem(rotulo, chave)
        fF.addRow("Perfil", self.cbPerfil)

        self.btScan = QtWidgets.QPushButton("1 — SCAN")
        self.btScan.clicked.connect(self._scan)
        fF.addRow(self.btScan)
        self.lbResumo = QtWidgets.QLabel("—")
        self.lbResumo.setWordWrap(True)
        fF.addRow(self.lbResumo)
        v1.addWidget(gF)

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
        v1.addWidget(gO, 1)

        gR = QtWidgets.QGroupBox("Renderers e saida")
        fR = QtWidgets.QFormLayout(gR)
        hb = QtWidgets.QHBoxLayout()
        self.cks = {}
        for r in RENDERERS:
            ck = QtWidgets.QCheckBox(r)
            ck.setChecked(False)   # "desliga os renderizadores" -- escolha
            self.cks[r] = ck       # por rodada e' do usuario
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
        v1.addWidget(gR)

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
        v1.addWidget(wrap3)
        abas.addTab(w1, "USD BUILDER")

        # ============ aba SETTINGS ============
        w2 = QtWidgets.QWidget()
        v2 = QtWidgets.QVBoxLayout(w2)
        gS = QtWidgets.QGroupBox("Settings")
        fS = QtWidgets.QFormLayout(gS)

        def spin(valor, passo=0.01, dec=4):
            sp = QtWidgets.QDoubleSpinBox()
            sp.setDecimals(dec)
            sp.setRange(0.0, 100.0)
            sp.setSingleStep(passo)
            sp.setValue(valor)
            # as setas default do Qt sao minusculas ("gosto das setas mas
            # esta muito pequena") -- campo mais alto e botoes largos
            sp.setMinimumHeight(26)
            sp.setStyleSheet(
                "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button "
                "{ width: 22px; }")
            return sp

        self.spDisp = spin(0.01)
        self.spGamma = spin(1.0)
        self.spNormal = spin(1.0)
        self.spSss = spin(0.25)
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

        # a escala vem diferente por biblioteca (KitBash em cm = 0.01,
        # Maxtree ja em metros = 1); 0 = usa a do perfil
        self.spUnit = spin(0.0)
        fS.addRow("Unit Scale (0 = do perfil)", self.spUnit)

        self.ckTexShared = QtWidgets.QCheckBox(
            "Texturas compartilhadas (UMA copia em <saida>/textures)")
        self.ckTexShared.setChecked(False)   # opcoes todas desligadas
        fS.addRow(self.ckTexShared)

        self.ckGallery = QtWidgets.QCheckBox(
            "Asset Gallery no export (thumbnail GL implicito; "
            "<saida>/asset_gallery.db)")
        self.ckGallery.setChecked(False)
        fS.addRow(self.ckGallery)

        self.ckTexRman = QtWidgets.QCheckBox(
            "Converter .tex ACEScg p/ RenderMan (etapa do Asset_USD_Builder)")
        self.ckTexRman.setChecked(False)
        fS.addRow(self.ckTexRman)

        # config do thumbnail (usada quando a Asset Gallery esta ligada)
        hbT = QtWidgets.QHBoxLayout()
        self.spThumbRes = QtWidgets.QSpinBox()
        self.spThumbRes.setRange(64, 4096)
        self.spThumbRes.setValue(512)
        self.spThumbRes.setMinimumHeight(26)
        self.spSpin = spin(0.0, passo=1.0, dec=1)
        self.spSpin.setRange(-360.0, 360.0)
        self.spPitch = spin(0.0, passo=1.0, dec=1)
        self.spPitch.setRange(-360.0, 360.0)
        self.spDist = spin(0.0, passo=0.1, dec=2)
        self.spDist.setRange(0.0, 100000.0)
        for rotulo, wdg in (("res", self.spThumbRes), ("spin", self.spSpin),
                            ("pitch", self.spPitch), ("dist", self.spDist)):
            hbT.addWidget(QtWidgets.QLabel(rotulo))
            hbT.addWidget(wdg)
        wrapT = QtWidgets.QWidget()
        wrapT.setLayout(hbT)
        fS.addRow("Thumbnail", wrapT)
        v2.addWidget(gS)

        self.btUpdate = QtWidgets.QPushButton("UPDATE MATERIALS")
        self.btUpdate.setMinimumHeight(34)
        self.btUpdate.setToolTip(
            "Reconstroi so' os materiais dos builds da etapa 2 com os "
            "Settings atuais (geometria e binds ficam)")
        self.btUpdate.clicked.connect(self._update_materials)
        v2.addWidget(self.btUpdate)
        v2.addStretch(1)
        abas.addTab(w2, "SETTINGS")

        # log embaixo, fora das abas (as duas escrevem nele)
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
            escolha = self.cbPerfil.currentData()
            if escolha and escolha != "auto":
                # o usuario marcou: o perfil escolhido manda
                self._profile = profiles.custom(escolha)
                avisos = ["perfil marcado pelo usuario: %s"
                          % self._profile.label]
            else:
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
            # ARQUIVOS; o Build abre cada um e monta os assets de dentro.
            # Variantes abolidas: material unico da LIGHT, sem sufixo.
            self._modo = "multifbx"
            for c in self._asset.geo_files:
                self.lista.addItem(os.path.basename(c))
            nome_m, mapas_m = library.atlas_material(self._asset)
            self._diz("✓ %d arquivos no set; material do atlas: %s (%s). "
                      "Selecione e 2 — BUILD ASSETS."
                      % (self.lista.count(), nome_m,
                         ", ".join(sorted(mapas_m)) or "sem mapas"))
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
        escolha = self.cbPerfil.currentData()
        if escolha and escolha != "auto":
            base_key = escolha            # o usuario marcou: ele manda
        else:
            self._profile, _e, _a = profiles.plan(self._asset)
            base_key = self._profile.key

        renderers = tuple(r for r, ck in self.cks.items() if ck.isChecked())
        if not renderers:
            self._diz("marque ao menos um renderer (aba USD BUILDER).")
            return
        out = self.edSaida.text().strip() or None
        tex_dir = None
        if out and self.ckTexShared.isChecked():
            tex_dir = out.rstrip("/") + "/textures"
        settings = {"basecolor_gamma": self.spGamma.value(),
                    "normal_scale": self.spNormal.value(),
                    "subsurface": self.spSss.value(),
                    "tex_renderman": self.ckTexRman.isChecked()}
        over = {"proxy": self.ckProxy.isChecked(),
                "simproxy": self.ckSimproxy.isChecked()}
        if self.spUnit.value() > 0:
            over["unit_scale"] = self.spUnit.value()
        # gallery ligada => thumbnail no export implicito (GL) -- um
        # checkbox so', como o Matheus pediu
        thumb_cfg = None
        if self.ckGallery.isChecked():
            thumb_cfg = {"mode": 1, "res": self.spThumbRes.value(),
                         "spin": self.spSpin.value(),
                         "pitch": self.spPitch.value(),
                         "dist": self.spDist.value()}

        # alvos: (geo_path|None, asset_name|None, parts|None)
        alvos = []
        if self._modo == "multifbx":
            arquivos = [i.text() for i in self.lista.selectedItems()]
            if not arquivos:
                self._diz("selecione ao menos um arquivo da lista.")
                return
            caminhos = {os.path.basename(c): c
                        for c in self._asset.geo_files}
            # variantes abolidas: UM material da light, sem sufixo
            nome_m, mapas_m = library.atlas_material(self._asset)
            partes = {nome_m: mapas_m} if mapas_m else None
            perfil = profiles.custom(base_key if escolha != "auto" else "kitbash", **over)
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
                    alvos.append((f, top, partes))
        elif self._modo == "objetos":
            perfil = profiles.custom(base_key, **over)
            sel = [i.text() for i in self.lista.selectedItems()]
            if not sel:
                self._diz("selecione ao menos um objeto da lista.")
                return
            alvos = [(None, nome, None) for nome in sel]
        else:
            perfil = profiles.custom(base_key, **over)
            alvos = [(None, None, None)]

        self._builds = []
        t = log.Tempo()
        self._diz("\n" + "-" * 10 + " START BUILDING ASSET SUBNETWORK "
                  + "-" * 10)
        with hou.InterruptableOperation("USD_Builder_Asset build",
                                        open_interrupt_dialog=True) as op:
            for i, (geo, alvo, partes) in enumerate(alvos):
                op.updateProgress(float(i) / max(1, len(alvos)))
                try:
                    res = builder.build_asset(
                        self._asset, perfil, out_dir=out,
                        asset_name=alvo, renderers=renderers, write=False,
                        geo_path=geo, parts=partes,
                        tex_dir=tex_dir, disp_scale=self.spDisp.value(),
                        settings=settings, thumb_cfg=thumb_cfg)
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

    def _update_materials(self):
        """Reconstroi so' os materiais (o UPDATE ALL SETTINGS do HDA).

        Mexe nos Settings -> UPDATE MATERIALS -> os materiais dos builds
        da etapa 2 sao remontados; geometria/binds/output ficam.
        """
        if not self._builds:
            self._diz("nada montado — rode o 2 — BUILD ASSETS antes.")
            return
        _reload_core()
        from usd_builder_asset import log
        from usd_builder_asset.lops import builder
        renderers = tuple(r for r, ck in self.cks.items() if ck.isChecked())
        if not renderers:
            self._diz("marque ao menos um renderer (aba USD BUILDER).")
            return
        settings = {"basecolor_gamma": self.spGamma.value(),
                    "normal_scale": self.spNormal.value(),
                    "subsurface": self.spSss.value(),
                    "tex_renderman": self.ckTexRman.isChecked()}
        t = log.Tempo()
        self._diz("-" * 10 + " START UPDATING MATERIALS " + "-" * 10)
        with hou.InterruptableOperation("USD_Builder_Asset update",
                                        open_interrupt_dialog=True) as op:
            for i, res in enumerate(self._builds):
                op.updateProgress(float(i) / max(1, len(self._builds)))
                try:
                    n = builder.rebuild_materials(
                        res, renderers, disp_scale=self.spDisp.value(),
                        settings=settings)
                    self._diz("✓ UPDATE: %s (%d materiais) ..... %d/%d"
                              % (res.asset_name, n, i + 1,
                                 len(self._builds)))
                except Exception:
                    self._diz(traceback.format_exc())
        self._diz(t.build_time())
        self._diz("-" * 10 + " FINISHED UPDATING " + "-" * 10)

    def _export(self):
        """Etapa 3: executa os componentoutput montados na etapa 2.

        Com o Thumbnail + Asset Gallery ligado, cada asset escrito ganha
        thumbnail (GL) e entra no asset_gallery.db da saida -- o esquema
        do video, mas com dedup ANTES de inserir.
        """
        _reload_core()
        from usd_builder_asset import gallery, log
        vivos = [r for r in self._builds
                 if r.nodes.get("componentoutput") is not None]
        if not vivos:
            self._diz("nada montado — rode o 2 — BUILD ASSETS antes.")
            return
        out = self.edSaida.text().strip()
        db = (out.rstrip("/") + "/asset_gallery.db"
              if out and self.ckGallery.isChecked() else None)
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
                    extra = ""
                    if ok and db:
                        # o autothumbnail do export (GL) ja deixa o png
                        # na pasta; render externo so' na falta dele
                        png = os.path.join(os.path.dirname(res.usd_path),
                                           "thumbnail.png")
                        if not os.path.isfile(png):
                            png = gallery.thumbnail(res.usd_path)
                        estado = gallery.registrar(
                            db, res.asset_name, res.usd_path, png,
                            )
                        extra = "  [gallery: %s%s]" % (
                            estado, "" if png else ", sem thumbnail")
                    self._diz("✓ EXPORT: %s ........... %d/%d%s"
                              % (res.asset_name, i + 1, len(vivos),
                                 extra if ok else "  (NAO escrito!)"))
                except Exception:
                    self._diz(traceback.format_exc())
        self._diz(t.build_time())
        self._diz("-" * 10 + " FINISHED EXPORTING (%d/%d) " %
                  (escritos, len(vivos)) + "-" * 10)
        if db:
            self._diz("Asset Gallery: aponte a pane Layout Asset Gallery "
                      "para %s" % db)


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
