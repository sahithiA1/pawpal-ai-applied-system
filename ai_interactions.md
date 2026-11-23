# AI Interactions Log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

## Agent Workflow (SF7)

> Document your experience using an AI agent (e.g., Cursor Agent, Claude, Copilot) to make multi-step changes autonomously.

**What task did you give the agent?**

I used Claude Code in VS Code to work through the reliability and AI stages of PawPilot AI. I gave it four tasks, one after another:

1. **AI reliability testing (CodePath Step 4).** Add automated reliability tests for PawPilot AI's AI features. Do not invent results or count the original 38 backend tests as AI tests, and report it if the AI features don't exist yet.
2. **Scheduler reliability evaluation.** Build a reproducible evaluation of the existing scheduler: valid schedules, time limits, overlapping tasks, invalid input, and empty task lists. Add the results to the README, keeping scheduler reliability separate from AI reliability, without changing the core code.
3. **Model card.** Write `model_card.md` from the actual test results, including one AI suggestion I accepted and one I changed, without inventing experiences.
4. **ML priority recommender.** Build a real, lightweight machine-learning model with Python's standard library that suggests a task's priority. Train it on documented synthetic examples, connect it to Streamlit with approve/reject buttons, add tests, and update the documentation. No APIs, installations, or commits.

**What did the agent do?**

- **Task 1: it stopped instead of faking it.** It searched the code and `requirements.txt` and found no model calls, AI library, or approval step. It ran the existing suite (38 passed) and reported that Step 4 couldn't honestly be completed yet. It proposed building an AI module first. I didn't take that route then, and asked for the scheduler evaluation instead.
- **Task 2: it tested edge inputs first, then wrote tests.** Before writing assertions, it ran short scripts to see how the scheduler really behaves. This exposed three real weaknesses:
  - negative durations add time back to the budget, so a 65-minute task fit into a 60-minute day,
  - unknown priorities are silently treated as "medium",
  - conflicts across midnight are not detected.

  It then wrote `tests/test_reliability.py` with 228 tests, including 200 random scenarios with fixed seeds, and recorded the three weaknesses as strict expected failures (`xfail`). It forced those three tests to run and confirmed they fail on their actual assertions, not because the test was broken. It also found that the system `python3` doesn't have pytest, so the tests only run in `.venv`. Result: **263 passed, 3 xfailed**. It added a Reliability Evaluation section to the README.
- **Task 3:** it drew the model card's collaboration examples from my existing `reflection.md` and from this session, rather than writing new stories.
- **Task 4: ML recommender.**
  - **Data:** wrote 120 synthetic training examples (40 high / 40 medium / 40 low) in `data/priority_training_data.csv`, and documented the labelling rules and limitations in `data/README.md`.
  - **Model:** wrote `pawpilot_ml.py`, a multinomial Naive Bayes classifier with Laplace smoothing. It learns from title words, category, species, preferred time, and duration. It returns a priority, a confidence, the main reasons, and an approve/reject helper (`review_recommendation()`).
  - **Evaluation:** measured **76.7% (23/30)** on a held-out test set against a 33.3% baseline, and **68.3%** with leave-one-out. It listed the 7 wrong predictions, including two health tasks ranked too low.
  - **Unrecognised titles:** after seeing a nonsense title ("Zorblax") get a fairly confident "low", it added a flag and an app warning for titles with no known words.
  - **App:** added a suggestion panel to `app.py` with **Approve**, **Reject**, and a **Suggestion history** table. `pawpal_system.py` was not changed.
  - **Tests:** wrote 29 recommender tests and 5 Streamlit `AppTest` tests. One app test failed at first because of a bug in the test itself: it clicked "Add task" before checking the one-time feedback message. It reordered the test.
  - **Results:** the full suite gave **297 passed, 3 xfailed** on four repeated runs.
  - **Docs:** updated the README and model card with the measured numbers. It flagged that it had changed `model_card.md` even though I had earlier told it not to modify that file.

**What did you have to verify or fix manually?**

- **I changed the scope when the AI wasn't there.** When the agent reported that there were no AI features to test, I chose to evaluate the existing scheduler first instead of accepting its offer to build an AI module right away.
- **I removed an invented example.** In the model card draft, the agent added `"hgih"` as an example typo next to `"urgent"`. It flagged this itself, but only `"urgent"` had actually been tested, so I had it removed.
- **I reviewed the results and the documentation.** I asked the agent to show the finished model card for review before accepting it, and I kept control of commits: nothing was committed or pushed during these tasks.
- **Things the agent flagged that I need to keep in mind:**
  - one `AppTest` run timed out once and could not be reproduced,
  - the recommender's confident wrong answer on "Treat hot spot on paw",
  - the app's `use_container_width` deprecation warning, which was there before these changes.

- **I tested the ML feature myself in the browser.** I ran the Streamlit app and added Mochi as a pet. I entered an "Insulin injection" task, and the PawPilot AI panel recommended **high** priority with **99%** confidence. I approved the suggestion, added the task, and generated the daily schedule.


---

## Prompt Comparison (SF11)

> Compare two different prompts (or two different models) on the same task.

| | Option A | Option B |
|-|----------|----------|
| **Model / tool used** | | |
| **Prompt** | | |
| **Response summary** | | |
| **What was useful** | | |
| **Problems noticed** | | |
| **Decision** | | |

**Which approach did you use in your final implementation and why?**

<!-- Your conclusion -->
