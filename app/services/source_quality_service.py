from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    ApiFeedRecord,
    ApiFeedRun,
    DestinationPartner,
    Event,
    EventSourceClaim,
    ImageCandidate,
    MasterCalendarSource,
    PartnerReport,
    PoiLocation,
    Region,
    SourceExtractedEventCandidate,
    SourceQualityGrade,
    SourceQualityScore,
    SourceQualitySourceKind,
    SourceReviewStatus,
    utc_now,
)

PUBLISHABLE_STATUSES = {"approved", "published"}
BAD_TICKET_CLASSIFICATIONS = {
    "missing",
    "invalid",
    "generic_platform",
    "generic_app",
    "platform_generic_or_app",
    "tracking_or_affiliate",
    "affiliate_tracking",
    "non_ticket",
    "suspicious",
    "unresolved",
}
PENDING_IMAGE_STATUSES = {
    "selected_pending_approval",
    "needs_approval",
}
BLOCKING_PUBLISH_STATUSES = {"rejected", "stale", "archived", "unpublished"}


@dataclass(frozen=True)
class SourceQualityFilters:
    source_kind: str | None = None
    grade: str | None = None
    region_id: int | None = None
    provider_key: str | None = None


@dataclass(frozen=True)
class SourceQualityDashboardSummary:
    average_score: int
    poor_source_count: int
    poor_region_count: int
    failed_extraction_source_count: int
    duplicate_source_count: int
    missing_ticket_source_count: int
    bad_image_source_count: int
    app_feed_ready_region_count: int
    region_report_due_count: int


def grade_score(score: float | int | None) -> str:
    """Return the source trust grade for a numeric score."""

    if score is None:
        return SourceQualityGrade.unknown.value
    numeric = float(score)
    if numeric >= 90:
        return SourceQualityGrade.excellent.value
    if numeric >= 75:
        return SourceQualityGrade.good.value
    if numeric >= 60:
        return SourceQualityGrade.fair.value
    if numeric >= 40:
        return SourceQualityGrade.poor.value
    return SourceQualityGrade.blocked.value


def build_source_recommendations(inputs: dict[str, object]) -> list[str]:
    """Generate deterministic highest-impact source cleanup recommendations."""

    recommendations: list[tuple[int, str]] = []
    if int_value(inputs, "extraction_failure_count") > 0:
        recommendations.append(
            (95, "Review extraction failures and update the source parser or cadence.")
        )
    if int_value(inputs, "unsupported_count") > 0:
        recommendations.append(
            (90, "Classify unsupported source formats before increasing automation.")
        )
    if float_value(inputs, "duplicate_rate") >= 0.25:
        recommendations.append(
            (85, "Investigate duplicate source claims and tighten dedupe signals.")
        )
    if int_value(inputs, "missing_ticket_count") > 0:
        recommendations.append(
            (80, "Repair missing ticket links or request event-specific ticket URLs.")
        )
    if int_value(inputs, "bad_ticket_count") > 0:
        recommendations.append(
            (
                78,
                "Replace generic or unresolved ticket links with event-specific links.",
            )
        )
    if int_value(inputs, "missing_image_count") > 0:
        recommendations.append(
            (70, "Run photo rescue or request approved event images from the source.")
        )
    if int_value(inputs, "generic_image_blocked_count") > 0:
        recommendations.append(
            (68, "Ask the source for non-generic artist or event images.")
        )
    if int_value(inputs, "missing_venue_count") > 0:
        recommendations.append(
            (65, "Add venue details so events can link to Music Roadtrip places.")
        )
    if int_value(inputs, "missing_geo_count") > 0:
        recommendations.append(
            (62, "Add venue coordinates or verified address data.")
        )
    if int_value(inputs, "app_feed_ready_count") == 0 and int_value(
        inputs,
        "event_count",
    ):
        recommendations.append(
            (60, "Review blockers preventing this source from becoming app-feed ready.")
        )
    if not recommendations:
        recommendations.append(
            (10, "Keep monitoring source quality before expanding automation.")
        )
    recommendations.sort(key=lambda item: item[0], reverse=True)
    return [text for _, text in recommendations[:5]]


def list_source_quality_scores(
    session: Session,
    filters: SourceQualityFilters | None = None,
) -> list[SourceQualityScore]:
    statement = select(SourceQualityScore).order_by(
        SourceQualityScore.updated_at.desc(),
        SourceQualityScore.id.desc(),
    )
    if filters:
        if filters.source_kind:
            statement = statement.where(
                SourceQualityScore.source_kind == filters.source_kind
            )
        if filters.grade:
            statement = statement.where(SourceQualityScore.score_grade == filters.grade)
        if filters.region_id:
            statement = statement.where(
                SourceQualityScore.region_id == filters.region_id
            )
        if filters.provider_key:
            statement = statement.where(
                SourceQualityScore.provider_key == filters.provider_key
            )
    return list(session.scalars(statement).all())


def get_source_quality_score(
    session: Session,
    score_id: int,
) -> SourceQualityScore | None:
    return session.get(SourceQualityScore, score_id)


def latest_source_quality_score(
    session: Session,
    *,
    source_kind: str,
    source_id: int | None = None,
    provider_key: str | None = None,
    region_id: int | None = None,
    partner_id: int | None = None,
) -> SourceQualityScore | None:
    statement = select(SourceQualityScore).where(
        SourceQualityScore.source_kind == source_kind
    )
    if source_id is not None:
        statement = statement.where(SourceQualityScore.source_id == source_id)
    if provider_key is not None:
        statement = statement.where(SourceQualityScore.provider_key == provider_key)
    if region_id is not None:
        statement = statement.where(SourceQualityScore.region_id == region_id)
    if partner_id is not None:
        statement = statement.where(SourceQualityScore.partner_id == partner_id)
    return session.scalars(
        statement.order_by(
            SourceQualityScore.updated_at.desc(),
            SourceQualityScore.id.desc(),
        )
    ).first()


def compute_source_quality_for_master_source(
    session: Session,
    source_id: int,
) -> SourceQualityScore:
    source = session.get(MasterCalendarSource, source_id)
    if source is None:
        raise ValueError("Master calendar source not found.")

    events = events_for_master_source(session, source.id)
    candidates = list(
        session.scalars(
            select(SourceExtractedEventCandidate).where(
                SourceExtractedEventCandidate.master_calendar_source_id == source.id
            )
        ).all()
    )
    claims = list(
        session.scalars(
            select(EventSourceClaim).where(
                EventSourceClaim.master_calendar_source_id == source.id
            )
        ).all()
    )
    inputs = metrics_for_events(session, events)
    inputs.update(
        {
            "source_kind": SourceQualitySourceKind.master_calendar_source.value,
            "source_id": source.id,
            "source_key": source.canonical_url_hash,
            "display_name": source.source_name,
            "region_id": source.region_id,
            "event_created_count": source_created_count(source, events),
            "event_updated_count": source_updated_count(source, events),
            "duplicate_candidate_count": int_value(
                inputs,
                "duplicate_candidate_count",
            ),
            "rejected_count": sum(
                1
                for candidate in candidates
                if candidate.review_status
                in {SourceReviewStatus.rejected.value, "rejected"}
            ),
            "extraction_success_count": source.extraction_success_count,
            "extraction_failure_count": source.extraction_failure_count,
            "unsupported_count": source.unsupported_count,
            "last_success_at": source.last_crawled_at
            if source.extraction_success_count > 0
            else None,
            "last_failure_at": source.last_crawled_at
            if source.extraction_failure_count > 0
            else None,
            "last_failure_reason": latest_candidate_error(candidates),
            "source_claim_count": len(claims),
            "trusted_source": source.review_status == SourceReviewStatus.approved.value
            and source.status == "approved",
        }
    )
    score = persist_source_quality_score(session, inputs)
    source.source_trust_score = score.score
    source.source_trust_grade = score.score_grade
    source.last_quality_score_id = score.id
    session.add(source)
    session.commit()
    session.refresh(score)
    return score


def compute_source_quality_for_api_provider(
    session: Session,
    provider_key: str,
) -> SourceQualityScore:
    provider_key = provider_key.strip()
    events = list(
        session.scalars(
            select(Event)
            .options(selectinload(Event.venue))
            .where(
                or_(
                    Event.api_provider_key == provider_key,
                    Event.ingestion_provider == provider_key,
                )
            )
        ).all()
    )
    runs = list(
        session.scalars(
            select(ApiFeedRun).where(ApiFeedRun.provider_key == provider_key)
        ).all()
    )
    records = list(
        session.scalars(
            select(ApiFeedRecord).where(ApiFeedRecord.provider_key == provider_key)
        ).all()
    )
    inputs = metrics_for_events(session, events)
    inputs.update(
        {
            "source_kind": SourceQualitySourceKind.api_provider.value,
            "source_id": None,
            "source_key": provider_key,
            "display_name": provider_key,
            "provider_key": provider_key,
            "event_count": max(int_value(inputs, "event_count"), len(records)),
            "event_created_count": sum(
                1 for record in records if record.created_event_id is not None
            ),
            "duplicate_candidate_count": max(
                int_value(inputs, "duplicate_candidate_count"),
                sum(1 for record in records if record.duplicate_status != "new"),
                sum(run.duplicate_candidate_count for run in runs),
            ),
            "rejected_count": sum(
                1
                for record in records
                if record.review_status == SourceReviewStatus.rejected.value
            )
            + sum(run.rejected_count for run in runs),
            "extraction_success_count": sum(
                1 for run in runs if run.status in {"success", "completed"}
            ),
            "extraction_failure_count": sum(
                1 for run in runs if run.status == "failure"
            ),
            "unsupported_count": 0,
            "missing_ticket_count": max(
                int_value(inputs, "missing_ticket_count"),
                sum(1 for record in records if not clean(record.tickets_link)),
            ),
            "bad_ticket_count": max(
                int_value(inputs, "bad_ticket_count"),
                sum(
                    1
                    for record in records
                    if is_bad_ticket(record.ticket_link_classification)
                ),
            ),
            "missing_image_count": max(
                int_value(inputs, "missing_image_count"),
                sum(1 for record in records if not clean(record.main_image_url)),
            ),
            "last_success_at": latest_run_time(runs, success=True),
            "last_failure_at": latest_run_time(runs, success=False),
            "last_failure_reason": latest_run_failure(runs),
        }
    )
    return persist_source_quality_score(session, inputs)


def compute_source_quality_for_region(
    session: Session,
    region_id: int,
) -> SourceQualityScore:
    region = session.get(Region, region_id)
    if region is None:
        raise ValueError("Region not found.")
    events = list(
        session.scalars(
            select(Event)
            .options(selectinload(Event.venue))
            .where(Event.region_id == region.id)
        ).all()
    )
    sources = list(
        session.scalars(
            select(MasterCalendarSource).where(
                MasterCalendarSource.region_id == region.id
            )
        ).all()
    )
    pois = list(
        session.scalars(
            select(PoiLocation).where(PoiLocation.region_id == region.id)
        ).all()
    )
    inputs = metrics_for_events(session, events)
    inputs.update(
        {
            "source_kind": SourceQualitySourceKind.region.value,
            "source_id": region.id,
            "source_key": region.region_key,
            "display_name": region.name,
            "region_id": region.id,
            "event_created_count": sum(
                source.extraction_success_count for source in sources
            ),
            "event_updated_count": sum(
                source.last_event_candidate_count for source in sources
            ),
            "extraction_success_count": sum(
                source.extraction_success_count for source in sources
            ),
            "extraction_failure_count": sum(
                source.extraction_failure_count for source in sources
            ),
            "unsupported_count": sum(source.unsupported_count for source in sources),
            "poi_count": len(pois),
            "last_success_at": latest_datetime(
                source.last_crawled_at
                for source in sources
                if source.extraction_success_count > 0
            ),
            "last_failure_at": latest_datetime(
                source.last_crawled_at
                for source in sources
                if source.extraction_failure_count > 0
            ),
            "last_failure_reason": latest_source_failure_reason(sources),
        }
    )
    return persist_source_quality_score(session, inputs)


def compute_source_quality_for_partner(
    session: Session,
    partner_id: int,
) -> SourceQualityScore:
    partner = session.get(DestinationPartner, partner_id)
    if partner is None:
        raise ValueError("Destination partner not found.")
    if partner.region_id:
        region_score = compute_source_quality_for_region(session, partner.region_id)
        inputs = dict(region_score.score_inputs)
        inputs.update(
            {
                "source_kind": SourceQualitySourceKind.destination_partner.value,
                "source_id": partner.id,
                "source_key": f"partner:{partner.id}",
                "display_name": partner.name,
                "partner_id": partner.id,
                "region_id": partner.region_id,
            }
        )
    else:
        inputs = {
            "source_kind": SourceQualitySourceKind.destination_partner.value,
            "source_id": partner.id,
            "source_key": f"partner:{partner.id}",
            "display_name": partner.name,
            "partner_id": partner.id,
            "event_count": 0,
        }
    return persist_source_quality_score(session, inputs)


def compute_all_source_quality(session: Session) -> dict[str, int]:
    """Compute current quality scores across known sources, providers, regions."""

    counts = {
        "master_calendar_source": 0,
        "api_provider": 0,
        "region": 0,
        "destination_partner": 0,
    }
    for source_id in session.scalars(select(MasterCalendarSource.id)):
        compute_source_quality_for_master_source(session, source_id)
        counts["master_calendar_source"] += 1
    provider_keys = set(session.scalars(select(ApiFeedRun.provider_key)).all())
    provider_keys.update(
        key for key in session.scalars(select(Event.api_provider_key)).all() if key
    )
    provider_keys.update(
        key for key in session.scalars(select(Event.ingestion_provider)).all() if key
    )
    for provider_key in sorted(provider_keys):
        compute_source_quality_for_api_provider(session, provider_key)
        counts["api_provider"] += 1
    for region_id in session.scalars(select(Region.id)):
        compute_source_quality_for_region(session, region_id)
        counts["region"] += 1
    for partner_id in session.scalars(select(DestinationPartner.id)):
        compute_source_quality_for_partner(session, partner_id)
        counts["destination_partner"] += 1
    return counts


def source_quality_dashboard_summary(
    session: Session,
) -> SourceQualityDashboardSummary:
    scores = list(session.scalars(select(SourceQualityScore)).all())
    average_score = (
        round(sum(score.score for score in scores) / len(scores)) if scores else 0
    )
    latest_reports = list(
        session.scalars(
            select(PartnerReport.region_id).where(PartnerReport.region_id.is_not(None))
        ).all()
    )
    report_region_ids = {region_id for region_id in latest_reports if region_id}
    return SourceQualityDashboardSummary(
        average_score=average_score,
        poor_source_count=sum(
            1
            for score in scores
            if score.score_grade
            in {SourceQualityGrade.poor.value, SourceQualityGrade.blocked.value}
        ),
        poor_region_count=sum(
            1
            for score in scores
            if score.source_kind == SourceQualitySourceKind.region.value
            and score.score_grade
            in {SourceQualityGrade.poor.value, SourceQualityGrade.blocked.value}
        ),
        failed_extraction_source_count=sum(
            1 for score in scores if score.extraction_failure_count > 0
        ),
        duplicate_source_count=sum(
            1 for score in scores if score.duplicate_candidate_count > 0
        ),
        missing_ticket_source_count=sum(
            1 for score in scores if score.missing_ticket_count > 0
        ),
        bad_image_source_count=sum(
            1
            for score in scores
            if score.missing_image_count > 0 or score.generic_image_blocked_count > 0
        ),
        app_feed_ready_region_count=sum(
            1
            for score in scores
            if score.source_kind == SourceQualitySourceKind.region.value
            and score.app_feed_ready_count > 0
            and score.score_grade
            in {
                SourceQualityGrade.excellent.value,
                SourceQualityGrade.good.value,
            }
        ),
        region_report_due_count=sum(
            1
            for region_id in session.scalars(select(Region.id)).all()
            if region_id not in report_region_ids
        ),
    )


def persist_source_quality_score(
    session: Session,
    inputs: dict[str, object],
) -> SourceQualityScore:
    normalized_inputs = normalize_inputs(inputs)
    score_value = calculate_score(normalized_inputs)
    grade = grade_score(score_value)
    recommendations = build_source_recommendations(normalized_inputs)
    score = SourceQualityScore(
        source_kind=str(
            normalized_inputs.get("source_kind")
            or SourceQualitySourceKind.unknown.value
        ),
        source_id=optional_int(normalized_inputs.get("source_id")),
        source_key=optional_str(normalized_inputs.get("source_key")),
        display_name=str(normalized_inputs.get("display_name") or "Unknown source"),
        region_id=optional_int(normalized_inputs.get("region_id")),
        provider_key=optional_str(normalized_inputs.get("provider_key")),
        partner_id=optional_int(normalized_inputs.get("partner_id")),
        score=score_value,
        score_grade=grade,
        event_count=int_value(normalized_inputs, "event_count"),
        event_created_count=int_value(normalized_inputs, "event_created_count"),
        event_updated_count=int_value(normalized_inputs, "event_updated_count"),
        duplicate_candidate_count=int_value(
            normalized_inputs,
            "duplicate_candidate_count",
        ),
        duplicate_rate=float_value(normalized_inputs, "duplicate_rate"),
        rejected_count=int_value(normalized_inputs, "rejected_count"),
        extraction_success_count=int_value(
            normalized_inputs,
            "extraction_success_count",
        ),
        extraction_failure_count=int_value(
            normalized_inputs,
            "extraction_failure_count",
        ),
        unsupported_count=int_value(normalized_inputs, "unsupported_count"),
        missing_ticket_count=int_value(normalized_inputs, "missing_ticket_count"),
        bad_ticket_count=int_value(normalized_inputs, "bad_ticket_count"),
        missing_image_count=int_value(normalized_inputs, "missing_image_count"),
        generic_image_blocked_count=int_value(
            normalized_inputs,
            "generic_image_blocked_count",
        ),
        selected_pending_approval_image_count=int_value(
            normalized_inputs,
            "selected_pending_approval_image_count",
        ),
        missing_venue_count=int_value(normalized_inputs, "missing_venue_count"),
        missing_geo_count=int_value(normalized_inputs, "missing_geo_count"),
        app_feed_ready_count=int_value(normalized_inputs, "app_feed_ready_count"),
        app_feed_blocked_count=int_value(normalized_inputs, "app_feed_blocked_count"),
        manual_correction_count=int_value(normalized_inputs, "manual_correction_count"),
        last_success_at=optional_datetime(normalized_inputs.get("last_success_at")),
        last_failure_at=optional_datetime(normalized_inputs.get("last_failure_at")),
        last_failure_reason=optional_str(normalized_inputs.get("last_failure_reason")),
        scoring_window_start=optional_datetime(
            normalized_inputs.get("scoring_window_start")
        ),
        scoring_window_end=optional_datetime(
            normalized_inputs.get("scoring_window_end")
        )
        or utc_now(),
        score_inputs_json=json.dumps(normalized_inputs, default=str, sort_keys=True),
        recommendations_json=json.dumps(recommendations, sort_keys=True),
    )
    session.add(score)
    session.commit()
    session.refresh(score)
    return score


def normalize_inputs(inputs: dict[str, object]) -> dict[str, object]:
    normalized = dict(inputs)
    event_count = int_value(normalized, "event_count")
    duplicate_count = int_value(normalized, "duplicate_candidate_count")
    if "duplicate_rate" not in normalized:
        normalized["duplicate_rate"] = (
            round(duplicate_count / event_count, 4) if event_count else 0.0
        )
    normalized.setdefault("scoring_window_end", utc_now())
    return normalized


def calculate_score(inputs: dict[str, object]) -> float:
    event_count = int_value(inputs, "event_count")
    issue_denominator = max(event_count, 1)
    if event_count == 0 and not any(
        int_value(inputs, key)
        for key in (
            "extraction_success_count",
            "extraction_failure_count",
            "unsupported_count",
            "rejected_count",
        )
    ):
        return 60.0

    score = 100.0
    score -= min(25.0, int_value(inputs, "extraction_failure_count") * 12.0)
    score -= min(18.0, int_value(inputs, "unsupported_count") * 8.0)
    score -= min(22.0, float_value(inputs, "duplicate_rate") * 35.0)
    score -= min(18.0, int_value(inputs, "rejected_count") * 4.0)
    score -= min(
        18.0,
        (int_value(inputs, "missing_ticket_count") / issue_denominator) * 22.0,
    )
    score -= min(
        16.0,
        (int_value(inputs, "bad_ticket_count") / issue_denominator) * 20.0,
    )
    score -= min(
        16.0,
        (int_value(inputs, "missing_image_count") / issue_denominator) * 20.0,
    )
    score -= min(12.0, int_value(inputs, "generic_image_blocked_count") * 4.0)
    score -= min(
        8.0,
        int_value(inputs, "selected_pending_approval_image_count") * 2.0,
    )
    score -= min(
        12.0,
        (int_value(inputs, "missing_venue_count") / issue_denominator) * 18.0,
    )
    score -= min(
        10.0,
        (int_value(inputs, "missing_geo_count") / issue_denominator) * 14.0,
    )
    score -= min(10.0, int_value(inputs, "app_feed_blocked_count") * 3.0)
    score -= min(8.0, int_value(inputs, "manual_correction_count") * 1.5)
    if event_count > 0 and optional_datetime(inputs.get("last_success_at")) is None:
        score -= 8.0

    app_ready_count = int_value(inputs, "app_feed_ready_count")
    success_count = int_value(inputs, "extraction_success_count")
    score += min(8.0, (app_ready_count / issue_denominator) * 10.0)
    score += min(6.0, success_count * 2.0)
    score += min(
        5.0,
        max(0, event_count - int_value(inputs, "missing_image_count"))
        / issue_denominator
        * 5.0,
    )
    score += min(
        5.0,
        max(0, event_count - int_value(inputs, "missing_ticket_count"))
        / issue_denominator
        * 5.0,
    )
    if bool(inputs.get("trusted_source")):
        score += 3.0
    if int_value(inputs, "source_claim_count") > event_count:
        score += 3.0

    if optional_datetime(inputs.get("last_success_at")):
        last_success = optional_datetime(inputs.get("last_success_at"))
        now = comparable_now(last_success) if last_success else utc_now()
        if last_success and now - last_success <= timedelta(days=45):
            score += 3.0

    return round(max(0.0, min(100.0, score)), 1)


def events_for_master_source(session: Session, source_id: int) -> list[Event]:
    event_ids = {
        event_id
        for event_id in session.scalars(
            select(EventSourceClaim.event_id).where(
                EventSourceClaim.master_calendar_source_id == source_id,
                EventSourceClaim.event_id.is_not(None),
            )
        ).all()
        if event_id is not None
    }
    if not event_ids:
        return []
    return list(
        session.scalars(
            select(Event)
            .options(selectinload(Event.venue))
            .where(Event.id.in_(sorted(event_ids)))
        ).all()
    )


def metrics_for_events(session: Session, events: list[Event]) -> dict[str, object]:
    event_ids = [event.id for event in events]
    image_candidates = (
        list(
            session.scalars(
                select(ImageCandidate).where(ImageCandidate.event_id.in_(event_ids))
            ).all()
        )
        if event_ids
        else []
    )
    duplicate_count = sum(
        1
        for event in events
        if event.duplicate_status not in {"", "none", "unique", "resolved"}
        or event.duplicate_candidate_group_id is not None
    )
    missing_ticket_count = sum(
        1
        for event in events
        if not clean(event.tickets_link) and not clean(event.recommended_ticket_link)
    )
    bad_ticket_count = sum(
        1 for event in events if is_bad_ticket(event.ticket_link_classification)
    )
    missing_image_count = sum(
        1
        for event in events
        if not clean(event.selected_main_image_url) and not clean(event.main_image_url)
    )
    selected_pending_count = sum(
        1
        for event in events
        if (event.image_status or "") in PENDING_IMAGE_STATUSES
        or (event.image_clearance_status or "") == "needs_approval"
    )
    generic_blocked_count = sum(
        1
        for candidate in image_candidates
        if candidate.generic_detection_score >= 70
        or candidate.appears_stock_or_placeholder
        or "generic_provider_image" in candidate.qa_flags
        or "stock_placeholder_candidate" in candidate.qa_flags
    )
    missing_venue_count = sum(
        1
        for event in events
        if event.event_venue_id is None and not clean(event.location_text)
    )
    missing_geo_count = sum(1 for event in events if event_missing_geo(event))
    app_ready_count = sum(
        1
        for event in events
        if event.publish_status in PUBLISHABLE_STATUSES
        and event.category == "Concert"
        and event.record_type == "event"
    )
    blocked_count = sum(
        1
        for event in events
        if event.publish_status in BLOCKING_PUBLISH_STATUSES
        or event.publish_blockers_json not in {"", "[]"}
    )
    return {
        "event_count": len(events),
        "event_created_count": len(events),
        "event_updated_count": sum(event.update_count for event in events),
        "duplicate_candidate_count": duplicate_count,
        "duplicate_rate": round(duplicate_count / len(events), 4) if events else 0.0,
        "missing_ticket_count": missing_ticket_count,
        "bad_ticket_count": bad_ticket_count,
        "missing_image_count": missing_image_count,
        "generic_image_blocked_count": generic_blocked_count,
        "selected_pending_approval_image_count": selected_pending_count,
        "missing_venue_count": missing_venue_count,
        "missing_geo_count": missing_geo_count,
        "app_feed_ready_count": app_ready_count,
        "app_feed_blocked_count": blocked_count,
        "manual_correction_count": sum(1 for event in events if event.update_count > 0),
        "last_success_at": latest_datetime(event.updated_at for event in events),
    }


def event_missing_geo(event: Event) -> bool:
    venue = event.venue
    if venue and venue.latitude is not None and venue.longitude is not None:
        return False
    return True


def is_bad_ticket(classification: str | None) -> bool:
    if not classification:
        return False
    return classification.strip().lower() in BAD_TICKET_CLASSIFICATIONS


def source_created_count(source: MasterCalendarSource, events: list[Event]) -> int:
    return sum(1 for event in events if event.created_at >= source.created_at)


def source_updated_count(source: MasterCalendarSource, events: list[Event]) -> int:
    return sum(1 for event in events if event.update_count > 0)


def latest_candidate_error(
    candidates: list[SourceExtractedEventCandidate],
) -> str | None:
    for candidate in sorted(candidates, key=lambda item: item.updated_at, reverse=True):
        if candidate.validation_errors:
            return "; ".join(candidate.validation_errors[:2])
        if candidate.quality_flags:
            return "; ".join(candidate.quality_flags[:2])
    return None


def latest_source_failure_reason(sources: list[MasterCalendarSource]) -> str | None:
    for source in sorted(sources, key=lambda item: item.updated_at, reverse=True):
        if source.extraction_failure_count > 0:
            if source.source_quality_flags:
                return "; ".join(source.source_quality_flags[:2])
            return source.last_extraction_status or "extraction_failure"
    return None


def latest_run_time(runs: list[ApiFeedRun], *, success: bool) -> datetime | None:
    matching = [
        run.completed_at or run.started_at
        for run in runs
        if (run.status in {"success", "completed"}) is success
        and (run.completed_at or run.started_at)
    ]
    return latest_datetime(matching)


def latest_run_failure(runs: list[ApiFeedRun]) -> str | None:
    for run in sorted(runs, key=lambda item: item.updated_at, reverse=True):
        if run.status == "failure" and run.error_message:
            return run.error_message
    return None


def latest_datetime(values: Iterable[datetime | None]) -> datetime | None:
    materialized = [value for value in values if value is not None]
    return max(materialized) if materialized else None


def optional_datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None


def comparable_now(value: datetime) -> datetime:
    now = utc_now()
    if value.tzinfo is None:
        return now.replace(tzinfo=None)
    return now


def optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def int_value(values: dict[str, object], key: str) -> int:
    value = values.get(key)
    if value in (None, ""):
        return 0
    try:
        return int(float(str(value)))
    except ValueError:
        return 0


def float_value(values: dict[str, object], key: str) -> float:
    value = values.get(key)
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value))
    except ValueError:
        return 0.0


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
