import numpy as np
import soxr
import torch
from silero_vad import VADIterator, load_silero_vad

torch.set_num_threads(1)
VAD_MODEL = load_silero_vad(onnx=True)

VAD_RATE = 16000
FRAME = 512
MAX_SEGMENTS_S = 15
KEEP_HISTORY = VAD_RATE # works as padding

class Segmenter:
    def __init__(self, in_rate, on_segment, threshold=0.5, min_silence_ms=500, speech_pad_ms=200):
        self.in_rate = in_rate
        self.on_segment = on_segment
        self.resampler = soxr.ResampleStream(in_rate, VAD_RATE, 1, dtype="float32")
        self.vad = VADIterator(VAD_MODEL, threshold=threshold, sampling_rate=VAD_RATE, min_silence_duration_ms=min_silence_ms, speech_pad_ms=speech_pad_ms)
        self.buf = np.zeros(0, dtype=np.float32)
        self.buf_start = 0
        self.fed = 0
        self.seg_start = None

    def feed(self, audio_bytes, last=False):
        x = np.frombuffer(audio_bytes, dtype="<i2").astype(np.float32) / 32768.0 # squashes the int value to -1.0 to 1.0
        y = self.resampler.resample_chunk(x, last=last)
        self.buf = np.concatenate([self.buf, y])

        buf_end = self.buf_start + len(self.buf)
        while self.fed + FRAME <= buf_end:
            i = self.fed - self.buf_start
            event = self.vad(self.buf[i:i + FRAME])
            self.fed += FRAME

            if event and "start" in event:
                self.seg_start = event["start"]
            elif event and "end" in event and self.seg_start is not None:
                self._emit(self.seg_start, event["end"])
                self.seg_start = None
            elif self.seg_start is not None and self.fed - self.seg_start >= MAX_SEGMENTS_S * VAD_RATE:
                self._emit(self.seg_start, self.fed)
                self.seg_start = self.fed

        self._trim()

    def finish(self):
        self.feed(b"", last=True)
        if self.seg_start is not None:
            self._emit(self.seg_start, self.fed)
            self.seg_start = None

    def to_original_sample(self, s16):
        return round(s16 * self.in_rate / VAD_RATE)

    def _emit(self, start, end):
        a = max(start, self.buf_start) - self.buf_start
        b = end - self.buf_start
        self.on_segment(start, self.buf[a:b].copy())

    def _trim(self):
        keep_from = self.seg_start if self.seg_start is not None else self.fed - KEEP_HISTORY
        drop = max(0, keep_from - self.buf_start)
        if drop:
            self.buf = self.buf[drop:]
            self.buf_start += drop