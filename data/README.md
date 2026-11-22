# Priority training data

`priority_training_data.csv` is the training set for the PawPilot AI priority recommender (`pawpilot_ml.py`).

## What it is

- **120 synthetic examples**, 40 each of `high`, `medium`, and `low`.
- Every row was **written by hand for this project**. None of it is real user data, real pet records, or data from a veterinary source.
- Columns: `title`, `category`, `duration_minutes`, `species`, `preferred_time`, `priority`.
- The `category`, `species`, and `preferred_time` values match the choices in the Streamlit app:
  - categories: `walk`, `feeding`, `meds`, `grooming`, `other`
  - species: `dog`, `cat`, `other`
  - times: `any`, `morning`, `afternoon`, `evening`

## Labelling rules

The labels follow these rules, which are judgment calls for a scheduling demo and not veterinary guidance:

| Priority | Rule | Examples |
|---|---|---|
| `high` | Health, safety, or a basic daily need that should not be skipped: medication, meals and water, potty breaks, wound care, vet visits, habitat safety | Insulin injection, Breakfast, Puppy potty break, Clean surgical wound, Check heat lamp |
| `medium` | Routine care that matters but can move by a few hours or a day: walks and exercise, litter and cage cleaning, training, supplements, dental care | Morning walk, Clean litter box, Obedience training, Monthly flea prevention, Brush teeth |
| `low` | Optional grooming, enrichment, and errands | Bath, Nail trim, Puzzle feeder, Photo shoot, Visit pet store |

Some examples deliberately go against what their category alone would suggest, so the model has to use the title words as well. For example, `Remove tick` (grooming) is `high`, `Monthly flea prevention` (meds) is `medium`, and `Give a treat` (feeding) is `low`.

## Known limitations

- The model can only learn these hand-written rules. Its accuracy shows how well it matches my labels, not how well it matches real pet-care needs.
- Most examples are for dogs and cats. "Other" pets (rabbits, fish, birds, reptiles, hamsters) have far fewer examples.
- The titles are short English phrases. Other languages, long descriptions, and misspellings are not covered.
