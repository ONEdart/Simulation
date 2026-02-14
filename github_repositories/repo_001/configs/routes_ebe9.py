# ml_d514a88b.py
import numpy as np
from sklearn.ensemble import RandomForestClassifier
MODEL_PARAMS = {
    "n_estimators": 146,
    "max_depth": 6,
    "random_state": 195
}
def train(X, y):
    clf = RandomForestClassifier(**MODEL_PARAMS)
    clf.fit(X, y)
    return clf
