
import cv2
import numpy as np
from pathlib import Path

class DatasetLoader:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
    
    def load_image(self, image_path: str):
        img = cv2.imread(str(image_path))
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            