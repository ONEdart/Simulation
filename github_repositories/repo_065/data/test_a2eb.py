# ml_3c1b1731.py
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# Model configuration
MODEL_PARAMS = {
    "n_estimators": 71,
    "max_depth": 13,
    "random_state": 223
}

def train(X, y):
    clf = RandomForestClassifier(**MODEL_PARAMS)
    clf.fit(X, y)
    return clf
