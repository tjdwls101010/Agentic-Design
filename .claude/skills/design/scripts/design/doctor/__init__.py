"""Whether this Mac can run the skill: the ArtCraft CLIs and apps in matching versions, codex logged in (gpt-image goes through it), macOS Vision, LightCraft's SAM 3 model, and data/ resolving to the vault."""

from __future__ import annotations

from design import codex, lightcraft, paths, photocraft, vectorcraft, vision

__all__ = ["check"]

def check() -> dict:
    problems, notes = [], []
    apps = {}
    for name, system in (("photocraft", photocraft), ("vectorcraft", vectorcraft), ("lightcraft", lightcraft)):
        state = system.app_state()
        apps[name] = {k: state.get(k) for k in ("installed", "app_version", "cli_version", "running")}
        if not state["cli_version"]:
            problems.append(f"{name}-cli is not on PATH")
        if not state["installed"]:
            notes.append(f"{name} app is not in /Applications (headless work still runs)")
        elif state["cli_version"] and state["app_version"] and state["cli_version"] != state["app_version"]:
            problems.append(f"{name} app {state['app_version']} and {name}-cli {state['cli_version']} differ: install the CLI of the app's version — gh release download v{state['app_version']} --repo storytold/{name} --pattern '{name}-cli-*-macos-universal.zip' --pattern SHA256SUMS.txt, check the zip against SHA256SUMS.txt (shasum -a 256), unzip it and put {name}-cli in ~/.local/bin")
    logged_in, detail = (codex.login_status() if codex.executable() else (False, "codex is not on PATH"))
    if not logged_in:
        problems.append(f"codex cannot generate images: {detail}")
    vision_ok, vision_detail = vision.available()
    if not vision_ok:
        problems.append(f"macOS Vision cannot run: {vision_detail}")
    sam = lightcraft.sam_status()
    if not sam.get("installed"):
        notes.append("LightCraft's SAM 3 model is not installed: cutout --select and LightCraft's Object/Describe masks need it")
    root = paths.data_root()
    data_ok = root.is_dir()
    if not data_ok:
        problems.append(f"data/ does not resolve to a folder ({root})")
    out = {"ok": not problems, "summary": "ready" if not problems else f"{len(problems)} problem(s)", "problems": problems, "apps": apps, "codex": {"path": codex.executable(), "version": codex.version(), "logged_in": logged_in}, "vision": {"ok": vision_ok, "detail": vision_detail}, "sam3": sam, "data": {"path": str(root), "ok": data_ok}, "fonts_dir": str(paths.fonts_dir())}
    if notes:
        out["notes"] = notes
    return out
