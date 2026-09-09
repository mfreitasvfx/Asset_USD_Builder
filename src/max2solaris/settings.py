"""Opcoes do export, num objeto serializavel.

Separado da UI de proposito: o exportador nao importa PySide, e por isso da'
pra rodar o export inteiro pelo 3dsmaxbatch (sem interface) nos testes. A
janela so' le e escreve este objeto.

Os defaults sao os que fazem o FBX chegar certo no Solaris:
Y-up e centimetros. Os dois sao a causa mais comum de asset chegar deitado
ou 100x fora de escala no Houdini.
"""
import json
import os

# Onde as preferencias ficam entre sessoes do Max.
PREFS_PATH = os.path.join(
    os.path.expanduser("~"), ".max2solaris", "prefs.json")


class Settings(object):

    #: nome -> (default, rotulo na UI)
    FIELDS = [
        # destino ------------------------------------------------------
        ("target_dir", "", "Pasta destino"),
        ("asset_name", "", "Nome do asset (vazio = nome da cena)"),

        # o que exportar -----------------------------------------------
        ("selection_only", True, "Somente a selecao"),
        ("one_asset_per_object", False, "Um asset por objeto de topo"),
        ("lod_token", "High", "Token de LOD"),
        ("variant_style", "letter", "Estilo de variante (letter/number)"),

        # FBX ----------------------------------------------------------
        ("up_axis", "Y", "Eixo Up"),
        ("units", "cm", "Unidades"),
        ("smoothing_groups", True, "Smoothing groups"),
        ("tangents", True, "Tangentes e binormais"),
        ("preserve_instances", True, "Preservar instancias"),
        ("triangulate", False, "Triangular"),
        ("smooth_mesh", False, "Exportar subdivisao (TurboSmooth)"),
        ("animation", False, "Animacao"),
        ("cameras", False, "Cameras"),
        ("lights", False, "Luzes"),
        ("embed_textures", False, "Embutir texturas no FBX"),
        ("fbx_version", "FBX202000", "Versao do FBX"),
        ("ascii", False, "FBX em ASCII"),

        # extras (desligados por padrao -- v1 e' so' export) ------------
        ("collect_textures", False, "Copiar texturas para a pasta do asset"),
        ("write_report", True, "Escrever relatorio .json ao lado"),
    ]

    def __init__(self, **kw):
        for nome, default, _rotulo in self.FIELDS:
            setattr(self, nome, kw.get(nome, default))

    # -- serializacao ----------------------------------------------------

    def to_dict(self):
        return {nome: getattr(self, nome) for nome, _d, _r in self.FIELDS}

    @classmethod
    def from_dict(cls, data):
        return cls(**{k: v for k, v in (data or {}).items()
                      if k in {n for n, _d, _r in cls.FIELDS}})

    def save(self, path=None):
        path = path or PREFS_PATH
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=1, sort_keys=True)
        return path

    @classmethod
    def load(cls, path=None):
        path = path or PREFS_PATH
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return cls.from_dict(json.load(fh))
        except Exception:
            # preferencia corrompida ou inexistente nao pode impedir o uso
            return cls()

    # -- validacao -------------------------------------------------------

    def problems(self):
        """Lista de motivos para nao deixar exportar ainda."""
        out = []
        if not str(self.target_dir).strip():
            out.append("Escolha a pasta destino.")
        else:
            raiz = os.path.splitdrive(os.path.abspath(self.target_dir))[0]
            if raiz and not os.path.isdir(raiz + os.sep):
                out.append("O drive %s nao existe nesta maquina." % raiz)
        if self.up_axis not in ("Y", "Z"):
            out.append("Eixo Up deve ser Y ou Z.")
        return out

    def __repr__(self):
        return "Settings(%s)" % ", ".join(
            "%s=%r" % (n, getattr(self, n)) for n, _d, _r in self.FIELDS[:4])
