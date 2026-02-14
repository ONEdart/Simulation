# ml_e700fc55.py
import numpy as np
from sklearn.ensemble import RandomForestClassifier
MODEL_PARAMS = {
    "n_estimators": 196,
    "max_depth": 10,
    "random_state": 121
}
def train(X, y):
    clf = RandomForestClassifier(**MODEL_PARAMS)
    clf.fit(X, y)
    return clf
