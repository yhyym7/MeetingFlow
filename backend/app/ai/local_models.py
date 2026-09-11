"""Small CPU models, loaded lazily from local files without runtime downloads."""
from functools import lru_cache
from threading import Lock

from app.config import get_settings

EMBEDDING_ID = 'bge-small-zh-v1.5:mean200:v1'
_asr_lock, _embedding_lock = Lock(), Lock()


@lru_cache
def asr_model():
    from faster_whisper import WhisperModel
    path = get_settings().model_dir / 'whisper-base'
    if not (path / 'model.bin').is_file():
        raise RuntimeError('ASR_MODEL_MISSING')
    return WhisperModel(str(path), device='cpu', compute_type='int8', cpu_threads=4, local_files_only=True)


def transcribe(path):
    from faster_whisper.audio import decode_audio
    with _asr_lock:
        import av
        with av.open(str(path)) as container:
            if container.duration and container.duration / av.time_base > get_settings().asr_max_seconds:
                raise RuntimeError('ASR_TOO_LONG')
        samples = decode_audio(str(path), sampling_rate=16000)
        if len(samples) / 16000 > get_settings().asr_max_seconds:
            raise RuntimeError('ASR_TOO_LONG')
        segments, _ = asr_model().transcribe(samples, language='zh', beam_size=3, vad_filter=True,
                                            initial_prompt='以下是简体中文的会议记录。',
                                            condition_on_previous_text=False)
        result = '\n'.join(segment.text.strip() for segment in segments if segment.text.strip())
        if not result:
            raise RuntimeError('ASR_NO_SPEECH')
        if len(result) > 12000:
            raise RuntimeError('ASR_TOO_LONG')
        return result


@lru_cache
def embedding_model():
    from fastembed import TextEmbedding
    path = get_settings().model_dir / 'bge-small-zh'
    if not (path / 'model_optimized.onnx').is_file():
        raise RuntimeError('EMBEDDING_MODEL_MISSING')
    return TextEmbedding('BAAI/bge-small-zh-v1.5', specific_model_path=str(path),
                         local_files_only=True, threads=2)


def embed_texts(texts: list[str]) -> list[list[float]]:
    import numpy as np
    with _embedding_lock:
        model = embedding_model()
        # Existing 600-character chunks can exceed the model's 512-token input.
        # Average short windows so the end of each source is not silently lost.
        results = []
        for text in texts:
            windows = [text[i:i + 200] for i in range(0, len(text), 160)] or ['']
            vectors = list(model.embed(windows))
            vector = np.mean(vectors, axis=0)
            vector /= max(float(np.linalg.norm(vector)), 1e-12)
            results.append(vector.tolist())
        return results
