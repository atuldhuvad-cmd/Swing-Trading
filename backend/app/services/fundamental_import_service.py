import hashlib
import json
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models import (
    StockMaster, FundamentalSnapshot, FundamentalMetric, SourceTypeMaster,
    SourceReference, DataImportBatch,
)
from app.schemas.fundamental import FundamentalManualImport
from app.services.fundamental_catalog import (
    METRICS, ENTITY_TYPES, STATUSES, PERIOD_TYPES, STATEMENT_SCOPES,
    ORIGINAL_UNITS, CANONICAL_SOURCE_LINE, default_status, catalog_payload,
)
from app.services.fundamental_service import FundamentalService

# Entity types whose provenance must be supplied explicitly, never defaulted.
STRICT_PROVENANCE_ENTITIES = frozenset({"INSURANCE"})


class FundamentalImportService:
    SOURCE_TYPE = "MANUAL_FUNDAMENTAL"

    @staticmethod
    def payload_sha256(payload: FundamentalManualImport) -> str:
        body = payload.model_dump(mode="json")
        canon = json.dumps(body, sort_keys=True, default=str)
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_value(raw: str | None) -> Decimal | None:
        if raw is None or str(raw).strip() == "":
            return None
        try:
            return Decimal(str(raw).replace(",", "").strip())
        except (InvalidOperation, ValueError):
            raise ValueError(f"Invalid decimal value: {raw}")

    @classmethod
    def _normalize_metrics(
        cls, entity_type: str, provided: List[Any]
    ) -> Dict[str, Dict[str, Any]]:
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"Invalid entity_type: {entity_type}")
        known_names = {m["metric_name"] for m in METRICS}
        overlay: Dict[str, Dict[str, Any]] = {}
        for item in provided:
            name = item.metric_name.strip()
            if name not in known_names:
                raise ValueError(f"Unknown metric: {name}")
            status = (item.status or "UNKNOWN").strip().upper()
            if status not in STATUSES:
                raise ValueError(f"Invalid status: {status}")
            val = cls._parse_value(item.metric_value)
            if status == "KNOWN" and val is None:
                raise ValueError(f"KNOWN metric {name} requires a value")
            if status != "KNOWN":
                val = None
            overlay[name] = {"value": val, "status": status}

        complete = {}
        for metric in METRICS:
            name = metric["metric_name"]
            if name in overlay:
                complete[name] = overlay[name]
            else:
                complete[name] = {"value": None, "status": default_status(metric, entity_type)}
        return complete

    @staticmethod
    def _canon_value(val) -> str | None:
        if val is None:
            return None
        return format(Decimal(str(val)).normalize(), "f")

    @classmethod
    def _resolve_provenance(cls, payload: FundamentalManualImport) -> Dict[str, Any]:
        entity = payload.entity_type
        if entity not in ENTITY_TYPES:
            raise ValueError(f"Invalid entity_type: {entity}")
        canonical_line = CANONICAL_SOURCE_LINE[entity]
        scope = (payload.statement_scope or "CONSOLIDATED").strip().upper()
        if scope not in STATEMENT_SCOPES:
            raise ValueError(f"Invalid statement_scope: {payload.statement_scope}")
        # Insurer results carry two differently scoped "Total Income" lines, so the
        # line and the reported unit must be stated explicitly rather than defaulted.
        strict_provenance = entity in STRICT_PROVENANCE_ENTITIES
        if strict_provenance and not (payload.source_line_item or "").strip():
            raise ValueError(f"source_line_item is required for {entity}")
        line = (payload.source_line_item or canonical_line).strip()
        if line != canonical_line:
            raise ValueError(
                f"source_line_item must be '{canonical_line}' for {entity}"
            )
        unit = payload.original_unit.strip().upper() if payload.original_unit else None
        if strict_provenance and unit is None:
            raise ValueError(f"original_unit is required for {entity}")
        if unit is not None and unit not in ORIGINAL_UNITS:
            raise ValueError(f"Invalid original_unit: {payload.original_unit}")
        return {
            "statement_scope": scope,
            "source_line_item": line,
            "original_unit": unit,
        }

    @classmethod
    def _fingerprint(cls, metrics: Dict[str, Dict[str, Any]], provenance: Dict[str, Any] | None = None) -> str:
        rows = []
        for name in sorted(metrics):
            rows.append({
                "n": name,
                "s": metrics[name]["status"],
                "v": cls._canon_value(metrics[name]["value"]),
            })
        payload = {
            "metrics": rows,
            "statement_scope": (provenance or {}).get("statement_scope"),
            "source_line_item": (provenance or {}).get("source_line_item"),
            "original_unit": (provenance or {}).get("original_unit"),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    @classmethod
    def _existing_current(cls, db: Session, stock_id: int, financial_period: str, period_type: str):
        return (
            db.query(FundamentalSnapshot)
            .filter(
                FundamentalSnapshot.stock_id == stock_id,
                FundamentalSnapshot.financial_period == financial_period,
                FundamentalSnapshot.period_type == period_type,
                FundamentalSnapshot.is_superseded == False,
            )
            .order_by(FundamentalSnapshot.version.desc())
            .first()
        )

    @classmethod
    def preview(cls, db: Session, payload: FundamentalManualImport) -> Dict[str, Any]:
        errors: List[str] = []
        symbol = payload.nse_symbol.strip().upper()
        stock = db.query(StockMaster).filter(StockMaster.nse_symbol == symbol).first()
        if not stock:
            raise ValueError(f"Stock symbol {symbol} not found in master")
        if payload.period_type not in PERIOD_TYPES:
            errors.append(f"Invalid period_type: {payload.period_type}")
        if not payload.source_name.strip():
            errors.append("source_name is required")
        if not payload.financial_period.strip():
            errors.append("financial_period is required")

        try:
            metrics = cls._normalize_metrics(payload.entity_type, payload.metrics)
            provenance = cls._resolve_provenance(payload)
        except ValueError as e:
            raise ValueError(str(e))

        age_days = (date.today() - payload.as_of_date).days
        stale_warning = None
        if age_days > FundamentalService.STALENESS_THRESHOLD_DAYS:
            stale_warning = (
                f"as_of_date is {age_days} days old; values are stored as submitted "
                f"(not auto-converted to PASS). Evaluation may later treat them as STALE."
            )

        existing = cls._existing_current(db, stock.stock_id, payload.financial_period, payload.period_type)
        action = "ACCEPTED"
        message = "New snapshot"
        existing_id = None
        if existing:
            existing_id = existing.snapshot_id
            existing_metrics = FundamentalService.get_metric_evidence(db, existing.snapshot_id)
            existing_fp = cls._fingerprint(
                {k: {"value": v["value"], "status": v["status"]} for k, v in existing_metrics.items()},
                {
                    "statement_scope": existing.statement_scope,
                    "source_line_item": existing.source_line_item,
                    "original_unit": existing.original_unit,
                },
            )
            new_fp = cls._fingerprint(metrics, provenance)
            if (
                existing.as_of_date == payload.as_of_date
                and existing.entity_type == payload.entity_type
                and existing_fp == new_fp
            ):
                action = "DUPLICATE"
                message = "Identical current snapshot (idempotent skip)"
            else:
                action = "CONFLICT"
                message = "Same period exists with different evidence; confirm creates a revision"

        metric_rows = [
            {
                "metric_name": name,
                "metric_value": str(data["value"]) if data["value"] is not None else None,
                "status": data["status"],
                "required_by_candidate_rule": name in [m["metric_name"] for m in METRICS if m["required_by_candidate_rule"]],
            }
            for name, data in metrics.items()
        ]

        return {
            "payload_sha256": cls.payload_sha256(payload),
            "action": action,
            "message": message,
            "errors": errors,
            "stale_warning": stale_warning,
            "stock": {
                "stock_id": stock.stock_id,
                "nse_symbol": stock.nse_symbol,
                "company_name": stock.company_name,
            },
            "entity_type": payload.entity_type,
            "statement_scope": provenance["statement_scope"],
            "source_line_item": provenance["source_line_item"],
            "original_unit": provenance["original_unit"],
            "as_of_date": payload.as_of_date.isoformat(),
            "financial_period": payload.financial_period,
            "period_type": payload.period_type,
            "source_name": payload.source_name,
            "source_reference": payload.source_reference,
            "existing_snapshot_id": existing_id,
            "metrics": metric_rows,
            "persisted": False,
        }

    @classmethod
    def _ensure_source_type(cls, db: Session) -> int:
        st = db.query(SourceTypeMaster).filter(SourceTypeMaster.type_name == cls.SOURCE_TYPE).first()
        if st:
            return st.source_type_id
        st = SourceTypeMaster(type_name=cls.SOURCE_TYPE, description="Manual fundamental evidence entry")
        db.add(st)
        db.flush()
        return st.source_type_id

    @classmethod
    def confirm(cls, db: Session, payload: FundamentalManualImport, payload_sha256: str) -> Dict[str, Any]:
        computed = cls.payload_sha256(payload)
        if payload_sha256 != computed:
            raise ValueError("payload_sha256 does not match payload")
        preview = cls.preview(db, payload)
        if preview["errors"]:
            raise ValueError("; ".join(preview["errors"]))

        batch = DataImportBatch(
            import_type="FUNDAMENTAL_MANUAL",
            source_name=payload.source_name,
            source_reference=payload.source_reference,
            original_filename=None,
            file_sha256=computed,
            status="SKIPPED_IDEMPOTENT" if preview["action"] == "DUPLICATE" else "COMPLETED",
            rows_received=len(preview["metrics"]),
            rows_accepted=0,
            rows_rejected=0,
            notes=preview["action"],
        )
        db.add(batch)
        db.flush()

        if preview["action"] == "DUPLICATE":
            db.commit()
            return {
                "status": "DUPLICATE",
                "snapshot_id": preview["existing_snapshot_id"],
                "import_batch_id": batch.import_batch_id,
                "version": None,
                "superseded_previous": False,
                "persisted": False,
                "audit_status": batch.status,
            }

        stock_id = preview["stock"]["stock_id"]
        metrics = cls._normalize_metrics(payload.entity_type, payload.metrics)
        provenance = cls._resolve_provenance(payload)
        source_type_id = cls._ensure_source_type(db)
        source = SourceReference(
            source_type_id=source_type_id,
            publication_name=payload.source_name,
            url=payload.source_reference,
            source_date=datetime.combine(payload.as_of_date, datetime.min.time()),
            original_text=f"Manual fundamental import for {payload.nse_symbol} {payload.financial_period}",
            verification_status="PROVISIONAL",
            import_batch_id=None,
        )
        db.add(source)
        db.flush()

        snapshot = FundamentalService.create_snapshot(
            db=db,
            stock_id=stock_id,
            as_of_date=payload.as_of_date,
            financial_period=payload.financial_period,
            period_type=payload.period_type,
            entity_type=payload.entity_type,
            metrics=metrics,
            source_reference_id=source.source_reference_id,
            reference_date=payload.as_of_date,
            statement_scope=provenance["statement_scope"],
            source_line_item=provenance["source_line_item"],
            original_unit=provenance["original_unit"],
        )
        batch.rows_accepted = len(metrics)
        db.commit()
        db.refresh(snapshot)
        return {
            "status": preview["action"],
            "snapshot_id": snapshot.snapshot_id,
            "import_batch_id": batch.import_batch_id,
            "version": snapshot.version,
            "superseded_previous": snapshot.version > 1,
            "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
            "persisted": True,
            "statement_scope": snapshot.statement_scope,
            "source_line_item": snapshot.source_line_item,
            "original_unit": snapshot.original_unit,
        }
