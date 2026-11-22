"""Reliability evaluation of the existing (non-AI) PawPal+ scheduler.

These tests exercise realistic, scenario-level behaviour of `pawpal_system.py`:
valid schedules, time limits, overlapping tasks, invalid input, and empty task lists.

They do NOT test any AI functionality: PawPilot AI's AI features are not implemented yet.

Known gaps in the current scheduler are recorded with `pytest.mark.xfail(strict=True)`.
They show up as "xfailed" in the results; if one is ever fixed, the strict marker makes the
run fail (XPASS) so the marker and the README evaluation table must be updated.

Run with:  python3 -m pytest tests/test_reliability.py -v
"""

import random
from datetime import date, timedelta

import pytest

from pawpal_system import Owner, Pet, Scheduler, Task

TODAY = date.today()


def build_owner(available_minutes: int, pets: dict[str, list[Task]]) -> Owner:
    """Return an owner with the given time budget and pets, each holding the given tasks."""
    owner = Owner("Jordan", available_minutes=available_minutes, preferences=["walk", "meds"])
    for pet_name, tasks in pets.items():
        pet = Pet(pet_name, species="dog", age=3)
        owner.add_pet(pet)
        for task in tasks:
            pet.add_task(task)
    return owner


def planned(owner: Owner) -> Scheduler:
    """Build today's plan for the owner and return the scheduler."""
    scheduler = Scheduler(owner)
    scheduler.build_daily_plan()
    return scheduler


def realistic_day() -> dict[str, list[Task]]:
    """A two-pet day with no overlapping times and 80 minutes of care in total."""
    return {
        "Mochi": [
            Task("Breakfast", 10, priority="high", category="feeding", time="07:30"),
            Task("Morning walk", 30, priority="high", category="walk", time="08:00"),
            Task("Nail trim", 15, priority="low", category="grooming", time="16:00"),
        ],
        "Luna": [
            Task("Thyroid medication", 5, priority="high", category="meds", time="09:00"),
            Task("Dinner", 10, priority="medium", category="feeding", time="18:00"),
            Task("Brushing", 10, priority="low", category="grooming"),
        ],
    }


# ---------------------------------------------------------------------------
# 1. Valid schedules
# ---------------------------------------------------------------------------


def test_realistic_day_that_fits_is_fully_scheduled_in_time_order():
    """When everything fits, every task is scheduled, timed tasks are chronological, and nothing conflicts."""
    scheduler = planned(build_owner(90, realistic_day()))

    assert len(scheduler.scheduled_tasks) == 6
    assert scheduler.skipped_tasks == []
    assert scheduler.total_scheduled_minutes() == 80
    times = [t.time for t in scheduler.scheduled_tasks]
    assert times == ["07:30", "08:00", "09:00", "16:00", "18:00", ""]
    assert scheduler.detect_conflicts() == []


def test_rebuilding_the_plan_is_deterministic():
    """Building the plan repeatedly from the same data gives the same result every time."""
    scheduler = Scheduler(build_owner(40, realistic_day()))

    first = [t.title for t in scheduler.build_daily_plan()]
    for _ in range(5):
        assert [t.title for t in scheduler.build_daily_plan()] == first


def test_explanation_mentions_every_scheduled_and_skipped_task():
    """explain_plan() should account for every task the scheduler considered."""
    scheduler = planned(build_owner(40, realistic_day()))
    explanation = scheduler.explain_plan()

    assert scheduler.skipped_tasks, "scenario should skip at least one task"
    for task in scheduler.scheduled_tasks + scheduler.skipped_tasks:
        assert task.title in explanation
    assert f"{scheduler.total_scheduled_minutes()}/40 min used" in explanation


@pytest.mark.parametrize("seed", range(200))
def test_randomized_plans_always_satisfy_scheduler_invariants(seed):
    """For 200 seeded random scenarios, the core scheduling invariants always hold.

    - total scheduled minutes never exceed the budget
    - every pending task due today is either scheduled or skipped, exactly once
    - a task was only skipped if it is longer than the minutes left over at the end
      (the greedy budget only shrinks, so this must hold for every skipped task)
    """
    rng = random.Random(seed)
    pets = {}
    for pet_name in ("Mochi", "Luna", "Biscuit")[: rng.randint(1, 3)]:
        pets[pet_name] = [
            Task(
                f"Task {i}",
                rng.randint(1, 60),
                priority=rng.choice(["low", "medium", "high"]),
                category=rng.choice(["walk", "meds", "feeding", "grooming"]),
                time=rng.choice(["", f"{rng.randint(6, 21):02d}:{rng.choice([0, 15, 30, 45]):02d}"]),
            )
            for i in range(rng.randint(0, 8))
        ]
    budget = rng.randint(0, 180)
    scheduler = planned(build_owner(budget, pets))

    used = scheduler.total_scheduled_minutes()
    assert used <= budget

    considered = scheduler.scheduled_tasks + scheduler.skipped_tasks
    assert len(considered) == len({id(t) for t in considered})
    assert {id(t) for t in considered} == {id(t) for t in scheduler.collect_tasks()}

    left_over = budget - used
    for task in scheduler.skipped_tasks:
        assert task.duration_minutes > left_over


# ---------------------------------------------------------------------------
# 2. Time limits
# ---------------------------------------------------------------------------


def test_one_minute_short_skips_only_the_lowest_priority_task_that_does_not_fit():
    """With 79 of 80 needed minutes, a low-priority task is dropped and high-priority care stays."""
    scheduler = planned(build_owner(79, realistic_day()))

    assert scheduler.total_scheduled_minutes() <= 79
    assert [t.priority for t in scheduler.skipped_tasks] == ["low"]
    scheduled_titles = {t.title for t in scheduler.scheduled_tasks}
    assert {"Breakfast", "Morning walk", "Thyroid medication"} <= scheduled_titles


def test_task_longer_than_whole_budget_is_skipped_with_a_reason():
    """A task that can never fit is skipped and the explanation says why."""
    owner = build_owner(30, {"Mochi": [Task("Vet visit", 120, priority="high")]})
    scheduler = planned(owner)

    assert scheduler.scheduled_tasks == []
    assert "needs 120 min but only 30 min left" in scheduler.explain_plan()


def test_full_day_budget_schedules_everything():
    """A 24-hour budget fits a realistic day without dropping anything."""
    scheduler = planned(build_owner(24 * 60, realistic_day()))

    assert scheduler.skipped_tasks == []


def test_negative_budget_schedules_nothing():
    """A negative time budget is treated like no time at all: nothing is scheduled."""
    scheduler = planned(build_owner(-15, realistic_day()))

    assert scheduler.scheduled_tasks == []
    assert len(scheduler.skipped_tasks) == 6


def test_duplicate_task_is_not_counted_twice_against_the_budget():
    """Adding the same task twice is ignored, so it does not use up time twice."""
    owner = build_owner(30, {"Mochi": [Task("Walk", 20, time="08:00")]})
    owner.pets[0].add_task(Task("Walk", 20, time="08:00"))
    scheduler = planned(owner)

    assert len(owner.pets[0].tasks) == 1
    assert scheduler.total_scheduled_minutes() == 20


# ---------------------------------------------------------------------------
# 3. Overlapping tasks
# ---------------------------------------------------------------------------


def test_three_way_overlap_reports_every_overlapping_pair():
    """Three tasks that all overlap produce one warning per overlapping pair (3 pairs)."""
    owner = build_owner(120, {
        "Mochi": [Task("Walk", 30, time="08:00"), Task("Brush", 30, time="08:10")],
        "Luna": [Task("Meds", 30, time="08:20")],
    })
    conflicts = planned(owner).detect_conflicts()

    assert len(conflicts) == 3


def test_conflicts_across_pets_appear_in_the_explanation():
    """A cross-pet clash is listed under 'Conflicts:' in the plan explanation."""
    owner = build_owner(60, {
        "Mochi": [Task("Breakfast", 10, time="07:30")],
        "Luna": [Task("Breakfast", 10, time="07:30")],
    })
    explanation = planned(owner).explain_plan()

    assert "Conflicts:" in explanation
    assert "both at 07:30" in explanation


def test_skipped_task_is_not_reported_as_a_conflict():
    """After planning, only tasks that made it into the plan are checked for overlaps."""
    owner = build_owner(30, {
        "Mochi": [Task("Walk", 30, priority="high", time="08:00")],
        "Luna": [Task("Grooming", 30, priority="low", time="08:10")],
    })
    scheduler = planned(owner)

    assert [t.title for t in scheduler.skipped_tasks] == ["Grooming"]
    assert scheduler.detect_conflicts() == []


def test_back_to_back_tasks_across_pets_do_not_conflict():
    """A task ending exactly when another starts is not an overlap."""
    owner = build_owner(60, {
        "Mochi": [Task("Walk", 30, time="08:00")],
        "Luna": [Task("Meds", 5, time="08:30")],
    })

    assert planned(owner).detect_conflicts() == []


@pytest.mark.xfail(strict=True, reason="Known gap: conflicts that cross midnight are not detected.")
def test_task_running_past_midnight_conflicts_with_early_task_next_day():
    """A 23:30 task lasting 60 min overlaps a 00:00 task on the following day."""
    owner = build_owner(600, {
        "Mochi": [
            Task("Overnight sitter", 60, time="23:30"),
            Task("Late meds", 10, time="00:00", due_date=TODAY + timedelta(days=1)),
        ],
    })
    scheduler = Scheduler(owner)
    scheduler.plan_date = TODAY + timedelta(days=1)  # both tasks are pending on this date
    scheduler.build_daily_plan()

    assert scheduler.detect_conflicts() != []


# ---------------------------------------------------------------------------
# 4. Invalid input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_time", [" 08:00", "08:00pm", "08-00", "-1:00", "8", ""])
def test_malformed_times_are_rejected_at_creation(bad_time):
    """Malformed times raise ValueError; the empty string is the one allowed 'no time' value."""
    if bad_time == "":
        assert Task("Walk", 10, time=bad_time).time == ""
    else:
        with pytest.raises(ValueError, match="24-hour HH:MM format"):
            Task("Walk", 10, time=bad_time)


def test_rejected_task_leaves_existing_plan_unchanged():
    """A task that fails validation never reaches the pet, so the plan is unaffected."""
    owner = build_owner(90, realistic_day())
    before = [t.title for t in planned(owner).scheduled_tasks]

    with pytest.raises(ValueError):
        owner.pets[0].add_task(Task("Bad", 10, time="99:99"))

    assert [t.title for t in planned(owner).scheduled_tasks] == before


def test_duplicate_pet_name_is_rejected_case_insensitively():
    """Adding a second pet with the same name (any case) raises ValueError."""
    owner = build_owner(60, {"Mochi": []})

    with pytest.raises(ValueError, match="already has a pet named"):
        owner.add_pet(Pet("mochi", species="cat", age=1))


def test_removing_unknown_pet_or_task_raises():
    """Removing something that does not exist is reported, not silently ignored."""
    owner = build_owner(60, {"Mochi": [Task("Walk", 10)]})

    with pytest.raises(ValueError):
        owner.remove_pet("Ghost")
    with pytest.raises(ValueError):
        owner.pets[0].remove_task("Swim")


@pytest.mark.xfail(strict=True, reason="Known gap: negative durations are accepted and add minutes back to the budget.")
def test_negative_duration_cannot_push_plan_over_budget():
    """A -10 min task should not let a 65 min task fit into a 60 min day."""
    owner = build_owner(60, {"Mochi": [Task("Bogus", -10), Task("Long walk", 65)]})
    scheduler = planned(owner)

    longest = max((t.duration_minutes for t in scheduler.scheduled_tasks), default=0)
    assert longest <= 60


@pytest.mark.xfail(strict=True, reason="Known gap: unknown priorities are silently treated as 'medium'.")
def test_unknown_priority_is_rejected():
    """A typo such as 'urgent' should be rejected instead of silently ranked as medium."""
    with pytest.raises(ValueError):
        Task("Walk", 10, priority="urgent")


# ---------------------------------------------------------------------------
# 5. Empty task lists
# ---------------------------------------------------------------------------


def test_pets_with_no_tasks_give_an_empty_plan():
    """Several pets but no tasks: empty plan, no conflicts, readable explanation."""
    scheduler = planned(build_owner(60, {"Mochi": [], "Luna": []}))

    assert scheduler.scheduled_tasks == []
    assert scheduler.skipped_tasks == []
    assert scheduler.detect_conflicts() == []
    assert "No tasks scheduled." in scheduler.explain_plan()


def test_all_tasks_completed_gives_an_empty_plan():
    """Completed tasks are not rescheduled."""
    day = realistic_day()
    for tasks in day.values():
        for task in tasks:
            task.mark_complete()
    scheduler = planned(build_owner(90, day))

    assert scheduler.scheduled_tasks == []
    assert scheduler.skipped_tasks == []


def test_only_future_tasks_gives_an_empty_plan():
    """Tasks due tomorrow are not pulled into today's plan."""
    tomorrow = TODAY + timedelta(days=1)
    owner = build_owner(90, {"Mochi": [Task("Walk", 30, due_date=tomorrow, time="08:00")]})
    scheduler = planned(owner)

    assert scheduler.scheduled_tasks == []
    assert scheduler.detect_conflicts() == []


def test_filters_and_sorting_handle_empty_lists():
    """Filtering and sorting an owner with no tasks return empty lists, not errors."""
    scheduler = Scheduler(build_owner(60, {"Mochi": []}))

    assert scheduler.filter_tasks() == []
    assert scheduler.filter_tasks(pet_name="Mochi", completed=False) == []
    assert scheduler.sort_tasks([]) == []
    assert scheduler.sort_by_time([]) == []
