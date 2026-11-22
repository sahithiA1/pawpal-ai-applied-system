# Model Card: PawPilot AI

## Overview

PawPilot AI is a pet-care scheduling assistant I am building on top of **PawPal+**, my CodePath AI110 Module 2 project. PawPal+ helps a pet owner register pets, add care tasks, and build a daily plan that fits the time they have.

The long-term goal for PawPilot AI is to add AI-generated scheduling recommendations that are checked against the existing scheduler's rules and approved by the owner before anything changes.

I want to be clear about where the project stands today:

| Part | Status | Where it lives |
|---|---|---|
| Priority-based daily scheduling within a time budget | ✅ Implemented and tested | `pawpal_system.py` |
| Conflict detection for overlapping timed tasks | ✅ Implemented and tested | `pawpal_system.py` |
| Daily and weekly recurring tasks | ✅ Implemented and tested | `pawpal_system.py` |
| Time validation, sorting, filtering, plan explanations | ✅ Implemented and tested | `pawpal_system.py` |
| Streamlit interface | ✅ Implemented. Only the priority-suggestion flow has saved `AppTest` tests | `app.py` |
| **ML task-priority recommender** (Naive Bayes, standard library only) | ✅ Implemented and tested | `pawpilot_ml.py`, `data/priority_training_data.csv` |
| Owner approval / rejection of priority suggestions | ✅ Implemented and tested | `app.py`, `review_recommendation()` in `pawpilot_ml.py` |
| Logging of priority decisions (current session only) | ✅ Implemented | `app.py` ("Suggestion history") |
| AI scheduling recommendations (whole schedules) | ⏳ Planned, not implemented | — |
| AI conflict review of proposed schedules | ⏳ Planned, not implemented | — |

**The only AI model in PawPilot AI is the priority recommender.** It is a small multinomial Naive Bayes classifier trained on 120 synthetic, hand-written example tasks. It suggests `low`, `medium`, or `high` priority for a new task, with a confidence and its main reasons, and the owner approves or rejects each suggestion. The scheduler itself is still rule-based: it sorts tasks by priority, preferred category, and preferred time, then adds them one at a time until the owner runs out of minutes. The architecture diagram in the README still shows planned AI parts that are not built.

## Intended Use

PawPilot AI is meant to help an individual pet owner organize everyday care, such as feeding, walks, medication reminders, and grooming, across one or more pets on a given day.

It is **not** meant to:

- give veterinary or medical advice,
- decide medication doses or whether a pet needs treatment,
- replace an owner's own judgment about their pet's health, or
- act as a reliable record of care that has actually been given.

## Evaluation Results

**Full suite, latest local run (Python 3.14.2, pytest 9.2.0, Streamlit 1.67.0, project `.venv`): 297 passed, 3 expected failures (xfail), 0 unexpected failures.** That is 263 scheduler tests plus 34 AI tests, all passing, plus the 3 known scheduler gaps.

### Scheduler evaluation

I evaluated the existing scheduler with two test files:

- `tests/test_pawpal.py`: the 38 original PawPal+ backend tests.
- `tests/test_reliability.py`: 228 scenario-level reliability tests covering valid schedules, time limits, overlapping tasks, invalid input, and empty task lists. 200 of these are randomized scenarios with fixed seeds, so every run checks the same inputs.

**Scheduler tests: 263 passed, 3 expected failures (xfail), 0 unexpected failures.**

| Category | Tests | Passed | Expected failures |
|---|---:|---:|---:|
| Original backend tests (`test_pawpal.py`) | 38 | 38 | 0 |
| Valid schedules | 203 | 203 | 0 |
| Time limits | 5 | 5 | 0 |
| Overlapping tasks | 5 | 4 | 1 |
| Invalid input | 11 | 9 | 2 |
| Empty task lists | 4 | 4 | 0 |
| **Total** | **266** | **263** | **3** |

None of these tests evaluate AI behaviour. I am not counting the 38 original tests or the scheduler reliability tests as AI tests.

### Priority recommender evaluation (AI)

| Measure | Result |
|---|---|
| Held-out test set (fixed stratified split, seed 110: 90 train / 30 test) | 23/30 correct = **76.7%** |
| Majority-class baseline on the same split | 33.3% |
| Leave-one-out accuracy (all 120 examples) | 82/120 = **68.3%** |
| `tests/test_priority_recommender.py` (data, training, prediction, invalid input, approve/reject, scheduler hand-off) | 29/29 passed |
| `tests/test_app_priority_suggestion.py` (Streamlit `AppTest`: approve, reject, warning, schedule still generates) | 5/5 passed |

The accuracy numbers measure agreement with my own hand-written labels, not real pet-care urgency. The 7 held-out mistakes included two health tasks ranked too low: *Monitor breathing after surgery* (labelled high, predicted medium) and *Treat hot spot* (labelled high, predicted low).

To reproduce:

```bash
source .venv/bin/activate
python -m pytest -q                                   # full suite
python -m pytest tests/test_reliability.py -q -rxX    # scheduler evaluation only, listing the 3 known gaps
python -m pawpilot_ml                                 # recommender accuracy and confusion matrix
```

### The three issues the evaluation found

The three expected failures are real weaknesses in the scheduler. I recorded them with `xfail(strict=True)` so they stay visible in every test run instead of being hidden. If one of them is fixed, pytest will report it and I will know to update the tests and documentation.

1. **Negative durations break the time limit.** A task like `Task("Bogus", -10)` is accepted. When the scheduler builds the plan, the −10 minutes are added back to the remaining time. In my test, that let a 65-minute walk into a 60-minute day. This is the most serious of the three, because staying within the owner's available time is the scheduler's main promise.
2. **Unknown priorities are silently treated as "medium".** If a priority is mistyped, for example `"urgent"`, the task is ranked as medium priority with no warning. In the Streamlit app the priority comes from a dropdown, so this mostly affects code that creates tasks directly. The priority recommender only ever outputs `low`, `medium`, or `high`, and `review_recommendation()` rejects any other value for the owner's current choice. But the scheduler itself still doesn't check.
3. **Conflicts that cross midnight are not detected.** A task at 23:30 that lasts an hour does not conflict with a 00:00 task on the next day, because conflict checks only compare tasks on the same date.

## Limitations and Biases

### Limitations of the current scheduler

- **Greedy, not optimal.** The scheduler fills the day in priority order. It never exceeds the budget with valid input, but it can leave time unused when a different set of tasks would have fit better.
- **Input validation is incomplete.** Times are validated, but durations and priorities are not (see the issues above). A non-numeric duration is not rejected when the task is created and only causes a `TypeError` later, when the plan is built.
- **Single-day view.** `sort_by_time()` sorts by clock time only and ignores the due date, and conflict detection does not look across midnight.
- **No persistence.** Pets and tasks live in Streamlit's session state and are lost when the page is refreshed.
- **Few saved UI tests.** Only the priority-suggestion flow has saved `AppTest` tests. The rest of the app was checked with `AppTest` and by hand during development, but those checks are not part of the automated suite.
- **Testing depends on the current date.** Tasks default to today's date, so tests run against whatever day it is. I don't know of any test that depends on a specific date.

### Biases built into the design

The scheduler doesn't learn from data, but it still makes value judgments that favour some tasks over others:

- **Priority comes first.** High-priority tasks always win over lower ones, even if several shorter lower-priority tasks would have used the time better. I chose this on purpose, because missing a medication is worse than missing a bath. It does mean the plan reflects the priorities the owner enters, including mistakes.
- **Owner preferences outrank time of day.** Tasks in the owner's preferred categories are placed ahead of other tasks with the same priority.
- **Unknown values fall back to "medium" and "any".** This hides mistakes instead of surfacing them.
- **Designed around a typical household.** The design assumes one owner, a handful of pets, and a few tasks a day. I have not tested larger households, multiple caregivers, or care routines for less common animals.

### Limitations and biases of the priority recommender

- **It learns my labels.** The training data is 120 synthetic examples I labelled with simple rules (documented in `data/README.md`). The model copies those judgments, including any I got wrong, and its accuracy only measures agreement with them.
- **Dogs and cats dominate.** Most examples are for dogs and cats. "Other" pets such as rabbits, fish, birds, and reptiles have far fewer, so suggestions for them rest on less evidence.
- **Single words can mislead it.** It treats a title as a bag of words. "Treat" appears mostly in snack examples ("Give a treat"), so "Treat hot spot on paw" was suggested as `low` with 80% confidence. It also ignores word order and negation.
- **It can be confidently wrong.** Confidence is the model's own probability, not real-world certainty, as the hot-spot example shows.
- **English, short titles only.** Other languages, long descriptions, and misspellings are not covered.

### Risks for the AI features that are still planned

These are not results. They are risks I plan to test for if I build the AI scheduling agent:

- An AI could suggest invalid task data, such as an unknown priority, a negative duration, or an impossible time. The issues above show that the current scheduler would not catch all of that.
- AI suggestions could sound confident about care decisions that really belong to a veterinarian.

## Misuse Prevention

What is in place today:

- **Time validation.** Tasks with malformed times such as `"8am"`, `"25:99"`, or `"08:00pm"` are rejected when they are created, so they never reach the plan.
- **Conflict warnings instead of silent changes.** The scheduler reports overlapping tasks but does not move them. The owner decides how to fix a conflict.
- **Plan explanations.** `explain_plan()` says why each task was scheduled or skipped, so the owner can see and question the reasoning.
- **No external data sharing.** Nothing is sent to an outside service. The priority recommender runs locally with no API. Data stays in the local Streamlit session.
- **Owner approval for priority suggestions.** The recommender never changes a task. Its suggestion only takes effect when the owner clicks **Approve**, and **Reject** keeps the owner's choice. Both are tested, in the app and at the code level.
- **Warnings and scope notes.** The app warns when none of the title words were seen in training or confidence is below 60%. It also says the suggestion comes from a small model trained on synthetic examples and is not veterinary advice.
- **Input checks in the recommender.** It rejects zero, negative, and non-integer durations, refuses to predict before training, and only trains on `low`/`medium`/`high` labels.
- **Decision history.** Each approve/reject decision is listed in the app for the current session, so the owner can see what the model suggested and what was used.

What I plan to add with future AI features:

- **Validate AI output with the existing rules.** Every AI-proposed schedule should pass the same checks as the scheduler (time budget, conflicts, valid times), plus the duration and priority validation that is currently missing.
- **Fix the three known issues first.** Before an AI generates whole tasks or schedules, I want the scheduler to reject negative durations and unknown priorities. Otherwise an AI mistake could quietly break the plan.

## Reliability Surprises

- **Negative durations.** In my original reflection I listed "invalid durations like zero or negative minutes" as something to test next. I expected them to be a bad-input problem. I did not expect a negative duration to give time back to the budget so that the plan goes over the limit. This was the clearest reminder that "the plan never goes over the budget" is only true when the input is valid.
- **Unknown priorities.** The fallback to "medium" was meant to keep the scheduler from crashing. The evaluation showed that the same fallback also hides user mistakes.
- **The midnight issue was not new.** I already knew about it and had documented it. The evaluation turned it into a test, so it is now tracked automatically instead of only written down.
- **The test command didn't work as documented.** The README says to run `python3 -m pytest`, but on my machine the system `python3` doesn't have pytest installed. The tests only run inside the project's virtual environment. The commands in this card use the virtual environment.
- **What held up.** All 200 randomized scenarios kept the scheduler's core rules: the budget was never exceeded with valid input, every task was either scheduled or skipped exactly once, and each skip was justified.

## Collaboration with AI

I used Claude Code throughout PawPal+ and PawPilot AI as an assistant that did much of the typing, while I made the design decisions, limited which files could change, and checked the results. Often I asked for a review or a plan before allowing any code changes.

### A suggestion I accepted after checking it

When Claude Code reviewed my finished Phase 4 scheduling algorithms, it pointed out that an invalid time like `"8am"` crashed the scheduler. I accepted its suggestion to add time validation to `Task`, so invalid times are rejected with a clear message when the task is created instead of failing later. I checked it with automated tests: valid times like `"08:00"` and `"23:59"` are accepted, while `"8am"`, `"25:99"`, `"12:60"`, `"24:00"`, and `"hello"` raise a `ValueError`. The new reliability evaluation added more malformed times, and those are rejected too.

### A suggestion I changed

During the testing phase, Claude Code wrote new tests for `build_daily_plan()`. To check whether they were useful, it also ran them against deliberately broken versions of the scheduler, changed only in memory. One version ignored priority completely and still passed the priority test. The low-priority Bath task in that test was too long to fit anyway, so it was skipped for the wrong reason. I didn't keep the test as written. I had it reordered so the Bath task is added first, which means a scheduler that ignores priority would pick it and fail. After that change, every broken version made at least one test fail. This taught me that a passing test doesn't always prove what its name says.

### Redirecting the AI reliability step

For this stage, I first asked Claude Code to add reliability tests for PawPilot AI's AI features. It inspected the code and reported that there were no AI features to test: no model calls, no AI library, and no approval step. Instead of writing tests that would look like AI results, it proposed building a small AI module with mocked tests first. I did not take that route at this stage. I asked for a reliability evaluation of the existing scheduler instead, and that evaluation is where the 263 passing tests and the three issues in this card come from.

### What I learned

AI is most useful to me when I keep the steps small and check its work myself. In both of the examples above, the useful part came from running tests and looking at what actually happened, not from accepting a suggestion because it sounded right. The same principle shapes my plan for PawPilot AI: AI suggestions should be checked against clear rules and approved by the owner before they change anything.
