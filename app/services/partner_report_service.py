from __future__ import annotations

import csv
import json
from io import StringIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    DestinationPartner,
    Event,
    EventSourceClaim,
    MasterCalendarSource,
    PartnerReport,
    PartnerReportStatus,
    PartnerReportType,
    PoiLocation,
    Region,
    SourceQualityScore,
    SourceQualitySourceKind,
    utc_now,
)
from app.services.app_feed_service import (
    AppEventFilters,
    AppPoiFilters,
    list_app_events,
    list_app_pois,
)
from app.services.region_service import region_source_coverage
from app.services.source_quality_service import (
    build_source_recommendations,
    compute_source_quality_for_master_source,
    compute_source_quality_for_region,
    latest_source_quality_score,
)


def generate_region_partner_report(
    session: Session,
    region_id: int,
    *,
    generated_by: str | None = None,
) -> PartnerReport:
    """Generate a destination-summary report for one region."""

    region = session.get(Region, region_id)
    if region is None:
        raise ValueError("Region not found.")

    region_score = compute_source_quality_for_region(session, region.id)
    sources = list(
        session.scalars(
            select(MasterCalendarSource).where(
                MasterCalendarSource.region_id == region.id
            )
        ).all()
    )
    source_scores: list[SourceQualityScore] = []
    for source in sources:
        if source.last_quality_score_id:
            score = session.get(SourceQualityScore, source.last_quality_score_id)
        else:
            score = compute_source_quality_for_master_source(session, source.id)
        if score is not None:
            source_scores.append(score)

    partner = first_region_partner(session, region.id)
    events = list(
        session.scalars(select(Event).where(Event.region_id == region.id)).all()
    )
    pois = list(
        session.scalars(
            select(PoiLocation).where(PoiLocation.region_id == region.id)
        ).all()
    )
    app_event_count = len(
        list_app_events(session, AppEventFilters(region_id=region.id, limit=10_000))
    )
    app_poi_count = len(
        list_app_pois(session, AppPoiFilters(region_id=region.id, limit=10_000))
    )
    coverage = region_source_coverage(session, region.id)
    metrics = {
        "event_count": len(events),
        "app_feed_ready_events": app_event_count,
        "poi_count": len(pois),
        "app_feed_ready_pois": app_poi_count,
        "approved_calendar_sources": coverage.get("approved_calendar_sources", 0),
        "pending_calendar_sources": coverage.get("pending_calendar_sources", 0),
        "failed_calendar_sources": coverage.get("failed_crawl_sources", 0),
        "unsupported_sources": coverage.get("unsupported_extraction_sources", 0),
        "events_created": sum(score.event_created_count for score in source_scores),
        "events_updated": sum(score.event_updated_count for score in source_scores),
        "duplicate_candidates_avoided": region_score.duplicate_candidate_count,
        "source_claims_created": source_claim_count_for_region(session, region.id),
        "image_issues": (
            region_score.missing_image_count
            + region_score.generic_image_blocked_count
            + region_score.selected_pending_approval_image_count
        ),
        "selected_images_pending_approval": (
            region_score.selected_pending_approval_image_count
        ),
        "generic_images_blocked": region_score.generic_image_blocked_count,
        "missing_ticket_links": region_score.missing_ticket_count,
        "ticket_link_issues": region_score.bad_ticket_count,
        "extraction_failures": region_score.extraction_failure_count,
        "source_quality_grades": {
            score.display_name: score.score_grade for score in source_scores
        },
        "region_quality_grade": region_score.score_grade,
        "region_quality_score": region_score.score,
    }
    top_sources = sorted(source_scores, key=lambda item: item.score, reverse=True)[:5]
    weak_sources = sorted(source_scores, key=lambda item: item.score)[:5]
    summary = {
        "region_name": region.name,
        "partner_name": partner.name if partner else None,
        "reporting_period": "current_local_snapshot",
        "top_performing_sources": [
            source_summary(score) for score in top_sources if score.score >= 75
        ],
        "sources_needing_attention": [
            source_summary(score) for score in weak_sources if score.score < 75
        ],
    }
    recommendation_inputs = {
        **region_score.score_inputs,
        "missing_ticket_count": metrics["missing_ticket_links"],
        "bad_ticket_count": metrics["ticket_link_issues"],
        "missing_image_count": region_score.missing_image_count,
        "generic_image_blocked_count": metrics["generic_images_blocked"],
        "extraction_failure_count": metrics["extraction_failures"],
        "duplicate_rate": region_score.duplicate_rate,
    }
    recommendations = build_source_recommendations(recommendation_inputs)
    report = PartnerReport(
        partner_id=partner.id if partner else None,
        region_id=region.id,
        report_type=PartnerReportType.destination_summary.value,
        status=PartnerReportStatus.generated.value,
        report_period_start=None,
        report_period_end=utc_now(),
        summary_json=json.dumps(summary, default=str, sort_keys=True),
        metrics_json=json.dumps(metrics, default=str, sort_keys=True),
        recommendations_json=json.dumps(recommendations, sort_keys=True),
        generated_at=utc_now(),
        generated_by=generated_by,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def generate_source_quality_report(
    session: Session,
    *,
    region_id: int | None = None,
    partner_id: int | None = None,
    generated_by: str | None = None,
) -> PartnerReport:
    """Generate a source-quality report for a region, partner, or all scores."""

    partner = session.get(DestinationPartner, partner_id) if partner_id else None
    if partner_id and partner is None:
        raise ValueError("Destination partner not found.")
    if partner and region_id is None:
        region_id = partner.region_id
    region = session.get(Region, region_id) if region_id else None
    if region_id and region is None:
        raise ValueError("Region not found.")
    statement = select(SourceQualityScore)
    if region_id:
        statement = statement.where(SourceQualityScore.region_id == region_id)
    if partner_id:
        statement = statement.where(SourceQualityScore.partner_id == partner_id)
    scores = list(
        session.scalars(statement.order_by(SourceQualityScore.score.asc())).all()
    )
    metrics = {
        "score_count": len(scores),
        "average_score": round(sum(score.score for score in scores) / len(scores), 1)
        if scores
        else 0,
        "poor_or_blocked_count": sum(
            1 for score in scores if score.score_grade in {"poor", "blocked"}
        ),
        "ticket_issue_count": sum(
            score.missing_ticket_count + score.bad_ticket_count for score in scores
        ),
        "image_issue_count": sum(
            score.missing_image_count + score.generic_image_blocked_count
            for score in scores
        ),
        "extraction_failure_count": sum(
            score.extraction_failure_count for score in scores
        ),
    }
    summary = {
        "region_name": region.name if region else None,
        "partner_name": partner.name if partner else None,
        "source_quality_grades": {
            score.display_name: score.score_grade for score in scores
        },
    }
    recommendations = build_report_recommendations(scores)
    report = PartnerReport(
        partner_id=partner.id if partner else None,
        region_id=region.id if region else None,
        report_type=PartnerReportType.source_quality.value,
        status=PartnerReportStatus.generated.value,
        report_period_end=utc_now(),
        summary_json=json.dumps(summary, default=str, sort_keys=True),
        metrics_json=json.dumps(metrics, default=str, sort_keys=True),
        recommendations_json=json.dumps(recommendations, sort_keys=True),
        generated_at=utc_now(),
        generated_by=generated_by,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def list_partner_reports(session: Session) -> list[PartnerReport]:
    return list(
        session.scalars(
            select(PartnerReport).order_by(
                PartnerReport.generated_at.desc().nullslast(),
                PartnerReport.id.desc(),
            )
        ).all()
    )


def get_partner_report(session: Session, report_id: int) -> PartnerReport | None:
    return session.get(PartnerReport, report_id)


def latest_region_partner_report(
    session: Session,
    region_id: int,
) -> PartnerReport | None:
    return session.scalars(
        select(PartnerReport)
        .where(PartnerReport.region_id == region_id)
        .order_by(
            PartnerReport.generated_at.desc().nullslast(),
            PartnerReport.id.desc(),
        )
    ).first()


def export_partner_report_json(report: PartnerReport) -> dict[str, object]:
    return {
        "id": report.id,
        "report_type": report.report_type,
        "status": report.status,
        "region_id": report.region_id,
        "partner_id": report.partner_id,
        "report_period_start": str(report.report_period_start or ""),
        "report_period_end": str(report.report_period_end or ""),
        "generated_at": str(report.generated_at or ""),
        "generated_by": report.generated_by,
        "summary": report.summary,
        "metrics": report.metrics,
        "recommendations": report.recommendations,
    }


def export_partner_report_csv(report: PartnerReport) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Section", "Metric", "Value"])
    writer.writerow(["report", "id", report.id])
    writer.writerow(["report", "type", report.report_type])
    writer.writerow(["report", "status", report.status])
    writer.writerow(["report", "generated_at", report.generated_at or ""])
    for key, value in report.summary.items():
        writer.writerow(["summary", key, json.dumps(value, default=str)])
    for key, value in report.metrics.items():
        writer.writerow(["metrics", key, json.dumps(value, default=str)])
    for recommendation in report.recommendations:
        writer.writerow(["recommendations", "recommendation", recommendation])
    return output.getvalue()


def region_report_context(session: Session, region_id: int) -> dict[str, object]:
    region = session.get(Region, region_id)
    if region is None:
        raise ValueError("Region not found.")
    latest_report = latest_region_partner_report(session, region.id)
    region_score = latest_source_quality_score(
        session,
        source_kind=SourceQualitySourceKind.region.value,
        source_id=region.id,
        region_id=region.id,
    )
    source_scores = list(
        session.scalars(
            select(SourceQualityScore)
            .where(
                SourceQualityScore.region_id == region.id,
                SourceQualityScore.source_kind
                == SourceQualitySourceKind.master_calendar_source.value,
            )
            .order_by(SourceQualityScore.score.asc(), SourceQualityScore.id.desc())
        ).all()
    )
    return {
        "region": region,
        "latest_report": latest_report,
        "region_score": region_score,
        "source_scores": source_scores,
    }


def first_region_partner(session: Session, region_id: int) -> DestinationPartner | None:
    return session.scalars(
        select(DestinationPartner)
        .where(DestinationPartner.region_id == region_id)
        .order_by(DestinationPartner.id.asc())
    ).first()


def source_claim_count_for_region(session: Session, region_id: int) -> int:
    source_ids = list(
        session.scalars(
            select(MasterCalendarSource.id).where(
                MasterCalendarSource.region_id == region_id
            )
        ).all()
    )
    if not source_ids:
        return 0
    return int(
        session.scalar(
            select(func.count(EventSourceClaim.id)).where(
                EventSourceClaim.master_calendar_source_id.in_(source_ids)
            )
        )
        or 0
    )


def source_summary(score: SourceQualityScore) -> dict[str, object]:
    return {
        "id": score.id,
        "name": score.display_name,
        "source_kind": score.source_kind,
        "score": score.score,
        "grade": score.score_grade,
        "event_count": score.event_count,
        "recommendations": score.recommendations,
    }


def build_report_recommendations(scores: list[SourceQualityScore]) -> list[str]:
    if not scores:
        return ["Generate source trust scores before sharing this report."]
    weak_scores = [
        score for score in scores if score.score_grade in {"poor", "blocked"}
    ]
    if weak_scores:
        return [
            f"Prioritize cleanup for {weak_scores[0].display_name}.",
            "Review extraction, ticket, image, and duplicate blockers before launch.",
        ]
    if any(score.missing_ticket_count for score in scores):
        return ["Repair missing ticket links for otherwise healthy sources."]
    if any(score.missing_image_count for score in scores):
        return ["Run photo rescue for sources with missing event images."]
    return ["Use these sources as candidates for higher crawl priority."]
