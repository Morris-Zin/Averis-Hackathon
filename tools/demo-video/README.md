# Averis submission video draft

This Remotion composition is a 3:45 editable, captioned draft for the GoodLord submission. It covers the problem, seven-field comparison, architecture, source-bound corrections, operational limits, shared Jev budget and the current evidence boundary.

The UI section is deliberately marked **REAL UI CAPTURE REQUIRED**. It is a visual placeholder, not fabricated application footage. Replace that 30-second section with a signed-out browser recording of the deployed app before publishing. The draft has no voiceover or music; the on-screen caption bar keeps the story understandable while real footage and audio are added.

## Commands

Install dependencies from this directory:

```console
pnpm install
```

Start the editable preview:

```console
pnpm dev
```

Open the `AverisSubmissionDraft` composition in Remotion Studio. Render only after replacing the placeholder and checking current validation facts:

```console
pnpm exec remotion render AverisSubmissionDraft out/averis-submission-draft.mp4
```

## Assets still needed

- A real signed-out browser capture of the deployed Railway UI: fresh workspace, five categories, Needs review, Mismatches, evidence and one source-bound correction.
- Optional narration/music, recorded separately and kept free of credentials, billing screens, ground truth and private browser tabs.
- Final measured evaluation results, if available, to replace the status card without claiming accuracy before the holdout run is complete.

The composition itself uses no external image or video assets, so the placeholder can be replaced by a Remotion `<Video>` or `<Img>` layer without changing the rest of the timeline.
