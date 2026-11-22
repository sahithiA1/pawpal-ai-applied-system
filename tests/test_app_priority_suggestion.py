"""Streamlit AppTest checks for the PawPilot AI priority suggestion in app.py.

These run the real app script headlessly and click the Approve / Reject buttons.
"""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


def start_app_with_task(title: str, category: str) -> AppTest:
    """Run the app, add the default pet, and fill in a task title and category."""
    at = AppTest.from_file(APP_PATH, default_timeout=30).run()
    next(b for b in at.button if b.label == "Add pet").click().run()
    next(t for t in at.text_input if t.label == "Task title").set_value(title).run()
    at.selectbox(key="task_category").set_value(category).run()
    return at


def suggestion_text(at: AppTest) -> str:
    """Return the text of the suggestion box."""
    return next(i.value for i in at.info if i.value.startswith("Suggested priority"))


def test_app_shows_a_suggestion_without_changing_the_priority():
    """The suggestion appears, but the priority dropdown keeps its value until the owner decides."""
    at = start_app_with_task("Insulin injection", "meds")
    at.selectbox(key="task_priority").set_value("low").run()

    assert "**high**" in suggestion_text(at)
    assert at.selectbox(key="task_priority").value == "low"
    assert not at.exception


def test_approve_sets_priority_and_logs_the_decision():
    """Clicking Approve sets the dropdown to the suggestion and records the decision."""
    at = start_app_with_task("Insulin injection", "meds")
    at.selectbox(key="task_priority").set_value("low").run()
    at.button(key="approve_priority").click().run()

    assert at.selectbox(key="task_priority").value == "high"
    assert "Approved: priority set to high." in [s.value for s in at.success]
    [decision] = at.session_state.priority_decisions
    assert (decision.approved, decision.previous_priority, decision.final_priority) == (True, "low", "high")


def test_reject_keeps_priority_and_task_is_added_with_owners_choice():
    """Clicking Reject keeps the owner's priority, and Add task uses it."""
    at = start_app_with_task("Insulin injection", "meds")
    at.selectbox(key="task_priority").set_value("medium").run()
    at.button(key="reject_priority").click().run()

    assert at.selectbox(key="task_priority").value == "medium"
    assert "Rejected: kept your choice (medium)." in [s.value for s in at.success]

    next(b for b in at.button if b.label == "Add task").click().run()
    [task] = at.session_state.owner.pets[0].tasks
    assert (task.title, task.priority) == ("Insulin injection", "medium")
    assert not at.exception


def test_unrecognized_title_shows_a_warning():
    """A title with no known words triggers the 'check it carefully' warning."""
    at = start_app_with_task("Zorblax", "other")

    assert any("None of the words in this title" in w.value for w in at.warning)


def test_schedule_still_generates_after_approval():
    """The existing scheduler still works after an approved suggestion is used."""
    at = start_app_with_task("Insulin injection", "meds")
    at.button(key="approve_priority").click().run()
    next(b for b in at.button if b.label == "Add task").click().run()
    next(b for b in at.button if b.label == "Generate schedule").click().run()

    assert not at.exception
    assert [m.value for m in at.metric if m.label == "Tasks scheduled"] == ["1"]
