
import librosa
import numpy as np

class AudioLoader:
    def __init__(self, sample_rate=22050):
        self.sample_rate = sample_rate
    
    def load_audio(self, file_path: str):
        audio, sr = librosa.load(file_path, sr=self.sample_rate)
        return audio
            