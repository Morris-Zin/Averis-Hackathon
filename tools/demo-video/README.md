# Averis submission video draft

This Remotion composition is a 4:15 editable, captioned draft for the GoodLord submission. It covers the problem, seven-field comparison, architecture, source-bound corrections, operational limits, shared Jev budget and the current evidence boundary.

The UI walkthrough uses four screenshots from the deployed app: queue, review, comparison and correction. It is labelled **SCREENSHOT WALKTHROUGH · SYNTHETIC DEMO**. The draft is captioned and has no voiceover or music. Continuous interaction footage and narration can be added before submission if the team prefers.

Review copy: https://drive.google.com/file/d/12hX70kszrn_eIjhXreldpp6YIJV-ek4T/view

## Commands

Install dependencies from this directory:

```console
pnpm install
```

Start the editable preview:

```console
pnpm dev
```

Open the `AverisSubmissionDraft` composition in Remotion Studio. Render the reviewable MP4:

```console
pnpm exec remotion render AverisSubmissionDraft out/averis-submission-review.mp4
```

## Evidence labels

- `public/captures/queue.png`, `review.png`, `comparison.png` and `correction.png` are actual deployed UI captures supplied for this draft.
- The captures show a saved synthetic scenario; the video does not present it as organizer ground truth or measured accuracy.
- The status card reports reused extraction-v3 validation: 84/97 automatic exports, 13 abstentions, 85/88 accepted categories correct, and 22 fully comparable pairs with 154/154 fields correct. It explicitly avoids all-request accuracy and independent-holdout claims.
- Optional narration/music, recorded separately and kept free of credentials, billing screens, ground truth and private browser tabs.

The composition uses only the four local PNG captures and editable Remotion layout. No interaction is fabricated and no upload or deployment is performed by the video tooling.
