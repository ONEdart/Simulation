# ml_c96f1235.py
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# Model configuration
MODEL_PARAMS = {
    "n_estimators": 54,
    "max_depth": 17,
    "random_state": 578
}

def train(X, y):
    clf = RandomForestClassifier(**MODEL_PARAMS)
    clf.fit(X, y)
    return clf
