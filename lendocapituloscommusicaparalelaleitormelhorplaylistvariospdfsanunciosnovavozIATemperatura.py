from gtts import gTTS
import pygame
import os
import tempfile
import time
from pydub import AudioSegment
import pdfplumber
import re
import random
from datetime import datetime, timedelta
import csv
from pydub import AudioSegment
from kokoro import KPipeline
import soundfile as sf
import numpy as np
from datetime import datetime
from datetime import datetime, timedelta
from meteostat import Point, Hourly
import geocoder
import sys

# Força saída UTF-8 no Windows
if os.name == "nt":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# ======================================================
#     SISTEMA DE ÁUDIO
# ======================================================

canal_musica = None
musica_loop = None


def inicializar_pygame():
    if not pygame.mixer.get_init():
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)


def inicializar_canais():
    global canal_musica
    pygame.mixer.set_num_channels(8)
    canal_musica = pygame.mixer.Channel(0)


# ======================================================
#     LEITURA E LIMPEZA DO PDF
# ======================================================

def limpar_texto_preservando_estrutura(texto):
    """Remove caracteres especiais mas preserva marcadores de capítulos."""
    if not texto:
        return ""
    
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    texto = re.sub(r'-\s*\n\s*', '', texto)
    texto = re.sub(r'[•○●■□▪▫]', '', texto)
    texto = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', texto)
    texto = re.sub(r'\S+@\S+', '', texto)
    
    return texto.strip()


def limpar_texto_para_leitura(texto):
    """Limpeza mais agressiva para o texto que será lido."""
    if not texto:
        return ""
    
    texto = re.sub(r'\n+', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'[–—―]', '-', texto)
    texto = re.sub(r'\b\d{1,3}\b(?=\s|$)', '', texto)
    texto = re.sub(r'\(\s*\d+\s*\)', '', texto)
    texto = re.sub(r'\[\s*\]', '', texto)
    texto = re.sub(r'[*_]{1,2}', '', texto)
    texto = re.sub(r'\s+([,.!?;:])', r'\1', texto)
    texto = re.sub(r'([,.!?;:])\s*', r'\1 ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    
    return texto.strip()


def extrair_texto_pdf(caminho_pdf):
    """Extrai texto do PDF usando pdfplumber."""
    try:
        texto_completo = ""
        
        with pdfplumber.open(caminho_pdf) as pdf:
            print(f"📄 Extraindo {len(pdf.pages)} páginas...")
            
            for i, page in enumerate(pdf.pages, 1):
                texto = page.extract_text()
                if texto:
                    texto_limpo = limpar_texto_preservando_estrutura(texto)
                    if texto_limpo:
                        texto_completo += texto_limpo + "\n\n"
                
                if i % 10 == 0:
                    print(f"   Processadas {i} páginas...")
        
        print(f"✓ Extração concluída: {len(texto_completo)} caracteres")
        return texto_completo
        
    except Exception as e:
        print(f"✗ Erro ao extrair PDF: {e}")
        return None


def extrair_texto_txt(caminho_txt):
    """Extrai texto de arquivo TXT."""
    try:
        with open(caminho_txt, 'r', encoding='utf-8') as f:
            texto = f.read()
        
        print(f"✓ Lido arquivo TXT: {len(texto)} caracteres")
        return limpar_texto_preservando_estrutura(texto)
        
    except Exception as e:
        print(f"✗ Erro ao ler TXT: {e}")
        return None


def dividir_em_capitulos(texto):
    """Divide o texto em capítulos ou seções."""
    
    padroes = [
        r'(?:^|\n)[\s]*(?:CAPÍTULO|Capítulo|CAPITULO|Capitulo|CHAPTER|Chapter)[\s]+([IVXLCDM\d]+)[\s]*[:\-\.]?[\s]*([^\n]{0,100})',
        r'(?:^|\n)[\s]*(\d+)[\s]*[:\-\.][\s]*([A-ZÀÁÂÃÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜÝ][^\n]{10,100})',
        r'(?:^|\n)[\s]*([IVXLCDM]+)[\s]*[:\-\.][\s]*([A-ZÀÁÂÃÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜÝ][^\n]{10,100})',
    ]

    posicoes = []

    for padrao in padroes:
        for match in re.finditer(padrao, texto, re.MULTILINE | re.IGNORECASE):
            titulo_completo = match.group(0).strip()
            posicoes.append((match.start(), titulo_completo, match.group(1).strip()))

    posicoes = list(set(posicoes))
    posicoes.sort(key=lambda x: x[0])

    print(f"\n🔍 Encontrados {len(posicoes)} possíveis capítulos")
    
    capitulos = []

    if not posicoes or len(posicoes) < 2:
        print("⚠️  Poucos capítulos detectados. Dividindo em seções de tamanho fixo...")
        tamanho_bloco = 3000
        num_secoes = max(1, len(texto) // tamanho_bloco)
        
        for i in range(num_secoes):
            inicio = i * tamanho_bloco
            fim = min((i + 1) * tamanho_bloco, len(texto))
            trecho = texto[inicio:fim].strip()
            
            if trecho and len(trecho) > 100:
                ultimo_ponto = trecho.rfind('.')
                if ultimo_ponto > len(trecho) * 0.7:
                    trecho = trecho[:ultimo_ponto+1]
                
                capitulos.append({
                    "numero": i + 1,
                    "titulo": f"Seção {i + 1}",
                    "texto": limpar_texto_para_leitura(trecho)
                })
        
        return capitulos

    for i, (pos, titulo, numero) in enumerate(posicoes):
        pos_fim = posicoes[i+1][0] if i + 1 < len(posicoes) else len(texto)
        trecho = texto[pos:pos_fim].strip()
        
        primeira_linha = trecho.split('\n')[0]
        if len(primeira_linha) < 200:
            trecho = '\n'.join(trecho.split('\n')[1:])

        trecho_limpo = limpar_texto_para_leitura(trecho)
        
        if trecho_limpo and len(trecho_limpo) > 200:
            capitulos.append({
                "numero": numero,
                "titulo": titulo,
                "texto": trecho_limpo
            })
            print(f"   ✓ {titulo[:50]}...")

    print(f"\n📚 Total de {len(capitulos)} capítulos extraídos")
    return capitulos


# ======================================================
#     CARREGAMENTO DE ARQUIVOS DO REPOSITÓRIO
# ======================================================

def carregar_arquivos_repositorio(pasta_repositorio):
    """Carrega todos os PDFs e TXTs da pasta repositório."""
    try:
        if not os.path.exists(pasta_repositorio):
            print(f"✗ Pasta {pasta_repositorio} não encontrada")
            return []
        
        arquivos = []
        
        for arquivo in os.listdir(pasta_repositorio):
            caminho_completo = os.path.join(pasta_repositorio, arquivo)
            
            if arquivo.lower().endswith('.pdf'):
                arquivos.append({
                    'tipo': 'pdf',
                    'caminho': caminho_completo,
                    'nome': arquivo
                })
            elif arquivo.lower().endswith('.txt'):
                arquivos.append({
                    'tipo': 'txt',
                    'caminho': caminho_completo,
                    'nome': arquivo
                })
        
        if not arquivos:
            print(f"✗ Nenhum arquivo PDF ou TXT encontrado em {pasta_repositorio}")
            return []
        
        print(f"📚 Encontrados {len(arquivos)} arquivos no repositório:")
        for i, arquivo in enumerate(arquivos, 1):
            print(f"   {i}. [{arquivo['tipo'].upper()}] {arquivo['nome']}")
        
        return arquivos
    
    except Exception as e:
        print(f"✗ Erro ao carregar repositório: {e}")
        return []


def processar_arquivo(info_arquivo):
    """Processa um arquivo (PDF ou TXT) e retorna seus capítulos."""
    print(f"\n📖 Processando: {info_arquivo['nome']}")
    
    if info_arquivo['tipo'] == 'pdf':
        texto = extrair_texto_pdf(info_arquivo['caminho'])
    else:  # txt
        texto = extrair_texto_txt(info_arquivo['caminho'])
    
    if not texto:
        print(f"✗ Não foi possível extrair texto de {info_arquivo['nome']}")
        return []
    
    capitulos = dividir_em_capitulos(texto)
    
    # Adiciona informação do arquivo de origem aos capítulos
    for cap in capitulos:
        cap['arquivo_origem'] = info_arquivo['nome'].replace('.pdf', '').replace('.txt', '')
        cap['tipo_arquivo'] = info_arquivo['tipo']
    
    return capitulos


# ======================================================
#     MÚSICA EM LOOP
# ======================================================

def carregar_musicas_playlist(pasta_playlist):
    """Carrega todas as músicas da pasta playlist."""
    try:
        if not os.path.exists(pasta_playlist):
            print(f"✗ Pasta {pasta_playlist} não encontrada")
            return []
        
        extensoes_validas = ('.mp3', '.wav', '.ogg', '.flac')
        musicas = [
            os.path.join(pasta_playlist, f) 
            for f in os.listdir(pasta_playlist) 
            if f.lower().endswith(extensoes_validas)
        ]
        
        if not musicas:
            print(f"✗ Nenhuma música encontrada em {pasta_playlist}")
            return []
        
        print(f"🎵 Encontradas {len(musicas)} músicas na playlist:")
        for i, musica in enumerate(musicas, 1):
            nome = os.path.basename(musica)
            print(f"   {i}. {nome}")
        
        return musicas
    
    except Exception as e:
        print(f"✗ Erro ao carregar playlist: {e}")
        return []


def iniciar_musica_fundo(musica_path, volume_musica=-20):
    global musica_loop, canal_musica

    try:
        inicializar_pygame()
        inicializar_canais()

        musica_loop = pygame.mixer.Sound(musica_path)
        musica_loop.set_volume(10 ** (volume_musica / 20))

        canal_musica.play(musica_loop, loops=-1)
        nome_musica = os.path.basename(musica_path)
        print(f"🎶 Tocando: {nome_musica}")

    except Exception as e:
        print(f"✗ Erro ao iniciar música: {e}")


def trocar_musica_fundo(musica_path, volume_musica=-20):
    """Troca a música de fundo com fade suave."""
    global musica_loop, canal_musica
    
    try:
        if canal_musica and canal_musica.get_busy():
            canal_musica.fadeout(500)
            time.sleep(0.6)
        
        iniciar_musica_fundo(musica_path, volume_musica)
        
    except Exception as e:
        print(f"✗ Erro ao trocar música: {e}")


def parar_musica_fundo():
    global canal_musica
    if canal_musica:
        canal_musica.fadeout(1000)
        time.sleep(1.1)


# ======================================================
#     TTS
# ======================================================

def ajustar_velocidade_audio(audio, velocidade):
    if velocidade > 1.0:
        return audio.speedup(playback_speed=velocidade)
    novo = audio._spawn(
        audio.raw_data,
        overrides={'frame_rate': int(audio.frame_rate * velocidade)}
    ).set_frame_rate(audio.frame_rate)
    return novo


# Inicializa pipeline (pt-br = código 'b')
pipeline = KPipeline(lang_code='p')   # 'b' = Brazilian Portuguese


def texto_para_audio(texto, voz='pf_dora', velocidade=1.0, formato='mp3'):
    """
    Converte texto em áudio usando Kokoro TTS para português brasileiro.
    
    Parâmetros:
    - texto: string com o texto a ser convertido
    - voz: nome da voz Kokoro para PT-BR
           Opções disponíveis:
           * 'af_sky' (feminina, brasileira)
           * 'af_bella' (feminina, americana)
           * 'am_adam' (masculina, americana)
    - velocidade: fator de velocidade (1.0 = normal, 0.5 = metade, 2.0 = dobro)
    - formato: 'mp3' ou 'wav'
    
    Retorna:
    - Caminho do arquivo de áudio gerado ou None em caso de erro
    """
    
    try:
        # Define a voz brasileira como padrão se não especificado
        # af_sky é uma das vozes com melhor suporte para PT-BR
        if voz not in ['af_sky', 'af_bella', 'am_adam']:
            # print(f"⚠ Voz '{voz}' não reconhecida, usando 'af_sky'")
            voz = 'pf_dora'  # Kokoro PT-BR padrão
        
        # Executa o gerador de áudio do Kokoro com a voz PT-BR
        # print(f"🎙️ Gerando áudio com voz '{voz}'...")
        generator = pipeline(texto, voice=voz)
        
        # Junta todos os segmentos de áudio gerados
        audio_final = []
        for _, _, audio in generator:
            audio_final.extend(audio)
        
        # Verifica se há áudio gerado
        if not audio_final:
            print("✗ Nenhum áudio foi gerado")
            return None
        
        # Converte lista para array numpy
        audio_np = np.array(audio_final, dtype='float32')
        
        # Normaliza o áudio para evitar distorções
        if np.max(np.abs(audio_np)) > 0:
            audio_np = audio_np / np.max(np.abs(audio_np)) * 0.95
        
        # Cria arquivo WAV temporário
        temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        wav_path = temp_wav.name
        temp_wav.close()
        
        # Salva WAV (Kokoro utiliza 24000 Hz)
        sf.write(wav_path, audio_np, 24000)
        # print(f"✓ Áudio WAV gerado: {wav_path}")
        
        # Se o usuário pedir WAV, retorna direto
        if formato.lower() == 'wav':
            return wav_path
        
        # --- Conversão para MP3 ---
        # print("🔄 Convertendo para MP3...")
        audio = AudioSegment.from_wav(wav_path)
        
        # Ajuste de velocidade (se necessário)
        # if velocidade != 1.0:
        #     print(f"⚡ Ajustando velocidade para {velocidade}x")
        #     # audio = audio.speedup(playback_speed=velocidade)
        
        # Cria arquivo MP3 temporário
        temp_mp3 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        mp3_path = temp_mp3.name
        temp_mp3.close()
        
        # Exporta como MP3 com qualidade alta
        audio.export(mp3_path, format="mp3", bitrate="192k")
        
        # Remove WAV temporário
        os.remove(wav_path)
        
        # print(f"✓ Áudio MP3 gerado: {mp3_path}")
        return mp3_path
    
    except ImportError as e:
        print(f"✗ Erro de importação: {e}")
        print("💡 Instale as dependências: pip install kokoro-onnx soundfile pydub numpy")
        return None
    
    except Exception as e:
        print(f"✗ Erro no Kokoro TTS: {e}")
        return None



# ======================================================
#     REPRODUÇÃO DE ÁUDIO
# ======================================================

def reproduzir_audio(arquivo):
    if not arquivo or not os.path.exists(arquivo):
        print("✗ Arquivo inválido para reprodução")
        return

    try:
        inicializar_pygame()
        inicializar_canais()

        pygame.mixer.music.load(arquivo)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.05)

        pygame.mixer.music.unload()
        time.sleep(0.05)

    except Exception as e:
        print(f"✗ Erro reprodução: {e}")


# ======================================================
#     LEITOR COMPLETO MULTI-ARQUIVOS
# ======================================================

def ler_repositorio_com_musica(
        pasta_repositorio,
        pasta_playlist,
        idioma='pt-br',
        velocidade=1.3,
        ordem_aleatoria=True,
        volume_musica=-20):

    print("\n" + "="*50)
    print("  📚 RÁDIO LIBERTADORA - REPOSITÓRIO COMPLETO")
    print("="*50 + "\n")

    # Carrega músicas
    musicas = carregar_musicas_playlist(pasta_playlist)
    if not musicas:
        print("✗ Sem músicas disponíveis. Abortando.")
        return
    
    if ordem_aleatoria:
        random.shuffle(musicas)
        print("🔀 Músicas em ordem aleatória\n")

    # Carrega arquivos do repositório
    arquivos = carregar_arquivos_repositorio(pasta_repositorio)
    if not arquivos:
        print("✗ Nenhum arquivo encontrado. Abortando.")
        return

    # Processa todos os arquivos e coleta capítulos
    print("\n" + "="*50)
    print("  📖 PROCESSANDO ARQUIVOS")
    print("="*50)
    
    todos_capitulos = []
    
    for arquivo in arquivos:
        capitulos = processar_arquivo(arquivo)
        todos_capitulos.extend(capitulos)
    
    if not todos_capitulos:
        print("✗ Nenhum capítulo encontrado em nenhum arquivo")
        return
    
    print(f"\n📚 Total: {len(todos_capitulos)} capítulos de {len(arquivos)} arquivos")
    
    # Embaralha capítulos se modo aleatório
    if ordem_aleatoria:
        random.shuffle(todos_capitulos)
        print("🔀 Capítulos em ordem aleatória\n")

    # Inicia reprodução
    try:
        for i, cap in enumerate(todos_capitulos, 1):
            
            # Seleciona música
            musica_atual = musicas[(i - 1) % len(musicas)]
            
            print(f"\n" + "="*50)
            print(f"📖 [{i}/{len(todos_capitulos)}] {cap['titulo']}")
            print(f"📚 Livro: {cap['arquivo_origem']}")
            print("="*50)
            
            # Troca música
            if i == 1:
                iniciar_musica_fundo(musica_atual, volume_musica)
            else:
                print(f"🎵 Trocando música...")
                trocar_musica_fundo(musica_atual, volume_musica)
            
            time.sleep(0.5)
            # print("\n"
            # "█████████████████████████████████████████████████████████████████████████████████████████████\n"
            # "█▄─▄▄▀██▀▄─██▄─▄▄▀█▄─▄█─▄▄─███▄─▄███▄─▄█▄─▄─▀█▄─▄▄─█▄─▄▄▀█─▄─▄─██▀▄─██▄─▄▄▀█─▄▄─█▄─▄▄▀██▀▄─██\n"
            # "██─▄─▄██─▀─███─██─██─██─██─████─██▀██─███─▄─▀██─▄█▀██─▄─▄███─████─▀─███─██─█─██─██─▄─▄██─▀─██\n"
            # "▀▄▄▀▄▄▀▄▄▀▄▄▀▄▄▄▄▀▀▄▄▄▀▄▄▄▄▀▀▀▄▄▄▄▄▀▄▄▄▀▄▄▄▄▀▀▄▄▄▄▄▀▄▄▀▄▄▀▀▄▄▄▀▀▄▄▀▄▄▀▄▄▄▄▀▀▄▄▄▄▀▄▄▀▄▄▀▄▄▀▄▄▀\n"
            # "█████████████████████████████████████████████████████████████████████████████████████████████\n")
            # print("\n\n")

            print(f"░░█▀▀▀▀▀▀▀▀▀▀▀▀▀▀█\n"
                "██▀▀▀██▀▀▀▀▀▀██▀▀▀██\n"
                "█▒▒▒▒▒█▒▀▀▀▀▒█▒▒▒▒▒█\n"
                "█▒▒▒▒▒█▒████▒█▒▒▒▒▒█\n"
                "██▄▄▄██▄▄▄▄▄▄██▄▄▄██\n")

            # Anúncio de início
            anuncio_inicio = f"Livro {cap['arquivo_origem']}, trecho {cap['titulo']}."
            print(f"🔊 Anunciando capítulo...")
            
            audio_anuncio = texto_para_audio(anuncio_inicio, idioma, 1.3)
            if audio_anuncio:
                time.sleep(3.0)
                reproduzir_audio(audio_anuncio)
                time.sleep(0.3)
                try:
                    os.remove(audio_anuncio)
                except:
                    pass

            # Leitura do conteúdo
            print(f"📢 Lendo conteúdo ({len(cap['texto'])} caracteres)...")
            audio_cap = texto_para_audio(cap['texto'], idioma, velocidade)

            if audio_cap:
                reproduzir_audio(audio_cap)
                time.sleep(0.3)
                try:
                    os.remove(audio_cap)
                except:
                    pass

            # Anúncio de encerramento
            anuncio_fim = f"Este foi o trecho do livro {cap['numero']}, {cap['titulo']}. Do livro {cap['arquivo_origem']}."
            print(f"✅ Encerrando capítulo...")
            
            audio_fim = texto_para_audio(anuncio_fim, idioma, 1.3)
            if audio_fim:
                reproduzir_audio(audio_fim)
                time.sleep(7.0)
                # pega a hora atual para inserir no áudio
                agora = datetime.now()
                reproduzir_audio(texto_para_audio(f"{agora.hour} horas e {agora.minute} minutos", idioma, 1.3))
                time.sleep(1.0)
                reproduzir_audio(texto_para_audio(temperatura_agora(), idioma, 1.3))
                time.sleep(1.0)
                reproduzir_audio(texto_para_audio("Rádio Libertadora. A sua rádio pessoal de liberdade e conhecimento!", idioma, 1.3))
                time.sleep(15.0)

                # Anuncios
                # Baixa CSV de anuncios e seleciona um aleatório
                arquivo = csv.reader(open('./anuncios/anuncios.csv', 'r', encoding='utf-8'))
                anuncios_lista = [row[0] for row in arquivo if row]
                anuncio_aleatorio = random.choice(anuncios_lista) if anuncios_lista else None

                if anuncio_aleatorio:
                    reproduzir_audio(texto_para_audio(anuncio_aleatorio, idioma, 1.3))
                    time.sleep(5.0)
                    reproduzir_audio(texto_para_audio("Você está ouvindo a Rádio Libertadora!", idioma, 1.3))
                    time.sleep(3.0)
                
                reproduzir_audio(texto_para_audio("Fique agora com outro capítulo de um livro aleatório do seu repositório de textos!", idioma, 1.3))
                time.sleep(3.0)
                try:
                    os.remove(audio_fim)
                except:
                    pass

            print(f"✓ Capítulo {i} concluído")
            #Limpa tela
            os.system('cls' if os.name == 'nt' else 'clear')

    except KeyboardInterrupt:
        print("\n\n⏸️  Leitura interrompida pelo usuário")
    except Exception as e:
        print(f"\n✗ Erro durante leitura: {e}")
    finally:
        print("\n🎵 Encerrando música...")
        parar_musica_fundo()
        time.sleep(0.5)

    print("\n✨ Leitura concluída!\n")


def pegar_localizacao():
    g = geocoder.ip('me')
    return g.latlng if g.ok else None

def temperatura_agora():
    coords = pegar_localizacao()
    if not coords:
        return "Não foi possível detectar sua localização."

    lat, lon = coords
    agora = datetime.now()
    
    inicio = agora - timedelta(hours=1)
    fim = agora
    
    ponto = Point(lat, lon)
    dados = Hourly(ponto, inicio, fim).fetch()

    if dados.empty:
        return "Não há dados climáticos disponíveis para sua região agora."

    temperatura = dados['temp'].iloc[-1]
    return f"Agora fazem {temperatura:.1f}°C em {geocoder.ip('me').city}."

# ======================================================
#     MAIN
# ======================================================

if __name__ == "__main__":

    pasta_repositorio = "./repositorio"  # Pasta com PDFs e TXTs
    pasta_playlist = "./playlist"        # Pasta com as músicas

    # Exemplo de uso: Vancouver
    
    ler_repositorio_com_musica(
        pasta_repositorio,
        pasta_playlist,
        idioma='pt-br',
        velocidade=1.3,
        ordem_aleatoria=True,
        volume_musica=-10
    )