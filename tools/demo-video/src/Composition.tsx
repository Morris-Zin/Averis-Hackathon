import {
  AbsoluteFill,
  Composition,
  Easing,
  Img,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type Props = Record<string, never>;

type Scene = {
  title: string;
  eyebrow: string;
  body: string;
  caption: string;
  accent: string;
  duration: number;
  kind:
    | "title"
    | "problem"
    | "architecture"
    | "ui"
    | "comparison"
    | "revision"
    | "controls"
    | "status";
};

const FPS = 30;

const SCENES: Scene[] = [
  {
    title: "Averis",
    eyebrow: "GOODLORD · SHIPPING DOCUMENT REVIEW",
    body: "Find the difference before it becomes a release problem.",
    caption: "GoodLord: Aung Phone Khant · Ella · Pei En · Congye",
    accent: "#70e1c1",
    duration: 15 * FPS,
    kind: "title",
  },
  {
    title: "The inbox is not the workflow",
    eyebrow: "THE PROBLEM",
    body: "Shipping teams receive requests, instructions, invoices and noise together. The Shipping Instruction is the reference; the draft Bill of Lading must agree before release.",
    caption:
      "Averis turns mixed messages into a review queue with visible uncertainty.",
    accent: "#f6c177",
    duration: 25 * FPS,
    kind: "problem",
  },
  {
    title: "One stack, one source of truth",
    eyebrow: "HOW IT WORKS",
    body: "Next.js static UI presents the work queue. FastAPI owns sessions and actions. PostgreSQL persists cases and durable runs. Private R2 stores originals. A private Railway worker processes jobs. Jev is budgeted at the boundary.",
    caption:
      "The application compares fields in code; Jev chooses categories and evidence candidates.",
    accent: "#8ea7ff",
    duration: 30 * FPS,
    kind: "architecture",
  },
  {
    title: "A reviewable queue, in four views",
    eyebrow: "ACTUAL APP CAPTURES · STATIC WALKTHROUGH",
    body: "Four static screenshots from the deployed interface show a saved synthetic example.",
    caption: "ACTUAL APP CAPTURE · SAVED SYNTHETIC EXAMPLE",
    accent: "#70e1c1",
    duration: 60 * FPS,
    kind: "ui",
  },
  {
    title: "Seven fields, explicit outcomes",
    eyebrow: "COMPARISON",
    body: "A valid SI/BL pair is checked across shipper, consignee, notify party, ports, container count and gross weight. Missing or unreadable evidence stays unknown. Known mismatches stay visible.",
    caption:
      "Only BL_COMPARISON enters shipment comparison; the SI remains authoritative.",
    accent: "#70e1c1",
    duration: 35 * FPS,
    kind: "comparison",
  },
  {
    title: "Corrections change the reading, not history",
    eyebrow: "REVIEW AND REVISIONS",
    body: "A reviewer can select source evidence, attach a controlled revised draft and recompute. Originals remain immutable. New document versions preserve the old finding and the action history.",
    caption:
      "A corrected extraction must never rewrite the original shipping document.",
    accent: "#c6a8ff",
    duration: 30 * FPS,
    kind: "revision",
  },
  {
    title: "Bounded by design",
    eyebrow: "OPERATIONS",
    body: "Durable checkpoints, leases and stale-run fencing protect retries. OCR and document readers run under explicit limits. The shared Jev ledger is capped at $7 across development and demo use. Limits reduce risk; they are not a guaranteed billing cap.",
    caption: "Confidence routes work; it is not measured accuracy.",
    accent: "#f6c177",
    duration: 30 * FPS,
    kind: "controls",
  },
  {
    title: "Useful now. Honest about what remains.",
    eyebrow: "STATUS",
    body: "Railway, Neon PostgreSQL and private R2 are live. Reused extraction-v3 validation on 97 records produced 84/97 automatic exports and 13 abstentions; 85/88 accepted categories were correct, and 22 fully comparable pairs had 154/154 fields correct.",
    caption:
      "Reused validation data · not all-request accuracy · not an independent holdout claim",
    accent: "#70e1c1",
    duration: 30 * FPS,
    kind: "status",
  },
];

const totalDuration = SCENES.reduce((sum, scene) => sum + scene.duration, 0);

const fade = (frame: number, duration: number) =>
  interpolate(frame, [0, 18, duration - 18, duration], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

const SceneFrame: React.FC<{ scene: Scene }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const opacity = fade(frame, scene.duration);
  if (scene.kind === "ui") {
    return <UiSceneFrame scene={scene} opacity={opacity} />;
  }
  const lift = interpolate(frame, [0, 24], [24, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <AbsoluteFill
      className="scene"
      style={{ opacity, padding: `${height * 0.105}px ${width * 0.085}px` }}
    >
      <div className="grain" />
      <div className="orb orb-one" style={{ backgroundColor: scene.accent }} />
      <div className="orb orb-two" style={{ borderColor: scene.accent }} />
      <header className="topline">
        <span className="brand-mark">A</span>
        <span>AVERIS / GOODLORD</span>
        <span className="topline-right">
          {String(SCENES.indexOf(scene) + 1).padStart(2, "0")} / 08
        </span>
      </header>

      <main className="main-copy" style={{ translate: `0px ${lift}px` }}>
        <div className="eyebrow" style={{ color: scene.accent }}>
          {scene.eyebrow}
        </div>
        <h1>{scene.title}</h1>
        <p className="body-copy">{scene.body}</p>
        <Visual scene={scene} />
      </main>

      <footer className="caption-bar">
        <span
          className="caption-dot"
          style={{ backgroundColor: scene.accent }}
        />
        <span>{scene.caption}</span>
      </footer>
    </AbsoluteFill>
  );
};

const UiSceneFrame: React.FC<{ scene: Scene; opacity: number }> = ({
  scene,
  opacity,
}) => (
  <AbsoluteFill className="scene ui-scene" style={{ opacity }}>
    <div className="grain" />
    <header className="ui-scene-header">
      <span className="brand-mark">A</span>
      <span>AVERIS / GOODLORD</span>
      <span>SCREENSHOT WALKTHROUGH · SYNTHETIC DEMO</span>
      <span className="topline-right">04 / 08</span>
    </header>
    <UiWalkthrough duration={scene.duration} full />
  </AbsoluteFill>
);

const Visual: React.FC<{ scene: Scene }> = ({ scene }) => {
  if (scene.kind === "title") {
    return (
      <div className="title-chip">
        <span>SI → BL</span>
        <span>evidence first</span>
        <span>review ready</span>
      </div>
    );
  }
  if (scene.kind === "problem") {
    return (
      <div className="inbox-grid">
        {[
          ["Shipping instruction", "REFERENCE", "#70e1c1"],
          ["Draft bill of lading", "COMPARE", "#8ea7ff"],
          ["Invoice query", "ROUTE", "#f6c177"],
          ["Uncertainty", "REVIEW", "#ff8f9e"],
        ].map(([label, tag, color]) => (
          <div
            className="inbox-card"
            key={label}
            style={{ borderTopColor: color }}
          >
            <span>{tag}</span>
            <strong>{label}</strong>
          </div>
        ))}
      </div>
    );
  }
  if (scene.kind === "architecture") {
    return (
      <div className="architecture-grid">
        <Node label="Next.js" sub="static UI" color="#8ea7ff" />
        <Arrow />
        <Node label="FastAPI" sub="workflow" color="#70e1c1" />
        <Arrow />
        <Node label="PostgreSQL" sub="durable state" color="#f6c177" />
        <Node label="Private R2" sub="originals" color="#c6a8ff" />
        <Arrow />
        <Node label="Railway worker" sub="leases + retries" color="#ff8f9e" />
        <Arrow />
        <Node label="Jev" sub="budgeted AI" color="#70e1c1" />
      </div>
    );
  }
  if (scene.kind === "ui") {
    return <UiWalkthrough duration={scene.duration} />;
  }
  if (scene.kind === "comparison") {
    const fields = [
      "SHIPPER",
      "CONSIGNEE",
      "NOTIFY",
      "LOAD PORT",
      "DISCHARGE",
      "CONTAINERS",
      "WEIGHT",
    ];
    return (
      <div className="field-row">
        {fields.map((field, index) => (
          <div className={`field field-${index}`} key={field}>
            <span>{field}</span>
            <b>{index === 4 || index === 5 ? "MISMATCH" : "MATCH"}</b>
          </div>
        ))}
      </div>
    );
  }
  if (scene.kind === "revision") {
    return (
      <div className="revision-flow">
        <div className="revision-card">
          ORIGINAL
          <br />
          <strong>BL v1</strong>
          <small>immutable</small>
        </div>
        <div className="revision-arrow">→</div>
        <div className="revision-card active">
          EVIDENCE
          <br />
          <strong>reading corrected</strong>
          <small>source-bound</small>
        </div>
        <div className="revision-arrow">→</div>
        <div className="revision-card">
          NEW VERSION
          <br />
          <strong>BL v2</strong>
          <small>history retained</small>
        </div>
      </div>
    );
  }
  if (scene.kind === "controls") {
    return (
      <div className="control-grid">
        <div>
          <strong>CHECKPOINTS</strong>
          <span>resume safely</span>
        </div>
        <div>
          <strong>LEASES</strong>
          <span>fence stale work</span>
        </div>
        <div>
          <strong>$7 LEDGER</strong>
          <span>shared allowance</span>
        </div>
        <div>
          <strong>OCR LIMITS</strong>
          <span>bounded readers</span>
        </div>
      </div>
    );
  }
  return (
    <div className="status-grid">
      <div className="status-badge live">
        <span /> RAILWAY LIVE
      </div>
      <div className="status-badge">NEON POSTGRES</div>
      <div className="status-badge">PRIVATE R2</div>
      <div className="status-badge pending">REUSED VALIDATION</div>
      <div className="status-url">
        averis-hackathon-production.up.railway.app
      </div>
    </div>
  );
};

const UI_STEPS = [
  {
    src: staticFile("captures/queue.png"),
    title: "Queue",
    detail: "Eight cases grouped by result, category and assignee.",
    position: "top",
    zoom: 1,
    offset: 0,
  },
  {
    src: staticFile("captures/review.png"),
    title: "Review",
    detail: "A saved synthetic comparison routes two mismatches to review.",
    position: "top",
    zoom: 1,
    offset: 0,
  },
  {
    src: staticFile("captures/comparison.png"),
    title: "Comparison",
    detail: "The SI is the reference; seven fields stay explicit.",
    position: "center",
    zoom: 1.6,
    offset: 32,
  },
  {
    src: staticFile("captures/correction.png"),
    title: "Correction",
    detail: "Evidence is selected before a source-bound reading is recomputed.",
    position: "center",
    zoom: 1.2,
    offset: 0,
  },
] as const;

const UiWalkthrough: React.FC<{ duration: number; full?: boolean }> = ({
  duration,
  full = false,
}) => {
  const frame = useCurrentFrame();
  const stepDuration = duration / UI_STEPS.length;
  const activeIndex = Math.min(
    UI_STEPS.length - 1,
    Math.floor(frame / stepDuration),
  );
  const localFrame = frame - activeIndex * stepDuration;
  const imageOpacity = interpolate(
    localFrame,
    [0, 18, stepDuration - 18, stepDuration],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const step = UI_STEPS[activeIndex];

  return (
    <div className={`ui-walkthrough ${full ? "ui-walkthrough-full" : ""}`}>
      <div className="ui-capture-frame">
        <Img
          src={step.src}
          className="ui-capture-image"
          style={{
            opacity: imageOpacity,
            objectPosition: step.position,
            transform: `translateX(${step.offset}px) scale(${step.zoom})`,
          }}
        />
      </div>
      <div className="ui-step-label">
        <span>
          {String(activeIndex + 1).padStart(2, "0")} / {UI_STEPS.length} ·{" "}
          {step.title}
        </span>
        <strong>{step.detail}</strong>
      </div>
    </div>
  );
};

const Node: React.FC<{ label: string; sub: string; color: string }> = ({
  label,
  sub,
  color,
}) => (
  <div className="arch-node" style={{ borderColor: color }}>
    <strong>{label}</strong>
    <span>{sub}</span>
  </div>
);

const Arrow: React.FC = () => <span className="arch-arrow">→</span>;

export const MyComposition = () => (
  <Composition
    id="AverisSubmissionDraft"
    component={MyComponent}
    durationInFrames={totalDuration}
    fps={FPS}
    width={1280}
    height={720}
    defaultProps={{}}
  />
);

export const MyComponent: React.FC<Props> = () => {
  let from = 0;
  return (
    <AbsoluteFill className="video-root">
      {SCENES.map((scene) => {
        const start = from;
        from += scene.duration;
        return (
          <Sequence
            key={scene.title}
            from={start}
            durationInFrames={scene.duration}
          >
            <SceneFrame scene={scene} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
