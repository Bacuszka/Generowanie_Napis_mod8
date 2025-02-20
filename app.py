import streamlit as st
import hashlib
import tempfile
import os
import srt
from pydub import AudioSegment
from io import BytesIO
from dotenv import load_dotenv
import openai
from datetime import timedelta
import imageio_ffmpeg as ffmpeg  # Dodaj import na początku


# Załaduj zmienne środowiskowe
load_dotenv()

# Sprawdzenie lokalizacji ffprobe (możesz wyświetlić to w konsoli, jeśli potrzebujesz)
ffprobe_path = ffmpeg.get_ffmpeg_exe()
print("FFprobe path:", ffprobe_path)  # To wyświetli ścieżkę do ffprobe w konsoli

st.markdown(
    """
    <style>
    video {
        max-width: 700px;
        width: 800px;
        height: 600px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

def get_md5(file_data):
    hasher = hashlib.md5()
    hasher.update(file_data)
    return hasher.hexdigest()

def process_video(file):
    file_data = file.read()
    file_md5 = get_md5(file_data)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
        temp_file.write(file_data)
        temp_filename = temp_file.name

    st.subheader("Przesłane wideo: 🎥")
    st.video(temp_filename, format="video/mp4", start_time=0)
    
    st.session_state["video_path"] = temp_filename
    st.session_state["video_filename"] = file.name.rsplit(".", 1)[0]

    if st.button("Wyodrębnij audio z wideo 🎧"):
        extract_audio()

def extract_audio():
    video_path = st.session_state.get("video_path", None)
    if not video_path:
        st.error("Najpierw załaduj plik wideo.")
        return

    try:
        audio = AudioSegment.from_file(video_path)
        audio_mp3 = BytesIO()
        audio.export(audio_mp3, format="mp3")
        audio_mp3.seek(0)

        st.subheader("Wyodrębnione audio: 🎵")
        st.markdown("<h4 style='font-size: 20px;'>Po transkrypcji drugi odtwarzacz zniknie. ❌</h4>", unsafe_allow_html=True)
        st.audio(audio_mp3, format="audio/mp3")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio_file:
            temp_audio_file.write(audio_mp3.read())
            temp_audio_filename = temp_audio_file.name

        st.session_state["audio_path"] = temp_audio_filename
        st.success("Audio zostało wyodrębnione!")
    except Exception as e:
        st.error(f"Nie udało się wyodrębnić dźwięku. Błąd: {str(e)}")

def transcribe_audio():
    audio_path = st.session_state.get("audio_path", None)
    if not audio_path:
        st.error("Najpierw wyodrębnij audio.")
        return
    
    try:
        client = openai.DeepAI(api_key=st.session_state.openai_api_key)
        with open(audio_path, "rb") as f:
            with st.spinner("Transkrypcja w toku..."):
                transcript = client.audio.transcriptions.create(
                    file=f,
                    model="whisper-1",
                    response_format="verbose_json"
                )

        segments = transcript.segments
        transcript_text = "\n".join([segment.text for segment in segments])
        st.session_state["transcript_text"] = transcript_text
        st.session_state["segments"] = segments
        st.success("Transkrypcja zakończona! Możesz teraz edytować tekst.")

        # Generowanie podsumowania zaraz po transkrypcji
        generate_summary()
    except Exception as e:
        st.error(f"Nie udało się uzyskać transkrypcji. Błąd: {str(e)}")

def generate_srt():
    if "segments" not in st.session_state:
        st.error("Brak transkrypcji do zapisania.")
        return

    transcript_text = st.session_state.get("transcript_text", "")
    edited_segments = transcript_text.split("\n")

    subtitles = []
    for i, (segment, text) in enumerate(zip(st.session_state["segments"], edited_segments)):
        start_time = timedelta(seconds=segment.start)
        end_time = timedelta(seconds=segment.end)
        subtitles.append(srt.Subtitle(index=i+1, start=start_time, end=end_time, content=text))
    
    srt_data = srt.compose(subtitles)
    st.session_state["srt_text"] = srt_data
    st.success("Napisy w formacie .srt zostały wygenerowane!")

def translate_srt():
    if "srt_text" not in st.session_state:
        st.error("Najpierw wygeneruj plik SRT.")
        return
    
    client = openai.DeepAI(api_key=st.session_state.openai_api_key)
    
    with st.spinner("Tłumaczenie na język polski..."):
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "system", "content": "Przetłumacz następujące napisy SRT na język polski, zachowując formatowanie."},
                      {"role": "user", "content": st.session_state["srt_text"]}]
        )
    
    # Zapisz przetłumaczone napisy w session_state
    st.session_state["srt_text_translated"] = response.choices[0].message.content
    st.success("Napisy przetłumaczone na język polski!")

def generate_summary():
    transcript_text = st.session_state.get("transcript_text", "")
    if not transcript_text:
        st.error("Brak transkrypcji do podsumowania.")
        return
    
    try:
        client = openai.DeepAI(api_key=st.session_state.openai_api_key)
        with st.spinner("Generowanie podsumowania..."):
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "system", "content": "Na podstawie poniższej transkrypcji, stwórz krótki opis filmu (do 300 znaków)."},
                          {"role": "user", "content": transcript_text}]
            )
        
        summary = response.choices[0].message.content.strip()
        st.session_state["summary"] = summary[:300]  # Ogranicz do 300 znaków
        st.success("Podsumowanie zostało wygenerowane!")
    except Exception as e:
        st.error(f"Nie udało się wygenerować podsumowania. Błąd: {str(e)}")

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    api_key = st.text_input("Podaj swój klucz API DeepAI", type="password")
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
        st.session_state.openai_api_key = api_key
        st.success("Klucz API DeepAI został ustawiony.")
else:
    st.session_state.openai_api_key = api_key
    st.success("Klucz API DeepAI załadowany z pliku .env.")

# Inicjalizacja klucza session_state "srt_text_translated" jeśli nie istnieje
if "srt_text_translated" not in st.session_state:
    st.session_state["srt_text_translated"] = ""

st.title("Generowanie napisów do filmu 🧾")
st.subheader("""
Aplikacja do transkrypcji wideo

Opis
Aplikacja umożliwia użytkownikowi przesłanie pliku wideo, wyodrębnienie z niego dźwięku,
transkrypcję mowy na tekst, generowanie napisów SRT oraz opcjonalne ich tłumaczenie na język polski.
Dodatkowo generuje podsumowanie filmu na podstawie transkrypcji.

Funkcje:

1. Wyodrębnienie audio z wideo
2. Transkrypcja audio na tekst
3. Generowanie napisów .srt
4. Tłumaczenie tekstu na język polski
5. Generowanie podsumowania

Uwagi:
* Użytkownik powinien mieć własny klucz API DeepAI.
* Użytkownik przesyła plik wideo w formatach (mp4, mov, avi).

""")
uploaded_file = st.file_uploader("Wybierz plik wideo 🎬", type=["mp4", "mov", "avi"])
if uploaded_file:
    process_video(uploaded_file)

# Pokazanie audio playera, jeżeli istnieje
if "audio_path" in st.session_state:
    audio_file = st.session_state.get("audio_path", None)
    if audio_file:
        st.audio(audio_file, format="audio/mp3")

if "audio_path" in st.session_state:
    if st.button("Transkrybuj z Whisper-1 [Open AI] 🤖"):
        transcribe_audio()

if "transcript_text" in st.session_state:
    # Ustawienie text_area na edytowalny tekst do pliku SRT
    transcript_text = st.text_area("Edytuj transkrypcję: ✏️", st.session_state["transcript_text"], height=300)
    st.session_state["transcript_text"] = transcript_text
    if st.button("Wygeneruj napisy .srt 🧾"):
        generate_srt()

    if st.button("Przetłumacz na polski 🥟🇵🇱"):
        translate_srt()
        # Zaktualizuj text_area na przetłumaczony tekst
        st.session_state["transcript_text"] = st.session_state["srt_text_translated"]
        transcript_text = st.session_state["transcript_text"]
        st.text_area("Edytuj transkrypcję:", transcript_text, height=300)

    # Opcja schowania/wyświetlenia podsumowania
    if "summary" in st.session_state:
        with st.expander("Podsumowanie filmu (kliknij, aby rozwinąć) 👁‍🗨"):
            st.write(st.session_state["summary"])

# Wyświetl przycisk "Pobierz napisy .srt" tylko wtedy, gdy napisy są dostępne
if "srt_text" in st.session_state:
    video_filename = st.session_state.get("video_filename", "napisy")  # Pobierz nazwę pliku z session_state
    srt_filename = f"{video_filename}.srt"
    st.download_button("Pobierz napisy (.srt) 💾", st.session_state["srt_text"], file_name=srt_filename, mime="text/plain")

# Wyświetl przycisk "Pobierz przetłumaczone napisy" tylko po tłumaczeniu
if "srt_text_translated" in st.session_state and st.session_state["srt_text_translated"]:
    video_filename = st.session_state.get("video_filename", "napisy")  # Pobierz nazwę pliku z session_state
    translated_srt_filename = f"{video_filename}_PL.srt"
    st.download_button("Pobierz przetłumaczone napisy (.srt)🧑‍🎤", st.session_state["srt_text_translated"], file_name=translated_srt_filename, mime="text/plain")