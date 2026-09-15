# -*- coding: utf-8 -*-
"""
MMA Chaveamento - App para organizar torneios de MMA entre amigos.
- Cadastro dos lutadores
- Sorteio / edição manual da ordem antes de gerar o chaveamento
- Chaveamento visual (mata-mata), com as fases se casando automaticamente
  conforme as lutas terminam
- Timer de round com som no início, aos 10s finais e no fim
- Pontuação por round com soma automática no final
- Encerramento antecipado da luta por Nocaute, Nocaute Técnico,
  Finalização (submissão) ou Decisão Médica
- Desempate: round extra ou decisão manual
- Geração automática de uma imagem de resultado (compartilhável) ao fim
  de cada luta e uma imagem final ao fim do torneio
"""

import os
import json
import random
import math
import wave
import struct

from kivy.app import App
from kivy.core.window import Window
from kivy.core.audio import SoundLoader
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.graphics import Color, RoundedRectangle, Line
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.uix.image import Image as KivyImage
from kivy.utils import platform

from PIL import Image as PilImage, ImageDraw, ImageFont

Window.clearcolor = (0.06, 0.06, 0.08, 1)

# ---------------------------------------------------------------------------
# Paleta de cores do app
# ---------------------------------------------------------------------------

COR_FUNDO = (0.06, 0.06, 0.08, 1)
COR_CARD = (0.12, 0.12, 0.16, 1)
COR_CARD_CLARO = (0.17, 0.17, 0.22, 1)
COR_PRIMARIA = (0.80, 0.14, 0.16, 1)      # vermelho
COR_PRIMARIA_ESCURA = (0.55, 0.08, 0.10, 1)
COR_SECUNDARIA = (0.14, 0.38, 0.78, 1)    # azul
COR_OURO = (0.86, 0.67, 0.13, 1)
COR_SUCESSO = (0.20, 0.66, 0.36, 1)
COR_NEUTRA = (0.30, 0.30, 0.36, 1)
COR_TEXTO = (0.94, 0.94, 0.96, 1)
COR_TEXTO_FRACO = (0.62, 0.62, 0.68, 1)


# ---------------------------------------------------------------------------
# Utilidades: geração de sons (beep) sem depender de arquivos externos
# ---------------------------------------------------------------------------

def gerar_beep(path, freq=880, duracao=0.35, volume=0.6, taxa=44100):
    if os.path.exists(path):
        return
    n = int(taxa * duracao)
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(taxa)
        frames = bytearray()
        for i in range(n):
            t = i / taxa
            fade = min(1.0, (n - i) / (taxa * 0.05))
            valor = int(volume * 32767 * math.sin(2 * math.pi * freq * t) * fade)
            frames += struct.pack("<h", valor)
        f.writeframesraw(bytes(frames))


def gerar_beep_triplo(path, freq=1200, duracao=0.15, intervalo=0.08, volume=0.7, taxa=44100):
    if os.path.exists(path):
        return
    n_beep = int(taxa * duracao)
    n_gap = int(taxa * intervalo)
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(taxa)
        frames = bytearray()
        for _ in range(3):
            for i in range(n_beep):
                t = i / taxa
                fade = min(1.0, (n_beep - i) / (taxa * 0.03))
                valor = int(volume * 32767 * math.sin(2 * math.pi * freq * t) * fade)
                frames += struct.pack("<h", valor)
            frames += b"\x00\x00" * n_gap
        f.writeframesraw(bytes(frames))


def pasta_base():
    try:
        app = App.get_running_app()
        return app.user_data_dir if app else "."
    except Exception:
        return "."


def pasta_sons():
    d = os.path.join(pasta_base(), "sons")
    os.makedirs(d, exist_ok=True)
    return d


def pasta_compartilhar():
    d = os.path.join(pasta_base(), "compartilhar")
    os.makedirs(d, exist_ok=True)
    return d


def preparar_sons():
    d = pasta_sons()
    inicio = os.path.join(d, "inicio.wav")
    aviso = os.path.join(d, "aviso.wav")
    fim = os.path.join(d, "fim.wav")
    gerar_beep(inicio, freq=700, duracao=0.4)
    gerar_beep(aviso, freq=1000, duracao=0.2)
    gerar_beep_triplo(fim, freq=1300, duracao=0.18, intervalo=0.1)
    return inicio, aviso, fim


# ---------------------------------------------------------------------------
# Mantém a tela ligada enquanto o app está em uso
# ---------------------------------------------------------------------------

def manter_tela_ligada(ligar=True):
    if platform != "android":
        return
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Params = autoclass("android.view.WindowManager$LayoutParams")
        activity = PythonActivity.mActivity

        def _run():
            if ligar:
                activity.getWindow().addFlags(Params.FLAG_KEEP_SCREEN_ON)
            else:
                activity.getWindow().clearFlags(Params.FLAG_KEEP_SCREEN_ON)

        activity.runOnUiThread(_run)
    except Exception as e:
        print("Aviso: não foi possível travar a tela ligada:", e)


# ---------------------------------------------------------------------------
# Persistência simples em JSON do torneio inteiro
# ---------------------------------------------------------------------------

def caminho_dados():
    return os.path.join(pasta_base(), "torneio.json")


def torneio_vazio():
    return {
        "nome": "Torneio MMA",
        "fighters": [],
        "bracket": None,
        "config": {"rounds": 3, "tempo_round": 300},
        "campeao": None,
    }


def carregar_torneio():
    p = caminho_dados()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                dados = json.load(f)
                base = torneio_vazio()
                base.update(dados)
                return base
        except Exception:
            return torneio_vazio()
    return torneio_vazio()


def salvar_torneio(torneio):
    p = caminho_dados()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(torneio, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Lógica do chaveamento (mata-mata)
# ---------------------------------------------------------------------------

def criar_luta(r, i, vermelho, azul, rounds_cfg, tempo_cfg):
    return {
        "id": f"r{r}_i{i}",
        "r": r,
        "i": i,
        "vermelho": vermelho,
        "azul": azul,
        "rounds": rounds_cfg,
        "tempo_round": tempo_cfg,
        "pontos": [],
        "vencedor": None,
        "metodo": None,
        "round_fim": None,
        "tempo_fim": None,
    }


def gerar_bracket(fighters, rounds_cfg, tempo_cfg):
    n = len(fighters)
    if n < 2:
        return None
    total = 1
    while total < n:
        total *= 2
    n_rounds = int(math.log2(total))

    # Distribui os "byes" (vagas vazias) uma por luta, para que nenhuma luta
    # fique com BYE dos dois lados (o que travaria aquele lado da chave).
    # Os primeiros lutadores da lista recebem passagem direta de round,
    # como em uma cabeça-de-chave.
    num_matches = total // 2
    num_byes = total - n
    restantes = list(fighters)
    pares = []
    for _ in range(num_byes):
        pares.append((restantes.pop(0), "BYE"))
    while restantes:
        v = restantes.pop(0)
        a = restantes.pop(0)
        pares.append((v, a))

    bracket = []
    primeira = []
    for k, (v, a) in enumerate(pares):
        primeira.append(criar_luta(0, k, v, a, rounds_cfg, tempo_cfg))
    bracket.append(primeira)

    n_lutas = total // 2
    for r in range(1, n_rounds):
        n_lutas //= 2
        bracket.append([criar_luta(r, k, None, None, rounds_cfg, tempo_cfg) for k in range(n_lutas)])

    torneio = {
        "nome": "Torneio MMA",
        "fighters": fighters,
        "bracket": bracket,
        "config": {"rounds": rounds_cfg, "tempo_round": tempo_cfg},
        "campeao": None,
    }
    processar_byes(torneio)
    return torneio


def buscar_luta(torneio, match_id):
    bracket = torneio.get("bracket") or []
    for rodada in bracket:
        for m in rodada:
            if m["id"] == match_id:
                return m
    return None


def propagar_resultado(torneio, r, i):
    bracket = torneio["bracket"]
    luta = bracket[r][i]
    if r + 1 >= len(bracket):
        torneio["campeao"] = luta["vencedor"]
        return
    prox = bracket[r + 1][i // 2]
    if i % 2 == 0:
        prox["vermelho"] = luta["vencedor"]
    else:
        prox["azul"] = luta["vencedor"]


def processar_byes(torneio):
    """Avança automaticamente qualquer luta em que um dos lados seja BYE."""
    mudou = True
    while mudou:
        mudou = False
        bracket = torneio["bracket"]
        for rodada in bracket:
            for m in rodada:
                if m["vencedor"] is not None:
                    continue
                v, a = m["vermelho"], m["azul"]
                if v == "BYE" and a and a != "BYE":
                    m["vencedor"] = a
                    m["metodo"] = "BYE"
                elif a == "BYE" and v and v != "BYE":
                    m["vencedor"] = v
                    m["metodo"] = "BYE"
                else:
                    continue
                propagar_resultado(torneio, m["r"], m["i"])
                mudou = True


def torneio_finalizado(torneio):
    return bool(torneio.get("campeao"))


# ---------------------------------------------------------------------------
# Geração de imagens de resultado (compartilháveis) com Pillow
# ---------------------------------------------------------------------------

def _fonte(tamanho, negrito=False):
    candidatos_negrito = [
        "/system/fonts/Roboto-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    candidatos_normal = [
        "/system/fonts/Roboto-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for c in (candidatos_negrito if negrito else candidatos_normal):
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, tamanho)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=tamanho)
    except Exception:
        return ImageFont.load_default()


def gerar_imagem_resultado(luta, nome_torneio, caminho_saida):
    W, H = 960, 680
    img = PilImage.new("RGB", (W, H), (16, 16, 20))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W, 12], fill=(196, 30, 30))
    draw.rectangle([0, H - 12, W, H], fill=(196, 30, 30))

    f_titulo = _fonte(34, True)
    f_sub = _fonte(20)
    f_nomes = _fonte(36, True)
    f_vs = _fonte(22)
    f_venc = _fonte(38, True)
    f_info = _fonte(24)
    f_linha = _fonte(20)
    f_rodape = _fonte(15)

    draw.text((W / 2, 55), nome_torneio.upper(), font=f_titulo, fill=(235, 235, 235), anchor="mm")
    draw.text((W / 2, 95), "RESULTADO DA LUTA", font=f_sub, fill=(170, 170, 180), anchor="mm")

    vermelho, azul = luta["vermelho"], luta["azul"]
    vencedor = luta.get("vencedor") or "-"
    cor_v = (255, 210, 40) if vencedor == vermelho else (225, 225, 230)
    cor_a = (255, 210, 40) if vencedor == azul else (225, 225, 230)

    draw.text((W * 0.27, 220), vermelho, font=f_nomes, fill=cor_v, anchor="mm")
    draw.text((W * 0.5, 220), "VS", font=f_vs, fill=(140, 140, 150), anchor="mm")
    draw.text((W * 0.73, 220), azul, font=f_nomes, fill=cor_a, anchor="mm")

    draw.line([(W * 0.15, 270), (W * 0.85, 270)], fill=(70, 70, 78), width=2)

    draw.text((W / 2, 320), "VENCEDOR", font=f_sub, fill=(150, 150, 160), anchor="mm")
    draw.text((W / 2, 365), vencedor, font=f_venc, fill=(255, 210, 40), anchor="mm")

    metodo = luta.get("metodo") or "Decisão"
    y = 430
    draw.text((W / 2, y), f"Método: {metodo}", font=f_info, fill=(215, 215, 220), anchor="mm")
    y += 36
    if luta.get("round_fim"):
        extra = f"Round: {luta['round_fim']}"
        if luta.get("tempo_fim"):
            extra += f"   Tempo: {luta['tempo_fim']}"
        draw.text((W / 2, y), extra, font=f_info, fill=(215, 215, 220), anchor="mm")
        y += 36

    pontos = luta.get("pontos") or []
    if pontos:
        y += 10
        draw.text((W / 2, y), "Placar por round", font=f_info, fill=(190, 190, 200), anchor="mm")
        y += 30
        tv = ta = 0
        for idx, (pv, pa) in enumerate(pontos, start=1):
            draw.text((W / 2, y), f"Round {idx}: {pv}  x  {pa}", font=f_linha, fill=(185, 185, 195), anchor="mm")
            tv += pv
            ta += pa
            y += 26
        draw.text((W / 2, y + 8), f"TOTAL: {tv}  x  {ta}", font=f_info, fill=(230, 230, 235), anchor="mm")

    draw.text((W / 2, H - 32), "Gerado pelo app MMA Chaveamento", font=f_rodape, fill=(115, 115, 125), anchor="mm")

    img.save(caminho_saida, "PNG")
    return caminho_saida


def gerar_imagem_campeao(torneio, caminho_saida):
    bracket = torneio.get("bracket") or []
    W = 960
    linhas_totais = sum(len(r) for r in bracket) + len(bracket)
    H = 420 + linhas_totais * 30
    img = PilImage.new("RGB", (W, H), (16, 16, 20))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W, 12], fill=(196, 30, 30))
    draw.rectangle([0, H - 12, W, H], fill=(196, 30, 30))

    f_titulo = _fonte(32, True)
    f_campeao_label = _fonte(22)
    f_campeao = _fonte(52, True)
    f_secao = _fonte(22, True)
    f_linha = _fonte(19)
    f_rodape = _fonte(15)

    nome = torneio.get("nome", "Torneio MMA")
    draw.text((W / 2, 55), nome.upper(), font=f_titulo, fill=(235, 235, 235), anchor="mm")
    draw.text((W / 2, 95), "TORNEIO FINALIZADO", font=f_campeao_label, fill=(170, 170, 180), anchor="mm")

    draw.text((W / 2, 160), "CAMPEÃO", font=f_campeao_label, fill=(150, 150, 160), anchor="mm")
    draw.text((W / 2, 220), torneio.get("campeao", "-"), font=f_campeao, fill=(255, 210, 40), anchor="mm")

    draw.line([(W * 0.1, 270), (W * 0.9, 270)], fill=(70, 70, 78), width=2)

    y = 310
    for idx, rodada in enumerate(bracket, start=1):
        titulo_rodada = f"Final" if idx == len(bracket) else (
            "Semifinal" if idx == len(bracket) - 1 else f"Fase {idx}")
        draw.text((W * 0.08, y), titulo_rodada, font=f_secao, fill=(220, 220, 225), anchor="lm")
        y += 30
        for m in rodada:
            v = m.get("vermelho") or "-"
            a = m.get("azul") or "-"
            venc = m.get("vencedor")
            metodo = m.get("metodo") or ""
            if venc:
                texto = f'{v}  vs  {a}   →   {venc}  ({metodo})'
            else:
                texto = f'{v}  vs  {a}   →   pendente'
            draw.text((W * 0.1, y), texto, font=f_linha, fill=(195, 195, 205), anchor="lm")
            y += 27
        y += 14

    draw.text((W / 2, H - 32), "Gerado pelo app MMA Chaveamento", font=f_rodape, fill=(115, 115, 125), anchor="mm")

    img.save(caminho_saida, "PNG")
    return caminho_saida


# ---------------------------------------------------------------------------
# Compartilhamento / salvamento de imagens
# ---------------------------------------------------------------------------

def salvar_copia_publica(caminho_origem):
    if platform == "android":
        destinos = ["/sdcard/Pictures", "/sdcard/Download", "/sdcard/DCIM"]
    else:
        destinos = [
            os.path.join(os.path.expanduser("~"), "Pictures"),
            os.path.join(os.path.expanduser("~"), "Downloads"),
        ]
    for d in destinos:
        try:
            if not os.path.isdir(d):
                continue
            destino = os.path.join(d, os.path.basename(caminho_origem))
            with open(caminho_origem, "rb") as fo, open(destino, "wb") as fd:
                fd.write(fo.read())
            return destino
        except Exception:
            continue
    return None


def compartilhar_arquivo(caminho, titulo="Compartilhar resultado"):
    try:
        from plyer import share
        share.share(title=titulo, text=titulo, filepath=caminho, mimetype="image/png")
        return True
    except Exception as e:
        print("Compartilhamento indisponível:", e)
        return False


# ---------------------------------------------------------------------------
# Widgets visuais reutilizáveis (tema "mais bonito")
# ---------------------------------------------------------------------------

class Cartao(BoxLayout):
    """Painel com cantos arredondados usado como fundo de seções."""

    def __init__(self, cor=COR_CARD, radius=16, **kwargs):
        super().__init__(**kwargs)
        self._cor = cor
        with self.canvas.before:
            Color(*cor)
            self._rect = RoundedRectangle(radius=[radius], pos=self.pos, size=self.size)
        self.bind(pos=self._atualizar, size=self._atualizar)

    def _atualizar(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


class BotaoP(Button):
    """Botão com cantos arredondados e cor customizável."""

    def __init__(self, cor=COR_PRIMARIA, cor_texto=COR_TEXTO, radius=14, **kwargs):
        kwargs.setdefault("font_size", "17sp")
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.color = cor_texto
        self.bold = True
        self._cor = cor
        with self.canvas.before:
            self._grupo_cor = Color(*cor)
            self._rect = RoundedRectangle(radius=[radius], pos=self.pos, size=self.size)
        self.bind(pos=self._atualizar, size=self._atualizar)

    def _atualizar(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def set_cor(self, cor):
        self._grupo_cor.rgba = cor


def botao(texto, cor=COR_PRIMARIA, **kwargs):
    return BotaoP(text=texto, cor=cor, **kwargs)


def titulo_tela(texto):
    lbl = Label(text=texto, font_size="24sp", bold=True, size_hint_y=None, height=dp(48),
                color=COR_TEXTO)
    return lbl


def mostrar_popup_simples(titulo, msg, altura=0.35):
    conteudo = BoxLayout(orientation="vertical", padding=16, spacing=12)
    conteudo.add_widget(Label(text=msg, color=COR_TEXTO))
    popup = Popup(title=titulo, content=conteudo, size_hint=(0.85, altura))
    btn = botao("OK", size_hint_y=None, height=dp(44))
    btn.bind(on_release=lambda *_: popup.dismiss())
    conteudo.add_widget(btn)
    popup.open()
    return popup


class LinhaLutadorCadastro(BoxLayout):
    def __init__(self, nome, on_remove=None, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(52),
                          spacing=8, padding=[10, 6], **kwargs)
        with self.canvas.before:
            Color(*COR_CARD_CLARO)
            self._rect = RoundedRectangle(radius=[10], pos=self.pos, size=self.size)
        self.bind(pos=self._att, size=self._att)

        lbl = Label(text=nome, color=COR_TEXTO, halign="left", valign="middle")
        lbl.bind(size=lbl.setter("text_size"))
        self.add_widget(lbl)

        if on_remove:
            btn = botao("X", cor=COR_PRIMARIA_ESCURA, size_hint_x=0.18)
            btn.bind(on_release=lambda *_: on_remove(nome))
            self.add_widget(btn)

    def _att(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


class LinhaLutadorOrdem(BoxLayout):
    def __init__(self, indice, nome, on_subir=None, on_descer=None, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(52),
                          spacing=6, padding=[10, 6], **kwargs)
        with self.canvas.before:
            Color(*COR_CARD_CLARO)
            self._rect = RoundedRectangle(radius=[10], pos=self.pos, size=self.size)
        self.bind(pos=self._att, size=self._att)

        lbl = Label(text=f"{indice}. {nome}", color=COR_TEXTO, halign="left", valign="middle")
        lbl.bind(size=lbl.setter("text_size"))
        self.add_widget(lbl)

        btn_up = botao("▲", cor=COR_SECUNDARIA, size_hint_x=0.16)
        btn_up.bind(on_release=lambda *_: on_subir(indice - 1))
        self.add_widget(btn_up)

        btn_down = botao("▼", cor=COR_SECUNDARIA, size_hint_x=0.16)
        btn_down.bind(on_release=lambda *_: on_descer(indice - 1))
        self.add_widget(btn_down)

    def _att(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


# ---------------------------------------------------------------------------
# Widget do chaveamento visual (desenha as caixas e conexões)
# ---------------------------------------------------------------------------

class ChaveamentoWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.on_toque_luta = None
        self._areas = []

    def montar(self, torneio):
        self.canvas.clear()
        self.clear_widgets()
        self._areas = []

        bracket = torneio.get("bracket") if torneio else None
        if not bracket:
            self.size = (dp(10), dp(10))
            return

        box_w = dp(168)
        box_h = dp(60)
        gap_x = dp(64)
        base_gap_y = dp(22)
        margem = dp(24)

        n0 = len(bracket[0])
        passo0 = box_h + base_gap_y
        ys = [[i * passo0 for i in range(n0)]]
        for r in range(1, len(bracket)):
            anterior = ys[r - 1]
            ys.append([(anterior[2 * i] + anterior[2 * i + 1]) / 2.0
                       for i in range(len(bracket[r]))])

        altura_total = ys[0][-1] + box_h + margem * 2 if n0 > 1 else box_h + margem * 2
        largura_total = len(bracket) * box_w + (len(bracket) - 1) * gap_x + margem * 2
        self.size = (largura_total, altura_total)

        cor_borda = (0.34, 0.34, 0.40, 1)
        cor_linha = (0.45, 0.45, 0.52, 1)

        caixas = []
        for r, rodada in enumerate(bracket):
            x = margem + r * (box_w + gap_x)
            for i, m in enumerate(rodada):
                y_centro = altura_total - margem - ys[r][i]
                y = y_centro - box_h / 2.0
                caixas.append((r, i, m, x, y))

        with self.canvas:
            # linhas de conexão primeiro (para ficarem atrás das caixas)
            Color(*cor_linha)
            for r, i, m, x, y in caixas:
                if r >= len(bracket) - 1:
                    continue
                if i % 2 != 0:
                    continue
                par = next((c for c in caixas if c[0] == r and c[1] == i + 1), None)
                if not par:
                    continue
                _, _, _, _, y2 = par
                my1 = y + box_h / 2.0
                my2 = y2 + box_h / 2.0
                midx = x + box_w + gap_x / 2.0
                prox = next((c for c in caixas if c[0] == r + 1 and c[1] == i // 2), None)
                if not prox:
                    continue
                _, _, _, xn, yn = prox
                myn = yn + box_h / 2.0
                Line(points=[x + box_w, my1, midx, my1], width=dp(1.6))
                Line(points=[x + box_w, my2, midx, my2], width=dp(1.6))
                Line(points=[midx, my1, midx, my2], width=dp(1.6))
                Line(points=[midx, myn, xn, myn], width=dp(1.6))

            for r, i, m, x, y in caixas:
                venc = m.get("vencedor")
                if venc:
                    cor_fundo = (0.10, 0.22, 0.14, 1)
                elif m.get("vermelho") and m.get("azul"):
                    cor_fundo = COR_CARD_CLARO
                else:
                    cor_fundo = (0.09, 0.09, 0.11, 1)
                Color(*cor_fundo)
                RoundedRectangle(pos=(x, y), size=(box_w, box_h), radius=[10])
                Color(*cor_borda)
                Line(rounded_rectangle=(x, y, box_w, box_h, 10), width=dp(1.1))

        for r, i, m, x, y in caixas:
            self._areas.append((x, y, box_w, box_h, m))
            v_nome = m.get("vermelho") or "-"
            a_nome = m.get("azul") or "-"
            venc = m.get("vencedor")
            cor_v = COR_OURO if venc and venc == v_nome else COR_TEXTO
            cor_a = COR_OURO if venc and venc == a_nome else COR_TEXTO
            if venc == v_nome:
                v_nome = "🏆 " + v_nome
            if venc == a_nome:
                a_nome = "🏆 " + a_nome

            lbl_v = Label(text=v_nome, font_size="13sp", bold=(venc == m.get("vermelho")),
                          color=cor_v, size_hint=(None, None),
                          size=(box_w - dp(10), box_h / 2.0),
                          pos=(x + dp(5), y + box_h / 2.0),
                          halign="left", valign="middle", shorten=True)
            lbl_v.bind(size=lbl_v.setter("text_size"))
            self.add_widget(lbl_v)

            lbl_a = Label(text=a_nome, font_size="13sp", bold=(venc == m.get("azul")),
                          color=cor_a, size_hint=(None, None),
                          size=(box_w - dp(10), box_h / 2.0),
                          pos=(x + dp(5), y),
                          halign="left", valign="middle", shorten=True)
            lbl_a.bind(size=lbl_a.setter("text_size"))
            self.add_widget(lbl_a)

    def on_touch_down(self, touch):
        # touch.pos já chega no sistema de coordenadas local do conteúdo
        # (o ScrollView faz esse ajuste antes de despachar o toque para os
        # filhos), então comparamos direto com as áreas calculadas em montar().
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        tx, ty = touch.x, touch.y
        for (x, y, w, h, m) in self._areas:
            if x <= tx <= x + w and y <= ty <= y + h:
                if self.on_toque_luta:
                    self.on_toque_luta(m)
                return True
        return super().on_touch_down(touch)


# ---------------------------------------------------------------------------
# Tela: Menu
# ---------------------------------------------------------------------------

class MenuScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*COR_FUNDO)
            self._fundo = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._att_fundo, size=self._att_fundo)

        raiz = BoxLayout(orientation="vertical", padding=28, spacing=14)
        raiz.add_widget(Label(text="🥊 MMA Chaveamento", font_size="30sp", bold=True,
                               size_hint_y=0.22, color=COR_TEXTO))
        raiz.add_widget(Label(text="Organize seu torneio entre amigos", font_size="15sp",
                               size_hint_y=0.10, color=COR_TEXTO_FRACO))

        b1 = botao("Cadastrar Lutadores", cor=COR_PRIMARIA, size_hint_y=None, height=dp(54))
        b1.bind(on_release=lambda *_: setattr(self.manager, "current", "cadastro"))
        raiz.add_widget(b1)

        b2 = botao("Ordem / Sortear", cor=COR_SECUNDARIA, size_hint_y=None, height=dp(54))
        b2.bind(on_release=lambda *_: setattr(self.manager, "current", "ordem"))
        raiz.add_widget(b2)

        b3 = botao("Ver Chaveamento", cor=(0.22, 0.55, 0.42, 1), size_hint_y=None, height=dp(54))
        b3.bind(on_release=self.abrir_chaveamento)
        raiz.add_widget(b3)

        raiz.add_widget(BoxLayout(size_hint_y=0.06))

        b4 = botao("Novo Torneio (apagar tudo)", cor=COR_PRIMARIA_ESCURA,
                   size_hint_y=None, height=dp(46))
        b4.bind(on_release=self.apagar_tudo)
        raiz.add_widget(b4)

        raiz.add_widget(BoxLayout())
        self.add_widget(raiz)

    def _att_fundo(self, *_):
        self._fundo.pos = self.pos
        self._fundo.size = self.size

    def abrir_chaveamento(self, *_):
        app = App.get_running_app()
        if not app.torneio.get("bracket"):
            mostrar_popup_simples("Chaveamento ainda não gerado",
                                   "Cadastre os lutadores e gere o chaveamento na tela "
                                   "'Ordem / Sortear' antes de visualizá-lo.")
            return
        self.manager.current = "chaveamento"

    def apagar_tudo(self, *_):
        conteudo = BoxLayout(orientation="vertical", padding=16, spacing=12)
        conteudo.add_widget(Label(text="Isso vai apagar todos os lutadores e o chaveamento "
                                        "atual. Tem certeza?", color=COR_TEXTO))
        linha = BoxLayout(size_hint_y=None, height=dp(48), spacing=10)
        popup = Popup(title="Confirmar", content=conteudo, size_hint=(0.85, 0.4))

        def confirmar(*_):
            app = App.get_running_app()
            app.torneio = torneio_vazio()
            salvar_torneio(app.torneio)
            popup.dismiss()
            mostrar_popup_simples("Tudo apagado", "O torneio foi reiniciado.")

        btn_sim = botao("Sim, apagar", cor=COR_PRIMARIA)
        btn_sim.bind(on_release=confirmar)
        btn_nao = botao("Cancelar", cor=COR_NEUTRA)
        btn_nao.bind(on_release=lambda *_: popup.dismiss())
        linha.add_widget(btn_nao)
        linha.add_widget(btn_sim)
        conteudo.add_widget(linha)
        popup.open()


# ---------------------------------------------------------------------------
# Tela: Cadastro de lutadores
# ---------------------------------------------------------------------------

class CadastroScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*COR_FUNDO)
            self._fundo = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._att_fundo, size=self._att_fundo)

        raiz = BoxLayout(orientation="vertical", padding=16, spacing=10)
        raiz.add_widget(titulo_tela("Cadastrar Lutadores"))

        cartao_cfg = Cartao(orientation="vertical", size_hint_y=None, height=dp(120),
                             padding=12, spacing=6)
        cartao_cfg.add_widget(Label(text="Configuração padrão das lutas", bold=True,
                                     size_hint_y=None, height=dp(24), color=COR_TEXTO))
        grid_cfg = GridLayout(cols=2, spacing=8, size_hint_y=None, height=dp(76))
        self.txt_rounds = TextInput(hint_text="Rounds (ex: 3)", multiline=False,
                                     input_filter="int", text="3")
        self.txt_minutos = TextInput(hint_text="Min./round (ex: 5)", multiline=False,
                                      input_filter="int", text="5")
        grid_cfg.add_widget(Label(text="Rounds:", color=COR_TEXTO_FRACO))
        grid_cfg.add_widget(self.txt_rounds)
        grid_cfg.add_widget(Label(text="Min./round:", color=COR_TEXTO_FRACO))
        grid_cfg.add_widget(self.txt_minutos)
        cartao_cfg.add_widget(grid_cfg)
        raiz.add_widget(cartao_cfg)

        linha_add = BoxLayout(size_hint_y=None, height=dp(48), spacing=8)
        self.txt_nome = TextInput(hint_text="Nome do lutador", multiline=False)
        btn_add = botao("Adicionar", cor=COR_PRIMARIA, size_hint_x=0.4)
        btn_add.bind(on_release=self.adicionar)
        self.txt_nome.bind(on_text_validate=self.adicionar)
        linha_add.add_widget(self.txt_nome)
        linha_add.add_widget(btn_add)
        raiz.add_widget(linha_add)

        raiz.add_widget(Label(text="Lutadores cadastrados:", size_hint_y=None, height=dp(26),
                               color=COR_TEXTO_FRACO))

        self.scroll = ScrollView()
        self.lista_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6)
        self.lista_box.bind(minimum_height=self.lista_box.setter("height"))
        self.scroll.add_widget(self.lista_box)
        raiz.add_widget(self.scroll)

        btn_voltar = botao("Voltar ao Menu", cor=COR_NEUTRA, size_hint_y=None, height=dp(48))
        btn_voltar.bind(on_release=lambda *_: setattr(self.manager, "current", "menu"))
        raiz.add_widget(btn_voltar)

        self.add_widget(raiz)

    def _att_fundo(self, *_):
        self._fundo.pos = self.pos
        self._fundo.size = self.size

    def on_pre_enter(self):
        app = App.get_running_app()
        cfg = app.torneio.get("config", {"rounds": 3, "tempo_round": 300})
        self.txt_rounds.text = str(cfg.get("rounds", 3))
        self.txt_minutos.text = str(cfg.get("tempo_round", 300) // 60)
        self.atualizar_lista()

    def adicionar(self, *_):
        app = App.get_running_app()
        if app.torneio.get("bracket"):
            mostrar_popup_simples("Chaveamento já gerado",
                                   "Para adicionar lutadores, gere um novo torneio primeiro "
                                   "(Menu > Novo Torneio).")
            return
        nome = self.txt_nome.text.strip()
        if not nome:
            return
        if nome in app.torneio["fighters"]:
            mostrar_popup_simples("Nome repetido", "Esse lutador já foi cadastrado.")
            return
        app.torneio["fighters"].append(nome)
        salvar_torneio(app.torneio)
        self.txt_nome.text = ""
        self.atualizar_lista()

    def remover(self, nome):
        app = App.get_running_app()
        app.torneio["fighters"] = [n for n in app.torneio["fighters"] if n != nome]
        salvar_torneio(app.torneio)
        self.atualizar_lista()

    def atualizar_lista(self):
        app = App.get_running_app()
        self.lista_box.clear_widgets()
        for nome in app.torneio["fighters"]:
            self.lista_box.add_widget(LinhaLutadorCadastro(nome, on_remove=self.remover))


# ---------------------------------------------------------------------------
# Tela: Ordem / Sorteio -> gerar chaveamento
# ---------------------------------------------------------------------------

class OrdemScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*COR_FUNDO)
            self._fundo = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._att_fundo, size=self._att_fundo)

        raiz = BoxLayout(orientation="vertical", padding=16, spacing=10)
        raiz.add_widget(titulo_tela("Ordem dos Lutadores"))
        raiz.add_widget(Label(text="Sorteie ou use as setas para reorganizar antes de gerar "
                                    "o chaveamento.", font_size="13sp", size_hint_y=None,
                               height=dp(36), color=COR_TEXTO_FRACO))

        self.scroll = ScrollView()
        self.lista_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6)
        self.lista_box.bind(minimum_height=self.lista_box.setter("height"))
        self.scroll.add_widget(self.lista_box)
        raiz.add_widget(self.scroll)

        linha1 = BoxLayout(size_hint_y=None, height=dp(50), spacing=8)
        btn_sortear = botao("🎲 Sortear Ordem", cor=COR_SECUNDARIA)
        btn_sortear.bind(on_release=self.sortear)
        linha1.add_widget(btn_sortear)
        raiz.add_widget(linha1)

        btn_gerar = botao("Gerar Chaveamento", cor=COR_SUCESSO, size_hint_y=None, height=dp(54))
        btn_gerar.bind(on_release=self.gerar_chaveamento)
        raiz.add_widget(btn_gerar)

        btn_voltar = botao("Voltar ao Menu", cor=COR_NEUTRA, size_hint_y=None, height=dp(46))
        btn_voltar.bind(on_release=lambda *_: setattr(self.manager, "current", "menu"))
        raiz.add_widget(btn_voltar)

        self.add_widget(raiz)

    def _att_fundo(self, *_):
        self._fundo.pos = self.pos
        self._fundo.size = self.size

    def on_pre_enter(self):
        self.atualizar_lista()

    def atualizar_lista(self):
        app = App.get_running_app()
        self.lista_box.clear_widgets()
        fighters = app.torneio["fighters"]
        if not fighters:
            self.lista_box.add_widget(Label(text="Cadastre lutadores primeiro.",
                                             size_hint_y=None, height=dp(48),
                                             color=COR_TEXTO_FRACO))
            return
        for idx, nome in enumerate(fighters, start=1):
            self.lista_box.add_widget(
                LinhaLutadorOrdem(idx, nome, on_subir=self.mover_cima, on_descer=self.mover_baixo))

    def mover_cima(self, idx):
        app = App.get_running_app()
        f = app.torneio["fighters"]
        if idx <= 0:
            return
        f[idx - 1], f[idx] = f[idx], f[idx - 1]
        salvar_torneio(app.torneio)
        self.atualizar_lista()

    def mover_baixo(self, idx):
        app = App.get_running_app()
        f = app.torneio["fighters"]
        if idx >= len(f) - 1:
            return
        f[idx + 1], f[idx] = f[idx], f[idx + 1]
        salvar_torneio(app.torneio)
        self.atualizar_lista()

    def sortear(self, *_):
        app = App.get_running_app()
        random.shuffle(app.torneio["fighters"])
        salvar_torneio(app.torneio)
        self.atualizar_lista()

    def gerar_chaveamento(self, *_):
        app = App.get_running_app()
        fighters = app.torneio["fighters"]
        if len(fighters) < 2:
            mostrar_popup_simples("Lutadores insuficientes",
                                   "Cadastre pelo menos 2 lutadores.")
            return

        def _gerar():
            tela_cadastro = self.manager.get_screen("cadastro")
            try:
                rounds_cfg = max(1, int(tela_cadastro.txt_rounds.text or "3"))
            except ValueError:
                rounds_cfg = 3
            try:
                minutos_cfg = max(1, int(tela_cadastro.txt_minutos.text or "5"))
            except ValueError:
                minutos_cfg = 5
            nome_torneio = app.torneio.get("nome", "Torneio MMA")
            novo = gerar_bracket(fighters, rounds_cfg, minutos_cfg * 60)
            novo["nome"] = nome_torneio
            app.torneio = novo
            salvar_torneio(app.torneio)
            self.manager.current = "chaveamento"

        if app.torneio.get("bracket"):
            conteudo = BoxLayout(orientation="vertical", padding=16, spacing=12)
            conteudo.add_widget(Label(text="Já existe um chaveamento em andamento. Gerar um "
                                            "novo vai apagar o progresso atual. Continuar?",
                                       color=COR_TEXTO))
            linha = BoxLayout(size_hint_y=None, height=dp(48), spacing=10)
            popup = Popup(title="Confirmar", content=conteudo, size_hint=(0.85, 0.4))

            def confirmar(*_):
                popup.dismiss()
                _gerar()

            btn_sim = botao("Sim, gerar", cor=COR_PRIMARIA)
            btn_sim.bind(on_release=confirmar)
            btn_nao = botao("Cancelar", cor=COR_NEUTRA)
            btn_nao.bind(on_release=lambda *_: popup.dismiss())
            linha.add_widget(btn_nao)
            linha.add_widget(btn_sim)
            conteudo.add_widget(linha)
            popup.open()
        else:
            _gerar()


# ---------------------------------------------------------------------------
# Tela: Chaveamento visual
# ---------------------------------------------------------------------------

class ChaveamentoScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*COR_FUNDO)
            self._fundo = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._att_fundo, size=self._att_fundo)

        raiz = BoxLayout(orientation="vertical", padding=12, spacing=8)
        raiz.add_widget(titulo_tela("Chaveamento"))

        self.lbl_campeao = Label(text="", font_size="16sp", bold=True, size_hint_y=None,
                                  height=dp(0), color=COR_OURO)
        raiz.add_widget(self.lbl_campeao)

        raiz.add_widget(Label(text="Toque numa luta pronta para iniciar. Arraste para navegar.",
                               font_size="12sp", size_hint_y=None, height=dp(26),
                               color=COR_TEXTO_FRACO))

        self.scroll = ScrollView(do_scroll_x=True, do_scroll_y=True, bar_width=dp(6))
        self.widget_chave = ChaveamentoWidget()
        self.widget_chave.on_toque_luta = self.tocar_luta
        self.scroll.add_widget(self.widget_chave)
        raiz.add_widget(self.scroll)

        linha_btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=8)
        btn_final = botao("🏆 Resultado Final", cor=COR_OURO)
        btn_final.bind(on_release=self.ver_resultado_final)
        linha_btns.add_widget(btn_final)
        btn_voltar = botao("Voltar", cor=COR_NEUTRA, size_hint_x=0.5)
        btn_voltar.bind(on_release=lambda *_: setattr(self.manager, "current", "menu"))
        linha_btns.add_widget(btn_voltar)
        raiz.add_widget(linha_btns)

        self.add_widget(raiz)

    def _att_fundo(self, *_):
        self._fundo.pos = self.pos
        self._fundo.size = self.size

    def on_pre_enter(self):
        self.atualizar()

    def atualizar(self):
        app = App.get_running_app()
        self.widget_chave.montar(app.torneio)
        campeao = app.torneio.get("campeao")
        if campeao:
            self.lbl_campeao.text = f"🏆 Campeão: {campeao}"
            self.lbl_campeao.height = dp(30)
        else:
            self.lbl_campeao.text = ""
            self.lbl_campeao.height = 0

    def tocar_luta(self, luta):
        v, a = luta.get("vermelho"), luta.get("azul")
        if luta.get("vencedor"):
            self.mostrar_info_luta(luta)
            return
        if not v or not a or v == "BYE" or a == "BYE":
            mostrar_popup_simples("Aguardando", "Essa luta ainda depende de resultados "
                                                 "anteriores.")
            return
        tela_luta = self.manager.get_screen("luta")
        tela_luta.carregar_luta(luta["id"])
        self.manager.current = "luta"

    def mostrar_info_luta(self, luta):
        conteudo = BoxLayout(orientation="vertical", padding=14, spacing=8)
        texto = (f'{luta["vermelho"]}  x  {luta["azul"]}\n'
                 f'Vencedor: {luta.get("vencedor")}\n'
                 f'Método: {luta.get("metodo") or "-"}')
        conteudo.add_widget(Label(text=texto, color=COR_TEXTO))
        popup = Popup(title="Resultado da luta", content=conteudo, size_hint=(0.85, 0.4))
        btn = botao("Fechar", cor=COR_NEUTRA, size_hint_y=None, height=dp(44))
        btn.bind(on_release=lambda *_: popup.dismiss())
        conteudo.add_widget(btn)
        popup.open()

    def ver_resultado_final(self, *_):
        app = App.get_running_app()
        if not torneio_finalizado(app.torneio):
            mostrar_popup_simples("Torneio em andamento", "O torneio ainda não terminou.")
            return
        try:
            caminho = os.path.join(pasta_compartilhar(), "campeao_final.png")
            gerar_imagem_campeao(app.torneio, caminho)
        except Exception as e:
            mostrar_popup_simples("Erro", f"Não foi possível gerar a imagem final:\n{e}")
            return
        mostrar_popup_imagem(f'🏆 Campeão: {app.torneio.get("campeao")}', caminho,
                              titulo_compartilhar="Resultado final do torneio")


def mostrar_popup_imagem(titulo, caminho_imagem, titulo_compartilhar="Compartilhar"):
    conteudo = BoxLayout(orientation="vertical", padding=10, spacing=10)
    conteudo.add_widget(Label(text=titulo, bold=True, size_hint_y=None, height=dp(30),
                               color=COR_TEXTO))
    if caminho_imagem and os.path.exists(caminho_imagem):
        conteudo.add_widget(KivyImage(source=caminho_imagem, allow_stretch=True,
                                       keep_ratio=True))
    linha = BoxLayout(size_hint_y=None, height=dp(48), spacing=8)
    popup = Popup(title="", content=conteudo, size_hint=(0.92, 0.85))

    def salvar(*_):
        destino = salvar_copia_publica(caminho_imagem)
        if destino:
            mostrar_popup_simples("Salvo!", f"Imagem salva em:\n{destino}")
        else:
            mostrar_popup_simples("Imagem pronta", f"A imagem está em:\n{caminho_imagem}")

    def compartilhar(*_):
        ok = compartilhar_arquivo(caminho_imagem, titulo=titulo_compartilhar)
        if not ok:
            mostrar_popup_simples("Compartilhar",
                                   f"Não foi possível abrir o menu de compartilhamento.\n"
                                   f"A imagem está salva em:\n{caminho_imagem}")

    btn_salvar = botao("💾 Salvar", cor=COR_SECUNDARIA)
    btn_salvar.bind(on_release=salvar)
    btn_compartilhar = botao("📤 Compartilhar", cor=COR_SUCESSO)
    btn_compartilhar.bind(on_release=compartilhar)
    btn_fechar = botao("Fechar", cor=COR_NEUTRA, size_hint_x=0.5)
    btn_fechar.bind(on_release=lambda *_: popup.dismiss())
    linha.add_widget(btn_salvar)
    linha.add_widget(btn_compartilhar)
    linha.add_widget(btn_fechar)
    conteudo.add_widget(linha)
    popup.open()
    return popup


# ---------------------------------------------------------------------------
# Tela: Luta (timer + pontuação + parada antecipada)
# ---------------------------------------------------------------------------

METODOS_PARADA = ["Nocaute (KO)", "Nocaute Técnico (TKO)", "Finalização (Submissão)",
                   "Decisão Médica"]


class LutaScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*COR_FUNDO)
            self._fundo = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._att_fundo, size=self._att_fundo)

        self.match_id = None
        self.round_atual = 1
        self.tempo_restante = 0
        self.rodando = False
        self.aviso_tocado = False
        self.evento_clock = None
        self.som_inicio = self.som_aviso = self.som_fim = None

        raiz = BoxLayout(orientation="vertical", padding=18, spacing=10)

        self.lbl_titulo = Label(text="", font_size="22sp", size_hint_y=None,
                                 height=dp(42), bold=True, color=COR_TEXTO)
        raiz.add_widget(self.lbl_titulo)

        self.lbl_round = Label(text="Round 1", font_size="17sp", size_hint_y=None,
                                height=dp(28), color=COR_TEXTO_FRACO)
        raiz.add_widget(self.lbl_round)

        cartao_timer = Cartao(orientation="vertical", size_hint_y=0.32, padding=10)
        self.lbl_timer = Label(text="00:00", font_size="60sp", color=COR_TEXTO)
        cartao_timer.add_widget(self.lbl_timer)
        raiz.add_widget(cartao_timer)

        linha_btns = BoxLayout(size_hint_y=None, height=dp(54), spacing=8)
        self.btn_iniciar = botao("Iniciar", cor=COR_SUCESSO)
        self.btn_iniciar.bind(on_release=self.iniciar_pausar)
        self.btn_zerar = botao("Reiniciar Round", cor=COR_NEUTRA)
        self.btn_zerar.bind(on_release=self.reiniciar_round)
        linha_btns.add_widget(self.btn_iniciar)
        linha_btns.add_widget(self.btn_zerar)
        raiz.add_widget(linha_btns)

        btn_parar = botao("⛔ Interromper Luta (KO / TKO / Finalização / Decisão Médica)",
                           cor=COR_PRIMARIA, size_hint_y=None, height=dp(50))
        btn_parar.bind(on_release=self.abrir_parar_luta)
        raiz.add_widget(btn_parar)

        self.scroll_placar = ScrollView(size_hint_y=0.28)
        self.lbl_placar = Label(text="", font_size="15sp", size_hint_y=None,
                                 color=COR_TEXTO_FRACO)
        self.lbl_placar.bind(texture_size=self._ajustar_altura_placar)
        self.scroll_placar.add_widget(self.lbl_placar)
        raiz.add_widget(self.scroll_placar)

        btn_voltar = botao("Voltar ao Chaveamento", cor=COR_NEUTRA, size_hint_y=None,
                            height=dp(46))
        btn_voltar.bind(on_release=self.sair)
        raiz.add_widget(btn_voltar)

        self.add_widget(raiz)

    def _att_fundo(self, *_):
        self._fundo.pos = self.pos
        self._fundo.size = self.size

    def _ajustar_altura_placar(self, *_):
        self.lbl_placar.height = self.lbl_placar.texture_size[1]
        self.lbl_placar.text_size = (self.lbl_placar.width, None)

    def on_pre_enter(self):
        if not self.som_inicio:
            ci, ca, cf = preparar_sons()
            self.som_inicio = SoundLoader.load(ci)
            self.som_aviso = SoundLoader.load(ca)
            self.som_fim = SoundLoader.load(cf)
        manter_tela_ligada(True)

    def on_leave(self):
        self.pausar()

    def carregar_luta(self, match_id):
        self.match_id = match_id
        luta = self.get_luta()
        self.round_atual = len(luta.get("pontos", [])) + 1
        if self.round_atual > luta["rounds"]:
            self.round_atual = luta["rounds"]
        self.tempo_restante = luta["tempo_round"]
        self.aviso_tocado = False
        self.rodando = False
        self.btn_iniciar.text = "Iniciar"
        self.atualizar_textos()

    def get_luta(self):
        app = App.get_running_app()
        return buscar_luta(app.torneio, self.match_id)

    def atualizar_textos(self):
        luta = self.get_luta()
        if not luta:
            return
        self.lbl_titulo.text = f'{luta["vermelho"]}  vs  {luta["azul"]}'
        self.lbl_round.text = f'Round {self.round_atual} de {luta["rounds"]}'
        m, s = divmod(self.tempo_restante, 60)
        self.lbl_timer.text = f"{m:02d}:{s:02d}"

        linhas = []
        total_v, total_a = 0, 0
        for i, (pv, pa) in enumerate(luta.get("pontos", []), start=1):
            linhas.append(f"Round {i}: {pv} x {pa}")
            total_v += pv
            total_a += pa
        if linhas:
            linhas.append(f"TOTAL: {total_v} x {total_a}")
        self.lbl_placar.text = "\n".join(linhas)

    def iniciar_pausar(self, *_):
        if self.rodando:
            self.pausar()
        else:
            self.iniciar()

    def iniciar(self):
        if self.tempo_restante <= 0:
            return
        self.rodando = True
        self.btn_iniciar.text = "Pausar"
        if self.som_inicio:
            self.som_inicio.play()
        if self.evento_clock:
            self.evento_clock.cancel()
        self.evento_clock = Clock.schedule_interval(self.tick, 1)

    def pausar(self):
        self.rodando = False
        self.btn_iniciar.text = "Continuar"
        if self.evento_clock:
            self.evento_clock.cancel()
            self.evento_clock = None

    def tick(self, dt):
        self.tempo_restante -= 1
        if self.tempo_restante == 10 and not self.aviso_tocado:
            self.aviso_tocado = True
            if self.som_aviso:
                self.som_aviso.play()
        if self.tempo_restante <= 0:
            self.tempo_restante = 0
            self.pausar()
            if self.som_fim:
                self.som_fim.play()
            self.btn_iniciar.text = "Round encerrado"
            Clock.schedule_once(lambda dt: self.abrir_pontuacao(), 0.3)
        self.atualizar_textos()

    def reiniciar_round(self, *_):
        luta = self.get_luta()
        if not luta:
            return
        self.pausar()
        self.tempo_restante = luta["tempo_round"]
        self.aviso_tocado = False
        self.btn_iniciar.text = "Iniciar"
        self.atualizar_textos()

    def _tempo_decorrido_formatado(self, luta):
        decorrido = max(0, luta["tempo_round"] - self.tempo_restante)
        m, s = divmod(decorrido, 60)
        return f"{m:02d}:{s:02d}"

    # -- pontuação por round (decisão) -------------------------------------

    def abrir_pontuacao(self):
        luta = self.get_luta()
        if not luta:
            return

        conteudo = BoxLayout(orientation="vertical", spacing=10, padding=10)
        conteudo.add_widget(Label(text=f"Pontuação - Round {self.round_atual}",
                                   font_size="18sp", size_hint_y=None, height=dp(30),
                                   color=COR_TEXTO))

        grid = GridLayout(cols=2, size_hint_y=None, height=dp(90), spacing=8)
        txt_v = TextInput(text="10", input_filter="int", multiline=False)
        txt_a = TextInput(text="9", input_filter="int", multiline=False)
        grid.add_widget(Label(text=f'{luta["vermelho"]}:', color=COR_TEXTO))
        grid.add_widget(txt_v)
        grid.add_widget(Label(text=f'{luta["azul"]}:', color=COR_TEXTO))
        grid.add_widget(txt_a)
        conteudo.add_widget(grid)

        linha_rapida = BoxLayout(size_hint_y=None, height=dp(44), spacing=6)

        def preencher(pv, pa):
            txt_v.text = str(pv)
            txt_a.text = str(pa)

        for label, pv, pa in [("10-9 V", 10, 9), ("10-9 A", 9, 10),
                               ("10-8 V", 10, 8), ("10-8 A", 8, 10)]:
            b = botao(label, cor=COR_NEUTRA, font_size="13sp")
            b.bind(on_release=lambda inst, pv=pv, pa=pa: preencher(pv, pa))
            linha_rapida.add_widget(b)
        conteudo.add_widget(linha_rapida)

        btn_confirmar = botao("Confirmar Round", cor=COR_SUCESSO, size_hint_y=None, height=dp(48))
        conteudo.add_widget(btn_confirmar)

        popup = Popup(title="Pontuar Round", content=conteudo, size_hint=(0.9, 0.58),
                       auto_dismiss=False)

        def confirmar(*_):
            try:
                pv = int(txt_v.text or "0")
                pa = int(txt_a.text or "0")
            except ValueError:
                pv, pa = 10, 9
            luta.setdefault("pontos", []).append([pv, pa])
            popup.dismiss()
            self.proximo_passo(luta)

        btn_confirmar.bind(on_release=confirmar)
        popup.open()

    def proximo_passo(self, luta):
        app = App.get_running_app()
        if self.round_atual >= luta["rounds"]:
            total_v = sum(p[0] for p in luta["pontos"])
            total_a = sum(p[1] for p in luta["pontos"])
            if total_v == total_a:
                self.mostrar_desempate(luta, total_v, total_a)
                return
            vencedor = luta["vermelho"] if total_v > total_a else luta["azul"]
            self.finalizar_luta(luta, "Decisão dos Pontos", vencedor)
        else:
            salvar_torneio(app.torneio)
            self.round_atual += 1
            self.tempo_restante = luta["tempo_round"]
            self.aviso_tocado = False
            self.btn_iniciar.text = "Iniciar"
            self.atualizar_textos()

    def mostrar_desempate(self, luta, total_v, total_a):
        conteudo = BoxLayout(orientation="vertical", padding=14, spacing=10)
        conteudo.add_widget(Label(
            text=f"Empate! {total_v} x {total_a}\nEscolha como resolver:",
            color=COR_TEXTO, size_hint_y=None, height=dp(60)))

        popup = Popup(title="Desempate", content=conteudo, size_hint=(0.9, 0.5),
                       auto_dismiss=False)

        btn_extra = botao("➕ Round Extra (Desempate)", cor=COR_SECUNDARIA,
                           size_hint_y=None, height=dp(48))

        def round_extra(*_):
            app = App.get_running_app()
            luta["rounds"] += 1
            salvar_torneio(app.torneio)
            popup.dismiss()
            self.round_atual += 1
            self.tempo_restante = luta["tempo_round"]
            self.aviso_tocado = False
            self.btn_iniciar.text = "Iniciar"
            self.atualizar_textos()

        btn_extra.bind(on_release=round_extra)
        conteudo.add_widget(btn_extra)

        conteudo.add_widget(Label(text="Ou decida manualmente quem venceu:",
                                   size_hint_y=None, height=dp(26), color=COR_TEXTO_FRACO))

        linha_manual = BoxLayout(size_hint_y=None, height=dp(48), spacing=8)
        btn_v = botao(luta["vermelho"], cor=COR_PRIMARIA)
        btn_a = botao(luta["azul"], cor=COR_SECUNDARIA)

        def decidir(nome, *_):
            popup.dismiss()
            self.finalizar_luta(luta, "Decisão do Organizador (desempate)", nome)

        btn_v.bind(on_release=lambda *_: decidir(luta["vermelho"]))
        btn_a.bind(on_release=lambda *_: decidir(luta["azul"]))
        linha_manual.add_widget(btn_v)
        linha_manual.add_widget(btn_a)
        conteudo.add_widget(linha_manual)

        btn_cancelar = botao("Cancelar", cor=COR_NEUTRA, size_hint_y=None, height=dp(40))
        btn_cancelar.bind(on_release=lambda *_: popup.dismiss())
        conteudo.add_widget(btn_cancelar)

        popup.open()

    # -- parada antecipada (KO / TKO / Finalização / Decisão Médica) -------

    def abrir_parar_luta(self, *_):
        luta = self.get_luta()
        if not luta:
            return
        conteudo = BoxLayout(orientation="vertical", padding=14, spacing=8)
        conteudo.add_widget(Label(text="Como a luta terminou?", bold=True,
                                   size_hint_y=None, height=dp(30), color=COR_TEXTO))
        popup = Popup(title="Interromper Luta", content=conteudo, size_hint=(0.9, 0.62),
                       auto_dismiss=False)

        for metodo in METODOS_PARADA:
            b = botao(metodo, cor=COR_PRIMARIA, size_hint_y=None, height=dp(46))
            b.bind(on_release=lambda inst, metodo=metodo: self._escolher_vencedor_parada(
                luta, metodo, popup))
            conteudo.add_widget(b)

        btn_cancelar = botao("Cancelar", cor=COR_NEUTRA, size_hint_y=None, height=dp(42))
        btn_cancelar.bind(on_release=lambda *_: popup.dismiss())
        conteudo.add_widget(btn_cancelar)
        popup.open()

    def _escolher_vencedor_parada(self, luta, metodo, popup_metodo):
        popup_metodo.dismiss()
        conteudo = BoxLayout(orientation="vertical", padding=14, spacing=10)
        conteudo.add_widget(Label(text=f"{metodo}\nQuem venceu?", color=COR_TEXTO,
                                   size_hint_y=None, height=dp(56)))
        popup = Popup(title="Vencedor", content=conteudo, size_hint=(0.85, 0.4),
                       auto_dismiss=False)

        btn_v = botao(luta["vermelho"], cor=COR_PRIMARIA, size_hint_y=None, height=dp(50))
        btn_a = botao(luta["azul"], cor=COR_SECUNDARIA, size_hint_y=None, height=dp(50))

        def escolher(nome, *_):
            popup.dismiss()
            self.finalizar_luta(luta, metodo, nome)

        btn_v.bind(on_release=lambda *_: escolher(luta["vermelho"]))
        btn_a.bind(on_release=lambda *_: escolher(luta["azul"]))
        conteudo.add_widget(btn_v)
        conteudo.add_widget(btn_a)

        btn_cancelar = botao("Cancelar", cor=COR_NEUTRA, size_hint_y=None, height=dp(40))
        btn_cancelar.bind(on_release=lambda *_: popup.dismiss())
        conteudo.add_widget(btn_cancelar)
        popup.open()

    # -- finalização comum ---------------------------------------------------

    def finalizar_luta(self, luta, metodo, vencedor):
        self.pausar()
        app = App.get_running_app()
        luta["vencedor"] = vencedor
        luta["metodo"] = metodo
        luta["round_fim"] = self.round_atual
        luta["tempo_fim"] = self._tempo_decorrido_formatado(luta)

        propagar_resultado(app.torneio, luta["r"], luta["i"])
        processar_byes(app.torneio)
        salvar_torneio(app.torneio)
        self.atualizar_textos()

        nome_torneio = app.torneio.get("nome", "Torneio MMA")
        caminho = None
        try:
            caminho = os.path.join(pasta_compartilhar(), f'{luta["id"]}.png')
            gerar_imagem_resultado(luta, nome_torneio, caminho)
        except Exception as e:
            print("Erro ao gerar imagem de resultado:", e)

        finalizou_torneio = torneio_finalizado(app.torneio)

        popup = mostrar_popup_imagem(
            f'{luta["vermelho"]}  x  {luta["azul"]}\nVencedor: {vencedor}  ({metodo})',
            caminho, titulo_compartilhar=f'Resultado: {luta["vermelho"]} x {luta["azul"]}')

        if finalizou_torneio:
            def ao_fechar(*_):
                try:
                    caminho_campeao = os.path.join(pasta_compartilhar(), "campeao_final.png")
                    gerar_imagem_campeao(app.torneio, caminho_campeao)
                    mostrar_popup_imagem(f'🏆 Torneio finalizado!\nCampeão: '
                                          f'{app.torneio.get("campeao")}',
                                          caminho_campeao,
                                          titulo_compartilhar="Resultado final do torneio")
                except Exception as e:
                    print("Erro ao gerar imagem final:", e)
                self.manager.current = "chaveamento"

            popup.bind(on_dismiss=ao_fechar)
        else:
            popup.bind(on_dismiss=lambda *_: setattr(self.manager, "current", "chaveamento"))

    def sair(self, *_):
        self.pausar()
        self.manager.current = "chaveamento"


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class MMAApp(App):
    def build(self):
        self.torneio = carregar_torneio()
        sm = ScreenManager(transition=SlideTransition())
        sm.add_widget(MenuScreen(name="menu"))
        sm.add_widget(CadastroScreen(name="cadastro"))
        sm.add_widget(OrdemScreen(name="ordem"))
        sm.add_widget(ChaveamentoScreen(name="chaveamento"))
        sm.add_widget(LutaScreen(name="luta"))
        return sm

    def on_start(self):
        manter_tela_ligada(True)

    def on_stop(self):
        salvar_torneio(self.torneio)


if __name__ == "__main__":
    MMAApp().run()
