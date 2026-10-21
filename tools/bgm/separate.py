"""인트로 소리에서 목소리(내레이션)를 걷어 내고 음악만 남긴다 (Demucs htdemucs)."""
import numpy as np
import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model

SRC = '/tmp/gl/hg/bgm/intro.wav'
wav, sr = sf.read(SRC, always_2d=True)
model = get_model('htdemucs')
model.eval()
assert sr == model.samplerate, (sr, model.samplerate)
x = torch.tensor(wav.T, dtype=torch.float32)
ref = x.mean(0)
mu, sd = ref.mean(), ref.std()
with torch.no_grad():
    out = apply_model(model, ((x - mu) / sd)[None], device='cpu', shifts=4, split=True, overlap=0.25, progress=False)[0]
out = out * sd + mu
for name, stem in zip(model.sources, out):
    sf.write(f'/tmp/gl/hg/bgm/stem_{name}.wav', stem.numpy().T, sr)
acc = sum(out[i] for i, n in enumerate(model.sources) if n != 'vocals')
sf.write('/tmp/gl/hg/bgm/accomp.wav', acc.numpy().T, sr)


def db(a):
    return 20 * np.log10(np.sqrt(np.mean(np.square(a))) + 1e-12)


print('sources', model.sources)
for name, stem in zip(model.sources, out):
    print(f'{name:7s} rms {db(stem.numpy()):6.1f} dBFS')
print(f'accomp  rms {db(acc.numpy()):6.1f} dBFS | original {db(wav):6.1f} dBFS')
