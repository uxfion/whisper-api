from fastapi import FastAPI, Form, UploadFile, File
from fastapi import HTTPException, status
import datetime
import time
import uvicorn

import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Union, Optional

from datetime import timedelta

import numpy as np
import whisper

app = FastAPI()

#url https://api.openai.com/v1/audio/transcriptions \
#  -H "Authorization: Bearer $OPENAI_API_KEY" \
#  -H "Content-Type: multipart/form-data" \
#  -F model="whisper-1" \
#  -F file="@/path/to/file/openai.mp3"

#{
#  "text": "Imagine the wildest idea that you've ever had, and you're curious about how it might scale to something that's a 100, a 1,000 times bigger..."
#}

# -----
# copied from https://github.com/hayabhay/whisper-ui

# Whisper transcription functions
# ----------------
@lru_cache(maxsize=1)
def get_whisper_model(whisper_model: str):
    """Get a whisper model from the cache or download it if it doesn't exist"""
    model = whisper.load_model(whisper_model)
    return model

def transcribe(audio_path: str, whisper_model: str, **whisper_args):
    """Transcribe the audio file using whisper"""

    # Get whisper model
    # NOTE: If mulitple models are selected, this may keep all of them in memory depending on the cache size
    transcriber = get_whisper_model(whisper_model)

    # Set configs & transcribe
    if whisper_args["temperature_increment_on_fallback"] is not None:
        whisper_args["temperature"] = tuple(
            np.arange(whisper_args["temperature"], 1.0 + 1e-6, whisper_args["temperature_increment_on_fallback"])
        )
    else:
        whisper_args["temperature"] = [whisper_args["temperature"]]

    del whisper_args["temperature_increment_on_fallback"]

    transcript = transcriber.transcribe(
        audio_path,
        **whisper_args,
    )

    return transcript

def transcribe_yue(audio_path: str, whisper_model: str, **whisper_args):
    """Transcribe the audio file using whisper"""

    # Get whisper model
    # NOTE: If mulitple models are selected, this may keep all of them in memory depending on the cache size
    transcriber = get_whisper_model(whisper_model)

    # Set configs & transcribe
    if whisper_args["temperature_increment_on_fallback"] is not None:
        whisper_args["temperature"] = tuple(
            np.arange(whisper_args["temperature"], 1.0 + 1e-6, whisper_args["temperature_increment_on_fallback"])
        )
    else:
        whisper_args["temperature"] = [whisper_args["temperature"]]

    del whisper_args["temperature_increment_on_fallback"]

    start_time = time.time()
    audio = whisper.load_audio(audio_path)
    audio = whisper.pad_or_trim(audio)
    mel = whisper.log_mel_spectrogram(audio, n_mels=128).to(transcriber.device)
    _, probs = transcriber.detect_language(mel)
    print("\n\n")
    print(f"Time: {datetime.datetime.now()}")
    print(f"First detected language: {max(probs, key=probs.get)}")
    print(f"en:  {round(probs['en'], 6)}")
    print(f"zh:  {round(probs['zh'], 6)}")
    print(f"yue: {round(probs['yue'], 6)}")
    if probs["yue"] > 0.001:
        whisper_args["language"] = "yue"
        print(f"Final detected language: yue")
    elif probs["yue"] <= 0.001 and max(probs, key=probs.get) == 'zh':
        whisper_args["language"] = "zh"
        whisper_args["initial_prompt"] = "以下是普通话的句子"
        print(f"Final detected language: zh")
    else:
        print(f"Final detected language: {max(probs, key=probs.get)}")

    transcript = transcriber.transcribe(
        audio_path,
        **whisper_args,
    )
    end_time = time.time()
    print(f"Cost time: {end_time - start_time:.4f}s")
    print(f"Result: '''\n{transcript['text']}\n'''")

    return transcript


WHISPER_DEFAULT_SETTINGS = {
#    "whisper_model": "base",
    "whisper_model": "large-v3",
    "temperature": 0.0,
    "temperature_increment_on_fallback": 0.2,
    "no_speech_threshold": 0.6,
    "logprob_threshold": -1.0,
    "compression_ratio_threshold": 2.4,
    "condition_on_previous_text": True,
    "verbose": False,
#    "verbose": True,
    "task": "transcribe",
#    "task": "translation",
}

UPLOAD_DIR="/tmp/whisper/"
# -----

@app.post('/v1/audio/transcriptions')
async def transcriptions(model: str = Form(...),
                         file: UploadFile = File(...),
                         response_format: Optional[str] = Form(None),
                         prompt: Optional[str] = Form(None),
                         temperature: Optional[float] = Form(None),
                         language: Optional[str] = Form(None)):

    assert model == "whisper-1"
    if file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bad Request, bad file"
            )
    if response_format is None:
        response_format = 'json'
    if response_format not in ['json',
                           'text',
                           'srt',
                           'verbose_json',
                           'vtt']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bad Request, bad response_format"
            )
    if temperature is None:
        temperature = 0.0
    if temperature < 0.0 or temperature > 1.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bad Request, bad temperature"
            )

    filename = file.filename
    fileobj = file.file
    upload_name = os.path.join(UPLOAD_DIR, filename)
    upload_file = open(upload_name, 'wb+')
    shutil.copyfileobj(fileobj, upload_file)
    upload_file.close()

    transcript = transcribe_yue(audio_path=upload_name, **WHISPER_DEFAULT_SETTINGS)


    if response_format in ['text']:
        return transcript['text']

    if response_format in ['srt']:
        ret = ""
        for seg in transcript['segments']:
            
            td_s = timedelta(milliseconds=seg["start"]*1000)
            td_e = timedelta(milliseconds=seg["end"]*1000)

            t_s = f'{td_s.seconds//3600:02}:{(td_s.seconds//60)%60:02}:{td_s.seconds%60:02}.{td_s.microseconds//1000:03}'
            t_e = f'{td_e.seconds//3600:02}:{(td_e.seconds//60)%60:02}:{td_e.seconds%60:02}.{td_e.microseconds//1000:03}'

            ret += '{}\n{} --> {}\n{}\n\n'.format(seg["id"], t_s, t_e, seg["text"])
        ret += '\n'
        return ret

    if response_format in ['vtt']:
        ret = "WEBVTT\n\n"
        for seg in transcript['segments']:
            td_s = timedelta(milliseconds=seg["start"]*1000)
            td_e = timedelta(milliseconds=seg["end"]*1000)

            t_s = f'{td_s.seconds//3600:02}:{(td_s.seconds//60)%60:02}:{td_s.seconds%60:02}.{td_s.microseconds//1000:03}'
            t_e = f'{td_e.seconds//3600:02}:{(td_e.seconds//60)%60:02}:{td_e.seconds%60:02}.{td_e.microseconds//1000:03}'

            ret += "{} --> {}\n{}\n\n".format(t_s, t_e, seg["text"])
        return ret

    if response_format in ['verbose_json']:
        transcript.setdefault('task', WHISPER_DEFAULT_SETTINGS['task'])
        transcript.setdefault('duration', transcript['segments'][-1]['end'])
        if transcript['language'] == 'ja':
            transcript['language'] = 'japanese'
        return transcript

    return {'text': transcript['text']}

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=10087)
