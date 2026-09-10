"""Log no estilo do Asset_USD_Builder: banners e checkmarks no console.

O pedido do Matheus: "printa o log no houdini igual ao usd asset builder".
Tudo vai para o stdout (o console/Python Shell do Houdini); a janela
espelha no widget dela por conta propria.
"""
import sys
import time


def diz(txt=""):
    print(txt)
    try:
        sys.stdout.flush()
    except Exception:
        pass


def banner(txt):
    diz("")
    diz("-" * 10 + " " + txt + " " + "-" * 10)


def titulo(txt):
    diz("")
    diz(txt + ":")
    diz("-" * (len(txt) + 1))


def check(txt, i=None, n=None):
    suf = ""
    if i is not None and n is not None:
        suf = " ........... %d/%d" % (i, n)
    diz("✓ " + txt + suf)


class Tempo(object):
    """Cronometro para o 'BuildTime: 00 hours 00 min 01 sec' do HDA."""

    def __init__(self):
        self.t0 = time.time()

    def build_time(self):
        s = int(time.time() - self.t0)
        return "BuildTime: %02d hours %02d min %02d sec" % (
            s // 3600, (s % 3600) // 60, s % 60)
