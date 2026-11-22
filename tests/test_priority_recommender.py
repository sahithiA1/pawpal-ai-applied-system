"""Tests for the PawPilot AI task-priority recommender (pawpilot_ml.py).

These are the project's AI-specific tests. They cover the training data, training and
prediction, measured accuracy on held-out examples, invalid input, the approve/reject
decision logic, and how an approved priority flows into the existing scheduler.
"""

import pytest

from pawpal_system import Owner, Pet, Scheduler, Task
from pawpilot_ml import (
    DEFAULT_DATA_PATH,
    PRIORITIES,
    PriorityRecommender,
    TaskExample,
    evaluate,
    extract_features,
    leave_one_out_accuracy,
    load_training_data,
    review_recommendation,
    stratified_split,
    tokenize,
    train_default_recommender,
)


@pytest.fixture(scope="module")
def model() -> PriorityRecommender:
    """The recommender trained on the bundled dataset, as used by the app."""
    return train_default_recommender()


# ---------------------------------------------------------------------------
# Training data
# ---------------------------------------------------------------------------


def test_training_data_is_balanced_and_well_formed():
    """The synthetic dataset has 120 examples, 40 per priority, with valid fields and unique titles."""
    examples = load_training_data()

    assert DEFAULT_DATA_PATH.exists()
    assert len(examples) == 120
    for label in PRIORITIES:
        assert sum(e.priority == label for e in examples) == 40
    assert len({e.title.lower() for e in examples}) == 120
    for e in examples:
        assert e.category in {"walk", "feeding", "meds", "grooming", "other"}
        assert e.species in {"dog", "cat", "other"}
        assert e.preferred_time in {"any", "morning", "afternoon", "evening"}
        assert e.duration_minutes > 0


def test_tokenize_lowercases_drops_stopwords_and_plurals():
    """Titles become comparable word tokens."""
    assert tokenize("Ear Drops for the Infection") == ["ear", "drop", "infection"]
    assert tokenize("Feed 2 cats!") == ["feed", "cat"]
    assert tokenize("Glass") == ["glass"]  # double-s words keep their ending
    assert tokenize("") == []


def test_features_include_title_words_and_task_details():
    """A task is described by its title words, category, species, time, and duration bucket."""
    features = extract_features(TaskExample("Insulin shot", "meds", 5, "cat", "morning"))

    assert features == [
        "word=insulin", "word=shot", "category=meds", "species=cat",
        "time=morning", "duration=short",
    ]


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "task, expected",
    [
        (TaskExample("Give insulin", "meds", 5, "cat", "morning"), "high"),
        (TaskExample("Ear medication", "meds", 5, "dog", "evening"), "high"),
        (TaskExample("Feed the cat", "feeding", 10, "cat", "morning"), "high"),
        (TaskExample("Walk to the park", "walk", 30, "dog", "morning"), "medium"),
        (TaskExample("Clean litter", "other", 10, "cat", "evening"), "medium"),
        (TaskExample("Bathe and brush", "grooming", 40, "dog", "afternoon"), "low"),
    ],
)
def test_clear_unseen_tasks_get_sensible_priorities(model, task, expected):
    """Tasks that are not in the training data, but clearly fit a labelling rule, are classified correctly."""
    assert model.predict(task) == expected


def test_probabilities_sum_to_one_and_confidence_is_the_top_probability(model):
    """predict_proba() is a proper distribution, and recommend() reports its maximum."""
    task = TaskExample("Evening walk", "walk", 30, "dog", "evening")
    probabilities = model.predict_proba(task)
    recommendation = model.recommend(task)

    assert set(probabilities) == set(PRIORITIES)
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert recommendation.confidence == pytest.approx(max(probabilities.values()))
    assert recommendation.probabilities[recommendation.priority] == recommendation.confidence


def test_recommendation_explains_itself_with_supporting_features(model):
    """The reasons name the features that most favoured the suggested priority."""
    recommendation = model.recommend(TaskExample("Insulin injection", "meds", 5, "cat", "morning"))

    assert recommendation.priority == "high"
    assert "the word 'insulin'" in recommendation.reasons
    assert 1 <= len(recommendation.reasons) <= 3


def test_training_is_deterministic():
    """Training twice on the same data gives identical predictions."""
    task = TaskExample("Brush teeth", "grooming", 5, "dog", "evening")

    first = train_default_recommender().predict_proba(task)
    second = train_default_recommender().predict_proba(task)

    assert first == second


def test_unrecognized_title_is_flagged_but_still_handled(model):
    """A title with no known words falls back on task details and is flagged for review."""
    recommendation = model.recommend(TaskExample("Zorblax", "other", 10, "dog", "any"))

    assert recommendation.title_unrecognized
    assert recommendation.priority in PRIORITIES
    assert not model.recommend(TaskExample("Morning walk", "walk", 20, "dog")).title_unrecognized


def test_empty_title_still_gives_a_recommendation(model):
    """An empty title is allowed; the model uses the other task details."""
    recommendation = model.recommend(TaskExample("", "meds", 5, "dog", "morning"))

    assert recommendation.priority in PRIORITIES
    assert recommendation.title_unrecognized


# ---------------------------------------------------------------------------
# Measured accuracy (actual results, used as regression guards)
# ---------------------------------------------------------------------------


def test_held_out_accuracy_beats_majority_baseline():
    """On a fixed 25% held-out split, accuracy is 23/30 (76.7%) vs. a 33.3% majority baseline."""
    train, test = stratified_split(load_training_data())
    result = evaluate(train, test)

    assert (len(train), len(test)) == (90, 30)
    assert result["correct"] == 23
    assert result["baseline_accuracy"] == pytest.approx(1 / 3)


def test_leave_one_out_accuracy_is_recorded():
    """Leave-one-out accuracy over all 120 examples is 82/120 (68.3%)."""
    assert leave_one_out_accuracy(load_training_data()) == pytest.approx(82 / 120)


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("duration", [0, -10, "10", 2.5, True])
def test_invalid_durations_are_rejected(model, duration):
    """Durations must be positive whole numbers (unlike the scheduler's Task, see test_reliability.py)."""
    with pytest.raises(ValueError, match="Duration"):
        model.recommend(TaskExample("Walk", "walk", duration, "dog"))


def test_untrained_model_refuses_to_predict():
    """Predicting before training raises instead of returning a meaningless answer."""
    with pytest.raises(RuntimeError, match="not been trained"):
        PriorityRecommender().predict(TaskExample("Walk", "walk", 10))


def test_training_rejects_empty_data_and_bad_labels():
    """Training needs at least one example and only accepts low/medium/high labels."""
    with pytest.raises(ValueError, match="empty"):
        PriorityRecommender().fit([])
    with pytest.raises(ValueError, match="Training label"):
        PriorityRecommender().fit([TaskExample("Walk", "walk", 10, priority="urgent")])
    with pytest.raises(ValueError, match="Training label"):
        PriorityRecommender().fit([TaskExample("Walk", "walk", 10, priority=None)])


def test_unknown_category_and_species_do_not_crash(model):
    """Values never seen in training are ignored rather than causing errors."""
    recommendation = model.recommend(TaskExample("Morning walk", "hiking", 20, "ferret", "dawn"))

    assert recommendation.priority == "medium"


# ---------------------------------------------------------------------------
# Owner approval / rejection
# ---------------------------------------------------------------------------


def test_approving_adopts_the_suggested_priority(model):
    """Approval returns the model's suggestion as the priority to use."""
    recommendation = model.recommend(TaskExample("Insulin injection", "meds", 5, "cat"))
    decision = review_recommendation("Insulin injection", recommendation, "low", approved=True)

    assert decision.approved
    assert decision.previous_priority == "low"
    assert decision.final_priority == recommendation.priority == "high"


def test_rejecting_keeps_the_owners_priority(model):
    """Rejection keeps whatever priority the owner had chosen."""
    recommendation = model.recommend(TaskExample("Insulin injection", "meds", 5, "cat"))
    decision = review_recommendation("Insulin injection", recommendation, "Medium", approved=False)

    assert not decision.approved
    assert decision.suggested_priority == "high"
    assert decision.final_priority == "medium"


def test_review_rejects_an_invalid_current_priority(model):
    """The owner's current priority must be a real priority level."""
    recommendation = model.recommend(TaskExample("Walk", "walk", 20, "dog"))

    with pytest.raises(ValueError, match="Current priority"):
        review_recommendation("Walk", recommendation, "urgent", approved=False)


def test_recommending_never_changes_an_existing_task(model):
    """Getting a recommendation for a task's details does not touch the scheduler Task."""
    task = Task("Insulin injection", 5, priority="low", category="meds")
    model.recommend(TaskExample(task.title, task.category, task.duration_minutes))

    assert task.priority == "low"


def test_approved_priority_changes_what_the_scheduler_keeps():
    """End to end: approving 'high' for insulin makes the existing scheduler keep it over a low task."""
    model = train_default_recommender()
    recommendation = model.recommend(TaskExample("Insulin injection", "meds", 5, "cat", "morning"))

    def plan_with(priority: str) -> list[str]:
        owner = Owner("Jordan", available_minutes=30)
        pet = Pet("Luna", species="cat", age=5)
        owner.add_pet(pet)
        pet.add_task(Task("Brush coat", 30, priority="medium", category="grooming"))
        pet.add_task(Task("Insulin injection", 5, priority=priority, category="meds"))
        return [t.title for t in Scheduler(owner).build_daily_plan()]

    rejected = review_recommendation("Insulin injection", recommendation, "low", approved=False)
    approved = review_recommendation("Insulin injection", recommendation, "low", approved=True)

    assert plan_with(rejected.final_priority) == ["Brush coat"]
    assert plan_with(approved.final_priority) == ["Insulin injection"]
