#!/usr/bin/env python3
"""Мини-пайплайн речевой аналитики для локальной проверки концепции.

Стерео-звонок (левый канал = клиент, правый = оператор) →
разделение каналов → ASR (faster-whisper, large-v3-turbo int8) →
слияние реплик по таймкодам → метрики (talk ratio, перебивания) →
классификация правилами (живой разговор / автоответчик / спам-блок / нет ответа).

Это уменьшенная копия прод-архитектуры из docs/02-architecture.md:
в проде вместо правил добавляется LLM-классификатор, вместо одной машины — GPU-кластер.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

BASE = Path(__file__).parent
TEST_DATA = BASE / "test_data"
OUT = BASE / "out"

AM_PATTERNS = [  # признаки автоответчика
    "оставьте", "сообщение после сигнала", "позвоните позднее", "перезвоните",
    "не могу ответить", "запишите", "автоответчик",
]
ROBOT_PATTERNS = [  # признаки спам-блокировщика / робота
    "внесён в чёрный список", "внесен в черный список", "отклонил звонок",
    "соединение будет завершено", "автоматический помощник",
]
HALLUCINATIONS = {  # типичные галлюцинации Whisper на тишине/музыке
    "продолжение следует", "субтитры", "спасибо за просмотр", "до новых встреч",
}


def sh(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def extract_channels(wav: Path, tmpdir: Path) -> tuple[Path, Path]:
    """Левый канал → клиент, правый → оператор (16 кГц моно)."""
    left, right = tmpdir / "left.wav", tmpdir / "right.wav"
    sh(["ffmpeg", "-y", "-i", str(wav), "-af", "pan=mono|c0=c0", "-ar", "16000", str(left)])
    sh(["ffmpeg", "-y", "-i", str(wav), "-af", "pan=mono|c0=c1", "-ar", "16000", str(right)])
    return left, right


def load_pcm(path: Path) -> np.ndarray:
    """Декодирование через ffmpeg в float32 16 кГц моно (обход несовместимости faster-whisper × PyAV>=14)."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ar", "16000", "-ac", "1", "-f", "f32le", "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32)


def transcribe(model: WhisperModel, wav: Path, max_dur: float) -> list[dict]:
    segments, _ = model.transcribe(
        load_pcm(wav), language="ru", beam_size=1, vad_filter=True,
        condition_on_previous_text=False,  # не тянуть контекст — меньше повторов/галлюцинаций
    )
    out = []
    for s in segments:
        text = s.text.strip()
        norm = text.lower().rstrip(".…! ").strip()
        if (not text or norm in HALLUCINATIONS
                or s.no_speech_prob > 0.6 or s.avg_logprob < -1.0):
            continue
        out.append({
            "start": round(min(s.start, max_dur), 2),
            "end": round(min(s.end, max_dur), 2),
            "text": text,
        })
    return out


def speech_dur(segs: list[dict]) -> float:
    return sum(s["end"] - s["start"] for s in segs)


def merge(left: list[dict], right: list[dict]) -> tuple[list[dict], int]:
    """Единая хронология реплик + число перебиваний (пересечение сегментов каналов)."""
    events = [
        {"start": s["start"], "end": s["end"], "speaker": "клиент", "text": s["text"]}
        for s in left
    ] + [
        {"start": s["start"], "end": s["end"], "speaker": "оператор", "text": s["text"]}
        for s in right
    ]
    events.sort(key=lambda e: e["start"])
    interruptions = 0
    for a in events:
        if a["speaker"] == "клиент":
            continue
        for b in left:  # оператор начал говорить до конца реплики клиента
            if b["end"] - a["start"] > 0.15 and a["start"] >= b["start"]:
                interruptions += 1
                break
    return events, interruptions


def classify(events: list[dict], left: list[dict], right: list[dict], duration: float) -> dict:
    # Фразы ищем в канале КЛИЕНТА: автоответчик/робот звучат со стороны вызываемого абонента,
    # оператор при этом тоже может говорить в трубку — поэтому односторонность не критерий.
    c_text = " ".join(s["text"].lower() for s in left)
    text = c_text + " " + " ".join(s["text"].lower() for s in right)
    c_dur, o_dur = speech_dur(left), speech_dur(right)
    one_sided = max(c_dur, o_dur) / max(c_dur + o_dur, 0.01) > 0.85
    tags = []

    if any(p in c_text for p in ROBOT_PATTERNS):
        call_type, conf, tags = "спам-блокировка", 0.95, ["робот"]
    elif any(p in c_text for p in AM_PATTERNS):
        call_type, conf, tags = "автоответчик", 0.9, ["голосовая почта"]
    elif c_dur + o_dur < 2.0:
        call_type, conf = "нет ответа", 0.8
    elif one_sided:
        call_type, conf = "монолог (уточнить)", 0.5
    else:
        call_type, conf = "живой разговор", 0.85
        if any(w in text for w in ("скидк", "заявку", "замер")):
            tags += ["интерес", "следующий шаг"]

    return {
        "type": call_type,
        "confidence": conf,
        "tags": tags,
        "metrics": {
            "client_speech_s": round(c_dur, 1),
            "operator_speech_s": round(o_dur, 1),
            "talk_ratio_client_%": round(100 * c_dur / (c_dur + o_dur), 1) if c_dur + o_dur else 0,
        },
    }


def audio_duration(wav: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(wav)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    model_name = sys.argv[1] if len(sys.argv) > 1 else "large-v3-turbo"
    print(f"Загрузка модели {model_name} (int8)…")
    t0 = time.perf_counter()
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=8)
    print(f"  модель готова за {time.perf_counter() - t0:.1f} с\n")

    total_audio, total_wall = 0.0, 0.0
    for wav in sorted(TEST_DATA.glob("*.wav")):
        dur = audio_duration(wav)
        t0 = time.perf_counter()
        with tempfile_dir() as tmpdir:
            left, right = extract_channels(wav, tmpdir)
            left_segs, right_segs = transcribe(model, left, dur), transcribe(model, right, dur)
        events, interruptions = merge(left_segs, right_segs)
        verdict = classify(events, left_segs, right_segs, dur)
        wall = time.perf_counter() - t0
        total_audio += dur
        total_wall += wall

        result = {
            "file": wav.name, "duration_s": round(dur, 1),
            "processing_s": round(wall, 1), "rtf": round(wall / dur, 2),
            **verdict, "interruptions": interruptions, "transcript": events,
        }
        (OUT / f"{wav.stem}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print(f"▶ {wav.name}  ({dur:.0f} c аудио → {wall:.1f} c обработки, RTF {wall/dur:.2f})")
        print(f"  Тип: {verdict['type']}  (уверенность {verdict['confidence']})  теги: {verdict['tags'] or '—'}")
        print(f"  Речь клиент/оператор: {verdict['metrics']['client_speech_s']}с / "
              f"{verdict['metrics']['operator_speech_s']}с, перебиваний: {interruptions}")
        for e in events:
            print(f"    [{e['start']:6.2f}–{e['end']:6.2f}] {e['speaker']:9s} | {e['text']}")
        print()

    print(f"Итого: {total_audio:.0f} с аудио обработано за {total_wall:.1f} с "
          f"(средний RTF {total_wall/total_audio:.2f}; на прод-GPU L40S ожидаем RTF ≈ 0.013–0.025, "
          f"т.е. в ~{(total_wall/total_audio)/0.025:.0f}–{(total_wall/total_audio)/0.013:.0f} раз быстрее)")


class tempfile_dir:
    def __enter__(self) -> Path:
        import tempfile
        self._d = tempfile.mkdtemp(prefix="poc_")
        return Path(self._d)

    def __exit__(self, *exc) -> None:
        import shutil
        shutil.rmtree(self._d, ignore_errors=True)


if __name__ == "__main__":
    main()
