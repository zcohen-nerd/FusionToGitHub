# Usability test: people new to Git

Before 1.0, at least **three people who have never used Git** try the add-in
on their own, using only the documentation. This checks the promise in the
README: a first backup in under ten minutes, the design found on GitHub, and
an old version brought back, without help. Results go into the
[acceptance matrix](../tests/ACCEPTANCE_MATRIX.md) as X1–X4.

## Who

- Three or more people who use Fusion (or another CAD program) but have
  **never used Git or GitHub**. Engineers, makers or students are ideal.
  Colleagues who have watched you use the add-in are not.
- Each session is one person, alone with the facilitator, about 45 minutes.

## Before the session (facilitator)

1. A computer with Fusion, a clean Windows account if possible, and **no**
   Git, add-in or saved settings from earlier tests. Uninstall them as in
   [docs/INSTALL.md](INSTALL.md#uninstall) if needed. Installing Git is part
   of the test.
2. A GitHub account for the participant: their own, or a fresh test account.
   They create the repository during the test.
3. A small design in Fusion that they don't mind backing up, for example one
   from the [test designs](../tests/live/README.md).
4. A timer, this sheet, and the participant's agreement to be observed. No
   recording of their screen or voice unless they agree; no personal data in
   the notes beyond a participant number.

## Instructions to read aloud

> "This add-in backs up Fusion designs to GitHub. We're testing the add-in and
> its instructions, not you. Please think aloud: say what you're looking for
> and what you expect. I won't help unless you're stuck for more than five
> minutes; if I do, that's useful for us, not a failure for you. Start from
> the GitHub page of the add-in: [README](../README.md)."

## Tasks

| # | Task | Success when | Time limit |
|---|---|---|---|
| T1 | Install Git and the add-in, so that the Push to GitHub button appears | The button is visible | — |
| T2 | Back up the open design to a new, private repository on your GitHub account | The summary says it was backed up | **T1+T2 under 10 minutes** without help |
| T3 | Find the backed-up design on GitHub | They show the design's folder with the Fusion file | 3 minutes |
| T4 | Change the design (for example, a hole size), back it up again with a note | The second backup's summary appears | 3 minutes |
| T5 | Get the *first* version back into Fusion, using only the documentation | The first version opens in Fusion as a new design | 10 minutes |

## What to record (one sheet per participant)

- Participant number, date, Fusion and Windows versions, add-in version.
- For each task: time taken, success (yes / with help / no), and every point
  where they hesitated, went wrong or asked for help, with what they said.
- Messages they didn't understand, quoted exactly.
- Anything the documentation said that didn't match what they saw.

## Debrief (5 minutes)

1. What was the hardest part?
2. Was anything surprising or worrying (for example the publication notice,
   or the sign-in window)?
3. Would you trust this to back up your work? Why or why not?
4. On a scale of 1 (very hard) to 5 (very easy), how easy was it overall?

## Passing

The usability criterion is met when **at least three participants** each
complete T1–T2 in under ten minutes without help, and T3 and T5 using only the
documentation. Every problem observed becomes an issue (a defect or a
documentation fix) and is noted against X1–X4, with a decision on whether it
blocks 1.0.
