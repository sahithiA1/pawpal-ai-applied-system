"""PawPilot AI: a lightweight machine-learning task-priority recommender.

The model is a multinomial Naive Bayes classifier written with Python's standard library only.
It learns from labelled example tasks (see data/priority_training_data.csv and data/README.md)
and suggests a priority ("low", "medium", or "high") for a new task.

The recommender only *suggests*. It never changes a task by itself: the owner approves or
rejects each suggestion, and `review_recommendation()` returns the priority to use.

Reproduce the evaluation with:  python -m pawpilot_ml
"""

from __future__ import annotations

import csv
import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

PRIORITIES = ("low", "medium", "high")
DEFAULT_DATA_PATH = Path(__file__).parent / "data" / "priority_training_data.csv"
LOW_CONFIDENCE_THRESHOLD = 0.6
EVALUATION_SEED = 110
STOPWORDS = {
    "a", "an", "and", "at", "after", "around", "before", "for", "in", "of", "on",
    "out", "the", "to", "with",
}


@dataclass(frozen=True)
class TaskExample:
    """One task description, with its priority label when used for training."""

    title: str
    category: str = "other"
    duration_minutes: int = 10
    species: str = "other"
    preferred_time: str = "any"
    priority: Optional[str] = None


@dataclass(frozen=True)
class Recommendation:
    """A suggested priority, how confident the model is, and the evidence behind it."""

    priority: str
    confidence: float
    probabilities: dict[str, float]
    reasons: tuple[str, ...]
    known_title_words: int = 0  # title words the model saw during training

    @property
    def low_confidence(self) -> bool:
        """True when the model's top probability is below LOW_CONFIDENCE_THRESHOLD."""
        return self.confidence < LOW_CONFIDENCE_THRESHOLD

    @property
    def title_unrecognized(self) -> bool:
        """True when no word in the title was seen in training, so only task details were used."""
        return self.known_title_words == 0


@dataclass(frozen=True)
class PriorityDecision:
    """The owner's response to a recommendation and the priority that results from it."""

    task_title: str
    suggested_priority: str
    confidence: float
    previous_priority: str
    final_priority: str
    approved: bool


def tokenize(text: str) -> list[str]:
    """Lowercase words from a title, without stopwords; a trailing plural 's' is dropped."""
    words = re.findall(r"[a-z]+", text.lower())
    tokens = []
    for word in words:
        if word in STOPWORDS:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        tokens.append(word)
    return tokens


def duration_bucket(minutes: int) -> str:
    """Group a duration into 'short' (<=10), 'medium' (11-30), or 'long' (>30)."""
    if minutes <= 10:
        return "short"
    if minutes <= 30:
        return "medium"
    return "long"


def extract_features(task: TaskExample) -> list[str]:
    """Turn a task into the feature strings the model counts (title words plus task details)."""
    if isinstance(task.duration_minutes, bool) or not isinstance(task.duration_minutes, int):
        raise ValueError(f"Duration must be a whole number of minutes, got {task.duration_minutes!r}.")
    if task.duration_minutes <= 0:
        raise ValueError(f"Duration must be positive, got {task.duration_minutes}.")
    features = [f"word={token}" for token in tokenize(task.title)]
    features.append(f"category={task.category.strip().lower()}")
    features.append(f"species={task.species.strip().lower()}")
    features.append(f"time={task.preferred_time.strip().lower()}")
    features.append(f"duration={duration_bucket(task.duration_minutes)}")
    return features


def describe_feature(feature: str) -> str:
    """Return a readable version of a feature string, e.g. "word=insulin" -> "the word 'insulin'"."""
    kind, value = feature.split("=", 1)
    labels = {
        "word": f"the word '{value}'",
        "category": f"category '{value}'",
        "species": f"species '{value}'",
        "time": f"preferred time '{value}'",
        "duration": f"{value} duration",
    }
    return labels[kind]


class PriorityRecommender:
    """Multinomial Naive Bayes classifier that predicts a task's priority."""

    def __init__(self, alpha: float = 1.0) -> None:
        """Create an untrained model; alpha is the Laplace smoothing strength."""
        if alpha <= 0:
            raise ValueError("alpha must be positive.")
        self.alpha = alpha
        self.class_counts: Counter[str] = Counter()
        self.feature_counts: dict[str, Counter[str]] = defaultdict(Counter)
        self.total_features: Counter[str] = Counter()
        self.vocabulary: set[str] = set()

    @property
    def is_trained(self) -> bool:
        """True once fit() has been called with data."""
        return bool(self.class_counts)

    def fit(self, examples: Iterable[TaskExample]) -> PriorityRecommender:
        """Learn class and feature counts from labelled examples, replacing any earlier training."""
        self.__init__(self.alpha)
        for example in examples:
            label = (example.priority or "").strip().lower()
            if label not in PRIORITIES:
                raise ValueError(f"Training label must be one of {PRIORITIES}, got {example.priority!r}.")
            features = extract_features(example)
            self.class_counts[label] += 1
            self.feature_counts[label].update(features)
            self.total_features[label] += len(features)
            self.vocabulary.update(features)
        if not self.is_trained:
            raise ValueError("Cannot train on an empty dataset.")
        return self

    def _log_likelihood(self, feature: str, label: str) -> float:
        """Smoothed log P(feature | label)."""
        count = self.feature_counts[label][feature]
        return math.log(
            (count + self.alpha) / (self.total_features[label] + self.alpha * len(self.vocabulary))
        )

    def predict_proba(self, task: TaskExample) -> dict[str, float]:
        """Return a probability for each priority. Features never seen in training are ignored."""
        if not self.is_trained:
            raise RuntimeError("The recommender has not been trained yet.")
        features = [f for f in extract_features(task) if f in self.vocabulary]
        total_examples = sum(self.class_counts.values())
        scores = {}
        for label in PRIORITIES:
            if self.class_counts[label] == 0:
                continue
            score = math.log(self.class_counts[label] / total_examples)
            score += sum(self._log_likelihood(f, label) for f in features)
            scores[label] = score
        top = max(scores.values())
        exp_scores = {label: math.exp(score - top) for label, score in scores.items()}
        norm = sum(exp_scores.values())
        return {label: exp_scores.get(label, 0.0) / norm for label in PRIORITIES}

    def predict(self, task: TaskExample) -> str:
        """Return the most likely priority (ties go to the higher priority)."""
        probabilities = self.predict_proba(task)
        return max(PRIORITIES, key=lambda label: (probabilities[label], PRIORITIES.index(label)))

    def recommend(self, task: TaskExample, max_reasons: int = 3) -> Recommendation:
        """Suggest a priority, with confidence and the features that most favoured it."""
        probabilities = self.predict_proba(task)
        priority = max(PRIORITIES, key=lambda label: (probabilities[label], PRIORITIES.index(label)))
        others = [label for label in PRIORITIES if label != priority and self.class_counts[label]]
        evidence = []
        for feature in dict.fromkeys(extract_features(task)):  # unique, in order
            if feature not in self.vocabulary or not others:
                continue
            margin = self._log_likelihood(feature, priority) - max(
                self._log_likelihood(feature, other) for other in others
            )
            if margin > 0:
                evidence.append((margin, feature))
        evidence.sort(key=lambda item: -item[0])
        reasons = tuple(describe_feature(f) for _, f in evidence[:max_reasons])
        known_words = sum(
            1 for token in set(tokenize(task.title)) if f"word={token}" in self.vocabulary
        )
        return Recommendation(priority, probabilities[priority], probabilities, reasons, known_words)


def review_recommendation(
    task_title: str, recommendation: Recommendation, current_priority: str, approved: bool
) -> PriorityDecision:
    """Apply the owner's decision: approval adopts the suggestion, rejection keeps the current priority."""
    current = current_priority.strip().lower()
    if current not in PRIORITIES:
        raise ValueError(f"Current priority must be one of {PRIORITIES}, got {current_priority!r}.")
    return PriorityDecision(
        task_title=task_title,
        suggested_priority=recommendation.priority,
        confidence=recommendation.confidence,
        previous_priority=current,
        final_priority=recommendation.priority if approved else current,
        approved=approved,
    )


def load_training_data(path: Path | str = DEFAULT_DATA_PATH) -> list[TaskExample]:
    """Read labelled examples from a CSV file with the training-data columns."""
    with open(path, newline="", encoding="utf-8") as handle:
        return [
            TaskExample(
                title=row["title"],
                category=row["category"],
                duration_minutes=int(row["duration_minutes"]),
                species=row["species"],
                preferred_time=row["preferred_time"],
                priority=row["priority"],
            )
            for row in csv.DictReader(handle)
        ]


def train_default_recommender() -> PriorityRecommender:
    """Train a recommender on the bundled synthetic dataset."""
    return PriorityRecommender().fit(load_training_data())


def stratified_split(
    examples: list[TaskExample], test_fraction: float = 0.25, seed: int = EVALUATION_SEED
) -> tuple[list[TaskExample], list[TaskExample]]:
    """Shuffle each class with a fixed seed and hold out test_fraction of it for testing."""
    rng = random.Random(seed)
    train, test = [], []
    for label in PRIORITIES:
        group = [e for e in examples if e.priority == label]
        rng.shuffle(group)
        cut = round(len(group) * test_fraction)
        test.extend(group[:cut])
        train.extend(group[cut:])
    return train, test


def evaluate(train: list[TaskExample], test: list[TaskExample]) -> dict:
    """Train on `train`, predict `test`, and return accuracy, a confusion matrix, and the majority baseline."""
    model = PriorityRecommender().fit(train)
    confusion = {actual: Counter() for actual in PRIORITIES}
    for example in test:
        confusion[example.priority][model.predict(example)] += 1
    correct = sum(confusion[label][label] for label in PRIORITIES)
    majority = Counter(e.priority for e in train).most_common(1)[0][0]
    baseline = sum(e.priority == majority for e in test) / len(test)
    return {
        "accuracy": correct / len(test),
        "correct": correct,
        "total": len(test),
        "baseline_accuracy": baseline,
        "confusion": {label: dict(confusion[label]) for label in PRIORITIES},
    }


def leave_one_out_accuracy(examples: list[TaskExample]) -> float:
    """Accuracy when each example is predicted by a model trained on all the others."""
    correct = 0
    for i, example in enumerate(examples):
        model = PriorityRecommender().fit(examples[:i] + examples[i + 1 :])
        correct += model.predict(example) == example.priority
    return correct / len(examples)


def main() -> None:
    """Print a reproducible evaluation of the recommender on the bundled dataset."""
    examples = load_training_data()
    train, test = stratified_split(examples)
    result = evaluate(train, test)
    print(f"Dataset: {len(examples)} synthetic examples "
          f"({', '.join(f'{c} {p}' for p, c in sorted(Counter(e.priority for e in examples).items()))})")
    print(f"Held-out split (seed {EVALUATION_SEED}): train {len(train)}, test {len(test)}")
    print(f"  Accuracy: {result['correct']}/{result['total']} = {result['accuracy']:.1%}")
    print(f"  Majority-class baseline: {result['baseline_accuracy']:.1%}")
    print("  Confusion matrix (rows = actual, columns = predicted):")
    print("            " + "".join(f"{p:>8}" for p in PRIORITIES))
    for actual in PRIORITIES:
        print(f"  {actual:>8}  " + "".join(f"{result['confusion'][actual].get(p, 0):>8}" for p in PRIORITIES))
    print(f"Leave-one-out accuracy: {leave_one_out_accuracy(examples):.1%}")


if __name__ == "__main__":
    main()
