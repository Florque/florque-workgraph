"""SignalHub: routes external observations to graph nodes (spec 6).

It talks to the graph only through graph-core, as an agent Actor with role
``hub``; graph-core enforces what that role may write (spec 6.5). Classes are
found by mixin role, never by work-graph class name.
"""

from __future__ import annotations

import socket
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from florque_graph_core import GraphCore, Principal
from florque_graph_core.errors import ErrorCode, GraphError
from florque_graph_core.hooks import WriteContext
from florque_graph_core.validation.values import format_datetime, parse_datetime

from florque_signal_hub.contract import Contract, verify_contract
from florque_signal_hub.envelope import Observation
from florque_signal_hub.evaluator import Evaluation, EvaluatorConfig, Point, evaluate
from florque_signal_hub.events import ORIGIN, EventBus
from florque_signal_hub.lane2 import Associator, NoAssociator
from florque_signal_hub.store.repository import HubStore, StoreConflict

HUB_ACTOR = "hub"
DEFAULT_TENANT = "default"  # registry scope of unscoped principals (local mode, operators)
EVALUATED_STATUSES = ("active",)
FINAL = {"succeeded", "failed", "expired"}


@dataclass(frozen=True)
class HubConfig:
    evaluator: EvaluatorConfig = EvaluatorConfig()
    default_time_zone: str = "UTC"
    lease_seconds: int = 60


def hub_principal(actor_id: str = HUB_ACTOR) -> Principal:
    return Principal(actor_id=actor_id, roles={"*": "hub"}, is_agent=True)


class SignalHub:
    def __init__(
        self,
        core: GraphCore,
        store: HubStore,
        config: HubConfig | None = None,
        *,
        principal: Principal | None = None,
        associator: Associator | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.core = core
        self.store = store
        self.config = config or HubConfig()
        self.principal = principal or hub_principal()
        self.associator = associator or NoAssociator()
        self.clock = clock or core.clock
        # Refuses to start on a mixin contract mismatch.
        self.contract: Contract = verify_contract(core.describe())
        self.events = EventBus(store)

    # ------------------------------------------------------------------ tenancy

    @staticmethod
    def tenant_of(actor: Principal) -> str:
        return actor.tenant_id or DEFAULT_TENANT

    def _store(self, tenant: str | None) -> HubStore:
        return self.store.scoped(tenant or DEFAULT_TENANT)

    def _node_tenant(self, node_id: str) -> str:
        node = self.core.get(self.principal, node_id, depth=0)["node"]
        return node.get("tenant_id") or DEFAULT_TENANT

    # ------------------------------------------------------------------ permissions

    def _require_admin(self, actor: Principal, project_id: str | None = None) -> None:
        role = self.core.role(actor, project_id)
        if role != "admin":
            raise GraphError(
                ErrorCode.FORBIDDEN,
                "Registry changes need a project admin",
                hint="Ask a project admin to register the source or sensor.",
            )

    def _require_member(self, actor: Principal, project_id: str | None = None) -> None:
        if not self.core.policy.can_read(self.core.role(actor, project_id)):
            raise GraphError(ErrorCode.FORBIDDEN, "Not a member of this project")

    # ------------------------------------------------------------------ graph-core hook

    def series_code_hook(self, ctx: WriteContext) -> None:
        """KR creation validates series_code against registered sensors (spec 6.6)."""
        if "Expectation" not in ctx.cls.mixins or "series_code" not in ctx.patch:
            return
        code = ctx.patch.get("series_code")
        if code is None:
            return
        sensor = self._store(ctx.tenant_id).sensor_by_code(code)
        if sensor is None:
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                f"series_code {code!r} is not registered",
                hint=f"Register a sensor first: fwg hub sensor add --series-code {code} --project <id> --unit <unit>.",
                details={"series_code": code},
            )
        if ctx.project_id and sensor["project_id"] != ctx.project_id:
            raise GraphError(
                ErrorCode.SCOPE_VIOLATION,
                f"series_code {code!r} is registered for another project",
                hint="Register a project-specific series code.",
            )
        unit = ctx.props.get("unit")
        if unit and unit != sensor["unit"]:
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                f"unit {unit!r} does not match the sensor unit {sensor['unit']!r}",
                hint=f"Use unit {sensor['unit']!r}.",
            )

    # ------------------------------------------------------------------ registry

    def add_source(
        self,
        actor: Principal,
        id: str,
        kind: str,
        name: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_admin(actor)
        st = self._store(actor.tenant_id)
        try:
            row = st.add_source(id, kind, name, config or {})
        except StoreConflict as e:
            raise GraphError(
                ErrorCode.DUPLICATE_EXACT, f"Source {id!r} exists", hint="Reuse it."
            ) from e
        st.audit(actor.actor_id, "source.add", id, {"kind": kind})
        return {"source": row}

    def list_sources(self, actor: Principal) -> dict[str, Any]:
        self._require_member(actor)
        return {"sources": self._store(actor.tenant_id).list_sources()}

    def archive_source(self, actor: Principal, id: str) -> dict[str, Any]:
        self._require_admin(actor)
        st = self._store(actor.tenant_id)
        if not st.archive_source(id):
            raise GraphError(ErrorCode.NOT_FOUND, f"Source {id!r} not found")
        st.audit(actor.actor_id, "source.archive", id, {})
        return {"archived": id}

    def add_sensor(
        self,
        actor: Principal,
        series_code: str,
        project_id: str,
        unit: str,
        aggregation: str = "last",
        source_id: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        self._require_admin(actor, project_id)
        project = self.core.get(actor, project_id, depth=0)["node"]  # must exist and be visible
        st = self._store(project.get("tenant_id"))
        if source_id and st.get_source(source_id) is None:
            raise GraphError(
                ErrorCode.NOT_FOUND,
                f"Source {source_id!r} not registered",
                hint="fwg hub source add first.",
            )
        try:
            row = st.add_sensor(
                {
                    "series_code": series_code,
                    "project_id": project_id,
                    "unit": unit,
                    "aggregation": aggregation,
                    "source_id": source_id,
                    "description": description,
                }
            )
        except StoreConflict as e:
            raise GraphError(
                ErrorCode.DUPLICATE_EXACT,
                f"series_code {series_code!r} is already registered",
                hint="Reuse the sensor.",
            ) from e
        st.audit(actor.actor_id, "sensor.add", series_code, {"project_id": project_id})
        return {"sensor": row}

    def list_sensors(self, actor: Principal, project_id: str | None = None) -> dict[str, Any]:
        self._require_member(actor, project_id)
        return {"sensors": self._store(actor.tenant_id).list_sensors(project_id)}

    def archive_sensor(self, actor: Principal, sensor_id: str) -> dict[str, Any]:
        st = self._store(actor.tenant_id)
        sensor = next((s for s in st.list_sensors() if s["id"] == sensor_id), None)
        if sensor is None:
            raise GraphError(ErrorCode.NOT_FOUND, f"Sensor {sensor_id!r} not found")
        self._require_admin(actor, sensor["project_id"])
        st.archive_sensor(sensor_id)
        st.audit(actor.actor_id, "sensor.archive", sensor_id, {})
        return {"archived": sensor_id}

    def add_binding(self, actor: Principal, kind: str, row: dict[str, Any]) -> dict[str, Any]:
        if kind not in ("channel", "thread"):
            raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, "binding kind must be channel or thread")
        project_id = row.get("project_id")
        if kind == "thread":
            node = self.core.get(actor, row["node_id"], depth=0)["node"]
            project_id = node.get("project_id")
        self._require_admin(actor, project_id)
        st = self._store(actor.tenant_id)
        try:
            out = st.add_binding(kind, row)
        except StoreConflict as e:
            raise GraphError(ErrorCode.DUPLICATE_EXACT, "Binding exists") from e
        st.audit(actor.actor_id, f"binding.{kind}.add", out["id"], row)
        return {"binding": out}

    def list_bindings(self, actor: Principal, kind: str) -> dict[str, Any]:
        self._require_member(actor)
        return {"bindings": self._store(actor.tenant_id).list_bindings(kind)}

    def archive_binding(self, actor: Principal, kind: str, binding_id: str) -> dict[str, Any]:
        self._require_admin(actor)
        if not self._store(actor.tenant_id).archive_binding(kind, binding_id):
            raise GraphError(ErrorCode.NOT_FOUND, f"Binding {binding_id!r} not found")
        return {"archived": binding_id}

    # ------------------------------------------------------------------ ingestion (lane 1)

    def ingest(self, actor: Principal, obs: Observation | dict[str, Any]) -> dict[str, Any]:
        if not isinstance(obs, Observation):
            try:
                obs = Observation.model_validate(obs)
            except ValueError as e:
                raise GraphError(
                    ErrorCode.ONTOLOGY_VIOLATION,
                    f"Invalid observation: {e}",
                    hint="See the envelope schema.",
                ) from e
        if self.core.role(actor, None) not in ("hub", "admin"):
            raise GraphError(ErrorCode.FORBIDDEN, "Only the hub or an admin may push observations")
        env = obs.model_dump(mode="json")
        st = self._store(actor.tenant_id)
        try:
            ledger = st.ledger_insert(obs.source_id, obs.external_id, env)
        except StoreConflict:
            prev = st.ledger_get(obs.source_id, obs.external_id) or {}
            return {
                "status": "duplicate",
                "ledger_id": prev.get("id"),
                "signal_id": prev.get("signal_id"),
            }

        if st.get_source(obs.source_id) is None:
            return self._to_inbox(st, ledger["id"], "unknown_source", env)
        if not obs.subject_code:
            assoc = self.associator.associate(obs, "")
            return self._to_inbox(st, ledger["id"], "no_subject_code", env, assoc.candidates)
        sensor = st.sensor_by_code(obs.subject_code)
        if sensor is None:
            # the hub never guesses
            return self._to_inbox(st, ledger["id"], "unregistered_code", env)
        if obs.type == "metric" and obs.unit and obs.unit != sensor["unit"]:
            return self._to_inbox(st, ledger["id"], "unit_mismatch", env)

        project_id = sensor["project_id"]
        expectations = self._expectations(project_id, obs.subject_code)
        about = [{"type": "about", "to": e["id"]} for e in expectations] or [
            {"type": "about", "to": project_id}
        ]
        try:
            if obs.type == "metric":
                result = self._write_metric(st, obs, sensor, project_id, about)
            else:
                result = self._write_signal(obs, project_id, about)
        except GraphError as e:
            st.ledger_update(ledger["id"], "rejected", detail=f"{e.code}: {e.message}")
            raise
        st.ledger_update(ledger["id"], result["status"], signal_id=result.get("signal_id"))
        evaluations = []
        if obs.type == "metric":
            evaluations = [self.evaluate_one(exp["id"]) for exp in expectations]
        return {**result, "ledger_id": ledger["id"], "evaluations": evaluations}

    def _to_inbox(
        self,
        st: HubStore,
        ledger_id: str,
        reason: str,
        env: dict[str, Any],
        candidates: list[Any] | None = None,
    ) -> dict[str, Any]:
        item = st.inbox_add(ledger_id, reason, env, candidates or [])
        st.ledger_update(ledger_id, "inbox", detail=reason)
        return {"status": "inbox", "reason": reason, "inbox_id": item["id"], "ledger_id": ledger_id}

    def _expectations(self, project_id: str, series_code: str) -> list[dict[str, Any]]:
        return self.core.find_by_mixin(
            self.principal, "Expectation", {"series_code": series_code}, project_id
        )["nodes"]

    def _tz(self, project_id: str) -> ZoneInfo:
        name = (
            self.core.get(self.principal, project_id, depth=0)["node"].get("time_zone")
            or self.config.default_time_zone
        )
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            return ZoneInfo(self.config.default_time_zone)

    def _write_metric(
        self,
        st: HubStore,
        obs: Observation,
        sensor: dict[str, Any],
        project_id: str,
        about: list[dict[str, Any]],
    ) -> dict[str, Any]:
        cls = self.contract.observation_class
        tz = self._tz(project_id)
        period = obs.period or obs.observed_at.astimezone(tz).date().isoformat()
        code = obs.subject_code
        assert code is not None
        current = self.core.list_nodes(
            self.principal,
            project_id,
            cls,
            {"kind": "metric", "series_code": code, "period": period, "source": obs.source_id},
        )["nodes"]
        fields = {
            "numeric_value": obs.value,
            "unit": sensor["unit"],
            "aggregation": sensor["aggregation"],
            "observed_at": format_datetime(obs.observed_at),
        }
        if obs.payload_ref:
            fields["payload_ref"] = obs.payload_ref
        if current:
            node = current[0]
            if node.get("numeric_value") == obs.value:
                return {"status": "unchanged", "signal_id": node["id"]}
            res = self.core.supersede(self.principal, node["id"], fields, origin=ORIGIN)
            st.audit(
                self.principal.actor_id,
                "metric.correction",
                code,
                {"period": period, "old": node["id"], "new": res["node"]["id"]},
            )
            return {"status": "corrected", "signal_id": res["node"]["id"], "superseded": node["id"]}
        props = {
            "kind": "metric",
            "title": f"{code} {period}",
            "series_code": code,
            "period": period,
            "source": obs.source_id,
            "status": "active",
            **fields,
        }
        res = self.core.create(
            self.principal, cls, props, parent_id=project_id, edges=about, origin=ORIGIN
        )
        return {"status": "accepted", "signal_id": res["node"]["id"]}

    def _write_signal(
        self, obs: Observation, project_id: str, about: list[dict[str, Any]]
    ) -> dict[str, Any]:
        props: dict[str, Any] = {
            "kind": obs.type,
            "title": obs.title or f"{obs.type}: {obs.subject_code}",
            "source": obs.source_id,
            "observed_at": format_datetime(obs.observed_at),
            "status": "active",
        }
        if obs.summary:
            props["summary"] = obs.summary
        if obs.payload_ref:
            props["payload_ref"] = obs.payload_ref
            props["sources"] = [obs.payload_ref]
        res = self.core.create(
            self.principal,
            self.contract.observation_class,
            props,
            parent_id=project_id,
            edges=about,
            confirm_new=True,
            origin=ORIGIN,
        )
        return {"status": "accepted", "signal_id": res["node"]["id"]}

    # ------------------------------------------------------------------ inbox

    def inbox(self, actor: Principal, status: str | None = "open") -> dict[str, Any]:
        self._require_member(actor)
        return {"items": self._store(actor.tenant_id).inbox_list(status)}

    def resolve_inbox(
        self, actor: Principal, inbox_id: str, action: str, node_id: str | None = None
    ) -> dict[str, Any]:
        st = self._store(actor.tenant_id)
        item = st.inbox_get(inbox_id)
        if item is None or item["status"] != "open":
            raise GraphError(ErrorCode.NOT_FOUND, f"Open inbox item {inbox_id!r} not found")
        if action not in ("attach", "dismiss"):
            raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, "action must be attach or dismiss")
        result: dict[str, Any] = {"inbox_id": inbox_id, "action": action}
        if action == "attach":
            if not node_id:
                raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, "attach needs node_id")
            node = self.core.get(actor, node_id, depth=0)["node"]
            self._require_member(actor, node.get("project_id"))
            env = item["envelope"]
            obs = Observation.model_validate(env)
            kind = obs.type if obs.type != "metric" else "update"
            props: dict[str, Any] = {
                "kind": kind,
                "title": obs.title or f"{obs.type}: {obs.subject_code or obs.external_id}",
                "source": obs.source_id,
                "observed_at": format_datetime(obs.observed_at),
                "status": "active",
            }
            if obs.summary:
                props["summary"] = obs.summary
            if obs.value is not None and obs.type == "metric":
                props["summary"] = f"value {obs.value:g}" + (f" {obs.unit}" if obs.unit else "")
            if obs.payload_ref:
                props["payload_ref"] = obs.payload_ref
            res = self.core.create(
                self.principal,
                self.contract.observation_class,
                props,
                parent_id=node["project_id"],
                edges=[{"type": "about", "to": node_id}],
                confirm_new=True,
                origin=ORIGIN,
            )
            result["signal_id"] = res["node"]["id"]
            if item.get("ledger_id"):
                st.ledger_update(item["ledger_id"], "accepted", signal_id=res["node"]["id"])
        st.inbox_resolve(inbox_id, action if not node_id else f"{action}:{node_id}", actor.actor_id)
        st.match_feedback_add(inbox_id, node_id, action, actor.actor_id)
        st.audit(actor.actor_id, "inbox.resolve", inbox_id, result)
        return result

    # ------------------------------------------------------------------ evaluation

    def _today(self, tz: ZoneInfo) -> date:
        return self.clock().astimezone(tz).date()

    def _points(self, exp: dict[str, Any]) -> list[Point]:
        rows = self.core.list_nodes(
            self.principal,
            exp["project_id"],
            self.contract.observation_class,
            {"kind": "metric", "series_code": exp["series_code"]},
        )["nodes"]
        rows = [
            r
            for r in rows
            if r.get("unit") == exp.get("unit") and r.get("numeric_value") is not None
        ]
        if rows:
            # Current values share one aggregation: the most recent one wins (spec 4.5).
            latest_agg = max(rows, key=lambda r: r.get("observed_at", "")).get("aggregation")
            rows = [r for r in rows if r.get("aggregation") == latest_agg]
        by_period: dict[tuple[str, str], dict[str, Any]] = {}
        for r in rows:
            key = (r.get("period") or r["observed_at"], r.get("source") or "")
            if key not in by_period or r.get("observed_at", "") > by_period[key].get(
                "observed_at", ""
            ):
                by_period[key] = r
        return [
            Point(parse_datetime(r["observed_at"]), float(r["numeric_value"]), r.get("period"))
            for r in by_period.values()
        ]

    def evaluate_one(self, node_id: str) -> dict[str, Any]:
        exp = self.core.get(self.principal, node_id, depth=0)["node"]
        if "Expectation" not in (self.core.model.classes[exp["class"]].mixins):
            raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, f"{node_id} carries no Expectation")
        if not exp.get("series_code") or exp.get("status") not in EVALUATED_STATUSES:
            return {
                "node_id": node_id,
                "skipped": f"status {exp.get('status')}"
                if exp.get("series_code")
                else "no expectation",
            }
        tz = self._tz(exp["project_id"])
        ev: Evaluation = evaluate(
            exp, self._points(exp), self._today(tz), tz, self.config.evaluator
        )
        fields = ev.fields()
        fields["last_observed_at"] = (
            format_datetime(ev.last_observed_at) if ev.last_observed_at else None
        )
        changed = {k: v for k, v in fields.items() if exp.get(k) != v}
        if not changed:
            return {
                "node_id": node_id,
                "outcome": ev.outcome,
                "health": ev.health,
                "changed": [],
                "reason": ev.reason,
            }
        changed["evaluated_at"] = format_datetime(self.clock())
        self.core.update(self.principal, node_id, changed, origin=ORIGIN)
        if "outcome" in changed:
            payload = {
                "from": exp.get("outcome"),
                "to": ev.outcome,
                "reason": ev.reason,
                "series_code": exp["series_code"],
            }
            tenant = exp.get("tenant_id") or DEFAULT_TENANT
            self.events.publish(
                "expectation.outcome_changed", node_id, payload, store=self._store(tenant)
            )
            self._store(tenant).audit(
                self.principal.actor_id, "expectation.outcome", node_id, payload
            )
        return {
            "node_id": node_id,
            "outcome": ev.outcome,
            "health": ev.health,
            "changed": sorted(k for k in changed if k != "evaluated_at"),
            "reason": ev.reason,
        }

    def evaluate_all(self, project_id: str | None = None) -> dict[str, Any]:
        nodes = self.core.find_by_mixin(self.principal, "Expectation", None, project_id)["nodes"]
        results = [
            self.evaluate_one(n["id"])
            for n in nodes
            if n.get("series_code") and n.get("status") in EVALUATED_STATUSES
        ]
        return {"evaluated": len(results), "results": results}

    # ------------------------------------------------------------------ reconciliation

    def reconcile(self) -> dict[str, Any]:
        """Report unregistered codes, unused sensors and bindings to archived nodes, per tenant.
        Flags; never deletes."""
        all_exps = self.core.find_by_mixin(self.principal, "Expectation", None, None)["nodes"]
        by_tenant: dict[str, list[dict[str, Any]]] = {}
        for e in all_exps:
            by_tenant.setdefault(e.get("tenant_id") or DEFAULT_TENANT, []).append(e)
        tenants = sorted({*self.store.tenants(), *by_tenant})
        reports = {t: self._reconcile_tenant(t, by_tenant.get(t, [])) for t in tenants}
        return {
            "unregistered_codes": sorted(
                {c for r in reports.values() for c in r["unregistered_codes"]}
            ),
            "unused_sensors": sorted({c for r in reports.values() for c in r["unused_sensors"]}),
            "archived_bindings": [b for r in reports.values() for b in r["archived_bindings"]],
            "tenants": reports,
        }

    def _reconcile_tenant(self, tenant: str, exps: list[dict[str, Any]]) -> dict[str, Any]:
        st = self._store(tenant)
        sensors = st.list_sensors()
        codes = {s["series_code"] for s in sensors}
        used = {e.get("series_code") for e in exps if e.get("series_code")}
        unregistered = sorted(
            {
                e["series_code"]
                for e in exps
                if e.get("series_code") and e["series_code"] not in codes
            }
        )
        unused = []
        for s in sensors:
            flag = None if s["series_code"] in used else "unused"
            if flag:
                unused.append(s["series_code"])
            if s.get("flag") != flag:
                st.flag_sensor(s["id"], flag)
        stale_bindings = []
        for b in st.list_bindings("thread"):
            try:
                node = self.core.get(self.principal, b["node_id"], depth=0)["node"]
                gone = node.get("status") == "archived"
            except GraphError:
                gone = True
            if gone:
                st.archive_binding("thread", b["id"], flag="target_archived")
                stale_bindings.append(b["id"])
        report = {
            "unregistered_codes": unregistered,
            "unused_sensors": unused,
            "archived_bindings": stale_bindings,
        }
        st.audit(self.principal.actor_id, "reconcile", None, report)
        return report

    # ------------------------------------------------------------------ jobs

    def enqueue(self, kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if kind not in ("evaluate", "reconcile"):
            raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, f"Unknown job kind {kind!r}")
        return {"job": self.store.enqueue(kind, payload or {})}

    def run_jobs_once(self, worker_id: str | None = None, max_jobs: int = 10) -> dict[str, Any]:
        worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
        done = []
        for _ in range(max_jobs):
            job = self.store.claim(worker_id, self.config.lease_seconds)
            if job is None:
                break
            try:
                payload = job.get("payload") or {}
                if job["kind"] == "evaluate":
                    if payload.get("node_id"):
                        out = self.evaluate_one(payload["node_id"])
                    else:
                        out = self.evaluate_all(payload.get("project_id"))
                else:
                    out = self.reconcile()
                self.store.complete(job["id"])
                done.append({"job_id": job["id"], "kind": job["kind"], "result": out})
            except Exception as e:  # noqa: BLE001 - a failing job must not stop the worker
                retry = 60 * job["attempts"] if job["attempts"] < 5 else None
                self.store.fail(job["id"], str(e), retry)
                done.append({"job_id": job["id"], "kind": job["kind"], "error": str(e)})
        return {"worker_id": worker_id, "jobs": done}


def utcnow() -> datetime:
    return datetime.now(UTC)
