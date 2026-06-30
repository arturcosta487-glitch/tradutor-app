# Tradutor PT-BR — Sistema de Key

Três partes, nessa ordem de configuração:

```
translator-app/
├── server/      -> API que gera e confere as keys (sobe no Render)
├── website/     -> página onde a pessoa pega a key
└── desktop/     -> o app final (launcher.py + tradutor_overlay.py),
                    isso é o que você transforma em .exe
```

---

## 1) Subir o servidor (Render, de graça)

1. Crie um repositório no GitHub com só a pasta `server/` (`app.py` +
   `requirements.txt`).
2. Entre em https://render.com → **New +** → **Web Service** → conecte
   esse repositório.
3. Configurações do serviço:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
4. Crie. Em alguns minutos o Render te dá uma URL tipo:
   `https://tradutor-key-server.onrender.com`

Guarde essa URL — você vai colar ela em **dois** lugares (passo 2 e 3).

> O plano free do Render "dorme" depois de uns minutos sem uso e demora
> ~30s pra acordar na primeira chamada do dia. Pra um app pessoal/grupo
> pequeno isso não costuma incomodar.

---

## 2) Configurar o site (`website/index.html`)

Abra `index.html` e troque a linha:

```js
const BASE_URL = "https://SEU-SERVIDOR-AQUI.onrender.com";
```

pela URL real do passo 1. Depois é só hospedar esse `index.html` em
qualquer lugar grátis (Render Static Site, Netlify, Vercel ou até
GitHub Pages — é um arquivo só, sem build).

---

## 3) Configurar o app desktop (`desktop/`)

Abra `launcher.py` e troque:

```python
BASE_URL = "https://SEU-SERVIDOR-AQUI.onrender.com"   # mesma URL do passo 1
SUPPORT_URL = "https://discord.gg/SEU-SERVIDOR-AQUI"  # seu discord, se tiver
```

### Gerando o `.exe` (escolha uma opção)

**Opção A — automático, sem instalar nada (recomendado):**

Esse projeto já vem com um workflow do GitHub Actions
(`.github/workflows/build.yml`) que builda o `.exe` num Windows de
verdade, na nuvem, e te entrega pronto pra baixar:

1. Suba esse repositório inteiro pro GitHub (a mesma conta que você
   usou pro servidor, pode ser o mesmo repo ou um separado).
2. Vá na aba **Actions** do repositório → você vai ver o workflow
   **"Build TradutorPT.exe"** já rodando (ele dispara sozinho quando
   sobe algo na pasta `desktop/`). Se não disparar, clique nele →
   **Run workflow**.
3. Quando terminar (ícone verde ✅, leva uns 2-3 minutos), entre na
   execução e baixe o artefato **TradutorPT** — dentro dele está o
   `TradutorPT.exe` pronto.

Toda vez que você editar algo em `desktop/` e subir pro GitHub, ele
gera um `.exe` novo automaticamente.

**Opção B — buildar na sua própria máquina Windows:**

```
pip install requests pyinstaller mss pytesseract pillow deep-translator pynput
pyinstaller --onefile --noconsole --name TradutorPT launcher.py
```

(rode dentro da pasta `desktop/`) — gera `desktop/dist/TradutorPT.exe`.

---

De qualquer uma das duas formas, o resultado é o mesmo: **um único
executável**. A pessoa clica duas vezes, cai na tela de key, e se a key
for válida o tradutor abre direto, sem `.bat` e sem terminal aparecendo.

> O Tesseract OCR continua precisando ser instalado separadamente no PC
> de quem for usar (é um programa C++ grande, não dá pra embutir no
> .exe). Isso já valia pro script original — só mantém as instruções
> que já tinham no topo do `tradutor_overlay.py`.

---

## Como funciona a trava de key

- Cada key gerada no site começa "livre" (sem dono).
- Na primeira vez que alguém usa essa key no app, o servidor grava o
  **HWID** (uma "impressão digital" do PC) junto com a key.
- Da próxima vez, só valida de novo se for o **mesmo PC**. Em outro PC,
  a validação falha com "key já está em uso em outro computador".

Se alguém trocar de computador e precisar reusar a key, dá pra liberar
na mão chamando (com curl, Postman, etc.):

```
POST https://SEU-SERVIDOR/api/keys/<A-KEY>/reset-hwid
```

E pra desativar uma key de vez:

```
POST https://SEU-SERVIDOR/api/keys/<A-KEY>/deactivate
```

(Essas duas rotas não têm tela — são só pra você usar manualmente por
enquanto. Se quiser um painel visual depois, dá pra fazer.)
