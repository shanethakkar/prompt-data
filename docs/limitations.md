# Known Limitations

The honest page. Every item here is something the eval measured or the design cannot
catch, stated plainly. Source for the /limitations page (Phase 5).

## Confidence is well-calibrated but low-resolution

Confidence comes from self-consistency: K generations at nonzero temperature, scored by
how often their result sets agree. On a strong model this signal is **coarse** — in the
Sonnet 4.6 BIRD run, 215 of 240 questions reached full agreement (raw confidence 1.0)
despite 56% execution accuracy. The model is often confidently consistent even when wrong.

Calibration (isotonic regression on a held-out split) fixes the *calibration* of this
signal — it deflates the over-confident 1.0 down to the empirically observed ~0.71, taking
ECE from 0.44 to 0.15. But it cannot add *resolution*: the calibrated score sorts answers
into a high-agreement majority (~0.71 accurate) and a smaller low-agreement minority, rather
than finely separating right from wrong within the majority. So the confidence number is
trustworthy as a probability but blunt as a per-answer right/wrong discriminator. Adding an
orthogonal signal (the model's own stated uncertainty, more diverse sampling, or a verifier
pass) is future work, deliberately not done in v1.

## The confidently-wrong reduction depends on the question mix

The headline "trust layer reduces confidently-wrong answers" is demonstrated on the **trap
set** (ambiguous, unanswerable, and prompt-injection questions over the Olist demo), where
the clarification arm fires. It is **not** demonstrated on BIRD, whose questions are
well-specified and ship with gold SQL, so the clarification gate correctly never triggers
there. Read the trap-eval numbers as the evidence for that claim, not the BIRD numbers.

## Metrics are a pinned subset, not full BIRD

Execution accuracy, semantic-error rate, and calibration are measured on a pinned,
stratified 240-question subset of BIRD dev (of 1534), with Sonnet 4.6. They are reported
with their N and should not be read as full-BIRD or leaderboard numbers. Calibration is
fit/evaluated on small splits (test_n ~96), so the exact ECE/Brier carry real noise.

## Semantic errors still slip through

Execution accuracy is ~56% on the subset, so a large fraction of answered questions return
the wrong result. The trust layer reduces how often those are surfaced *confidently*, but it
does not make them correct. A wrong query that executes and that the model agrees with itself
on will still be answered.

## What the validator cannot catch

The SELECT-only validator guarantees no write ever reaches the database, and it blocks
multi-statement and DDL/DML injection. It does **not** judge whether a read is semantically
appropriate: a SELECT that reads columns it arguably should not, or a cleverly-phrased
prompt that still yields a valid SELECT, executes. Semantic appropriateness is the trust
layer's job, and it is probabilistic.

## Non-determinism in the confidence signal

The displayed answer is generated at temperature 0 and is reproducible. The K-1 confidence
samples use nonzero temperature and are not seeded, so the confidence value can vary slightly
between runs. The committed eval_results.json is the canonical record for reported numbers.
