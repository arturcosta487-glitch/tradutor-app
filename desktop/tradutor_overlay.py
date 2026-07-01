"""
TRADUTOR DE JOGOS EM TEMPO REAL (OCR + Overlay)
================================================
Captura uma região da tela continuamente, lê o texto com OCR e mostra
a tradução numa janela flutuante por cima do jogo.
 
Idiomas: Inglês -> Português (pode trocar nas variáveis SRC_LANG / TGT_LANG)
 
----------------------------------------------------------------------
INSTALAÇÃO (rode no PowerShell / CMD do Windows):
----------------------------------------------------------------------
1) Instale o Python (se ainda não tiver):
   https://www.python.org/downloads/
   IMPORTANTE: marque a opção "Add Python to PATH" durante a instalação.
 
2) Instale o Tesseract OCR (motor que lê texto em imagem):
   https://github.com/UB-Mannheim/tesseract/wiki
   Baixe o instalador "tesseract-ocr-w64-setup...exe" e instale.
   Anote o caminho de instalação (padrão costuma ser):
   C:\\Program Files\\Tesseract-OCR\\tesseract.exe
 
3) Instale as bibliotecas Python (abra o CMD e rode):
   pip install mss pytesseract pillow deep-translator pynput
 
4) Ajuste a variável TESSERACT_PATH abaixo se necessário.
 
----------------------------------------------------------------------
COMO USAR:
----------------------------------------------------------------------
1) Rode o script:  python tradutor_overlay.py
2) Na primeira vez, uma janela pedirá para você desenhar (clicar e
   arrastar) a região da tela onde aparecem as legendas/diálogos do
   jogo. Da próxima vez que rodar o script, ele já abre direto na
   mesma área (não precisa selecionar de novo).
3) Depois disso, a tradução aparece com fundo transparente, numa caixa
   flutuante logo ABAIXO da área selecionada (o texto original em
   inglês continua visível normalmente, sem se misturar com a
   tradução).
4) Teclas de atalho (funcionam mesmo com o jogo em foco):
     F9  = encerrar o tradutor
     F10 = selecionar uma nova área, sem precisar fechar o programa
----------------------------------------------------------------------
"""
 
import time
import re
import hashlib
import threading
import json
import os
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from tkinter import colorchooser
 
import mss
import pytesseract
from PIL import Image, ImageOps, ImageFilter
from deep_translator import GoogleTranslator
from pynput import keyboard
 
# ====================== CONFIGURAÇÕES ======================
SRC_LANG = "en"     # idioma do jogo (en = inglês)
TGT_LANG = "pt"     # idioma de destino (pt = português)
POLL_INTERVAL = 0.05  # segundos entre cada captura de tela (checagem de pixels)
TESSERACT_PATH = r"C:\Users\Oktsu\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
 
# Muitos jogos/visual novels mostram o texto aparecendo aos poucos (efeito
# "datilografado"), às vezes em rajadas com pausinhas no meio. Se o script
# ler o texto durante essa animação (mesmo numa pausinha), ele pega uma
# frase incompleta -> tradução sai com gramática quebrada e fica trocando
# toda hora. A solução mais confiável é olhar os PIXELS da região: enquanto
# o texto ainda está sendo desenhado, os pixels ficam mudando a cada
# instante; só quando eles ficam REALMENTE parados por um tempinho é que a
# fala terminou de aparecer. SETTLE_DELAY é esse "tempinho" de espera.
SETTLE_DELAY = 0.6  # segundos que a região precisa ficar sem mudar pixel nenhum
DEBUG = True  # se True, imprime no console o texto OCR bruto e se foi descartado como "lixo"
UPSCALE_FACTOR = 4  # quanto a imagem é ampliada antes do OCR; aumente (5, 6...)
                    # se estiver perdendo palavras pequenas/conectivos na leitura
OVERLAY_GAP = 8     # espaço (em pixels) entre a área capturada e a caixa de
                    # tradução, que agora aparece LOGO ABAIXO da área (em vez
                    # de cobrir o texto original, evitando sobreposição).
OVERLAY_OFFSET_X = 0  # desloca a caixa de tradução pra esquerda/direita (px),
                      # se precisar alinhar melhor com a tela do seu jogo
STOP_KEY = keyboard.Key.f9       # tecla para ENCERRAR o tradutor (não usa ESC pra não atrapalhar o jogo)
RESELECT_KEY = keyboard.Key.f10  # tecla para SELECIONAR UMA NOVA ÁREA sem reiniciar o programa
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "regiao_salva.json")
 
# Glossário do jogo: nomes próprios e termos que NÃO devem ser traduzidos.
# O Google Translate costuma "traduzir" nomes próprios sem querer (ex:
# transformar "Itsuki" em outra coisa) — esses termos são protegidos antes
# de mandar pro tradutor e devolvidos do jeito certo depois.
#
# Cada item é (termo, gênero). O gênero ("f", "m" ou None pra termos que
# não são pessoa, tipo lugares) existe porque o Google Translate não tem
# como saber se "Miku" é homem ou mulher só de olhar a palavra protegida
# — e às vezes erra o artigo (ex: traduz "the Miku" como "o Miku" em vez
# de "a Miku"). Depois da tradução, usamos esse gênero pra corrigir
# artigos errados que sobraram colados no nome (veja
# fix_glossary_gender_agreement). Não precisa se preocupar com
# maiúscula/minúscula na hora de detectar o termo no texto.
#
# Jogo: The Quintessential Quintuplets - Five Memories Spent With You
# (personagens: as quíntuplas Nakano, o protagonista Futaro e a irmã dele).
# Adicione/remova itens à vontade.
GLOSSARY = [
    ("Futaro", "m"),
    ("Futaro Uesugi", "m"),
    ("Uesugi", "m"),
    ("Ichika", "f"),
    ("Ichika Nakano", "f"),
    ("Nino", "f"),
    ("Nino Nakano", "f"),
    ("Miku", "f"),
    ("Miku Nakano", "f"),
    ("Yotsuba", "f"),
    ("Yotsuba Nakano", "f"),
    ("Itsuki", "f"),
    ("Itsuki Nakano", "f"),
    ("Nakano", None),       # sobrenome das 5 -> ambíguo, sem correção de gênero
    ("Raiha", "f"),
    ("Raiha Uesugi", "f"),
    ("Okinawa", None),      # lugar
    ("Ocean Expo Park", None),
    ("Churaumi Aquarium", None),
    ("Churaumi", None),
]
# =============================================================
 
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
 
stop_flag = False
reselect_flag = False
pause_flag = False  # controlado pelo Painel de Controle (botão Pausar/Retomar)
 
GA_ROOT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
 
 
def _process_name_from_hwnd(hwnd):
    """Dado um HWND, retorna o nome do executável (ex: 'jogo.exe') dono
    dessa janela, ou None se não for possível identificar."""
    try:
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None
        h_process = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if not h_process:
            return None
        try:
            buffer_len = wintypes.DWORD(260)
            buffer = ctypes.create_unicode_buffer(buffer_len.value)
            ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(
                h_process, 0, buffer, ctypes.byref(buffer_len)
            )
            if not ok:
                return None
            return os.path.basename(buffer.value).lower()
        finally:
            ctypes.windll.kernel32.CloseHandle(h_process)
    except Exception:
        return None
 
 
def get_process_name_at(x, y):
    """Retorna o nome do processo dono da janela que ocupa o ponto (x, y)
    na tela. Usado para 'travar' o tradutor na janela do jogo assim que
    a área é selecionada. Retorna None se não conseguir detectar (ex:
    sistema que não é Windows)."""
    try:
        pt = wintypes.POINT(int(x), int(y))
        hwnd = ctypes.windll.user32.WindowFromPoint(pt)
        if not hwnd:
            return None
        root_hwnd = ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT) or hwnd
        return _process_name_from_hwnd(root_hwnd)
    except Exception:
        return None
 
 
def get_foreground_process_name():
    """Retorna o nome do processo da janela que está em foco (em uso)
    no momento. Retorna None se não conseguir detectar."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        return _process_name_from_hwnd(hwnd)
    except Exception:
        return None
 
 
def read_text_from_capture(shot, variant=0):
    """Converte uma captura do mss em texto via OCR. Aumenta a imagem,
    melhora contraste e nitidez antes de ler — o Tesseract reconhece
    muito melhor textos pequenos/estilizados de jogo assim, o que reduz
    erros e 'alucinações' de texto (tipo ler ícones ou bordas como se
    fossem letras).
 
    'variant' escolhe uma combinação diferente de pré-processamento.
    Isso é usado nas tentativas de retry quando o OCR lê "lixo": como
    re-tirar print da MESMA imagem e processar do MESMO jeito sempre dá
    o mesmo resultado (o Tesseract é determinístico), só repetir não
    ajuda em nada quando o problema é a imagem em si ser difícil de ler
    (fonte fina/itálica, nitidez "estourando" os traços da letra, etc).
    Variando o pré-processamento a cada tentativa, é mais provável que
    uma das variantes "acerte" o que a outra perdeu."""
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
 
    # variant 0 (padrão): nitidez normal, como sempre foi.
    # variant 1: SEM o filtro de nitidez — em fontes finas/itálicas (comuns
    #   em falas de pensamento/narração) a nitidez pode "estourar" os
    #   traços finos das letras e confundir o Tesseract em vez de ajudar.
    # variant 2: upscale maior e sem esticar tanto o contraste — ajuda em
    #   textos pequenos demais ou com pouco contraste com o fundo.
    if variant == 1:
        upscale_factor = UPSCALE_FACTOR
        use_sharpen = False
        autocontrast_cutoff = 2
    elif variant >= 2:
        upscale_factor = UPSCALE_FACTOR + 2
        use_sharpen = False
        autocontrast_cutoff = 0
    else:
        upscale_factor = UPSCALE_FACTOR
        use_sharpen = True
        autocontrast_cutoff = 2
 
    # Aumenta a imagem (interpolação suave) e converte pra escala de
    # cinza. Palavras pequenas/conectivos (ex: "a", "de", "is", "to")
    # são as primeiras a sumir quando a imagem fica pequena demais pro
    # Tesseract — UPSCALE_FACTOR maior ajuda a não perdê-las. Se ainda
    # estiver perdendo conectivos, suba esse valor (ex: 5 ou 6).
    upscale_w = img.width * upscale_factor
    upscale_h = img.height * upscale_factor
    img_big = img.resize((upscale_w, upscale_h), Image.LANCZOS).convert("L")
 
    # Estica o contraste (separa melhor o texto do fundo) e realça
    # bordas das letras, o que ajuda bastante com fontes estilizadas de
    # jogo sobre fundos com textura/imagem.
    img_big = ImageOps.autocontrast(img_big, cutoff=autocontrast_cutoff)
    if use_sharpen:
        img_big = img_big.filter(ImageFilter.SHARPEN)
 
    # --psm 6: trata a região como um bloco uniforme de texto (bom para
    # legendas/diálogos com 1 ou mais linhas).
    # --oem 1: usa só o motor LSTM (rede neural), que costuma ser mais
    # confiável que o motor legado pra não "comer" palavras pequenas.
    custom_config = "--psm 6 --oem 1"
    raw_text = pytesseract.image_to_string(
        img_big,
        lang="eng" if SRC_LANG == "en" else SRC_LANG,
        config=custom_config,
    ).strip()
 
    if not raw_text:
        # Fallback pra textos bem curtos (interjeições tipo "Huh?",
        # "...!"): o --psm 6 espera um "bloco" de texto e às vezes não
        # reconhece nada quando sobra muito pouca coisa pra ler. O
        # --psm 7 trata a região como UMA linha única, o que costuma
        # resolver esses casos.
        fallback_config = "--psm 7 --oem 1"
        raw_text = pytesseract.image_to_string(
            img_big,
            lang="eng" if SRC_LANG == "en" else SRC_LANG,
            config=fallback_config,
        ).strip()
 
    raw_text = " ".join(raw_text.split())
    raw_text = normalize_common_ocr_mistakes(raw_text)
    return strip_windows_watermark_text(raw_text)
 
 
# Trechos típicos da marca d'água "Ative o Windows" / "Activate Windows"
# que aparece no canto da tela. Se a área selecionada encostar nela, o
# OCR pode ler esse texto junto — essa lista remove esses pedaços antes
# de traduzir, mesmo que o resto do diálogo do jogo seja mantido.
WINDOWS_WATERMARK_SNIPPETS = [
    "activate windows",
    "ative o windows",
    "ativar o windows",
    "go to settings to activate windows",
    "vá para configurações para ativar o windows",
    "vá para configuracoes para ativar o windows",
]
 
 
def strip_windows_watermark_text(text):
    """Remove qualquer trecho da marca d'água 'Ative o Windows' que o
    OCR tenha capturado junto com o texto do jogo."""
    if not text:
        return text
    cleaned = text
    lowered = cleaned.lower()
    for snippet in WINDOWS_WATERMARK_SNIPPETS:
        idx = lowered.find(snippet)
        if idx != -1:
            cleaned = cleaned[:idx] + cleaned[idx + len(snippet):]
            lowered = cleaned.lower()
    return " ".join(cleaned.split())
 
 
def normalize_common_ocr_mistakes(text):
    """Corrige confusões clássicas do Tesseract antes de qualquer outra
    análise. A mais comum de longe: o pronome 'I' (maiúsculo, sozinho ou
    em contrações como I'll/I'm/I've/I don't) sai lido como barra(s)
    vertical(is) '|' — e às vezes até o 'll' de contrações como "I'll"
    vira '||', porque visualmente são quase idênticos em várias fontes.
    Sem essa correção, qualquer frase com 'I' — ou seja, a esmagadora
    maioria dos diálogos em inglês — corre o risco de ser descartada
    como lixo só por causa dessas barras.
 
    Importante: a sequência inteira de pipes grudados (ex: "|", "||",
    "|||"...) é resolvida de UMA VEZ SÓ, olhando o tamanho do bloco
    inteiro. A versão antiga fazia isso em duas passadas separadas
    (primeiro "||"->"ll", depois "|"->"I"), e isso podia deixar pipe
    sobrando sem converter quando vinham 3+ pipes seguidos ou variações
    fora do padrão — daí o texto ia pro tradutor/checagem de lixo ainda
    com '|' no meio, mesmo sendo uma frase perfeitamente normal."""
    if not text:
        return text
 
    def _replace_pipe_run(match):
        run_length = len(match.group(0))
        if run_length == 1:
            return "I"
        if run_length == 2:
            return "ll"
        # 3+ pipes grudados: bem raro, mas o padrão mais comum nesse
        # caso é "I" seguido de um ou mais "l" (ex: de "I'll"/"Ill").
        return "I" + "l" * (run_length - 1)
 
    # Só mexe em blocos de pipe que não estão grudados em letra/número
    # de verdade (evita estragar algo como "HP|100" se isso existir).
    text = re.sub(r"(?<![A-Za-z0-9])\|+(?![A-Za-z0-9])", _replace_pipe_run, text)
 
    # "»"/"«" colado entre duas letras (sem espaço) -> quase sempre é
    # um espaço, aspas ou travessão do jogo que o OCR leu errado (ex:
    # "book»something" devia ser "book something" ou 'book "something').
    # Vira espaço, que é a aposta mais segura pra não juntar duas
    # palavras sem querer.
    text = re.sub(r"(?<=[A-Za-z])[»«](?=[A-Za-z])", " ", text)
 
    # "?" no MEIO de uma palavra (entre duas letras, ex: "didn?t") quase
    # sempre é o apóstrofo de uma contração mal lido — uma interrogação
    # de verdade não aparece grudada assim dentro de uma palavra.
    text = re.sub(r"(?<=[A-Za-z])\?(?=[A-Za-z])", "'", text)
 
    return text
 
 
def looks_like_ocr_garbage(text):
    """Detecta textos que provavelmente são lixo de OCR (o Tesseract
    'inventando' letras a partir de ícones, bordas ou ruído visual) em
    vez de texto de verdade do jogo. Ajuda a não traduzir e mostrar
    coisas tipo '[S I ISto Ss BSlv /'."""
    if not text:
        return False
 
    letters = sum(1 for ch in text if ch.isalpha())
 
    # Pontuação "normal" de diálogo (reticências de hesitação, hífen de
    # gagueira tipo "I-I", "N-No", exclamação, interrogação, aspas,
    # vírgula, dois-pontos, espaço) NÃO deve contar contra o texto na
    # proporção letras/total. Falas de anime/visual novel com gagueira
    # ("I-I... N-No...", "Y-You can't be serious...") são naturalmente
    # curtas em letras e carregadas dessa pontuação, e antes disso
    # acabavam classificadas como lixo só por causa disso.
    DIALOGUE_PUNCTUATION = set(" .,!?'\"-:;…")
    non_punct_total = sum(1 for ch in text if ch not in DIALOGUE_PUNCTUATION)
 
    if non_punct_total == 0:
        # Só sobrou pontuação "normal" (ex: "..." de uma pausa silenciosa
        # sem fala nenhuma) -> não é lixo, é só um texto vazio de
        # conteúdo; deixa o resto do fluxo decidir o que fazer com isso.
        return False
 
    # Pouquíssimas letras em relação ao conteúdo "real" do texto (muito
    # símbolo estranho/ruído solto) -> provavelmente lixo.
    if letters / non_punct_total < 0.55:
        return True
 
    # Símbolos que quase nunca aparecem em legenda/diálogo normal de
    # jogo, mas são comuns quando o OCR "inventa" caracteres a partir de
    # bordas, ícones ou ruído visual da imagem. ('|' fica de fora: é
    # corrigido antes, em normalize_common_ocr_mistakes, por ser quase
    # sempre um "I" mal lido; '»'/'«' coladas em palavra também já são
    # tratadas lá.)
    # Um símbolo suspeito ISOLADO em frase comprida pode ser só um
    # acento/pontuação esquisita que o OCR pegou (ex: aspas decorativas
    # do jogo) — não é motivo sozinho pra jogar a frase inteira fora.
    # Só conta como lixo de verdade quando aparecem VÁRIOS, ou quando
    # são uma fração grande de um texto curto.
    SUSPICIOUS_CHARS = set("«»\\^~`{}_¢¥§¤")
    suspicious_count = sum(1 for ch in text if ch in SUSPICIOUS_CHARS)
    if suspicious_count >= 3 or (suspicious_count >= 1 and suspicious_count / total > 0.05):
        return True
 
    words = text.split()
    if not words:
        return True
 
    # Muitas "palavras" de uma letra só (especialmente maiúscula solta)
    # é um padrão clássico de OCR mal lido em ícones/bordas.
    single_char_words = sum(1 for w in words if len(w) == 1)
    if len(words) >= 3 and single_char_words / len(words) > 0.4:
        return True
 
    # Maiúscula "perdida" no meio de uma palavra (ex: "IGurag",
    # "cacTtla") é outro padrão clássico de letra mal reconhecida -
    # texto de jogo normal não mistura caixa assim no meio da palavra.
    # Padrão de "gagueira" comum em fala de anime/visual novel: uma letra
    # ou sílaba curta, hífen, e a palavra de novo começando com maiúscula
    # (ex: "N-No", "I-I", "Y-You", "W-Wait"). Isso é diálogo perfeitamente
    # normal, mas tem exatamente a "cara" de um erro clássico de OCR
    # (maiúscula no meio da palavra) — então precisa ser reconhecido à
    # parte ANTES de cair na checagem de maiúscula deslocada, ou a frase
    # inteira (que geralmente é curta) é descartada como lixo por engano.
    STUTTER_PATTERN = re.compile(r"^[A-Za-z]{1,2}-[A-Z][a-zA-Z']*[.,!?]*$")
 
    def has_misplaced_capital(word):
        if STUTTER_PATTERN.match(word):
            return False
        core = "".join(ch for ch in word if ch.isalpha())
        if len(core) < 3:
            return False
        # Ignora siglas/abreviações totalmente maiúsculas (ex: "OK", "VIP").
        if core.isupper():
            return False
        return any(ch.isupper() for ch in core[1:])
 
    # Em frases curtas (1-2 palavras), 1 erro já é suspeito o bastante
    # (pouca coisa pra "diluir" o erro). Em frases mais longas, normais
    # de diálogo/legenda, é comum o Tesseract errar a caixa de UMA letra
    # isolada mesmo em texto perfeitamente válido (fontes estilizadas de
    # jogo, sombra/contorno no texto, etc.) — então só consideramos lixo
    # se isso acontecer numa proporção considerável das palavras.
    misplaced_capitals = sum(1 for w in words if has_misplaced_capital(w))
    if len(words) <= 2:
        if misplaced_capitals >= 1:
            return True
    elif misplaced_capitals / len(words) > 0.35:
        return True
 
    return False
 
 
def prepare_text_for_translation(text):
    """Ajeita o texto antes de mandar pro tradutor: capitaliza a
    primeira letra e garante pontuação no final. Frases sem pontuação
    costumam confundir o tradutor; isso ajuda a entender melhor o
    contexto e devolver uma frase mais natural."""
    if not text:
        return text
    fixed = text[0].upper() + text[1:] if text else text
    if fixed[-1] not in ".!?":
        fixed += "."
    return fixed
 
 
# Marcador usado para "esconder" os termos do glossário do tradutor.
# Um padrão que o Google Translate praticamente nunca altera (letras
# maiúsculas + número), ex: XQGLOSS0X, XQGLOSS1X...
_GLOSSARY_TOKEN = "XQGLOSS{}X"
 
# Ordena o glossário do termo mais longo pro mais curto, pra "Ichika
# Nakano" ser protegido inteiro antes de "Ichika" ou "Nakano" sozinhos.
_GLOSSARY_SORTED = sorted(GLOSSARY, key=lambda item: len(item[0]), reverse=True)
 
 
def protect_glossary_terms(text):
    """Substitui cada termo do GLOSSARY encontrado no texto por um
    marcador (token) que o Google Translate não traduz. Devolve o texto
    com os marcadores e um dicionário {marcador: (termo_original, gênero)}
    para reverter depois da tradução."""
    found = {}
    result = text
    for i, (term, gender) in enumerate(_GLOSSARY_SORTED):
        token = _GLOSSARY_TOKEN.format(i)
        # Busca o termo ignorando maiúscula/minúscula, mas preserva o
        # termo como está escrito no GLOSSARY ao restaurar.
        lowered = result.lower()
        term_lower = term.lower()
        start = lowered.find(term_lower)
        if start == -1:
            continue
        # Troca todas as ocorrências desse termo.
        while start != -1:
            result = result[:start] + token + result[start + len(term):]
            found[token] = (term, gender)
            lowered = result.lower()
            start = lowered.find(term_lower)
    return result, found
 
 
def restore_glossary_terms(text, found):
    """Troca de volta os marcadores pelos termos originais do glossário,
    já no formato certo (sem aspas/lixo que o tradutor possa ter
    adicionado em volta do marcador)."""
    result = text
    for token, (term, _gender) in found.items():
        # O Google Translate às vezes muda a capitalização do marcador
        # (ex: "Xqgloss0x") ou adiciona espaços; busca de forma tolerante.
        for variant in (token, token.lower(), token.capitalize(), token.title()):
            result = result.replace(variant, term)
    return result
 
 
# Artigos que são SEMPRE artigo (nunca preposição/outra função) em
# português, por isso são seguros de corrigir automaticamente:
# "o/O" e "um/Um" só existem como artigo/numeral masculino; "uma/Uma" só
# existe como artigo/numeral feminino. ("a/A" fica de fora de propósito:
# também é preposição comum — "dar isso a Miku" está certo do jeito que
# está — então mexer nele arriscaria estragar frases corretas.)
_MASCULINE_ARTICLE_FIX = {"o": "a", "O": "A", "um": "uma", "Um": "Uma"}
_FEMININE_ARTICLE_FIX = {"uma": "um", "Uma": "Um"}
 
 
def fix_glossary_gender_agreement(text, found):
    """Corrige artigo errado colado bem antes de um nome do glossário
    quando o gênero do personagem é conhecido (ex: 'o Miku' -> 'a Miku').
    Só mexe em artigos que nunca têm outro significado em português
    (evita estragar frases onde a palavra antes do nome é preposição)."""
    if not found:
        return text
 
    # Termos únicos com gênero conhecido (sem repetir o mesmo nome).
    seen = {}
    for term, gender in found.values():
        if gender:
            seen[term] = gender
 
    for term, gender in seen.items():
        fixes = _MASCULINE_ARTICLE_FIX if gender == "f" else _FEMININE_ARTICLE_FIX if gender == "m" else None
        if not fixes:
            continue
        articles_pattern = "|".join(re.escape(a) for a in fixes)
        pattern = re.compile(r"\b(" + articles_pattern + r")(\s+)" + re.escape(term) + r"\b")
 
        def _fix(match, _fixes=fixes):
            return _fixes[match.group(1)] + match.group(2) + term
 
        text = pattern.sub(_fix, text)
 
    return text
 
 
def _looks_partially_untranslated(original, translated):
    """Heurística: às vezes o marcador do glossário (ex: 'XQGLOSS0X')
    cai bem no meio de uma frase e faz o Google Translate 'engasgar' —
    ele traduz o resto do texto normalmente, mas deixa exatamente o
    trecho com o marcador intacto, em inglês. Detectamos isso vendo se
    boa parte das palavras do texto original (as mais longas, que
    dificilmente coincidem por acaso entre os dois idiomas) ainda
    aparecem, intactas, no resultado 'traduzido'."""
    orig_words = {w.strip(".,!?;:\"'").lower() for w in original.split() if len(w) > 3}
    if not orig_words:
        return False
    trans_words = {w.strip(".,!?;:\"'").lower() for w in translated.split() if len(w) > 3}
    overlap = orig_words & trans_words
    return (len(overlap) / len(orig_words)) > 0.4
 
 
def translate_with_glossary(translator, text):
    """Traduz o texto protegendo antes os termos do GLOSSARY (nomes
    próprios e afins), pra eles não saírem traduzidos/distorcidos."""
    protected_text, found = protect_glossary_terms(text)
    translated = translator.translate(protected_text)
    if found:
        translated = restore_glossary_terms(translated, found)
 
        # Se o marcador travou a tradução de parte da frase, tenta de
        # novo SEM proteção: o nome próprio corre o risco de sair
        # traduzido/estranho, mas é melhor que metade da frase ficar em
        # inglês.
        if _looks_partially_untranslated(text, translated):
            retry = translator.translate(text)
            if not _looks_partially_untranslated(text, retry):
                translated = retry
 
        # Corrige artigo errado que o Google às vezes deixa colado no
        # nome (ex: "o Miku" -> "a Miku"), já que ele não tem como saber
        # o gênero de um nome próprio japonês sozinho.
        translated = fix_glossary_gender_agreement(translated, found)
 
    return translated
 
 
def on_press(key):
    global stop_flag, reselect_flag
    if key == STOP_KEY:
        stop_flag = True
        return False
    if key == RESELECT_KEY:
        reselect_flag = True
 
 
def load_saved_region():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None
 
 
def save_region(region):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(region, f)
    except Exception:
        pass
 
 
def select_region():
    """Abre uma janela transparente em tela cheia para o usuário
    desenhar (clicar e arrastar) a região a ser monitorada."""
    coords = {}
 
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.25)
    root.attributes("-topmost", True)
    root.configure(bg="black")
    root.title("Selecione a região do texto - clique e arraste")
 
    canvas = tk.Canvas(root, cursor="cross", bg="gray12", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)
 
    label = tk.Label(
        root,
        text="Clique e arraste sobre a área das legendas/diálogos. Solte para confirmar.",
        fg="white",
        bg="black",
        font=("Segoe UI", 14),
    )
    label.place(relx=0.5, y=30, anchor="n")
 
    start = {}
    rect_id = {"id": None}
 
    def on_mouse_down(event):
        start["x"], start["y"] = event.x_root, event.y_root
        if rect_id["id"]:
            canvas.delete(rect_id["id"])
        rect_id["id"] = canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#39ff8f", width=3
        )
 
    def on_mouse_move(event):
        if rect_id["id"]:
            x0 = start["x"] - root.winfo_rootx()
            y0 = start["y"] - root.winfo_rooty()
            canvas.coords(rect_id["id"], x0, y0, event.x, event.y)
 
    def on_mouse_up(event):
        x1, y1 = start["x"], start["y"]
        x2, y2 = event.x_root, event.y_root
        coords["left"] = int(min(x1, x2))
        coords["top"] = int(min(y1, y2))
        coords["width"] = int(abs(x2 - x1))
        coords["height"] = int(abs(y2 - y1))
        root.destroy()
 
    canvas.bind("<ButtonPress-1>", on_mouse_down)
    canvas.bind("<B1-Motion>", on_mouse_move)
    canvas.bind("<ButtonRelease-1>", on_mouse_up)
 
    root.mainloop()
 
    if coords.get("width") and coords.get("height"):
        cx = coords["left"] + coords["width"] // 2
        cy = coords["top"] + coords["height"] // 2
        time.sleep(0.05)  # dá tempo da janela de seleção sumir de vez
        coords["process"] = get_process_name_at(cx, cy)
 
    return coords
 
 
class OverlayWindow:
    # Cor "chave" usada como transparente. Evite usar essa cor no texto,
    # pois qualquer pixel dessa cor exata vira invisível.
    TRANSPARENT_KEY = "#fe01fe"
 
    # Faixa de tamanhos de fonte permitidos no autofit (a fonte se ajusta
    # automaticamente dentro desse intervalo para caber na caixa).
    MIN_FONT_SIZE = 8
    MAX_FONT_SIZE = 40
 
    def _compute_position(self, region):
        """Decide onde colocar a caixa de tradução: por padrão LOGO
        ABAIXO da região monitorada, pra não cobrir o texto original.
        Mas se a área selecionada já estiver perto da borda inferior da
        tela (comum quando a legenda do jogo ocupa a caixa toda, perto
        do rodapé), não cabe embaixo -> nesse caso usa o espaço ACIMA da
        região no lugar. Se nem em cima nem embaixo houver espaço
        sobrando, usa embaixo mesmo e só "encaixa" (clamp) pra não sair
        da tela."""
        width = region["width"]
        height = region["height"]
        x = region["left"] + OVERLAY_OFFSET_X
        screen_h = self.root.winfo_screenheight()
 
        y_below = region["top"] + region["height"] + OVERLAY_GAP
        y_above = region["top"] - height - OVERLAY_GAP
 
        if y_below + height <= screen_h:
            y = y_below
        elif y_above >= 0:
            y = y_above
        else:
            y = max(0, min(y_below, screen_h - height))
 
        return x, y, width, height
 
    def __init__(self, region):
        self.root = tk.Tk()
        self.root.overrideredirect(True)       # sem borda de janela
        self.root.attributes("-topmost", True)  # sempre por cima
        self.root.configure(bg=self.TRANSPARENT_KEY)
        # Torna a cor-chave 100% transparente (somente Windows).
        self.root.attributes("-transparentcolor", self.TRANSPARENT_KEY)
 
        x, y, width, height = self._compute_position(region)
 
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self._box_width = width
        self._box_height = height
 
        self._font = tkfont.Font(family="Segoe UI", size=self.MAX_FONT_SIZE, weight="bold")
 
        # Cor do texto e limites de tamanho de fonte ficam em atributos de
        # instância (em vez de constantes fixas) pra poderem ser mudados
        # em tempo real pelo Painel de Controle.
        self._text_color = "#ffffff"
        self.min_font_size = self.MIN_FONT_SIZE
        self.max_font_size = self.MAX_FONT_SIZE
 
        # Guarda o último texto que o OCR leu (mesmo quando é descartado
        # como "lixo"), pra mostrar ao vivo no Painel de Controle.
        self.last_ocr_var = tk.StringVar(value="(nada lido ainda)")
 
        self.text_var = tk.StringVar(value="...")
        self.label = tk.Label(
            self.root, textvariable=self.text_var, fg=self._text_color, bg=self.TRANSPARENT_KEY,
            font=self._font, wraplength=width - 16, justify="center", anchor="center"
        )
        self.label.pack(fill="both", expand=True, padx=4, pady=4)
 
 
        # Faz a janela ficar invisível para qualquer captura de tela (print,
        # screenshot, gravação) no Windows 10 2004+ / Windows 11, mas
        # continua 100% visível pra você normalmente. Assim o OCR nunca
        # "lê" a própria tradução e não precisamos esconder/mostrar a
        # janela a cada captura (sem mais piscar).
        self._exclude_from_screen_capture()
 
        # permite arrastar a janela do overlay com o mouse
        self.label.bind("<ButtonPress-1>", self._start_move)
        self.label.bind("<B1-Motion>", self._do_move)
        self._drag = {}
 
    def _exclude_from_screen_capture(self):
        """Usa a API do Windows (SetWindowDisplayAffinity) pra impedir que
        esta janela apareça em capturas de tela, incluindo a do mss usada
        no OCR. Requer Windows 10 versão 2004 ou mais recente. Se algo
        falhar (Windows mais antigo, outro SO, etc.), ignora silenciosamente
        e o programa continua funcionando normalmente."""
        try:
            self.root.update_idletasks()
            hwnd = self.root.winfo_id()
            WDA_EXCLUDEFROMCAPTURE = 0x11
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        except Exception:
            pass
 
    def _start_move(self, event):
        self._drag["x"] = event.x
        self._drag["y"] = event.y
 
    def _do_move(self, event):
        x = self.root.winfo_pointerx() - self._drag["x"]
        y = self.root.winfo_pointery() - self._drag["y"]
        self.root.geometry(f"+{x}+{y}")
 
    def set_text_color(self, color):
        """Muda a cor do texto da tradução em tempo real."""
        self._text_color = color
        self.label.config(fg=color)
 
    def set_max_font_size(self, size):
        """Muda o tamanho máximo de fonte permitido no autofit e já
        reaplica no texto atual."""
        self.max_font_size = max(self.min_font_size, int(size))
        self._autofit_font(self.text_var.get())
 
    def update_text(self, text):
        self.text_var.set(text)
        self._autofit_font(text)
 
    def _autofit_font(self, text):
        """Escolhe o maior tamanho de fonte (dentro do intervalo permitido)
        que faz o texto caber na caixa, sem cortar linhas."""
        if not text:
            return
 
        avail_width = max(self._box_width - 16, 10)
        avail_height = max(self._box_height - 8, 10)
 
        best_size = self.min_font_size
        for size in range(self.max_font_size, self.min_font_size - 1, -1):
            self._font.configure(size=size)
            line_height = self._font.metrics("linespace")
 
            # Quebra o texto em linhas simulando o wraplength do Label.
            lines = self._wrap_text(text, avail_width)
            total_height = line_height * len(lines)
            widest_line = max((self._font.measure(line) for line in lines), default=0)
 
            if total_height <= avail_height and widest_line <= avail_width:
                best_size = size
                break
 
        self._font.configure(size=best_size)
 
    def _wrap_text(self, text, avail_width):
        """Quebra o texto em linhas que respeitam avail_width, usando a
        fonte atual (self._font) para medir a largura de cada palavra."""
        words = text.split()
        if not words:
            return [""]
 
        lines = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if self._font.measure(candidate) <= avail_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines
 
    def reposition(self, region):
        x, y, width, height = self._compute_position(region)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self._box_width = width
        self._box_height = height
        self.label.config(wraplength=width - 16)
        self._autofit_font(self.text_var.get())
 
    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass
 
 
def _rounded_rect_points(x1, y1, x2, y2, radius):
    """Gera os pontos de um retângulo de cantos arredondados, prontos
    pra usar com canvas.create_polygon(..., smooth=True). O Tkinter não
    tem um jeito nativo de desenhar isso, então construímos a forma
    "cortando" os 4 cantos e deixando o smooth=True arredondar essas
    quinas pra virarem curvas."""
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
 
 
def _draw_rounded_rect(canvas, x1, y1, x2, y2, radius=12, **kwargs):
    """Desenha um retângulo arredondado num Canvas e devolve o id do
    item criado (útil pra apagar/redesenhar depois)."""
    points = _rounded_rect_points(x1, y1, x2, y2, radius)
    return canvas.create_polygon(points, smooth=True, **kwargs)
 
 
class RoundedCard(tk.Frame):
    """Card com cantos bem arredondados — visual fofinho."""
 
    def __init__(self, parent, bg, outline=None, radius=18, **kwargs):
        parent_bg = parent["bg"]
        super().__init__(parent, bg=parent_bg, **kwargs)
        self._bg = bg
        self._outline = outline or bg
        self._radius = radius
 
        self.canvas = tk.Canvas(self, bg=parent_bg, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
 
        self.body = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
 
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.body.bind("<Configure>", self._on_body_resize)
 
    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self._window, width=event.width)
        self._redraw(event.width, event.height)
 
    def _on_body_resize(self, _event):
        req_h = self.body.winfo_reqheight()
        if req_h > 1:
            self.canvas.config(height=req_h)
            self._redraw(self.canvas.winfo_width(), req_h)
 
    def _redraw(self, w, h):
        self.canvas.delete("card_bg")
        if w > 2 and h > 2:
            item = _draw_rounded_rect(
                self.canvas, 1, 1, w - 1, h - 1, self._radius,
                fill=self._bg, outline=self._outline, width=1, tags="card_bg",
            )
            self.canvas.tag_lower(item)
 
 
class RoundedButton(tk.Canvas):
    """Botão com cantos bem arredondados — visual fofinho."""
 
    def __init__(self, parent, text, command=None, fill="#7eb8f7",
                 hover="#a78bfa", fg="#060c1a", fg_hover=None,
                 font=("Segoe UI", 10, "bold"),
                 radius=14, padx=16, pady=10, outline=None, min_width=0):
        parent_bg = parent["bg"]
        super().__init__(parent, bg=parent_bg, highlightthickness=0, cursor="hand2")
        self._fill    = fill
        self._hover   = hover
        self._fg      = fg
        self._fg_hover = fg_hover or fg
        self._font    = tkfont.Font(
            family=font[0], size=font[1],
            weight=font[2] if len(font) > 2 else "normal",
        )
        self._radius   = radius
        self._padx     = padx
        self._pady     = pady
        self._command  = command
        self._text     = text
        self._outline  = outline
        self._min_width = min_width
        self._hovering = False
 
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>",     lambda e: self._set_hover(True))
        self.bind("<Leave>",     lambda e: self._set_hover(False))
        self.bind("<Button-1>",  self._on_click)
 
        text_w = self._font.measure(text)
        text_h = self._font.metrics("linespace")
        super().config(
            width=max(text_w + padx * 2, min_width),
            height=text_h + pady * 2,
        )
        self._redraw()
 
    def _set_hover(self, hovering):
        self._hovering = hovering
        self._redraw()
 
    def _redraw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 2 or h < 2:
            return
        color      = self._hover if self._hovering else self._fill
        text_color = self._fg_hover if self._hovering else self._fg
        outline    = self._outline or color
        _draw_rounded_rect(self, 1, 1, w-1, h-1, self._radius,
                           fill=color, outline=outline, width=1)
        self.create_text(w/2, h/2, text=self._text,
                         fill=text_color, font=self._font)
 
    def _on_click(self, _event):
        if self._command:
            self._command()
 
    def set_text(self, text):
        self._text = text
        text_w = self._font.measure(text)
        super().config(width=max(text_w + self._padx * 2, self._min_width))
        self._redraw()
 
    def config(self, **kwargs):
        if "text" in kwargs:
            self.set_text(kwargs.pop("text"))
        if kwargs:
            super().config(**kwargs)
 
    configure = config
 
 
class ControlPanel:
    """Painel de controle — tema fofinho/arredondado, igual ao launcher."""
 
    # ── Paleta (mesma do launcher) ──────────────────────────────────
    BG        = "#0f111a"
    PANEL_BG  = "#161b29"
    CARD_BG   = "#1a1f31"
    BORDER    = "#252d42"
    TEXT_MAIN = "#e8eaf6"
    TEXT_MUTED= "#8b93b0"
    ACCENT    = "#7eb8f7"   # azul pastel
    ACCENT_H  = "#a78bfa"   # lilás pastel (hover)
    ACCENT_SOFT="#0f1624"
    SUCCESS   = "#6ee7b7"   # verde menta
    DANGER    = "#f87171"   # vermelho pastel
    DANGER_H  = "#fca5a5"
    PAUSE_COL = "#8b93b0"
 
    def __init__(self, overlay, region=None):
        self.overlay = overlay
        self.paused  = False
        self._text_before_pause = "..."
        self._region = dict(region) if region else {}
 
        self.win = tk.Toplevel(overlay.root)
        self.win.title("Tradutor de Jogos — Painel de Controle")
        self.win.attributes("-topmost", True)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.win.destroy)
        self.win.configure(bg=self.BG)
        self.win.overrideredirect(True)   # sem barra de título branca
 
        W, H = 600, 430
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
 
        self._drag_x = self._drag_y = 0
        self._round_window_corners()
 
        self._style = ttk.Style(self.win)
        try:
            self._style.theme_use("clam")
        except Exception:
            pass
        self._setup_styles()
 
        self._build(W, H)
 
    # ------------------------------------------------------------------
    def _round_window_corners(self):
        try:
            self.win.update_idletasks()
            hwnd = self.win.winfo_id()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33,
                ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int),
            )
        except Exception:
            pass
 
    # ------------------------------------------------------------------
    def _pill(self, canvas, x1, y1, x2, y2, r=20, **kw):
        pts = [
            x1+r, y1,   x2-r, y1,
            x2,   y1,   x2,   y1+r,
            x2,   y2-r, x2,   y2,
            x2-r, y2,   x1+r, y2,
            x1,   y2,   x1,   y2-r,
            x1,   y1+r, x1,   y1,
        ]
        return canvas.create_polygon(pts, smooth=True, **kw)
 
    # ------------------------------------------------------------------
    def _build(self, W, H):
        # ── base canvas ──────────────────────────────────────────────
        base = tk.Canvas(self.win, width=W, height=H,
                         bg=self.BG, highlightthickness=0)
        base.pack()
 
        # moldura pill
        self._pill(base, 6, 6, W-6, H-6, r=26,
                   fill=self.CARD_BG, outline=self.BORDER, width=1)
 
        # divisória vertical
        base.create_line(180, 24, 180, H-24, fill=self.BORDER, width=1)
 
        # arrastar
        base.bind("<Button-1>",  self._drag_start)
        base.bind("<B1-Motion>", self._drag_move)
 
        # ✕ fechar painel
        xid = base.create_text(W-22, 22, text="✕",
                                fill=self.TEXT_MUTED, font=("Segoe UI", 11),
                                tags="xbtn")
        base.tag_bind("xbtn", "<Button-1>", lambda e: self.win.destroy())
        base.tag_bind("xbtn", "<Enter>",    lambda e: base.itemconfig(xid, fill=self.DANGER))
        base.tag_bind("xbtn", "<Leave>",    lambda e: base.itemconfig(xid, fill=self.TEXT_MUTED))
 
        # ── SIDEBAR ──────────────────────────────────────────────────
        # ícone + título
        self._pill(base, 18, 18, 58, 58, r=14,
                   fill=self.ACCENT_H, outline="")
        base.create_text(38, 38, text="T", fill="#ffffff",
                         font=("Segoe UI", 16, "bold"))
        base.create_text(70, 30, text="Tradutor",
                         fill=self.TEXT_MAIN, font=("Segoe UI", 10, "bold"), anchor="w")
        base.create_text(70, 46, text="PT-BR",
                         fill=self.TEXT_MUTED, font=("Segoe UI", 9), anchor="w")
 
        # nav lateral
        nav_items = [
            ("inicio",    "🏠  Início"),
            ("aparencia", "🎨  Aparência"),
            ("atalhos",   "⌨️  Atalhos"),
        ]
        self._nav_labels = {}
        self._nav_base   = base
        nav_y = 90
        for key, label in nav_items:
            lbl = tk.Label(
                self.win, text=label, bg=self.CARD_BG,
                fg=self.TEXT_MUTED, font=("Segoe UI", 10),
                anchor="w", padx=14, pady=8, cursor="hand2",
            )
            lbl.place(x=12, y=nav_y, width=160)
            lbl.bind("<Button-1>", lambda e, k=key: self._show_page(k))
            lbl.bind("<Enter>", lambda e, l=lbl: l.config(fg=self.ACCENT))
            lbl.bind("<Leave>", lambda e, l=lbl, k2=key: l.config(
                fg=self.ACCENT if self._cur_page == k2 else self.TEXT_MUTED))
            self._nav_labels[key] = lbl
            nav_y += 44
 
        # ── CONTEÚDO ─────────────────────────────────────────────────
        cx, cy, cw, ch = 190, 16, W-202, H-32
 
        self._pages = {}
        self._cur_page = "inicio"
        for key in ("inicio", "aparencia", "atalhos"):
            fr = tk.Frame(self.win, bg=self.BG, width=cw, height=ch)
            fr.place(x=cx, y=cy)
            fr.pack_propagate(False)
            self._pages[key] = fr
 
        self._build_inicio(self._pages["inicio"], cw)
        self._build_aparencia(self._pages["aparencia"], cw)
        self._build_atalhos(self._pages["atalhos"], cw)
 
        self._show_page("inicio")
 
    # ------------------------------------------------------------------
    def _drag_start(self, e):
        self._drag_x, self._drag_y = e.x, e.y
 
    def _drag_move(self, e):
        nx = self.win.winfo_x() + e.x - self._drag_x
        ny = self.win.winfo_y() + e.y - self._drag_y
        self.win.geometry(f"+{nx}+{ny}")
 
    # ------------------------------------------------------------------
    def _card(self, parent):
        return RoundedCard(parent, bg=self.PANEL_BG, outline=self.BORDER, radius=18)
 
    def _section_lbl(self, parent, text):
        tk.Label(parent, text=text, bg=self.BG, fg=self.TEXT_MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 6))
 
    # ------------------------------------------------------------------
    def _build_inicio(self, page, cw):
        # status row
        sr = tk.Frame(page, bg=self.BG)
        sr.pack(fill="x", pady=(10, 10))
        tk.Label(sr, text="STATUS", bg=self.BG, fg=self.TEXT_MUTED,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self.status_dot = tk.Canvas(sr, width=10, height=10,
                                    bg=self.BG, highlightthickness=0)
        self.status_dot.pack(side="left", padx=(10, 4))
        self._dot_id = self.status_dot.create_oval(1, 1, 9, 9,
                                                    fill=self.SUCCESS, outline="")
        self.status_label = tk.Label(sr, text="ATIVO ✨", bg=self.BG,
                                      fg=self.SUCCESS, font=("Segoe UI", 10, "bold"))
        self.status_label.pack(side="left")
 
        # card região
        rc = self._card(page)
        rc.pack(fill="x", pady=(0, 10))
        rb_out = rc.body
        tk.Label(rb_out, text="🗺️  Região da tela", bg=self.PANEL_BG,
                 fg=self.TEXT_MUTED, font=("Segoe UI", 8, "bold"),
                 anchor="w").pack(fill="x", padx=14, pady=(12, 6))
        rb = tk.Frame(rb_out, bg=self.PANEL_BG)
        rb.pack(fill="x", padx=14, pady=(0, 12))
 
        pv = tk.Canvas(rb, width=68, height=48, bg=self.ACCENT_SOFT,
                       highlightthickness=0)
        pv.pack(side="left")
        _draw_rounded_rect(pv, 3, 3, 65, 45, radius=10,
                           outline=self.ACCENT, width=2, dash=(4, 3), fill="")
 
        info = tk.Frame(rb, bg=self.PANEL_BG)
        info.pack(side="left", fill="x", expand=True, padx=12)
        self.region_var = tk.StringVar(value=self._format_region(self._region))
        tk.Label(info, textvariable=self.region_var, bg=self.PANEL_BG,
                 fg=self.TEXT_MAIN, font=("Consolas", 9),
                 justify="left", anchor="w").pack(fill="x")
 
        RoundedButton(rb, text="Selecionar área ✏️",
                      fill=self.ACCENT, hover=self.ACCENT_H,
                      radius=14, command=self._change_area).pack(side="right")
 
        # card OCR
        oc = self._card(page)
        oc.pack(fill="x", pady=(0, 12))
        ob = oc.body
        tk.Label(ob, text="🔍  Último texto lido pelo OCR", bg=self.PANEL_BG,
                 fg=self.TEXT_MUTED, font=("Segoe UI", 8, "bold"),
                 anchor="w").pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(ob, textvariable=self.overlay.last_ocr_var,
                 wraplength=cw-60, justify="left", anchor="w",
                 bg=self.PANEL_BG, fg=self.TEXT_MAIN,
                 font=("Segoe UI", 9)).pack(fill="x", padx=14, pady=(0, 12))
 
        # botões
        self.pause_btn = RoundedButton(
            page, text="⏸️  Parar tradução",
            fill=self.ACCENT, hover=self.ACCENT_H,
            radius=16, pady=12, command=self._toggle_pause,
        )
        self.pause_btn.pack(fill="x", pady=(0, 8))
 
        RoundedButton(
            page, text="✕  Fechar tradutor",
            fill=self.CARD_BG, hover=self.DANGER,
            fg=self.DANGER, fg_hover="#ffffff",
            outline=self.DANGER, radius=16, pady=10,
            command=self._close_program,
        ).pack(fill="x")
 
    # ------------------------------------------------------------------
    def _build_aparencia(self, page, cw):
        self._section_lbl(page, "🎨  APARÊNCIA DA TRADUÇÃO")
 
        card = self._card(page)
        card.pack(fill="x")
        body = card.body
 
        color_row = tk.Frame(body, bg=self.PANEL_BG)
        color_row.pack(fill="x", padx=14, pady=(14, 8))
        tk.Label(color_row, text="Cor do texto", bg=self.PANEL_BG,
                 fg=self.TEXT_MAIN, font=("Segoe UI", 9)).pack(side="left")
        self.color_preview = tk.Label(
            color_row, text="  ", bg=self.overlay._text_color,
            highlightbackground=self.BORDER, highlightthickness=1,
        )
        self.color_preview.pack(side="right", padx=(8, 0))
        RoundedButton(
            color_row, text="Escolher… 🎨",
            fill=self.PANEL_BG, hover=self.BORDER,
            fg=self.TEXT_MAIN, outline=self.BORDER,
            font=("Segoe UI", 9), padx=12, pady=6,
            radius=12, command=self._pick_color,
        ).pack(side="right")
 
        size_row = tk.Frame(body, bg=self.PANEL_BG)
        size_row.pack(fill="x", padx=14, pady=(0, 16))
        tk.Label(size_row, text="Tamanho máx. da fonte",
                 bg=self.PANEL_BG, fg=self.TEXT_MAIN,
                 font=("Segoe UI", 9)).pack(anchor="w")
        self.size_scale = ttk.Scale(
            size_row, from_=self.overlay.min_font_size, to=72,
            orient="horizontal", style="Soft.Horizontal.TScale",
            command=self._on_size_change,
        )
        self.size_scale.set(self.overlay.max_font_size)
        self.size_scale.pack(fill="x", pady=(4, 0))
 
    # ------------------------------------------------------------------
    def _build_atalhos(self, page, cw):
        self._section_lbl(page, "⌨️  ATALHOS DE TECLADO")
 
        card = self._card(page)
        card.pack(fill="x")
        body = card.body
 
        shortcuts = [
            ("F9",  "Encerrar o tradutor"),
            ("F10", "Selecionar uma nova área"),
        ]
        for i, (key, desc) in enumerate(shortcuts):
            row = tk.Frame(body, bg=self.PANEL_BG)
            row.pack(fill="x", padx=14,
                     pady=(14 if i == 0 else 0,
                            14 if i == len(shortcuts)-1 else 10))
            badge = tk.Label(row, text=key, bg=self.ACCENT_SOFT,
                              fg=self.ACCENT, font=("Segoe UI", 9, "bold"),
                              padx=10, pady=4)
            badge.pack(side="left")
            tk.Label(row, text=desc, bg=self.PANEL_BG,
                     fg=self.TEXT_MAIN, font=("Segoe UI", 9)
                     ).pack(side="left", padx=(12, 0))
 
        tk.Label(page, text="Funcionam mesmo com o jogo em foco  🎮",
                 bg=self.BG, fg=self.TEXT_MUTED,
                 font=("Segoe UI", 8), anchor="w",
                 ).pack(fill="x", pady=(10, 0))
 
    # ------------------------------------------------------------------
    def _show_page(self, key):
        self._cur_page = key
        self._pages[key].tkraise()
        for k, lbl in self._nav_labels.items():
            if k == key:
                lbl.config(bg=self.ACCENT, fg="#060c1a")
            else:
                lbl.config(bg=self.CARD_BG, fg=self.TEXT_MUTED)
 
    # ------------------------------------------------------------------
    def _setup_styles(self):
        s = self._style
        s.configure("Soft.Horizontal.TScale",
                     background=self.PANEL_BG,
                     troughcolor=self.BORDER)
 
    # ------------------------------------------------------------------
    @staticmethod
    def _format_region(region):
        if not region or not region.get("width"):
            return "X: —    Y: —\nL: —    A: —"
        return (
            f"X: {region.get('left', 0)}    Y: {region.get('top', 0)}\n"
            f"L: {region.get('width', 0)}    A: {region.get('height', 0)}"
        )
 
    def update_region_info(self, region):
        self._region = dict(region) if region else {}
        self.region_var.set(self._format_region(self._region))
 
    def _pick_color(self):
        result = colorchooser.askcolor(
            color=self.overlay._text_color, title="Escolha a cor do texto"
        )
        color = result[1]
        if color:
            self.overlay.set_text_color(color)
            self.color_preview.config(bg=color)
 
    def _on_size_change(self, value):
        self.overlay.set_max_font_size(value)
 
    def _set_status(self, paused):
        color = self.PAUSE_COL if paused else self.SUCCESS
        self.status_dot.itemconfig(self._dot_id, fill=color)
        self.status_label.config(
            text="PAUSADO ⏸️" if paused else "ATIVO ✨", fg=color)
 
    def _toggle_pause(self):
        global pause_flag
        self.paused = not self.paused
        pause_flag  = self.paused
        if self.paused:
            self._text_before_pause = self.overlay.text_var.get()
            self.overlay.update_text("[Pausado]")
            self.pause_btn.config(text="▶️  Retomar tradução")
        else:
            self.overlay.update_text(self._text_before_pause)
            self.pause_btn.config(text="⏸️  Parar tradução")
        self._set_status(self.paused)
 
    def _change_area(self):
        global reselect_flag
        reselect_flag = True
 
    def _close_program(self):
        global stop_flag
        stop_flag = True
 
 
 
def ocr_loop(region_holder, overlay, control_panel=None):
    global reselect_flag
    translator = GoogleTranslator(source=SRC_LANG, target=TGT_LANG)
    pending_hash = None       # último hash de pixels visto (ainda "em observação")
    pending_since = None      # desde quando esse hash está parado
    last_processed_hash = None  # último hash que já foi lido/traduzido com sucesso (ou definitivamente desistido)
    last_text = ""
    overlay_visible = True
 
    # Quando o OCR lê e o resultado parece "lixo", isso pode ser um lapso
    # isolado (ex: capturou bem no meio de uma sombra/efeito visual,
    # mesmo com os pixels já "parados") e não necessariamente significa
    # que a área não tem texto de verdade. Antes, o script marcava esse
    # frame como "já processado" e NUNCA mais tentava de novo enquanto a
    # tela ficasse parada -- então um único lapso de OCR travava a
    # tradução pro resto daquela fala. Agora damos algumas chances de
    # tentar ler de novo (com uma pausa entre tentativas) antes de
    # desistir de vez e aceitar como lixo mesmo.
    GARBAGE_MAX_RETRIES = 3
    garbage_retry_hash = None
    garbage_retry_count = 0
 
    with mss.mss() as sct:
        while not stop_flag:
            try:
                if reselect_flag:
                    reselect_flag = False
                    overlay.root.after(0, overlay.update_text, "Selecione a nova área...")
                    new_region = select_region()
                    if new_region.get("width") and new_region.get("height"):
                        region_holder["region"] = new_region
                        save_region(new_region)
                        overlay.root.after(0, overlay.reposition, new_region)
                        if control_panel is not None:
                            overlay.root.after(0, control_panel.update_region_info, new_region)
                    pending_hash = None
                    pending_since = None
                    last_processed_hash = None
                    last_text = ""
                    garbage_retry_hash = None
                    garbage_retry_count = 0
 
                # Pausado pelo Painel de Controle -> não captura nem
                # traduz nada, só fica esperando (reselect/fechar ainda
                # funcionam normalmente mesmo pausado).
                if pause_flag:
                    time.sleep(POLL_INTERVAL)
                    continue
 
                region = region_holder["region"]
                target_process = region.get("process")
 
                # Se a área selecionada está travada num processo específico
                # (jogo), só captura/traduz enquanto ele estiver em foco.
                # Quando o usuário troca de janela, o overlay some sozinho.
                if target_process:
                    current_process = get_foreground_process_name()
                    if current_process != target_process:
                        if overlay_visible:
                            overlay.root.after(0, overlay.root.withdraw)
                            overlay_visible = False
                        time.sleep(POLL_INTERVAL)
                        continue
                    elif not overlay_visible:
                        overlay.root.after(0, overlay.root.deiconify)
                        overlay_visible = True
                        # Volta a observar do zero ao reaparecer.
                        pending_hash = None
                        pending_since = None
                        last_processed_hash = None
                        garbage_retry_hash = None
                        garbage_retry_count = 0
 
                # 1) Captura rápida só pra ver SE os pixels da região mudaram
                #    (pode incluir nosso próprio texto, sem problema, é só
                #    gatilho de "ainda mudando" vs "parado").
                quick_shot = sct.grab(region)
                quick_hash = hashlib.md5(quick_shot.raw).hexdigest()
                now = time.monotonic()
 
                if quick_hash != pending_hash:
                    # Pixels mudaram de novo (provavelmente ainda digitando
                    # o texto, ou trocou de fala) -> reinicia a contagem de
                    # "tempo parado".
                    pending_hash = quick_hash
                    pending_since = now
 
                elif (
                    pending_hash != last_processed_hash
                    and (now - pending_since) >= SETTLE_DELAY
                ):
                    # 2) Pixels ficaram parados por tempo suficiente -> a
                    #    animação de digitação (se houver) já terminou.
                    #    Agora sim vale a pena ler o texto.
                    current_text = overlay.text_var.get()
                    if current_text not in ("", "..."):
                        overlay.root.after(0, overlay.text_var.set, "")
                        time.sleep(0.015)
 
                    clean_shot = sct.grab(region)
                    # Cada tentativa de retry usa uma variante diferente
                    # de pré-processamento de imagem (ver
                    # read_text_from_capture) -- repetir a MESMA variante
                    # na mesma imagem sempre dá o mesmo resultado, então
                    # variar aumenta a chance de uma das tentativas
                    # conseguir ler direito o que a outra não conseguiu.
                    retry_count_for_this_hash = (
                        garbage_retry_count if pending_hash == garbage_retry_hash else 0
                    )
                    ocr_variant = min(retry_count_for_this_hash, 2)
                    raw_text = read_text_from_capture(clean_shot, variant=ocr_variant)
 
                    if current_text not in ("", "..."):
                        overlay.root.after(0, overlay.text_var.set, current_text)
 
                    is_garbage = raw_text and looks_like_ocr_garbage(raw_text)
                    if DEBUG:
                        print(f"[debug] OCR leu: {raw_text!r} | lixo? {bool(is_garbage)}")
 
                    if is_garbage:
                        # Pode ter sido um lapso isolado do OCR (ex:
                        # capturou no meio de uma sombra/efeito visual
                        # mesmo com os pixels já parados). Em vez de
                        # desistir na primeira leitura ruim e travar
                        # pro resto da fala, conta quantas vezes seguidas
                        # esse MESMO frame deu "lixo" e dá mais algumas
                        # chances antes de aceitar como lixo de vez.
                        if pending_hash != garbage_retry_hash:
                            garbage_retry_hash = pending_hash
                            garbage_retry_count = 0
                        garbage_retry_count += 1
 
                        if garbage_retry_count < GARBAGE_MAX_RETRIES:
                            display_text = raw_text if raw_text else "(vazio)"
                            display_text += f"  [lixo, tentando de novo {garbage_retry_count}/{GARBAGE_MAX_RETRIES - 1}...]"
                            overlay.root.after(0, overlay.last_ocr_var.set, display_text)
                            # NÃO marca como processado -> empurra
                            # "pending_since" pra frente, o que faz o
                            # loop esperar outro SETTLE_DELAY e tentar
                            # ler de novo, em vez de tentar a cada
                            # POLL_INTERVAL (que seria rápido demais e
                            # gastaria à toa).
                            pending_since = now
                            time.sleep(POLL_INTERVAL)
                            continue
 
                        # Esgotou as tentativas -> desiste de vez desse
                        # frame (provável lixo de verdade) e mantém a
                        # tradução anterior na tela.
                        last_processed_hash = pending_hash
                        display_text = raw_text if raw_text else "(vazio)"
                        display_text += "  [descartado como lixo]"
                        overlay.root.after(0, overlay.last_ocr_var.set, display_text)
                        time.sleep(POLL_INTERVAL)
                        continue
 
                    # Leitura válida -> marca como processado de vez e
                    # zera o contador de retry de lixo.
                    last_processed_hash = pending_hash
                    garbage_retry_hash = None
                    garbage_retry_count = 0
 
                    display_text = raw_text if raw_text else "(vazio)"
                    overlay.root.after(0, overlay.last_ocr_var.set, display_text)
 
                    if raw_text and raw_text != last_text:
                        last_text = raw_text
                        try:
                            translated = translate_with_glossary(translator, prepare_text_for_translation(raw_text))
                        except Exception as e:
                            translated = f"[erro ao traduzir: {e}]"
                        if DEBUG:
                            print(f"[debug] traduzido: {translated!r}")
                        overlay.root.after(0, overlay.update_text, translated)
                    elif not raw_text and last_text:
                        last_text = ""
                        overlay.root.after(0, overlay.update_text, "...")
 
                time.sleep(POLL_INTERVAL)
 
            except Exception as loop_err:
                # Qualquer erro inesperado (captura, OCR, etc.) não derruba
                # mais o programa: só registra no console e segue rodando.
                print(f"[aviso] erro ignorado no loop de tradução: {loop_err}")
                time.sleep(POLL_INTERVAL)
 
    overlay.root.after(0, overlay.close)
 
 
def main():
    saved = load_saved_region()
 
    if saved:
        print(f"Região salva encontrada: {saved}")
        print("Usando a última área selecionada. Pressione F10 a qualquer momento para escolher uma nova área.")
        region = saved
        # Configurações salvas por uma versão antiga do script ainda não
        # tinham a "trava" no processo do jogo. Detecta agora, pra já
        # funcionar pausando ao trocar de janela sem precisar reselecionar.
        if region.get("width") and region.get("height") and not region.get("process"):
            cx = region["left"] + region["width"] // 2
            cy = region["top"] + region["height"] // 2
            region["process"] = get_process_name_at(cx, cy)
    else:
        print("Selecione a região da tela com o texto do jogo...")
        region = select_region()
 
    if not region.get("width") or not region.get("height"):
        print("Nenhuma região selecionada. Encerrando.")
        return
 
    save_region(region)
    region_holder = {"region": region}
 
    if region.get("process"):
        print(f"Tradutor travado na janela: {region['process']}")
        print("Ele pausa e some automaticamente quando você troca de janela.")
    else:
        print("Não foi possível identificar a janela do jogo automaticamente;")
        print("o tradutor vai ficar ativo o tempo todo, em qualquer janela.")
 
    print(f"Região em uso: {region}")
    print("Iniciando tradução ao vivo.")
    print("  F9  = encerrar o tradutor")
    print("  F10 = selecionar uma nova área (sem fechar o programa)")
    print("Abriu também o Painel de Controle (cor, tamanho da fonte, pausar, etc).")
 
    overlay = OverlayWindow(region)
    control_panel = ControlPanel(overlay, region)
 
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
 
    t = threading.Thread(target=ocr_loop, args=(region_holder, overlay, control_panel), daemon=True)
    t.start()
 
    overlay.root.mainloop()
 
 
if __name__ == "__main__":
    main()
