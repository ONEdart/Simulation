# ml_299ff208.py
import numpy as np
from sklearn.ensemble import RandomForestClassifier
MODEL_PARAMS = {
    "n_estimators": 196,
    "max_depth": 14,
    "random_state": 818
}
def train(X, y):
    clf = RandomForestClassifier(**MODEL_PARAMS)
    clf.fit(X, y)
    return clf
