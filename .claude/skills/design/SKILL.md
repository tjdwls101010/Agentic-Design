---
name: design
description: Work with 성진 on promotional images — web posters, card news, YouTube thumbnails, anniversary posters, shorts templates, logos and assets, photo grading — built as ArtCraft documents he can open and finish by hand (PhotoCraft .pcraft, VectorCraft .vectorcraft, LightCraft libraries), with material generated through Codex gpt-image, people cut out with macOS Vision and SAM 3, Korean fonts found on noonnu, and every version on one live contact sheet. Not for charts or dashboards in an artifact (dataviz) or designing an artifact page (artifact-design).
disable-model-invocation: true
allowed-tools: Bash(uv run "${CLAUDE_SKILL_DIR}/scripts/cli.py" *), Bash(photocraft-cli *), Bash(lightcraft-cli *), Bash(vectorcraft-cli *)
---

# design

The work happens in three ArtCraft apps and their CLIs: PhotoCraft (Photoshop), VectorCraft (Illustrator) and LightCraft (Lightroom). Their commands belong to `photocraft-cli commands`, `vectorcraft-cli commands`, `lightcraft-cli commands` and each `--help`; the apps change every few days, so read them there, and when this skill, a `--help` and what a command does disagree, follow what it does and say so. This skill holds what those do not say: where the CLIs fail without an error, how to work with 성진, what is wrong whatever the taste, and the commands of `uv run "${CLAUDE_SKILL_DIR}/scripts/cli.py"` (`--help` is the map; each `<command> --help` gives its arguments, output and failures). When a command fails unexpectedly or 성진 says he updated an app, run `doctor`; its problems say how to fix each.

## Working with 성진

- 성진's eye judges; you carry your own judgment to the end and give its reason in a line. What he says overrides this skill. Talk with him in Korean.
- His taste lives in the work, not here. Before the first draft of a kind of job he has done before, read `show --all` (accepted results and reusable notes of every job) and look at the senior designer's work in the references folder it names. Carry a choice from one job only as far as its reason reaches.
- Read a reference for how it was built — list its layers, effects and material (a photo background, a speech bubble, a 3D icon, a texture, the type treatment) — and take what this brief needs. Its layout, wording and date format belong to its own message; carried over, they are a defect.
- Before making anything, ask only what an image cannot show: where it is posted and what it is for, strings that must appear, size, areas to keep clear, who or what must be in it, and for print the printer's colour, bleed and size requirements. Ask direction with drafts. When the structure (what goes in which band, what is left out) is not agreed, show an empty layout draft first.
- After a result, give your verdict first — what works, what bothers you, what you recommend — then let him describe. Do not follow a result with "which one?" choices.
- Check each request against the brief (`show`): when doing it as asked would undercut what the brief says the piece must do, say so once with the evidence (`proof` views, the two versions side by side), recommend, and do what he decides; when making the requested version is cheap, show your alternative beside it. When one property has been adjusted for the third time, or he returns to an earlier version, say what you think the underlying problem is before the next tweak. Do not hedge a taste choice with "you may prefer…". Asked "솔직히 어때?", answer with a verdict and its reason.
- When turning a complaint into a new constraint, confirm your reading in a line; a fix inside an agreed intent is just made.
- Record his verdicts verbatim on the version they are about (`record --note … --version N`), keeping facts of this job apart from preferences that hold later (`--scope reusable`).
- What is cheap to change, do and show. Ask first before what is costly to undo or sets the character of the result: rebuilding or overwriting a document he has touched, the overall direction, a large batch of generations (say how many and how long first), deleting files in a job.
- Handing over, say what changed, what you decided that he did not, and what you could not check (how it looks in his phone's feed, colour on his screen, strings he has not supplied).

## The document is the work

- The result is a document 성진 can open in the app and change; the PNG is its export. Do not make a flat canvas he cannot edit.
- A build script regenerates the document and discards everything done to it since, his edits in the app included. Once he has touched or chosen a document, edit it in place: open, run steps, save (`show` lists documents holding edits no version has).
- Every state he is shown becomes a version (`version`).
- Place photos and cut-outs linked: every `version` snapshots the document byte for byte, so an embedded photo is copied into the vault — which is pushed to GitHub, refusing files over 100 MiB — once per version; linked, it is stored once. A small logo can go in either way. Linked placement works only in a headless `photocraft-cli run`. When the layered file itself is delivered outside the job, deliver a copy with its links embedded (`layer.smartObjects.convertToEmbedded`) so it opens wherever it goes; the work document stays linked.
- A document open in an app is changed through the app: a change made on disk is silently overwritten by the app's next save. `apps-status` says what each app has open.

## Tool roles

- LightCraft develops photos (tone, colour, local masks) and gives several shots one look, in a library per job (`work/lightcraft/`). A photo developed for compositing goes to `assets/` as an 8-bit sRGB JPEG at the long edge the composition needs; 16 bits and a wide gamut multiply the file without adding anything from a JPEG original, and pay only from a RAW one.
- VectorCraft holds what is vector by nature (logos, icons, infographics, print). To bring its work into PhotoCraft, export SVG and place that linked: PhotoCraft places neither .vectorcraft nor PDF nor AI, and a re-exported SVG shows once linked content is updated (every render here does that).
- gpt-image makes what the brief needs and the handed-over material lacks: props, backgrounds, illustrations, lettering, textures. Missing material is not a reason to leave an element out, and a prop drawn from vector or code shapes is the usual substitute: beside a photo it matches neither the scene's light nor its perspective nor its texture. Do not generate a real person photorealistically — ask for a real photo; an obvious illustration or caricature is another matter.
- Code makes what ends up as editable material: mattes, data charts as SVG (opened in VectorCraft, so bars and labels stay editable), texture layers, layout arithmetic for a series, measurements.
- When a person must sit over a new background or panel, `cutout` makes a full-resolution matte; covering the person with a panel, or a rectangular or straight-edged crop, works around a cut the tools can make, and a straight edge through hair or shoulders is an unintended edge.

## How the CLIs fail quietly

- PhotoCraft gives a fontStyle the family lacks as Regular with no error; only the PostScript name in `type.info` shows it (`proof` compares them).
- A headless engine command ignores a parameter key it does not know (a misspelt key changes nothing), while a value out of range is an error; `file.new`, the `--new` document, refuses unknown keys.
- `photocraft-cli run` is all or nothing: one failing step saves nothing, though earlier steps worked. Use that as a transaction, and put a step that needs a state (a selection, an active document) in the same run as what makes it.
- A linked smart object renders from the pixels cached in the document: a changed file shows only after `layer.smartObjects.updateAllModifiedContent`, and a missing one renders from the cache without a word (`version`, `proof` and `export` update first and report missing links).
- PhotoCraft's Select Subject and Select Sky, and LightCraft's Subject, Sky and People masks, are heuristics without a model and take walls and people behind; LightCraft's Object and Describe masks use SAM 3.
- `paint.remove` smears hands, sleeves and desks; it is for generated or background material only, never a documentary photo.
- LightCraft clamps an out-of-range slider value to its limit silently, and drops an unknown key in a develop-settings file silently (an unknown control in `--set` is an error).
- VectorCraft area type breaks Korean between any two syllables (제/보를) without a warning, so break Korean title lines yourself at phrase boundaries; its overflow is reported.
- A web copy of a font can map Hangul it does not draw: those syllables print as gaps with no fallback and no missing-glyph count (`fonts-install` refuses such files; `proof` checks the glyphs of every type layer).
- The running PhotoCraft does not see a font installed after it started; headless runs do. VectorCraft rescans with `text.rescanFonts`.

## What does not depend on taste

- Every string on the canvas comes from 성진 or the brief; check names, titles, dates and numbers against them. A string the piece needs and you were not given is not invented: leave a named placeholder and say so.
- It reads at the size it is seen: judge a thumbnail at feed size (`proof` views).
- No unintended edge, halo or smeared skin from a cut-out or an adjustment, and no hair a matte lost (100% crops).
- Nothing that must be seen, a prop included, sits where the platform's interface covers it (YouTube's duration badge in the bottom-right corner, the top and bottom of a Story). `proof --target` draws those areas, and a number the platform does not publish only warns, but the area is covered all the same; `export --target` checks size and file limits.

## Composition

When: planning a draft.

- The brief's required elements stay and read at the size seen; when a decision crowds one out or makes it unreadable, the decision is what changes.
- When the goal is to be recognised in the feed as part of a series, that series' existing layout is the source (`show --all`, the references folder).

## Cutouts

When: separating a person or an object from its background.

Look at 100% where `cutout --help` says mattes go wrong, then fix the mask or ask; the mask stays on the layer for 성진 to paint further.

## Type

When: setting text.

- Installed fonts are listed at the time by `type.fonts` (PhotoCraft) and `text.fontList` (VectorCraft); whether a layer got the face it asked for is `proof`'s. Render a sample of an unfamiliar face before choosing it.
- A font that is not installed is found on noonnu (`fonts-search`); match each license's uses to where this piece goes (video for YouTube, BI/CI for a logo or slogan) before choosing it.

## Photos

When: developing or grading a real photo.

- A photo used as a record keeps its content: light, colour, crop, level, noise and sharpness only — no removing people or objects, no skin retouching, because the office's photos are records of real events (성진's standing rule); asked for it, say why it is not done. A cut-out for a composite is another matter: it does not present the photo as a record.
- The same strength is too much at one viewing size and too little at another, so read the photo for its use first: the size it is seen at, the type it will carry, and how where the eye goes now differs from the intended hierarchy.
- Unnoticeable is not the same as changing little: the intended hierarchy has to read at the size it is seen (check with `proof`'s views). Global sliders move the whole frame together and rarely change where the eye goes; the hierarchy moves with local light — lifting the subject and letting the surroundings fall off with soft radial, brush or SAM masks — kept wide and soft enough that no outline shows (below). When the wording ("티 안 나게") and the use (a photo shown large) pull apart, raise it as in Working with 성진.
- When the goal is correction, what goes is the cast the lighting put on neutral surfaces; the colour of materials (a wooden door, a leather chair, a banner) is a fact of the scene. The usual mistake runs the other way — desaturating a strong material colour that competes for attention while keeping the wall's yellow light as atmosphere; when a material colour competes, fix the hierarchy (brightness, falloff, crop), not the colour. When the goal is a look, this does not apply; the look comes from 성진 and his past jobs.
- An adjustment that stops at an outline looks cut and pasted (unlike a composite's intended cut-out edge): its cause, area and transition must match. Splitting person and background into masks with different amounts is the common cause; a widely feathered mask, and local contrast (highlights, shadows, clarity), make halos against a bright ground.
- In LightCraft, a person or object is masked with SAM 3 — Describe (a prompt mask; English only, Korean finds nothing) or Object (clicks) — the first analysis of a photo taking tens of seconds. On a JPEG `wb.temp` is an absolute temperature with 6500 as no change, though the app's slider shows it relative. A reference is matched by impression, not slider values: its light, camera and exposure differ, so the same numbers do not give the same look. A grade is shown one at a time (성진's way of working: a deterministic grade's variants are only differences you chose); the exception is a request you disagree with, shown as asked beside your alternative.

## Generating with gpt-image

When: generating material or drafts.

- How the model reads a prompt is in `add --help`; read it before the first prompt.
- Without a direction, show a few hypotheses that differ in why they would reach the goal, a line each, and generate them so he chooses from images. Refusals are probabilistic: say a subject may be blocked rather than declaring it impossible.
- On mood subjects (night, technology, festivals, prestige) the model — and you, writing the prompt — drift to navy night, gold and cyan glow, bokeh and floating particles. When trust is the goal, every light and colour needs a source to point to (the scene, the use, the brief, a reference) or it reads as generated; test your own draft by that. When unsure whether a decision improves on the plain result or only replaces it, generate a plain control in the same round.
- Fix in order: a wrong composition is a new version; one element is an `edit` with the approved image as `--ref`; a small defect is covered with a mask in PhotoCraft from a corrected generation.

## Vector work

When: logos, icons, infographics, print.

The original is a `.vectorcraft`: decorated type saved as plain SVG comes back as paths, no longer editable type.

## Seeing the work

Measure where the eye is systematically wrong: it reads a saturation difference as a brightness one, and cannot tell whether "cramped" is ink at the edge or the amount of ink. A measurement backs a factual claim (legibility, a spec); it never overrules 성진's eye on taste.

## Working in the running apps

When: 성진 wants to watch or touch the work, or a document is open in an app.

- Start the app with `apps-open`. An app already running without a control port is his: ask him to save and quit it, never quit it yourself. Do not drive the pointer or keys while he works, and leave the app open.
- The bridge (`apps-send`) refuses commands that take a file path, linked placement included, and its own `doc.place` embeds. To link a new photo or asset into a document open in the app: save it in the app, ask 성진 to close it, place it headlessly, open it again — or he uses File › Place Linked.
- Version a document open in the app with `version --from-app`: the app saves it to its own path first (saved to another path, that path would become the document's file).

## Working files

Nothing is written outside `data/` unless 성진 names a place (`export --to`). The work is done when the result he accepted is exported at the agreed size and place and recorded with `record --final`.
