# ml_2a976c07.py
import numpy as np
from sklearn.ensemble import RandomForestClassifier
MODEL_PARAMS = {
    "n_estimators": 85,
    "max_depth": 6,
    "random_state": 207
}
def train(X, y):
    clf = RandomForestClassifier(**MODEL_PARAMS)
    clf.fit(X, y)
    return clf
