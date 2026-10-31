"""Small classical classifiers, with all fitting confined to training data."""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .data import WEATHER_FEATURES
from .metrics import classification_metrics

CATEGORICAL_FEATURES = ["airport", "carrier", "dest"]
SCHEDULE_NUMERIC_FEATURES = ["month", "day_of_week", "local_hour", "scheduled_duration_min", "distance_miles"]


@dataclass
class FittedRiskModel:
    estimator: object
    name: str
    threshold: float
    features: list
    validation: dict
    candidate_validation: dict
    include_weather: bool

    def predict(self, frame):
        # Never pass outcome fields into an estimator, even when frame has them.
        return self.estimator.predict_proba(frame[self.features])[:, 1]


def choose_threshold(labels, probabilities):
    """Maximise validation F1; break ties toward fewer positive alerts."""
    precision, recall, thresholds = precision_recall_curve(labels, probabilities)
    if not len(thresholds):
        return 0.5
    f1 = np.divide(2 * precision[:-1] * recall[:-1], precision[:-1] + recall[:-1], out=np.zeros_like(thresholds), where=(precision[:-1] + recall[:-1]) != 0)
    best = np.flatnonzero(np.isclose(f1, f1.max(), rtol=1e-12, atol=1e-12))
    return float(thresholds[best[-1]])


def _estimator(kind, include_weather):
    numeric = SCHEDULE_NUMERIC_FEATURES + (["horizon_hours"] + WEATHER_FEATURES if include_weather else [])
    dense = kind == "hist_gradient_boosting"
    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scale", StandardScaler()),
    ])
    preprocess = ColumnTransformer([
        ("numeric", numeric_pipeline, numeric),
        ("categories", OneHotEncoder(handle_unknown="ignore", max_categories=25, sparse_output=not dense), CATEGORICAL_FEATURES),
    ], sparse_threshold=0 if dense else 1)
    if kind == "logistic_regression":
        estimator = LogisticRegression(C=1.0, max_iter=500, random_state=27)
    else:
        estimator = HistGradientBoostingClassifier(max_iter=100, max_depth=3, max_leaf_nodes=8, learning_rate=0.08, l2_regularization=2.0, min_samples_leaf=25, early_stopping=False, random_state=27)
    return Pipeline([("preprocess", preprocess), ("classifier", estimator)]), numeric + CATEGORICAL_FEATURES


def fit_candidates(train, validation, include_weather=False):
    for name, part in [("train", train), ("validation", validation)]:
        if part.empty or part.severe_delay.nunique() != 2:
            raise ValueError(f"{name} must contain known labels from both classes")
    models, candidate_metrics = {}, {}
    for name in ["logistic_regression", "hist_gradient_boosting"]:
        estimator, features = _estimator(name, include_weather)
        estimator.fit(train[features], train.severe_delay)
        probabilities = estimator.predict_proba(validation[features])[:, 1]
        threshold = choose_threshold(validation.severe_delay, probabilities)
        metrics = classification_metrics(validation.severe_delay, probabilities, threshold)
        candidate_metrics[name] = metrics | {"threshold": threshold}
        models[name] = (estimator, features, threshold, metrics)
    # PR-AUC is suited to the minority class; Brier breaks ties, then stable name.
    winner = max(models, key=lambda name: (candidate_metrics[name]["pr_auc"], -candidate_metrics[name]["brier"], name))
    estimator, features, threshold, metrics = models[winner]
    return FittedRiskModel(estimator, winner, threshold, features, metrics, candidate_metrics, include_weather)


def fit_historical_baseline(train):
    grouped = train.assign(hour=train.local_hour.fillna(-1).astype(int)).groupby(["airport", "hour"]).severe_delay.agg(["sum", "count"])
    airport = train.groupby("airport").severe_delay.mean().to_dict()
    overall = float(train.severe_delay.mean())
    # Shrink small airport/hour cells toward the training airport rate.
    cells = {(str(code), int(hour)): float((row["sum"] + 20 * airport[code]) / (row["count"] + 20)) for (code, hour), row in grouped.iterrows()}
    return {"cells": cells, "airport": airport, "overall": overall, "smoothing_prior_count": 20}


def baseline_probabilities(baseline, frame):
    return np.asarray([baseline["cells"].get((str(code), int(hour)), baseline["airport"].get(code, baseline["overall"])) for code, hour in zip(frame.airport, frame.local_hour.fillna(-1))])
