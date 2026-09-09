"""Janela do max2solaris (PySide6, o binding que o 3ds Max 2027 traz).

A janela nao contem regra nenhuma: ela le e escreve um `Settings` e chama
`exporter.export`. E' o que permite testar o export inteiro pelo 3dsmaxbatch,
sem interface.
"""
import os

from PySide6 import QtCore, QtWidgets

from ..settings import Settings
from .. import exporter

TITULO = "max2solaris  —  export para o Asset_USD_Builder"


def _max_main_window():
    try:
        import qtmax
        return qtmax.GetQMaxMainWindow()
    except Exception:
        return None


class ExportWindow(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super(ExportWindow, self).__init__(parent or _max_main_window())
        self.setWindowFlag(QtCore.Qt.Window, True)
        self.setWindowTitle(TITULO)
        self.resize(620, 640)

        self.s = Settings.load()
        self._campos = {}
        self._montar()
        self._do_settings()

    # -- construcao ------------------------------------------------------

    def _montar(self):
        raiz = QtWidgets.QVBoxLayout(self)

        # --- destino ---
        gDest = QtWidgets.QGroupBox("Destino")
        fDest = QtWidgets.QFormLayout(gDest)

        linha = QtWidgets.QHBoxLayout()
        self.edDir = QtWidgets.QLineEdit()
        btDir = QtWidgets.QPushButton("...")
        btDir.setFixedWidth(34)
        btDir.clicked.connect(self._escolher_pasta)
        linha.addWidget(self.edDir)
        linha.addWidget(btDir)
        w = QtWidgets.QWidget()
        w.setLayout(linha)
        fDest.addRow("Pasta destino", w)

        self.edNome = QtWidgets.QLineEdit()
        self.edNome.setPlaceholderText("vazio = nome da cena")
        fDest.addRow("Nome do asset", self.edNome)
        raiz.addWidget(gDest)

        # --- o que exportar ---
        gQue = QtWidgets.QGroupBox("O que exportar")
        fQue = QtWidgets.QFormLayout(gQue)
        self.ckSel = QtWidgets.QCheckBox("Somente a selecao")
        self.ckPorObj = QtWidgets.QCheckBox(
            "Um asset por objeto de topo (cada um na sua pasta)")
        self.edLod = QtWidgets.QLineEdit()
        self.edLod.setToolTip(
            "O Asset_USD_Builder detecta LOD pelo token colado na extensao:\n"
            "_High.fbx, _LOD0.fbx, _LOD1.fbx ...")
        fQue.addRow(self.ckSel)
        fQue.addRow(self.ckPorObj)
        fQue.addRow("Token de LOD", self.edLod)
        raiz.addWidget(gQue)

        # --- FBX ---
        gFbx = QtWidgets.QGroupBox("FBX")
        fFbx = QtWidgets.QFormLayout(gFbx)
        self.cbUp = QtWidgets.QComboBox()
        self.cbUp.addItems(["Y", "Z"])
        self.cbUp.setToolTip("Houdini e' Y-up. Z aqui faz o asset chegar "
                             "deitado no Solaris.")
        self.cbUnid = QtWidgets.QComboBox()
        self.cbUnid.addItems(["cm", "m", "mm", "in", "ft"])
        self.cbVer = QtWidgets.QComboBox()
        self.cbVer.addItems(["FBX202000", "FBX201900", "FBX201800"])
        fFbx.addRow("Eixo Up", self.cbUp)
        fFbx.addRow("Unidades", self.cbUnid)
        fFbx.addRow("Versao", self.cbVer)

        for nome, rotulo in (("smoothing_groups", "Smoothing groups"),
                             ("tangents", "Tangentes e binormais"),
                             ("preserve_instances", "Preservar instancias"),
                             ("triangulate", "Triangular"),
                             ("smooth_mesh", "Exportar subdivisao"),
                             ("animation", "Animacao"),
                             ("cameras", "Cameras"),
                             ("lights", "Luzes"),
                             ("ascii", "FBX em ASCII")):
            ck = QtWidgets.QCheckBox(rotulo)
            self._campos[nome] = ck
            fFbx.addRow(ck)
        raiz.addWidget(gFbx)

        # --- extras ---
        gEx = QtWidgets.QGroupBox("Extras")
        fEx = QtWidgets.QVBoxLayout(gEx)
        self.ckTex = QtWidgets.QCheckBox(
            "Copiar texturas para a pasta do asset")
        self.ckTex.setToolTip(
            "Desligado: a v1 so' exporta geometria.\n"
            "Sem textura na pasta, o Asset_USD_Builder acha o FBX mas nao\n"
            "monta material nenhum.")
        self.ckRel = QtWidgets.QCheckBox("Escrever relatorio .json")
        fEx.addWidget(self.ckTex)
        fEx.addWidget(self.ckRel)
        raiz.addWidget(gEx)

        # --- acoes ---
        acoes = QtWidgets.QHBoxLayout()
        self.btPrev = QtWidgets.QPushButton("Ver o que vai sair")
        self.btPrev.clicked.connect(self._prever)
        self.btExp = QtWidgets.QPushButton("Exportar")
        self.btExp.setMinimumHeight(32)
        self.btExp.clicked.connect(self._exportar)
        acoes.addWidget(self.btPrev)
        acoes.addWidget(self.btExp, 1)
        raiz.addLayout(acoes)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)
        raiz.addWidget(self.log, 1)

    # -- settings <-> widgets --------------------------------------------

    def _do_settings(self):
        s = self.s
        self.edDir.setText(s.target_dir)
        self.edNome.setText(s.asset_name)
        self.ckSel.setChecked(s.selection_only)
        self.ckPorObj.setChecked(s.one_asset_per_object)
        self.edLod.setText(s.lod_token)
        self.cbUp.setCurrentText(s.up_axis)
        self.cbUnid.setCurrentText(s.units)
        self.cbVer.setCurrentText(s.fbx_version)
        for nome, ck in self._campos.items():
            ck.setChecked(bool(getattr(s, nome)))
        self.ckTex.setChecked(s.collect_textures)
        self.ckRel.setChecked(s.write_report)

    def _para_settings(self):
        s = self.s
        s.target_dir = self.edDir.text().strip()
        s.asset_name = self.edNome.text().strip()
        s.selection_only = self.ckSel.isChecked()
        s.one_asset_per_object = self.ckPorObj.isChecked()
        s.lod_token = self.edLod.text().strip() or "High"
        s.up_axis = self.cbUp.currentText()
        s.units = self.cbUnid.currentText()
        s.fbx_version = self.cbVer.currentText()
        for nome, ck in self._campos.items():
            setattr(s, nome, ck.isChecked())
        s.collect_textures = self.ckTex.isChecked()
        s.write_report = self.ckRel.isChecked()
        return s

    # -- acoes -----------------------------------------------------------

    def _escolher_pasta(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Pasta destino", self.edDir.text() or os.path.expanduser("~"))
        if d:
            self.edDir.setText(d.replace("\\", "/"))

    def _diz(self, texto):
        self.log.appendPlainText(texto)
        print(texto)

    def _prever(self):
        """Mostra os caminhos ANTES de escrever qualquer coisa."""
        from .. import naming
        s = self._para_settings()
        problemas = s.problems()
        self.log.clear()
        if problemas:
            self._diz("\n".join(problemas))
            return
        try:
            from pymxs import runtime as rt
            if s.one_asset_per_object:
                alvos = exporter._top_level_nodes(s.selection_only)
                nomes = [naming.sanitize(str(o.name)) for o in alvos]
            else:
                nomes = [naming.sanitize(s.asset_name) if s.asset_name
                         else exporter.scene_asset_name()]
        except Exception as e:
            self._diz("nao consegui ler a cena: %s" % e)
            return
        if not nomes:
            self._diz("Nada selecionado.")
            return
        self._diz("vai escrever:")
        for n in nomes:
            arq = naming.geo_filename(n, lod=s.lod_token)
            self._diz("   %s/%s" % (naming.asset_dir(s.target_dir, n), arq))

    def _exportar(self):
        s = self._para_settings()
        self.log.clear()
        try:
            s.save()
        except Exception as e:
            self._diz("(nao consegui salvar as preferencias: %s)" % e)
        try:
            resultado = exporter.export(s)
        except Exception as e:
            self._diz("FALHOU: %s" % e)
            import traceback
            traceback.print_exc()
            return
        for linha in exporter.report_lines(resultado):
            self._diz(linha)


_janela = None


def show():
    """Abre a janela (uma so' por sessao do Max)."""
    global _janela
    if _janela is None:
        _janela = ExportWindow()
    _janela.show()
    _janela.raise_()
    _janela.activateWindow()
    return _janela
