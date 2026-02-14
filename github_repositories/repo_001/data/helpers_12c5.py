# ml_7d10f8c9.py
import numpy as np
from sklearn.ensemble import RandomForestClassifier
MODEL_PARAMS = {
    "n_estimators": 65,
    "max_depth": 9,
    "random_state": 754
}
def train(X, y):
    clf = RandomForestClassifier(**MODEL_PARAMS)
    clf.fit(X, y)
    return clf
