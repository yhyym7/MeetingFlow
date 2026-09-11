"""One-time public model downloads; never uses the DeepSeek key."""
import os
os.environ['HF_HUB_DISABLE_XET'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'

from huggingface_hub import snapshot_download
from app.config import get_settings


def main():
    root = get_settings().model_dir
    for repo, directory, files in [
        ('Systran/faster-whisper-base', 'whisper-base', ['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt']),
        ('Qdrant/bge-small-zh-v1.5', 'bge-small-zh', ['*.json', 'vocab.txt', 'model_optimized.onnx']),
    ]:
        print(f'Downloading {repo}', flush=True)
        snapshot_download(repo, local_dir=root / directory, allow_patterns=files, max_workers=2)
    print('Local models ready.', flush=True)


if __name__ == '__main__':
    main()
