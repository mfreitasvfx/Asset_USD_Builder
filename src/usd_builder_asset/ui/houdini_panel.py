"""Janela do USD_Builder_Asset dentro do Houdini.

    import sys; sys.path.insert(0, r"C:/dev/USD_Builder_Asset/src")
    from usd_builder_asset.ui import houdini_panel
    houdini_panel.show()

Etapas numeradas, como no Asset_USD_Builder do Carlo:
    1 - SCAN          le a pasta e lista os objetos (KitBash)
    2 - BUILD ASSETS  monta a rede em /stage SEM escrever -- da' para
                      abrir o subnet (nome do asset) e alterar antes
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


def _S(n):
    """px que acompanham o Global UI Size do Houdini (o Matheus usa 1.5)."""
    try:
        return hou.ui.scaledSize(n)
    except AttributeError:           # hython/headless nao tem hou.ui
        return n


def _bt(texto, dica, cb):
    """Botao curto que NAO corta o texto.

    O base.qss do Houdini poe padding 15px de cada lado em TODO QPushButton,
    e esses 15 sao multiplicados pelo Global UI Size: na escala 1.5 do
    Matheus sobravam 4px dos 48px fixos de antes e o Qt CLIPAVA a palavra --
    o botao OPEN aparecia vazio. Quem dimensiona agora e' o texto na fonte
    corrente, entao serve em qualquer escala.
    """
    b = QtWidgets.QPushButton(texto)
    b.setToolTip(dica)
    fm = b.fontMetrics()
    larg = (fm.horizontalAdvance(texto) if hasattr(fm, "horizontalAdvance")
            else fm.width(texto))
    b.setMinimumWidth(max(b.sizeHint().width(), larg + _S(36)))
    b.clicked.connect(cb)
    return b


def _bt_icone(nome, dica, cb, texto_fallback):
    """O botao de escolher pasta com o icone do proprio Houdini.

    Mesma receita do FileChooserButton da SideFX (QToolButton + icone em
    hou.ui.scaledSize(16)); sem GUI (hython) cai no botao de texto.
    """
    ic = None
    try:
        if not hou.qt.canCreateIcon(nome):
            raise ValueError(nome)
        fabrica = getattr(hou.qt, "createIcon", None) or hou.qt.Icon
        s = _S(16)
        ic = fabrica(nome, s, s)
        if ic is None or ic.isNull():
            raise ValueError(nome)
    except Exception:
        ic = None
    if ic is None:                   # sem GUI, ou icone que nao existe
        return _bt(texto_fallback, dica, cb)
    b = QtWidgets.QToolButton()
    b.setIcon(ic)
    b.setIconSize(QtCore.QSize(s, s))
    b.setAutoRaise(True)
    b.setToolTip(dica)
    b.clicked.connect(cb)
    return b


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
        # a janela acompanha a escala da UI do Houdini, mas nunca nasce
        # maior que a tela (a 1.5 os 760 viram 1140)
        larg, alt = _S(560), _S(760)
        try:
            tela = QtWidgets.QApplication.primaryScreen().availableGeometry()
            larg, alt = min(larg, tela.width() - 60), min(alt,
                                                          tela.height() - 80)
        except Exception:
            pass
        self.resize(larg, alt)
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

        def aba(w, titulo):
            """Cada aba entra com rolagem: sem isso o conteudo mais largo
            (a linha Thumbnail) vira piso de largura e a janela nao
            encolhe -- medido 791px de minimo na escala 1.5 do Matheus."""
            sc = QtWidgets.QScrollArea()
            sc.setWidgetResizable(True)
            sc.setFrameShape(QtWidgets.QFrame.NoFrame)
            sc.setWidget(w)
            abas.addTab(sc, titulo)

        # ============ aba USD BUILDER ============
        w1 = QtWidgets.QWidget()
        v1 = QtWidgets.QVBoxLayout(w1)

        gF = QtWidgets.QGroupBox("Source")
        fF = QtWidgets.QFormLayout(gF)
        # combo editavel com as ULTIMAS PASTAS abertas (pedido do Matheus:
        # memoria de pelo menos 5)
        self.edFonte = self._combo_pasta(self._ARQ_RECENTES, primeira=True)
        fF.addRow("Asset Folder", self._linha_pasta(self.edFonte))

        # pasta de texturas OPCIONAL (pedido do Matheus: "CASO nao ache a
        # textura eu aponte um local") -- mesma memoria de recentes, mas
        # comeca VAZIA: opcional nao se auto-preenche
        self.cbTex = self._combo_pasta(self._ARQ_RECENTES_TEX)
        fF.addRow("Textures (optional)", self._linha_pasta(self.cbTex))

        # linha separadora + Output Folder logo abaixo (pedido do Matheus)
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setFrameShadow(QtWidgets.QFrame.Sunken)
        fF.addRow(sep)

        # saida com o MESMO esquema dos outros dois: triangulo de recentes,
        # escolher pasta e OPEN
        self.edSaida = self._combo_pasta(self._ARQ_RECENTES_OUT,
                                         primeira=True)
        if not self._texto(self.edSaida):
            self.edSaida.setCurrentText(
                "C:/Users/Matheus/Downloads/MaxToLama/Testes/lops_ui")
        fF.addRow("Output Folder", self._linha_pasta(self.edSaida))

        # perfil: Auto (o scanner decide) ou o usuario MARCA
        self.cbPerfil = QtWidgets.QComboBox()
        self.cbPerfil.addItem("Auto — scanner decides", "auto")
        for chave, rotulo in (("megascans", "Megascans"),
                              ("maxtree", "Maxtree (plants)"),
                              ("kitbash", "KitBash3D"),
                              ("construido", "Already built"),
                              ("generico", "Generic")):
            self.cbPerfil.addItem(rotulo, chave)
        fF.addRow("Profile", self.cbPerfil)

        self.btScan = QtWidgets.QPushButton("1 — SCAN")
        self.btScan.clicked.connect(self._scan)
        fF.addRow(self.btScan)
        self.lbResumo = QtWidgets.QLabel("—")
        self.lbResumo.setWordWrap(True)
        fF.addRow(self.lbResumo)
        v1.addWidget(gF)

        # objetos (kitbash) ou arquivos (set multi-FBX)
        gO = QtWidgets.QGroupBox("Objects / Files (KitBash)")
        vO = QtWidgets.QVBoxLayout(gO)
        self.edFiltro = QtWidgets.QLineEdit()
        self.edFiltro.setPlaceholderText("filter…")
        self.edFiltro.textChanged.connect(self._filtrar)
        vO.addWidget(self.edFiltro)
        self.lista = QtWidgets.QListWidget()
        self.lista.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        vO.addWidget(self.lista)
        v1.addWidget(gO, 1)

        gR = QtWidgets.QGroupBox("Renderers")
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

        # opt-in do two-sided na TELA PRINCIPAL (pedido do Matheus)
        # rotulo curto + explicacao no tooltip: texto comprido em checkbox
        # vira piso de largura da janela (medido: 498px so' neste)
        self.ckTwoSided = QtWidgets.QCheckBox("Two-Sided leaves")
        self.ckTwoSided.setToolTip(
            "Frente/verso nas folhas: usa a textura <Nome>_Back quando ela "
            "existe e, quando nao existe, repete a da frente no verso")
        self.ckTwoSided.setChecked(False)
        fR.addRow(self.ckTwoSided)
        v1.addWidget(gR)

        linha3 = QtWidgets.QHBoxLayout()
        self.btBuild = QtWidgets.QPushButton("2 — BUILD ASSETS")
        self.btBuild.setMinimumHeight(_S(34))
        self.btBuild.clicked.connect(self._build)
        linha3.addWidget(self.btBuild)
        self.btExport = QtWidgets.QPushButton("3 — EXPORT USD's")
        self.btExport.setMinimumHeight(_S(34))
        self.btExport.clicked.connect(self._export)
        linha3.addWidget(self.btExport)
        wrap3 = QtWidgets.QWidget()
        wrap3.setLayout(linha3)
        v1.addWidget(wrap3)
        aba(w1, "USD BUILDER")

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
            sp.setMinimumHeight(_S(26))
            sp.setStyleSheet(
                "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button "
                "{ width: %dpx; }" % _S(22))   # px de qss nao escalam sozinhos
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
        self.ckSimproxy = QtWidgets.QCheckBox("simproxy (physics)")
        # o proxy/simproxy ja' gravado ao lado do fbx (pasta proxy/ e
        # simproxy/) entra como um File so'; Force monta a rede de novo
        self.ckForce = QtWidgets.QCheckBox("force")
        self.ckForce.setToolTip(
            "Monta a rede de proxy/simproxy mesmo que o arquivo ja' exista "
            "em <pasta do fbx>/proxy e /simproxy -- para refazer o setup")
        hbP.addWidget(self.ckProxy)
        hbP.addWidget(self.ckSimproxy)
        hbP.addWidget(self.ckForce)
        wrapP = QtWidgets.QWidget()
        wrapP.setLayout(hbP)
        fS.addRow("Branches", wrapP)

        # a escala vem diferente por biblioteca (KitBash em cm = 0.01,
        # Maxtree ja em metros = 1); 0 = usa a do perfil
        self.spUnit = spin(0.01)
        self.spUnit.setToolTip(
            "Vai direto para o convert_units do builder. 1 = sem conversao")
        fS.addRow("Unit Scale", self.spUnit)

        self.ckTexShared = QtWidgets.QCheckBox("Shared textures")
        self.ckTexShared.setToolTip(
            "UMA copia das texturas em <out>/textures, em vez de uma por "
            "asset")
        self.ckTexShared.setChecked(False)   # opcoes todas desligadas
        fS.addRow(self.ckTexShared)

        self.ckGallery = QtWidgets.QCheckBox("Asset Gallery on export")
        self.ckGallery.setToolTip(
            "Registra cada asset exportado em <out>/asset_gallery.db "
            "(o banco viaja junto com os USDs) com thumbnail GL implicito")
        self.ckGallery.setChecked(False)
        fS.addRow(self.ckGallery)

        self.ckTexRman = QtWidgets.QCheckBox("Convert .tex (RenderMan)")
        self.ckTexRman.setToolTip(
            "Converte as texturas para .tex ACEScg, a mesma etapa que o "
            "Asset_USD_Builder faz para o RenderMan")
        self.ckTexRman.setChecked(False)
        fS.addRow(self.ckTexRman)

        # config do thumbnail (usada quando a Asset Gallery esta ligada)
        hbT = QtWidgets.QHBoxLayout()
        self.spThumbRes = QtWidgets.QSpinBox()
        self.spThumbRes.setRange(64, 4096)
        self.spThumbRes.setValue(512)
        self.spThumbRes.setMinimumHeight(_S(26))
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
        self.btUpdate.setMinimumHeight(_S(34))
        self.btUpdate.setToolTip(
            "Reconstroi so' os materiais dos builds da etapa 2 com os "
            "Settings atuais (geometria e binds ficam)")
        self.btUpdate.clicked.connect(self._update_materials)
        v2.addWidget(self.btUpdate)

        self.btPreset = QtWidgets.QPushButton("SAVE PRESET")
        self.btPreset.setMinimumHeight(_S(34))
        self.btPreset.setToolTip(
            "Ajuste um builder (vray_*/karma_*/...) no capricho, selecione "
            "o no e salve: TODO build seguinte daquele renderer+tipo "
            "(leaf/trunk/default) usa o preset, so' trocando as texturas")
        self.btPreset.clicked.connect(self._save_preset)
        v2.addWidget(self.btPreset)
        v2.addStretch(1)
        aba(w2, "SETTINGS")

        # log embaixo, fora das abas (as duas escrevem nele)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        raiz.addWidget(self.log, 1)

    # ------------------------------------------------------------------

    # -- memoria das ultimas pastas (pedido: pelo menos 5) ---------------
    _ARQ_RECENTES = os.path.join(
        hou.homeHoudiniDirectory() if hasattr(hou, "homeHoudiniDirectory")
        else os.path.expanduser("~"), "usd_builder_asset_recent.json")
    _ARQ_RECENTES_TEX = os.path.join(
        os.path.dirname(_ARQ_RECENTES), "usd_builder_asset_recent_tex.json")
    _ARQ_RECENTES_OUT = os.path.join(
        os.path.dirname(_ARQ_RECENTES), "usd_builder_asset_recent_out.json")

    def _combo_pasta(self, arq, primeira=False):
        """Campo de pasta com o triangulo de recentes, como as linhas
        'type directory' do Asset_USD_Builder."""
        cb = QtWidgets.QComboBox()
        cb.setEditable(True)
        cb.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        nossas = self._recentes_json(arq)
        for p in self._recentes_carrega(arq):
            cb.addItem(p)
        # auto-preenche so' com a ULTIMA PASTA NOSSA: as do historico do
        # Houdini ficam no triangulo, mas escrever sozinho uma pasta de
        # saida vinda de outro trabalho seria pedir para exportar no lugar
        # errado
        cb.setCurrentText(nossas[0] if (primeira and nossas) else "")
        # caminho comprido nao pode DITAR a largura minima da janela
        # ("nao consigo diminuir a janela" -- Matheus): o combo trunca o
        # texto e o caminho inteiro vai para o tooltip
        cb.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        cb.setMinimumContentsLength(18)
        cb.setToolTip(cb.currentText())
        cb.currentTextChanged.connect(
            lambda t, c=cb: c.setToolTip(t))
        return cb

    def _linha_pasta(self, campo):
        """campo + escolher + OPEN na mesma linha. No HDA do Carlo o
        Houdini desenha isso sozinho para todo parm 'type directory'; numa
        janela Qt os tres widgets sao na mao."""
        linha = QtWidgets.QHBoxLayout()
        linha.setContentsMargins(0, 0, 0, 0)
        linha.addWidget(campo, 1)
        linha.addWidget(_bt_icone("BUTTONS_chooser_folder", "choose folder",
                                  lambda: self._escolher(campo), "..."))
        linha.addWidget(_bt("OPEN", "open this folder in Explorer",
                            lambda: self._abrir(campo)))
        w = QtWidgets.QWidget()
        w.setLayout(linha)
        return w

    def _hist_houdini(self):
        """As pastas do triangulo de recentes do PROPRIO Houdini
        (dir.history, secao DIRECTORY) -- e' dai que o Asset_USD_Builder
        tira o menu dele, entao a nossa janela oferece as mesmas."""
        arq = os.path.join(os.path.dirname(self._ARQ_RECENTES),
                           "dir.history")
        saida, dentro = [], False
        try:
            with open(arq, "r", encoding="utf-8", errors="ignore") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if not dentro:
                        dentro = (ln == "DIRECTORY")
                    elif ln == "}":
                        break
                    elif ln and ln != "{":
                        saida.append(ln.replace("\\", "/"))
        except Exception:
            return []
        return saida[:12]

    def _recentes_json(self, arq=None):
        import json
        try:
            with open(arq or self._ARQ_RECENTES, "r",
                      encoding="utf-8") as fh:
                return [p for p in json.load(fh) if os.path.isdir(p)][:8]
        except Exception:
            return []

    def _recentes_carrega(self, arq=None):
        lista = self._recentes_json(arq)
        vistos = set(p.lower() for p in lista)
        for p in self._hist_houdini():          # completa com as do Houdini
            if p.lower() not in vistos and os.path.isdir(p):
                lista.append(p)
                vistos.add(p.lower())
        return lista[:12]

    def _recentes_salva(self, pasta, combo=None, arq=None):
        import json
        combo = combo if combo is not None else self.edFonte
        arq = arq or self._ARQ_RECENTES
        pasta = pasta.replace("\\", "/")
        lista = [pasta] + [p for p in self._recentes_json(arq)
                           if p.lower() != pasta.lower()]
        try:
            with open(arq, "w", encoding="utf-8") as fh:
                json.dump(lista[:8], fh, indent=1)
        except Exception:
            pass
        combo.blockSignals(True)
        atual = combo.currentText()
        combo.clear()
        for p in self._recentes_carrega(arq):
            combo.addItem(p)
        combo.setCurrentText(atual)
        combo.blockSignals(False)

    def _texto(self, campo):
        return (campo.currentText() if isinstance(campo, QtWidgets.QComboBox)
                else campo.text()).strip()

    def _abrir(self, campo):
        """O botao OPEN do Asset_USD_Builder: abre a pasta no Explorer."""
        p = self._texto(campo)
        if os.path.isdir(p):
            os.startfile(os.path.normpath(p))
        else:
            self._diz("folder does not exist: %r" % p)

    def _escolher(self, campo):
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Folder", self._texto(campo) or os.path.expanduser("~"))
        if d:
            d = d.replace("\\", "/")
            if isinstance(campo, QtWidgets.QComboBox):
                campo.setCurrentText(d)
            else:
                campo.setText(d)

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
        pasta = self._texto(self.edFonte)
        if not os.path.isdir(pasta):
            self._diz("invalid folder: %r" % pasta)
            return
        tex = self._texto(self.cbTex)
        if tex and not os.path.isdir(tex):
            self._diz("invalid textures folder: %r" % tex)
            return
        self._diz("-" * 10 + " START SCANNING " + "-" * 10)
        try:
            self._asset = library.scan(pasta, tex_dir=tex or None)
            escolha = self.cbPerfil.currentData()
            if escolha and escolha != "auto":
                # o usuario marcou: o perfil escolhido manda
                self._profile = profiles.custom(escolha)
                avisos = ["profile picked by user: %s"
                          % self._profile.label]
            else:
                self._profile, _etapas, avisos = profiles.plan(self._asset)
        except Exception:
            self._diz(traceback.format_exc())
            return
        self._recentes_salva(pasta)
        if tex:
            self._recentes_salva(tex, self.cbTex, self._ARQ_RECENTES_TEX)
        # branches: o perfil da' o ponto de partida, o usuario sobrepoe
        # desmarcando antes do BUILD (ferramenta adaptativa)
        self.ckProxy.setChecked(bool(getattr(self._profile, "proxy", False)))
        self.ckSimproxy.setChecked(
            bool(getattr(self._profile, "simproxy", False)))
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
            self._diz("✓ %d files in set; atlas material: %s (%s). "
                      "Select and 2 — BUILD ASSETS."
                      % (self.lista.count(), nome_m,
                         ", ".join(sorted(mapas_m)) or "sem mapas"))
        elif self._profile.asset_grain == "object":
            self._modo = "objetos"
            self._diz("reading objects from file…")
            try:
                for nome in builder.list_assets_in_file(
                        self._asset.default_geo):
                    self.lista.addItem(nome)
                self._diz("✓ %d objects. Select and 2 — BUILD ASSETS."
                          % self.lista.count())
            except Exception:
                self._diz(traceback.format_exc())
        else:
            self._modo = "pasta"
            self._diz("profile %s: Build makes the whole folder ONE asset."
                      % self._profile.label)
        self._diz("-" * 10 + " FINISHED SCANNING " + "-" * 10)

    def _build(self):
        """Etapa 2: monta a rede em /stage SEM escrever.

        Da' para abrir o subnet (nome do asset) e mexer no que quiser
        antes do export -- o pedido do Matheus: 'chegar e alterar'.
        """
        if self._asset is None:
            self._diz("run 1 — SCAN first.")
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
            self._diz("check at least one renderer (USD BUILDER tab).")
            return
        out = self._texto(self.edSaida) or None
        if out:
            self._recentes_salva(out, self.edSaida, self._ARQ_RECENTES_OUT)
        tex_dir = None
        if out and self.ckTexShared.isChecked():
            tex_dir = out.rstrip("/") + "/textures"
        settings = {"basecolor_gamma": self.spGamma.value(),
                    "normal_scale": self.spNormal.value(),
                    "subsurface": self.spSss.value(),
                    "tex_renderman": self.ckTexRman.isChecked()}
        over = {"proxy": self.ckProxy.isChecked(),
                "simproxy": self.ckSimproxy.isChecked()}
        # o campo da janela manda no convert_units, sempre (padrao 0.01;
        # o BigMediumSmall ja' vem em metros e ali o Matheus poe 1)
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
                self._diz("select at least one file from the list.")
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
                # DEPOIS do list (a importacao extrai texturas embutidas
                # p/ <arquivo>.fbm): arquivo com texturas proprias usa as
                # SUAS partes; sem elas, o atlas do set (Post Apocalypse)
                partes_f = library.parts_for_file(self._asset, f) or partes
                if partes_f is not partes:
                    self._diz("PROCESSING FILE: %s (%d assets, %d own "
                              "texture parts)" % (nome_arq, len(tops),
                                                  len(partes_f)))
                else:
                    self._diz("PROCESSING FILE: %s (%d assets)"
                              % (nome_arq, len(tops)))
                for top in tops:
                    alvos.append((f, top, partes_f))
        elif self._modo == "objetos":
            perfil = profiles.custom(base_key, **over)
            sel = [i.text() for i in self.lista.selectedItems()]
            if not sel:
                self._diz("select at least one object from the list.")
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
                        settings=settings, thumb_cfg=thumb_cfg,
                        two_sided=self.ckTwoSided.isChecked(),
                        force_proxy=self.ckForce.isChecked())
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
        self._diz("Check/tweak the asset subnets in /stage "
                  "and press 3 — EXPORT USD's.")

    def _update_materials(self):
        """Reconstroi so' os materiais (o UPDATE ALL SETTINGS do HDA).

        Mexe nos Settings -> UPDATE MATERIALS -> os materiais dos builds
        da etapa 2 sao remontados; geometria/binds/output ficam.
        """
        if not self._builds:
            self._diz("nothing built — run 2 — BUILD ASSETS first.")
            return
        _reload_core()
        from usd_builder_asset import log
        from usd_builder_asset.lops import builder
        renderers = tuple(r for r, ck in self.cks.items() if ck.isChecked())
        if not renderers:
            self._diz("check at least one renderer (USD BUILDER tab).")
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

    def _save_preset(self):
        """Salva o builder selecionado como preset de look.

        A fase de "ajuste de look": capricha num vray_Leaf_02, salva, e
        toda folha V-Ray dos proximos builds herda -- so' as texturas
        mudam (re-apontadas por papel).
        """
        _reload_core()
        from usd_builder_asset import presets
        sel = hou.selectedNodes()
        if len(sel) != 1:
            self._diz("selecione UM builder (karma_*/arnold_*/renderman_*/"
                      "vray_*) dentro da materiallibrary.")
            return
        try:
            alvo, tipo = presets.salvar(sel[0])
        except ValueError as e:
            self._diz(str(e))
            return
        self._diz("✓ PRESET salvo: %s (tipo '%s'). Builds seguintes desse "
                  "renderer+tipo usam ele; UPDATE MATERIALS aplica nos "
                  "builds atuais." % (alvo, tipo))

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
            self._diz("nothing built — run 2 — BUILD ASSETS first.")
            return
        out = self._texto(self.edSaida)
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
