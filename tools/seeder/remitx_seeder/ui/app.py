"""The seeder's local web UI (NiceGUI), on http://127.0.0.1:8090.

The UI never touches a database itself. Every button runs one runner command
in a child process (process.py) and renders what it reports, so the UI stays
thin and every rule lives in the engine. It binds to 127.0.0.1 only and is
never deployed.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import fields

from nicegui import ui

from remitx_seeder.guards import evaluate
from remitx_seeder.reset import confirmation_phrase
from remitx_seeder.scenario import (
    KycBehaviour,
    MoneyBehaviour,
    Scenario,
    list_scenarios,
    load_scenario,
    save_scenario,
)
from remitx_seeder.settings import RUNS_DIR, load_targets, read_target_env
from remitx_seeder.ui.process import run_command

HOST = "127.0.0.1"
DEFAULT_PORT = 8090

LEVEL_COLOURS = {
    "error": "text-red-600",
    "warning": "text-amber-600",
    "debug": "text-gray-400",
}
SEVERITY_COLOURS = {"error": "red", "warning": "amber", "info": "blue-grey"}


class State:
    def __init__(self) -> None:
        self.targets = load_targets()
        self.target = "local"
        self.busy = False


state = State()


def guard_report():
    return evaluate(
        state.target, read_target_env(state.target), state.targets.get(state.target)
    )


def _log_line(log: ui.log, event: dict) -> None:
    if event.get("type") == "log":
        level = event.get("level", "info")
        log.push(
            f"[{level}] {event.get('message', '')}",
            classes=LEVEL_COLOURS.get(level, ""),
        )
    elif event.get("type") == "error":
        log.push(f"[error] {event.get('message')}", classes="text-red-600")
        if event.get("traceback"):
            log.push(event["traceback"], classes="text-red-400")


async def _run(command: str, *args: str, log: ui.log | None = None, on_event=None):
    if state.busy:
        ui.notify("Another operation is still running.", type="warning")
        return None
    report = guard_report()
    if not report.ok:
        ui.notify("This target fails its guards; see Status.", type="negative")
        return None
    state.busy = True
    try:

        def handle(event: dict) -> None:
            if log is not None:
                _log_line(log, event)
            if on_event is not None:
                on_event(event)

        outcome = await run_command(command, state.target, *args, on_event=handle)
    finally:
        state.busy = False
    if not outcome.ok:
        ui.notify(
            f"{command} failed: {outcome.error}", type="negative", multi_line=True
        )
    return outcome


# --- sections ---------------------------------------------------------------


def status_section() -> None:
    guards_box = ui.column().classes("w-full")
    info_box = ui.column().classes("w-full")

    def render_guards() -> None:
        guards_box.clear()
        report = guard_report()
        with guards_box:
            ui.label("Guards").classes("text-lg font-medium")
            ui.label(
                "Checked before every command. A failed guard is a refusal, "
                "never a warning."
            ).classes("text-sm text-gray-500")
            for check in report.checks:
                with ui.row().classes("items-center gap-2"):
                    ui.icon("check_circle" if check.ok else "block").classes(
                        "text-green-600" if check.ok else "text-red-600"
                    )
                    ui.label(check.name).classes("font-medium w-24")
                    ui.label(check.detail).classes("text-sm")

    async def refresh() -> None:
        render_guards()
        outcome = await _run("status")
        info_box.clear()
        if outcome is None or outcome.result is None:
            return
        result = outcome.result
        with info_box:
            ui.label("Database").classes("text-lg font-medium mt-4")
            rows = [
                ("Alembic revision", result.get("alembic_revision")),
                ("Users", result.get("users")),
                ("Seeded users", result.get("seeded_users")),
                ("People in Clerk", result.get("clerk_users", "—")),
                ("Clerk mode", result.get("clerk_mode")),
                ("Ready to seed", "yes" if result.get("ready") else "no"),
            ]
            for label, value in rows:
                with ui.row().classes("gap-2"):
                    ui.label(label).classes("w-40 text-gray-600")
                    ui.label(str(value))
            ui.label(result.get("ready_detail", "")).classes("text-sm text-gray-500")

    render_guards()
    ui.button("Check the target", icon="refresh", on_click=refresh).classes("mt-2")


def _number(
    label: str, value, on_change, *, step=1, minimum=0, maximum=None, fmt="%.0f"
):
    return ui.number(
        label,
        value=value,
        step=step,
        min=minimum,
        max=maximum,
        format=fmt,
        on_change=on_change,
    ).classes("w-40")


def seed_section() -> None:
    current = {
        "scenario": load_scenario("default")
        if "default" in list_scenarios()
        else Scenario()
    }
    form = ui.column().classes("w-full")
    results = ui.column().classes("w-full")

    def set_top(name: str, cast=int):
        def change(event) -> None:
            if event.value is not None:
                setattr(current["scenario"], name, cast(event.value))

        return change

    def set_nested(group: str, name: str, cast=float):
        def change(event) -> None:
            if event.value is not None:
                setattr(getattr(current["scenario"], group), name, cast(event.value))

        return change

    def set_dict(attribute: str, key: str):
        def change(event) -> None:
            if event.value is not None:
                getattr(current["scenario"], attribute)[key] = int(event.value)

        return change

    def render_form() -> None:
        form.clear()
        scenario = current["scenario"]
        with form:
            with ui.row().classes("items-end gap-4"):
                ui.select(
                    list_scenarios() or ["default"],
                    value=scenario.name,
                    label="Scenario",
                    on_change=lambda e: pick(e.value),
                ).classes("w-48")
                name_input = ui.input("Save as", value=scenario.name).classes("w-48")
                ui.button(
                    "Save scenario",
                    icon="save",
                    on_click=lambda: save(name_input.value),
                ).props("outline")
            ui.label(scenario.description).classes("text-sm text-gray-500")
            ui.label("Shape").classes("text-md font-medium mt-2")
            with ui.row().classes("gap-4 flex-wrap"):
                _number(
                    "Days of history",
                    scenario.days,
                    set_top("days"),
                    minimum=1,
                    maximum=365,
                )
                _number("Random seed", scenario.seed, set_top("seed"))
                _number("Senders", scenario.senders, set_top("senders"))
                _number(
                    "Clerk user cap",
                    scenario.clerk_user_cap,
                    set_top("clerk_user_cap"),
                    maximum=100,
                )
            ui.label("Recipients per country").classes("text-md font-medium mt-2")
            with ui.row().classes("gap-4 flex-wrap"):
                for country, count in scenario.recipients.items():
                    _number(country, count, set_dict("recipients", country))
            ui.label("Staff").classes("text-md font-medium mt-2")
            with ui.row().classes("gap-4 flex-wrap"):
                for role, count in scenario.staff.items():
                    _number(role.replace("_", " "), count, set_dict("staff", role))
            for group, kind, title in (
                ("kyc", KycBehaviour, "Verification behaviour"),
                ("money", MoneyBehaviour, "Money behaviour"),
            ):
                with ui.expansion(title).classes("w-full"):
                    with ui.row().classes("gap-4 flex-wrap"):
                        for f in fields(kind):
                            value = getattr(getattr(scenario, group), f.name)
                            if isinstance(value, tuple):
                                continue
                            _number(
                                f.name.replace("_", " "),
                                value,
                                set_nested(group, f.name),
                                step=0.01,
                                maximum=1 if f.name.endswith("_rate") else None,
                                fmt="%.2f",
                            )
            ui.label("Live tail (real settlements through the API and XRPL)").classes(
                "text-md font-medium mt-2"
            )
            with ui.row().classes("gap-4 flex-wrap"):
                _number(
                    "Live settlements",
                    scenario.live_settlements,
                    set_top("live_settlements"),
                    maximum=10,
                )
                _number(
                    "Budget (uctusd)",
                    scenario.live_token_budget,
                    set_top("live_token_budget", float),
                    step=1,
                    fmt="%.2f",
                )

    def pick(name: str) -> None:
        current["scenario"] = load_scenario(name)
        render_form()

    def save(name: str) -> None:
        scenario = current["scenario"]
        scenario.name = (name or scenario.name).strip().replace(" ", "-")
        try:
            path = save_scenario(scenario)
        except ValueError as error:
            ui.notify(str(error), type="negative")
            return
        ui.notify(f"Saved {path.name}")
        render_form()

    render_form()
    progress = ui.linear_progress(value=0, show_value=False).classes("w-full mt-4")
    progress_label = ui.label("").classes("text-sm text-gray-500")
    log = ui.log(max_lines=2000).classes("w-full h-72 font-mono text-xs")

    async def run_seed() -> None:
        scenario = current["scenario"]
        try:
            scenario.validate()
            save_scenario(scenario)
        except ValueError as error:
            ui.notify(str(error), type="negative")
            return
        log.clear()
        results.clear()
        progress.value = 0

        def on_event(event: dict) -> None:
            if event.get("type") == "progress":
                done, queued = event["done"], event["queued"]
                progress.value = done / max(1, done + queued)
                progress_label.text = (
                    f"{done} events replayed, replay clock at {event['at'][:16]}"
                )

        outcome = await _run(
            "seed", "--scenario", scenario.name, log=log, on_event=on_event
        )
        if outcome and outcome.result:
            progress.value = 1
            render_summary(results, outcome.result)

    ui.button("Seed", icon="play_arrow", on_click=run_seed).props(
        "color=primary"
    ).classes("mt-2")


def render_summary(container, summary: dict) -> None:
    with container:
        ui.label("Run summary").classes("text-lg font-medium mt-4")
        ui.label(
            f"{summary['run_id']} · {summary['events']['run']} events · "
            f"{summary['duration_seconds']}s · "
            f"manifest {summary.get('manifest_path', '')}"
        ).classes("text-sm text-gray-500")
        counts = [
            {"what": key, "count": value}
            for key, value in summary["counts"].items()
            if not key.startswith("events.")
        ]
        ui.table(
            columns=[
                {"name": "what", "label": "What", "field": "what", "align": "left"},
                {"name": "count", "label": "Count", "field": "count"},
            ],
            rows=counts,
            pagination=15,
        ).classes("w-full")
        if summary.get("refusals"):
            ui.label(f"{len(summary['refusals'])} refusals").classes(
                "text-amber-700 font-medium"
            )
            for refusal in summary["refusals"][:20]:
                ui.label(
                    f"{refusal['at'][:16]} {refusal['event']}: "
                    f"{refusal['error']}: {refusal['message']}"
                ).classes("text-sm")
        render_findings(container, summary["verify"])
        if summary.get("live_tail"):
            ui.label("Live tail").classes("text-md font-medium")
            ui.code(
                json.dumps(summary["live_tail"], indent=2), language="json"
            ).classes("w-full")


def render_findings(container, report: dict) -> None:
    with container:
        ui.label(
            "Verify: every rule holds" if report["ok"] else "Verify: rules broken"
        ).classes(
            "text-lg font-medium mt-4 "
            + ("text-green-700" if report["ok"] else "text-red-700")
        )
        for finding in report["findings"]:
            with ui.row().classes("items-start gap-2 w-full"):
                if finding["severity"] == "info":
                    ui.badge("info", color=SEVERITY_COLOURS["info"])
                elif finding["ok"]:
                    ui.badge("ok", color="green")
                else:
                    ui.badge(
                        finding["severity"], color=SEVERITY_COLOURS[finding["severity"]]
                    )
                with ui.column().classes("gap-0"):
                    ui.label(f"{finding['check']}: {finding['summary']}")
                    for example in finding.get("examples", []):
                        ui.label(example).classes("text-xs text-gray-500")


def people_section() -> None:
    ui.label(
        "Seeded people. Anyone who can sign in uses their email and the code 424242 "
        "(Clerk test mode); database-only people exist for the admin screens and "
        "as beneficiaries."
    ).classes("text-sm text-gray-500")
    table_box = ui.column().classes("w-full")

    async def refresh() -> None:
        outcome = await _run("people")
        table_box.clear()
        if outcome is None or outcome.result is None:
            return
        rows = [
            {
                "name": p["full_name"] or p["first_name"],
                "email": p["email"],
                "sign_in": "yes, code 424242"
                if p["can_sign_in"]
                else "no (database-only)",
                "roles": p["roles"] or "customer",
                "kyc": p["kyc_status"] or "not started",
                "zar": p["zar_balance"],
                "joined": str(p["created_at"])[:10],
            }
            for p in outcome.result["people"]
        ]
        with table_box:
            ui.table(
                columns=[
                    {
                        "name": key,
                        "label": label,
                        "field": key,
                        "sortable": True,
                        "align": "left",
                    }
                    for key, label in (
                        ("name", "Name"),
                        ("email", "Email"),
                        ("sign_in", "Can sign in"),
                        ("roles", "Roles"),
                        ("kyc", "KYC"),
                        ("zar", "ZAR balance"),
                        ("joined", "Joined"),
                    )
                ],
                rows=rows,
                pagination=25,
            ).props("dense").classes("w-full")

    ui.button("Load people", icon="group", on_click=refresh).classes("mt-2")


def verify_section() -> None:
    ui.label(
        "Checks the business rules over the whole database, seeded or not."
    ).classes("text-sm text-gray-500")
    chain = ui.checkbox("Also compare the treasury with its on-chain balance")
    box = ui.column().classes("w-full")

    async def run_verify() -> None:
        args = ["--chain"] if chain.value else []
        outcome = await _run("verify", *args)
        box.clear()
        if outcome and outcome.result:
            render_findings(box, outcome.result)

    ui.button("Verify", icon="rule", on_click=run_verify).classes("mt-2")


def schema_section() -> None:
    ui.label(
        "The live schema and how much of it the seeder fills. An uncovered table or "
        "an always-empty column means the schema moved on: add a generator."
    ).classes("text-sm text-gray-500")
    box = ui.column().classes("w-full")

    async def refresh() -> None:
        outcome = await _run("schema")
        box.clear()
        if outcome is None or outcome.result is None:
            return
        tables = outcome.result["tables"]
        uncovered = [t["table"] for t in tables if t["kind"] == "uncovered"]
        with box:
            if uncovered:
                ui.label("No generator yet: " + ", ".join(uncovered)).classes(
                    "text-amber-700 font-medium"
                )
            ui.table(
                columns=[
                    {
                        "name": "table",
                        "label": "Table",
                        "field": "table",
                        "sortable": True,
                        "align": "left",
                    },
                    {
                        "name": "rows",
                        "label": "Rows",
                        "field": "rows",
                        "sortable": True,
                    },
                    {
                        "name": "kind",
                        "label": "Kind",
                        "field": "kind",
                        "sortable": True,
                    },
                    {
                        "name": "written_by",
                        "label": "Written by",
                        "field": "written_by",
                        "align": "left",
                    },
                    {
                        "name": "always_null",
                        "label": "Always NULL",
                        "field": "always_null",
                        "align": "left",
                    },
                ],
                rows=[
                    {**t, "always_null": ", ".join(t["always_null"])} for t in tables
                ],
                pagination=40,
            ).props("dense wrap-cells").classes("w-full")

    ui.button("Read the schema", icon="schema", on_click=refresh).classes("mt-2")


def runs_section() -> None:
    box = ui.column().classes("w-full")

    def refresh() -> None:
        box.clear()
        manifests = (
            sorted(RUNS_DIR.glob("*.json"), reverse=True) if RUNS_DIR.exists() else []
        )
        with box:
            if not manifests:
                ui.label("No runs yet.").classes("text-gray-500")
            for path in manifests[:30]:
                manifest = json.loads(path.read_text())
                title = (
                    f"{manifest.get('started_at', '')[:16]} · "
                    f"{manifest.get('target')} · {manifest['scenario']['name']} · "
                    f"seed {manifest['scenario']['seed']} · "
                    f"{'verify ok' if manifest['verify']['ok'] else 'verify FAILED'}"
                )
                with ui.expansion(title).classes("w-full"):
                    ui.label(
                        f"git {manifest.get('git_sha') or 'unknown'} · {path.name}"
                    ).classes("text-xs text-gray-500")
                    inner = ui.column().classes("w-full")
                    render_summary(inner, manifest)

    refresh()
    ui.button("Refresh", icon="refresh", on_click=refresh).classes("mt-2")


def reset_section() -> None:
    ui.label("Reset throws away the target's data and rebuilds it empty:").classes(
        "font-medium"
    )
    ui.markdown(
        "1. deletes the Clerk users the seeder made (your own accounts stay)\n"
        "2. empties the KYC document bucket\n"
        "3. drops and recreates the database schema, then `alembic upgrade head`"
        " (which also creates the platform accounts)\n\n"
        "Staff roles are **not** restored: grant your testers theirs again on "
        "the Access page."
    )
    phrase = ui.input(label="Type the confirmation phrase").classes("w-72")
    hint = ui.label("").classes("text-sm text-gray-500")
    log = ui.log(max_lines=500).classes("w-full h-64 font-mono text-xs")

    def update_hint() -> None:
        hint.text = f'Type "{confirmation_phrase(state.target)}" to enable Reset.'

    async def run_reset() -> None:
        expected = confirmation_phrase(state.target)
        if phrase.value != expected:
            ui.notify(f'Type "{expected}" first.', type="warning")
            return
        log.clear()
        await _run("reset", "--confirm", phrase.value, log=log)
        phrase.value = ""

    update_hint()
    ui.timer(1.0, update_hint)
    ui.button("Reset", icon="delete_forever", on_click=run_reset).props(
        "color=negative"
    ).classes("mt-2")


@ui.page("/")
def index() -> None:
    ui.page_title("RemitX seeder")
    with ui.header().classes("items-center justify-between"):
        ui.label("RemitX seeder · local only, never deployed").classes(
            "text-lg font-medium"
        )
        with ui.row().classes("items-center gap-2"):
            ui.label("Target")
            ui.select(
                sorted(state.targets),
                value=state.target,
                on_change=lambda e: switch_target(e.value),
            ).props("dense dark standout").classes("w-32")

    def switch_target(target: str) -> None:
        state.target = target
        ui.notify(f"Target: {target}. Commands now run against {target}.")
        ui.navigate.reload()

    with ui.tabs().classes("w-full") as tabs:
        names = ["Status", "Seed", "People", "Verify", "Schema", "Runs", "Reset"]
        tab_items = {name: ui.tab(name) for name in names}
    with ui.tab_panels(tabs, value=tab_items["Status"]).classes("w-full"):
        for name, builder in (
            ("Status", status_section),
            ("Seed", seed_section),
            ("People", people_section),
            ("Verify", verify_section),
            ("Schema", schema_section),
            ("Runs", runs_section),
            ("Reset", reset_section),
        ):
            with ui.tab_panel(tab_items[name]):
                builder()


def serve(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="remitx_seeder")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv or [])
    ui.run(
        host=HOST,
        port=args.port,
        title="RemitX seeder",
        reload=False,
        show=not args.no_browser,
        show_welcome_message=True,
    )
