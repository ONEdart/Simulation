
import torch
import tensorflow as tf
from pathlib import Path

class ModelLoader:
    def __init__(self, model_dir: str):
        self.model_dir = Path(model_dir)
    
    def load_pytorch_model(self, model_path: str):
        return torch.load(model_path, map_location='cpu')
            