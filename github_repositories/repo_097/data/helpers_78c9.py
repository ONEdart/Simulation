# ml_92d00cb9.py
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# Model configuration
MODEL_PARAMS = {
    "n_estimators": 106,
    "max_depth": 18,
    "random_state": 478
}

def train(X, y):
    clf = RandomForestClassifier(**MODEL_PARAMS)
    clf.fit(X, y)
    return clf
