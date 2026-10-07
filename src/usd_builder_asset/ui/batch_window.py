"""Janela do lote: uma pasta de .max, a lista para marcar quais, um FBX por
arquivo. PySide6, como a janela principal.

Nao contem regra nenhuma: le a pasta com `batch.list_max_files`, monta a
lista e chama `batch.export_files`. As opcoes de FBX (eixo, unidades,
texturas...) sao as mesmas prefs da janela principal -- ajuste la'.
"""
import os

from PySide6 import QtCore, QtGui, QtWidgets

from ..settings import Settings
from .. import batch

TITULO = "usd_builder_asset  —  lote de .max para FBX"
THUMB = 128   # lado do thumbnail na lista


def _max_main_window():
    try:
        import qtmax
        return qtmax.GetQMaxMainWindow()
    except Exception:
        return None


class BatchWindow(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super(BatchWindow, self).__init__(parent or _max_main_window())
        self.setWindowFlag(QtCore.Qt.Window, True)
        self.setWindowTitle(TITULO)
        self.resize(760, 900)

        self.s = Settings.load()
        self._montar()
        self.edDest.setText(self.s.target_dir)
        if self.s.batch_source_dir:
            self.edOrigem.setText(self.s.batch_source_dir)
            self._listar()

    # -- construcao ------------------------------------------------------

    def _linha_pasta(self, edit, slot):
        linha = QtWidgets.QHBoxLayout()
        bt = QtWidgets.QPushButton("...")
        bt.setFixedWidth(34)
        bt.clicked.connect(slot)
        linha.addWidget(edit)
        linha.addWidget(bt)
        w = QtWidgets.QWidget()
        w.setLayout(linha)
        return w

    def _montar(self):
        raiz = QtWidgets.QVBoxLayout(self)

        # --- origem ---
        gOri = QtWidgets.QGroupBox("Arquivos .max")
        vOri = QtWidgets.QVBoxLayout(gOri)
        self.edOrigem = QtWidgets.QLineEdit()
        self.edOrigem.setPlaceholderText("pasta com os .max (um asset por arquivo)")
        self.edOrigem.editingFinished.connect(self._listar)
        vOri.addWidget(self._linha_pasta(self.edOrigem, self._escolher_origem))

        filtro = QtWidgets.QHBoxLayout()
        self.edFiltro = QtWidgets.QLineEdit()
        self.edFiltro.setPlaceholderText("filtrar pelo nome")
        self.edFiltro.setClearButtonEnabled(True)
        self.edFiltro.textChanged.connect(self._filtrar)
        filtro.addWidget(self.edFiltro, 1)
        for rotulo, slot in (("Todos", lambda: self._marcar(True)),
                             ("Nenhum", lambda: self._marcar(False)),
                             ("Inverter", self._inverter)):
            bt = QtWidgets.QPushButton(rotulo)
            bt.clicked.connect(slot)
            filtro.addWidget(bt)
        vOri.addLayout(filtro)

        self.lista = QtWidgets.QListWidget()
        self.lista.setIconSize(QtCore.QSize(THUMB, THUMB))
        self.lista.setUniformItemSizes(True)   # linhas da altura do thumb
        self.lista.setSpacing(2)
        self.lista.setAlternatingRowColors(True)
        self.lista.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.lista.itemChanged.connect(self._contar)
        self.lista.itemDoubleClicked.connect(
            lambda it: it.setCheckState(
                QtCore.Qt.Unchecked if it.checkState() == QtCore.Qt.Checked
                else QtCore.Qt.Checked))
        vOri.addWidget(self.lista, 1)

        self.lbContagem = QtWidgets.QLabel("")
        vOri.addWidget(self.lbContagem)
        raiz.addWidget(gOri, 1)

        # --- destino ---
        gDest = QtWidgets.QGroupBox("Destino")
        fDest = QtWidgets.QFormLayout(gDest)
        self.edDest = QtWidgets.QLineEdit()
        fDest.addRow("Pasta destino",
                     self._linha_pasta(self.edDest, self._escolher_destino))
        nota = QtWidgets.QLabel(
            "Cada .max vira <destino>/<nome do arquivo>/<nome>_%s.fbx. "
            "Eixo, unidades e texturas: as prefs da janela principal."
            % (self.s.lod_token or "High"))
        nota.setWordWrap(True)
        nota.setStyleSheet("color: gray")
        fDest.addRow(nota)
        raiz.addWidget(gDest)

        # --- acoes ---
        acoes = QtWidgets.QHBoxLayout()
        self.btPrev = QtWidgets.QPushButton("Ver o que vai sair")
        self.btPrev.clicked.connect(self._prever)
        self.btExp = QtWidgets.QPushButton("Exportar marcados")
        self.btExp.setMinimumHeight(32)
        self.btExp.clicked.connect(self._exportar)
        acoes.addWidget(self.btPrev)
        acoes.addWidget(self.btExp, 1)
        raiz.addLayout(acoes)

        self.barra = QtWidgets.QProgressBar()
        self.barra.setTextVisible(True)
        self.barra.setFormat("%v / %m")
        raiz.addWidget(self.barra)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(120)
        raiz.addWidget(self.log)

    # -- lista -----------------------------------------------------------

    def _listar(self):
        pasta = self.edOrigem.text().strip().replace("\\", "/")
        self.lista.blockSignals(True)
        self.lista.clear()
        for p in batch.list_max_files(pasta):
            it = QtWidgets.QListWidgetItem(os.path.basename(p))
            it.setData(QtCore.Qt.UserRole, p)
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Checked)
            prev = batch.preview_of(p)
            if prev:
                it.setIcon(QtGui.QIcon(prev))
                it.setToolTip(prev)
            self.lista.addItem(it)
        self.lista.blockSignals(False)
        self._filtrar(self.edFiltro.text())
        self._contar()

    def _itens(self, so_visiveis=False):
        for i in range(self.lista.count()):
            it = self.lista.item(i)
            if so_visiveis and it.isHidden():
                continue
            yield it

    def _marcados(self):
        return [it.data(QtCore.Qt.UserRole) for it in self._itens()
                if it.checkState() == QtCore.Qt.Checked]

    def _filtrar(self, texto):
        t = (texto or "").strip().lower()
        for it in self._itens():
            it.setHidden(bool(t) and t not in it.text().lower())

    def _marcar(self, ligado):
        # Todos/Nenhum agem so' no que o filtro deixa ver.
        self.lista.blockSignals(True)
        for it in self._itens(so_visiveis=True):
            it.setCheckState(QtCore.Qt.Checked if ligado else QtCore.Qt.Unchecked)
        self.lista.blockSignals(False)
        self._contar()

    def _inverter(self):
        self.lista.blockSignals(True)
        for it in self._itens(so_visiveis=True):
            it.setCheckState(QtCore.Qt.Unchecked
                             if it.checkState() == QtCore.Qt.Checked
                             else QtCore.Qt.Checked)
        self.lista.blockSignals(False)
        self._contar()

    def _contar(self, *_):
        n = len(self._marcados())
        self.lbContagem.setText("%d de %d marcado(s)" % (n, self.lista.count()))
        self.btExp.setEnabled(n > 0)

    # -- acoes -----------------------------------------------------------

    def _escolher_origem(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Pasta com os .max",
            self.edOrigem.text() or os.path.expanduser("~"))
        if d:
            self.edOrigem.setText(d.replace("\\", "/"))
            self._listar()

    def _escolher_destino(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Pasta destino", self.edDest.text() or os.path.expanduser("~"))
        if d:
            self.edDest.setText(d.replace("\\", "/"))

    def _diz(self, texto):
        self.log.appendPlainText(texto)
        print(texto)

    def _para_settings(self):
        s = self.s
        s.target_dir = self.edDest.text().strip()
        s.batch_source_dir = self.edOrigem.text().strip()
        return s

    def _prever(self):
        s = self._para_settings()
        self.log.clear()
        problemas = s.problems()
        if problemas:
            self._diz("\n".join(problemas))
            return
        marcados = self._marcados()
        if not marcados:
            self._diz("Nada marcado.")
            return
        self._diz("vai escrever %d arquivo(s):" % len(marcados))
        for p in marcados:
            self._diz("   " + batch.target_of(p, s))

    def _exportar(self):
        s = self._para_settings()
        self.log.clear()
        problemas = s.problems()
        if problemas:
            self._diz("\n".join(problemas))
            return
        marcados = self._marcados()
        if not marcados:
            self._diz("Nada marcado.")
            return

        # Abrir cada .max descarta a cena que esta' aberta agora.
        r = QtWidgets.QMessageBox.question(
            self, "Exportar lote",
            "Vai abrir %d arquivo(s) .max nesta sessao, um por vez.\n"
            "A cena aberta agora sera' descartada (sem salvar).\n\nContinuar?"
            % len(marcados))
        if r != QtWidgets.QMessageBox.Yes:
            return

        try:
            s.save()
        except Exception as e:
            self._diz("(nao consegui salvar as preferencias: %s)" % e)

        self.barra.setRange(0, len(marcados))
        self.barra.setValue(0)
        self.setEnabled(False)

        def progresso(i, total, p, item):
            self.barra.setValue(i)
            nome = os.path.basename(p)
            if item["ok"]:
                extra = ("  (%d aviso(s))" % len(item["avisos"])) if item["avisos"] else ""
                self._diz("ok   %s%s" % (nome, extra))
            else:
                self._diz("ERRO %s: %s" % (nome, item.get("erro")))
            QtWidgets.QApplication.processEvents()

        try:
            rel = batch.export_files(marcados, s, on_progress=progresso)
        except Exception as e:
            self._diz("FALHOU: %s" % e)
            import traceback
            traceback.print_exc()
            return
        finally:
            self.setEnabled(True)

        self._diz("")
        self._diz(batch.report_lines(rel)[0])
        self._diz(batch.report_lines(rel)[-1])
        if rel["falhas"]:
            self._diz("falhas: %d -- detalhes no relatorio" % len(rel["falhas"]))


_janela = None


def show():
    """Abre a janela (uma so' por sessao do Max)."""
    global _janela
    if _janela is None:
        _janela = BatchWindow()
    _janela.show()
    _janela.raise_()
    _janela.activateWindow()
    return _janela
