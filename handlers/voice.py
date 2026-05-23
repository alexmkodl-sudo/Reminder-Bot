"""
Модуль распознавания голосовых сообщений через OpenAI Whisper API.
"""
import io
from typing import Optional

import requests

from utils.logger import logger

WHISPER_API_URL = "https://api.openai.com/v1/audio/transcriptions"


def transcribe_voice(audio_bytes: bytes, api_key: str) -> Optional[str]:
    """
    Отправляет аудио в OpenAI Whisper и возвращает распознанный текст.

    :param audio_bytes: байты OGG-файла (формат Telegram voice)
    :param api_key: ключ OpenAI API
    :return: распознанный текст или None при ошибке
    """
    try:
        response = requests.post(
            WHISPER_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={
                # Telegram отдаёт голосовые в OGG/Opus
                "file": ("voice.ogg", io.BytesIO(audio_bytes), "audio/ogg"),
            },
            data={
                "model": "whisper-1",
                "language": "ru",  # Указываем язык для точности
                "response_format": "text",
            },
            timeout=30,
        )
        response.raise_for_status()
        text = response.text.strip()
        logger.info(f"Whisper transcribed: '{text[:80]}{'...' if len(text) > 80 else ''}'")
        return text if text else None

    except requests.exceptions.Timeout:
        logger.error("Whisper API timeout")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"Whisper API HTTP error: {e.response.status_code} — {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Whisper transcription error: {e}")
        return None
