# Engram Pitch Deck v2

> Story-first, light-theme, Excalidraw-style deck spec aligned with the current Engram landing page visual language.
> Use this as your source of truth for Keynote, Google Slides, Figma, or Excalidraw export.

---

## 0) Visual System (Match Landing Page)

### Theme Tokens

- Canvas: `#F6F6F6`
- Card surface: `#FFFFFF`
- Border: `rgba(0,0,0,0.08)`
- Headline text: `#111111`
- Body text: `#525252`
- Label text: `#9CA3AF`
- Accent (sparingly): `#6366F1` at 10-20% opacity
- Divider grid: `rgba(0,0,0,0.05)`

### Typography

- Headlines: `Space Grotesk` (semibold)
- Body and labels: `Manrope`
- Micro-labels: uppercase, tracking `0.28em` to `0.35em`

### Excalidraw Style Rules

- Use hand-drawn rectangles, rounded corners, and arrows.
- Stroke width: 1.5-2 px, dark gray (`#1F2937`), roughness medium.
- Keep icon style monoline, rounded caps.
- Add subtle paper-grid background on every slide.
- Avoid heavy gradients; if needed, use very soft radial highlights.

### Icon Language

Use simple line icons (Lucide/Tabler style), monochrome:

- Memory: `brain`, `database`
- Trust/Safety: `shield-check`, `lock`, `alert-triangle`
- Interop: `plug`, `network`
- Retrieval: `search`, `layers`, `clock`
- Motion/flow: `arrow-right`, `git-branch`

---

## 1) Cover Slide

### On-Slide Content

**PERSONAL MEMORY KERNEL FOR AI AGENTS**

# One memory store.
# Every agent, personalized.

Engram makes AI remember your context across tools while keeping memory user-owned.

`pip install engram-memory`

### Excalidraw Composition

- Center sketch: one "Memory Vault" box in the middle.
- Around it, small agent cards: Claude Code, Cursor, Codex, Custom Agent.
- Hand-drawn arrows from all cards to the vault.
- Tiny lock icon on the vault.

### Speaker Notes

"Today, every agent forgets you. Engram changes that with one user-owned memory kernel any agent can plug into. Same user context, across tools, under your control."

---

## 2) The Context Tax (Problem)

### On-Slide Content

## Every agent starts from zero.

- You repeat preferences across sessions.
- Decisions made yesterday are lost today.
- Work quality drops from context resets.

**The hidden tax:** re-explaining what your systems should already know.

### Excalidraw Composition

- Left-to-right comic strip, 3 panels:
  - "Tell agent your setup"
  - "Agent forgets"
  - "Tell it again"
- Loop arrow from panel 3 back to panel 1.
- Add clock icon + "time lost" note.

### Speaker Notes

"The biggest AI productivity drain is not model quality. It is memory reset. Teams keep paying a context tax in every interaction."

---

## 3) Why This Gets Worse

### On-Slide Content

## More agents -> more memory silos.

- Workflows are becoming multi-agent by default.
- Each tool builds isolated context.
- User identity fragments across vendors.

**Without a memory layer, AI stacks become context-fragmented systems.**

### Excalidraw Composition

- One user avatar at center top.
- Five agent boxes below, each connected to separate mini-databases.
- Red cross-lines between databases to show no interoperability.

### Speaker Notes

"As agent count increases, fragmentation compounds. You do not have one assistant with weak memory. You have many assistants with disconnected memory."

---

## 4) The Insight + Vision

### On-Slide Content

## Memory should be infrastructure, not a feature.

What users need:

- One portable memory layer
- Works across any agent runtime
- Local-first by default
- User approval on writes

**Engram = Personal Memory Kernel (PMK)**

### Excalidraw Composition

- Split slide:
  - Left: "Current" (silos)
  - Right: "PMK" (one shared kernel)
- Use plug icons on right side to show easy integration.

### Speaker Notes

"We are not building another assistant. We are building the memory substrate that personalizes every assistant."

---

## 5) Product Reveal

### On-Slide Content

## Engram in 3 commands

```bash
pip install engram-memory
export GEMINI_API_KEY="your-key"
engram install
```

Then restart your agent.

- Persistent memory across sessions
- Scoped retrieval
- Staged writes and approval

### Excalidraw Composition

- Terminal card on left with the 3 commands.
- Right side: before/after cards:
  - Before: "stateless assistant"
  - After: "context-aware assistant"
- Arrow between before and after.

### Speaker Notes

"This is designed for zero-friction adoption. Install, configure once, and your existing agent stack becomes memory-enabled."

---

## 6) Trust and Safety by Design

### On-Slide Content

## Agents are untrusted writers.

Write pipeline:

1. Propose -> staging
2. Verify -> invariants, conflicts, risk
3. Approve/reject -> user or policy
4. Promote -> canonical memory

**All-but-mask:** out-of-scope data returns structure only, details redacted.

### Excalidraw Composition

- Horizontal 4-step pipeline with boxes and arrows.
- Small side stash box labeled "Conflict Stash".
- Shield icon above the pipeline.
- Masked response bubble:
  - `type`
  - `time`
  - `importance`
  - `details: [REDACTED]`

### Speaker Notes

"Most memory systems optimize for write convenience. We optimize for trust. Engram treats every agent as untrusted until proven reliable."

---

## 7) Retrieval Quality: Dual Memory Engine

### On-Slide Content

## Better recall with fewer hallucinated joins.

Engram retrieves in parallel:

- Semantic memory (facts, entities, preferences)
- Episodic memory (CAST scenes: time/place/topic)

Intersection promotion boosts results appearing in both.

**Output:** token-bounded context packet with citations.

### Excalidraw Composition

- Two circles (semantic, episodic) with overlap region highlighted.
- Arrow from overlap to a "Context Packet" card.
- Magnifier icon + timeline icon.

### Speaker Notes

"Dual retrieval reduces the classic failure mode: semantically similar, temporally wrong answers."

---

## 8) The Bio-Inspired Core

### On-Slide Content

## Not just vector search.

- **FadeMem:** decay and consolidation
- **EchoMem:** multi-path encoding
- **CAST:** episodic scene memory

Result: higher signal density, lower storage bloat, better long-horizon recall.

### Excalidraw Composition

- Three stacked cards with icons:
  - Brain + clock (FadeMem)
  - Spark/echo waves (EchoMem)
  - Film frames/timeline (CAST)
- Curved arrows showing loop: write -> recall -> reinforce/decay.

### Speaker Notes

"Engram uses memory dynamics inspired by cognitive science: reinforcement for important memory, decay for stale memory, and episodic grouping for narrative recall."

---

## 9) Why We Win (Positioning)

### On-Slide Content

## Category wedge: user-owned memory

Most alternatives optimize for hosted convenience.
Engram optimizes for user control + interoperability.

### Comparison Snapshot

| Capability | Typical memory SaaS | Engram |
|:--|:--|:--|
| Data location | Vendor cloud first | Local-first |
| Write control | Direct writes | Staged + verification |
| Cross-agent portability | Partial | Native goal |
| Episodic memory | Limited | CAST scenes |
| Scope masking | Basic ACL | Structural redaction |

### Excalidraw Composition

- Matrix table inside hand-drawn frame.
- Add check icons in Engram column.
- Add a bold outline around Engram column.

### Speaker Notes

"Our differentiation is architectural, not cosmetic. User-owned memory is the default, not an enterprise add-on."

---

## 10) Adoption and GTM

### On-Slide Content

## Open source adoption, productized monetization.

Top-of-funnel:

- `pip install` developer adoption
- MCP-native integrations
- Docs + demos + benchmark narratives

Monetization path:

- Managed cloud for teams
- Enterprise controls and support
- Usage-based billing tied to memory operations

### Excalidraw Composition

- Flywheel sketch:
  - OSS adoption -> integrations -> community trust -> enterprise pull -> managed revenue -> faster product
- Use circular arrows and small icon nodes.

### Speaker Notes

"The open core gives distribution. Managed and enterprise offerings give durable revenue without breaking the user-owned thesis."

---

## 11) Roadmap (12-Month)

### On-Slide Content

## Execution roadmap

- **Q1:** Benchmark publication + retrieval quality report
- **Q2:** Deeper graph/entity memory and tooling
- **Q3:** Team memory and governance controls
- **Q4:** Managed cloud GA + migration tooling

### Excalidraw Composition

- Horizontal timeline with 4 milestones.
- Milestone cards include one icon each.
- Add "today" marker near Q1.

### Speaker Notes

"Roadmap sequencing is deliberate: prove quality, expand capability, then scale distribution and revenue."

---

## 12) The Ask

### On-Slide Content

## We are building the memory substrate for the agent era.

**Raising:** `[amount]` at `[stage]`

Use of funds:

- 60% product + infrastructure
- 25% GTM + developer growth
- 15% operations + compliance

**CTA:** If you believe memory should be user-owned and portable, we should work together.

Contact:

- GitHub: `Ashish-dwi99/Engram`
- PyPI: `engram-memory`
- Email: `[you@email.com]`

### Excalidraw Composition

- Single centered ask card with strong border.
- Background doodles: plug, shield, brain, arrow-up.

### Speaker Notes

"Models will commoditize. Memory will differentiate. We are building the independent memory layer that every agent stack will need."

---

## Appendix A: Slide Build Checklist (Fast)

- Create one master with grid overlay and light paper texture.
- Keep max 1 core message per slide.
- Keep max 3 visual objects per quadrant.
- Use one accent color only for emphasis.
- Keep icon stroke consistent across all slides.

---

## Appendix B: Objection Handling

### "Could larger vendors just add this?"

They can add memory features. Harder to add user-owned portability as their default architecture and business model.

### "Why not just store everything forever?"

Because unbounded memory degrades retrieval quality. Intelligent decay improves precision and cost.

### "How do you handle privacy?"

Local-first by default, staged writes, scoped retrieval, and structural masking for out-of-scope data.

### "What is the moat?"

Product moat: integrations + workflow depth.
Architecture moat: trust-aware memory operations and episodic + semantic retrieval.
Data moat: user-retained memory continuity across toolchains.

---

## Timing Guide (7-8 minutes)

| Segment | Time |
|:--|:--|
| Slides 1-3 (Problem) | 2:00 |
| Slides 4-6 (Solution + Trust) | 2:15 |
| Slides 7-9 (Tech + Positioning) | 1:45 |
| Slides 10-12 (Business + Ask) | 1:30 |

Target total: ~7:30 + optional 2-minute product demo.
