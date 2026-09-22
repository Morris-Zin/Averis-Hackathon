# Averis benchmark report

[Project document](PROJECT.md) | [Source code and setup](README.md)

## Key results

| Test set | Result |
| --- | --- |
| 520 organizer emails | **99.63/100** official combined score |
| Recorded category suggestions on 520 organizer emails | **520/520 correct**, or **100%** |
| Known shipment defects in that set | **46/46** cases caught |
| 170 team-made test emails | **162/170**, or **95.3%**, complete results correct |

Both sets use saved AI and OCR readings from data used during development.
We ran those readings through the app's processing rules again. These are
development benchmarks, with no new AI calls during the replay. The two sets
have different scoring methods and are reported separately.

### Email category suggestions

In the recorded organizer classification test, all **520 AI category suggestions**
matched the supplied labels. Of these, 515 were accepted automatically and five
remained for review. This classification check was recorded at code version
`0ca0e00`, before the organizer-score version below.

A suggestion and an accepted decision are different. The app keeps uncertain
suggestions for review. The official category score also depends on which rows
can be exported, so it is a different measure from suggestion correctness.

## Organizer test set

Code version: [68ffe2e](https://github.com/Morris-Zin/Averis-Hackathon/commit/68ffe2eaf52b762b90df8232ae897f1d5758c4e4).

The unchanged organizer scorer combines three measures:

| Measure | Weight | Recorded value |
| --- | --- | --- |
| Success on the planted defect cases | 50% | 46/46, or 1.000000 |
| Balance of correct email categories across the five groups, called macro-F1 | 30% | 0.987507 |
| Balance of correctly flagged defects and caught defects, called defect-F1 | 20% | 1.000000 |

The weighted result is **0.996252**, or **99.63/100**.

The saved export contains **513 of the 520 email rows**. The official scorer
applies its own defaults to the seven omitted rows. Those defaults are included
in the score above. The export has 358 OK rows, 46 MISMATCH rows and 109
NEEDS_REVIEW rows. Mismatches also go to human review in the app, so OK and
NEEDS_REVIEW counts alone do not measure total review work.

For the 20 emails labelled as needing review, the scorer recorded 18 correct
review escalations. This measure is reported separately from the combined score.

### Check the saved outputs

- [Official scorer output](evidence/organizer-score.json): full scores and category counts.
- [Predictions passed to the scorer](evidence/organizer-predictions.json): the 513 exported rows.
- [File checksums](evidence/sha256.json): SHA-256 values to check file identity.

The scorer was run again against this exact prediction file while preparing
this report and returned the same score. This checks the calculation; it does
not make fresh AI predictions.

To repeat the calculation, obtain the organizer Docker kit and place it under
`resources/official/docker`. From the repository root, after the README setup:

```powershell
uv run --project backend python resources/official/docker/server/score_cli.py evidence/organizer-predictions.json --json
```

This uses the kit's supplied answer file only for evaluation. The scorer accepts
partial exports and applies defaults. The app's stricter submission validator
requires every email ID, so this saved export is a benchmark artifact rather
than a complete submission file.

## Team-made test set

Code version: [b4522d8](https://github.com/Morris-Zin/Averis-Hackathon/commit/b4522d8c9b8efe5cfe434f0397b39af03e8da231).

These 170 synthetic emails cover multiple categories, languages and file types.
A complete result counts as correct only when the category, status and defect
fields all agree with the test answer.

| Measure | Result |
| --- | --- |
| Complete results correct | 162/170, or 95.3% |
| Known defect cases with a confirmed expected warning | 61/62 |
| Incorrect all-clears | 0 |
| Processing failures | 0 |
| Comparison cases sent to review, including mismatches | 89/110 |

Eight cases did not match the complete expected result. Four needed a category
decision, and four involved Chinese documents. All eight stayed in review.
Sending a case to review and identifying its exact defect are different results.

The review count includes real mismatches as well as unclear readings. It shows
how much work reaches a person, not the number of software failures.

[Saved counts and the eight case outcomes](evidence/synthetic-results.json)
provide the details. Network calls were blocked during this replay. No new OCR,
AI calls or simulated human corrections were included.

## Software and live-flow checks

The organizer-score release passed 589 backend tests and 27 frontend tests,
with three backend tests skipped. Checks included PostgreSQL, code checks, API
data formats and an app build. [View the release CI run](https://github.com/Morris-Zin/Averis-Hackathon/actions/runs/35660169349).

Three live imports also completed on their first attempt: one matching case
and two mismatch cases. Checks covered source evidence, the visible kg default
and automatic review routing. These live checks are separate from the saved-data
benchmark and the automated software tests.

## Next measurement

The next pilot will use new shipment documents and measure reviewer time,
missed errors, false warnings, review workload and cost per email. That will
test the value of Averis in daily shipping work.
