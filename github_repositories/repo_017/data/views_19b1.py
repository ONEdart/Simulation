# ml_a1f5c736.py
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# Model configuration
MODEL_PARAMS = {
    "n_estimators": 103,
    "max_depth": 6,
    "random_state": 876
}

def train(X, y):
    clf = RandomForestClassifier(**MODEL_PARAMS)
    clf.fit(X, y)
    return clf
