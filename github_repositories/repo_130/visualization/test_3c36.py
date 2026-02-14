# ml_bc6c96c9.py
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# Model configuration
MODEL_PARAMS = {
    "n_estimators": 54,
    "max_depth": 6,
    "random_state": 341
}

def train(X, y):
    clf = RandomForestClassifier(**MODEL_PARAMS)
    clf.fit(X, y)
    return clf
