# Every AI Agent You Use Has Amnesia. I Spent Months Fixing It.

I hit my breaking point on a Tuesday.

I was three hours into a coding session with Claude. We'd made real progress. Refactored the auth system, decided on JWT with short-lived tokens, mapped out the middleware chain. Good stuff.

Then my terminal crashed.

New session. "Hi, how can I help you today?"

Three hours of shared context. Gone. Like it never happened.

I sat there staring at the screen thinking — we put AI in everything. Code editors. Chat apps. Email. Planning tools. And not a single one of them remembers what happened yesterday.

That was the moment I stopped being annoyed and started being obsessed.

---

I started digging. Surely someone had solved this.

Turns out, yeah, people have tried. The standard approach is simple: store everything the user says, embed it into vectors, retrieve with similarity search.

I tried a few. They work. Sort of.

But something kept nagging me. Three things, specifically. And the more I thought about them, the more I realized they weren't edge cases. They were fundamental design flaws.

---

**The first thing: nobody forgets.**

I was using one of these memory layers for about two months. Worked great at first. My AI remembered my preferences, my stack, my decisions.

Then it started getting weird. I'd ask about my current auth approach and it would pull up a decision I made in week one. Before I'd changed my mind. Before I'd learned better. That old decision was sitting right next to the current one. Same priority. Same weight.

My context window was filling up with ghosts. Stale facts haunting my retrieval results.

And I thought — that's not how my brain works. I don't remember what I had for lunch three Tuesdays ago. That memory decayed. Naturally. Because it wasn't important enough to keep.

I went looking for research and found a paper called FadeMem. Bio-inspired forgetting for AI agents. The core idea: the Ebbinghaus forgetting curve isn't a flaw in human cognition. It's a feature. Important stuff gets reinforced through repeated access. Unimportant stuff fades. The result is a memory system that's always current, always relevant, and about 45% smaller than one that hoards everything.

I read that paper three times. Then I started building.

---

**The second thing: agents write whatever they want.**

I was testing a setup where my coding agent could save notes to memory. Useful in theory. In practice, it was writing garbage.

Half-formed thoughts. Duplicate facts phrased slightly differently. One time it contradicted something I'd explicitly told it a week earlier. And I didn't notice for days because the writes just went straight in. No review. No staging. No nothing.

Would you give a new intern root access to your production database on day one?

Then why does every memory system give every AI agent full write permissions from the start?

I kept thinking about how real teams handle this. New hire submits a PR. Someone reviews it. Over time they earn trust. Eventually they get merge rights. There's a progression.

Nobody was building memory like that.

---

**The third thing: memory was just "find similar text."**

I was trying to recall a specific debugging session. I knew roughly when it happened. I knew what we were working on. I could almost see the conversation in my head.

But when I searched, I got scattered facts. A JWT token reference from one session. A middleware mention from another. An auth decision from a third. All "similar" to my query. None of them the actual session I was thinking of.

Because I wasn't looking for similar text. I was looking for an episode. A scene. Time, place, what happened, what we decided.

That's how human memory works. You don't remember Tuesday as a bag of keywords. You remember the morning meeting. The long debugging session after lunch. The architecture argument at 4pm. Scenes.

I found another paper. CAST — Contextual Associative Scene Theory. It explains exactly this. Humans organize memory into episodes defined by shifts in time, place, and topic. When you recall something, you're pulling an entire scene, not running a text search.

Nobody was building AI memory this way either.

---

So I built it.

I spent months on it. It's called Engram. And it works differently from anything else I've seen.

---

Here's the core idea. Memory should work like memory actually works. Biologically.

**New memories start weak.** When your AI stores something, it goes into short-term storage. Strength of 1.0. A proposal, not a permanent record.

**Repeated access makes them stronger.** Ask about your TypeScript preference three times across different sessions? That memory gets promoted to long-term storage. It earned its place.

**Unused memories fade.** That random note from two months ago that nobody's referenced since? Its strength decays. Gradually. Following the same curve Ebbinghaus mapped in 1885. Eventually it's gone. No manual cleanup. No "memory management." It just happens.

The result surprised me. 45% less storage. And retrieval got better, not worse. Because when you search, you're not wading through ghosts anymore. Everything that surfaces is current and relevant.

There's a catch though. What if Agent A stopped using a memory but Agent B still relies on it? Should it decay?

No. So I built reference-aware decay. The system tracks who's using what. A memory stays alive as long as any agent references it. Even if the original writer forgot about it.

---

Writes were the next problem to solve.

In Engram, every write is a proposal. It lands in staging. Not in your canonical memory. Staging.

The system runs checks. Does this contradict something already stored? Is it a duplicate? Is it from a trusted agent or a new one?

Contradictions go to a conflict stash. You decide which version wins.

New agents start with low trust. Everything they write waits for your approval. As you approve good writes, their trust score climbs. Eventually they earn auto-merge. Just like that new hire earning commit access.

Your memory. Your rules. Always.

---

Episodic memory was the hardest part to build. And the most satisfying.

Engram watches the conversation flow and detects scene boundaries. Long pause? New scene. Topic shifted from frontend to deployment? New scene. Different repo? New scene.

Each scene captures when it happened, where (which project, which repo), who was involved, what was discussed, and what decisions came out of it. Plus links to the semantic facts that were extracted.

So when you ask "what did we decide in that auth session?" Engram doesn't fumble through scattered vector matches. It pulls the scene. The whole episode. Timeline, participants, synopsis, decisions.

It's the difference between searching your email for "auth" and actually remembering the meeting where you made the call.

---

Then I thought — why does each memory get one shot at being found?

Standard approach: embed the text, store the vector, pray the query matches.

I built something called EchoMem. Every memory gets encoded five ways:

The raw text. A paraphrase. Keywords extracted from it. Implications (what does this fact suggest?). And a question form (what question would this be the answer to?).

Five retrieval paths instead of one. Five chances to match.

The question encoding turned out to be weirdly powerful. When an agent asks "what stack should I recommend?" it directly matches against memories stored as "What language does the user prefer?" Much stronger signal than fuzzy cosine similarity between unrelated phrasings.

---

And retrieval itself is dual-path. Semantic search and episodic search run in parallel.

If a fact shows up in both? Its confidence score gets boosted. Intersection promotion.

This kills the most annoying failure mode in AI memory: semantically similar but contextually wrong results. "You mentioned JWT tokens" — yes, three months ago, in a different project, before I changed my mind. The episodic layer catches that. The semantic layer alone never would.

---

There's one more thing that I think matters.

When an agent queries outside its scope, it doesn't get nothing. It gets structure without details.

```json
{
  "type": "private_event",
  "time": "2026-02-10T17:00:00Z",
  "importance": "high",
  "details": "[REDACTED]"
}
```

Your scheduling agent knows you're busy. It doesn't need to know why. Your coding agent knows a decision was made. It doesn't need to see the financial discussion behind it.

I call it "all but mask." Need-to-know, enforced at the memory layer.

---

The part I didn't expect to build: cross-agent handoff.

I was using Claude Code for a task, got halfway through, then switched to Cursor the next day. Fresh start. No memory of what Claude Code had done.

So I built a handoff bus. When an agent pauses work, it saves a session digest. What was the task. What decisions were made. What files were touched. What's left to do.

Next agent picks up. Calls `get_last_session`. Gets the full context. Continues from where the last agent stopped.

No re-explanation. No copying context between tools. Your agents work like a relay team.

---

All of this runs locally. `127.0.0.1:8100`. Your data never leaves your machine unless you want it to.

Three commands to set up:

```
pip install engram-memory
export GEMINI_API_KEY="your-key"
engram install
```

Restart your agent. Done.

`engram install` auto-configures Claude Code, Cursor, Codex. One command. All your agents. Same memory kernel underneath.

Want fully offline? Use Ollama. No API keys. No cloud. Nothing leaves your laptop.

Open source. MIT licensed.

---

I've been running this for my own workflow for a while now. The difference is hard to overstate.

Monday I make a decision in Claude Code. Tuesday, Cursor knows about it. Not because I told it. Because the memory is shared.

Last week's debugging session? I can pull the whole episode. Not scattered facts. The scene. What we tried, what failed, what worked, what we decided.

And the context window isn't full of ghosts from three months ago. Decay took care of those. What surfaces is current and relevant.

It sounds small. It's not. The compound effect of never re-explaining yourself changes how you work with AI.

---

I built this because I needed it. I'm sharing it because I think everyone does.

Models will keep getting better. They'll get faster, cheaper, smarter. But without memory, every session still starts from zero. The smartest model in the world is useless if it can't remember what you told it yesterday.

Memory is the missing infrastructure layer. Not a feature. Infrastructure.

```
pip install engram-memory
```

[GitHub](https://github.com/Ashish-dwi99/Engram)

Your agents forget everything between sessions. Engram fixes that.
