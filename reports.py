import io
from datetime import datetime, timedelta, timezone
from app.celery_app import celery_app


@celery_app.task(bind=True, max_retries=2)
def export_team_report_pdf(self, team_id: str, period_days: int = 30) -> str:
    """
    Generate a PDF performance report for a team and upload it to S3.
    Returns the S3 URL of the generated PDF.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table,
            TableStyle, HRFlowable,
        )
        from app.tasks.activities import generate_performance_report
        from app.tasks.activities import upload_image_to_s3

        # Gather data
        report_data = generate_performance_report(team_id, period_days)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "Title",
            parent=styles["Heading1"],
            fontSize=20,
            spaceAfter=6,
        )
        subtitle_style = ParagraphStyle(
            "Subtitle",
            parent=styles["Normal"],
            fontSize=11,
            textColor=colors.grey,
            spaceAfter=20,
        )

        story = []

        # Header
        story.append(Paragraph("Informe de Rendimiento del Equipo", title_style))
        story.append(Paragraph(
            f"Período: últimos {period_days} días · "
            f"Generado el {datetime.now(timezone.utc).strftime('%d/%m/%Y')}",
            subtitle_style,
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
        story.append(Spacer(1, 0.5 * cm))

        # Summary table
        athletes = report_data.get("athletes", [])
        if athletes:
            table_data = [
                ["Atleta", "Sesiones", "Distancia (km)", "Tiempo (h)", "Desnivel (m)"]
            ]
            for a in athletes:
                table_data.append([
                    a.get("full_name") or a.get("username", "—"),
                    str(a.get("sessions", 0)),
                    f"{a.get('total_km', 0):.1f}",
                    f"{a.get('total_hours', 0):.1f}",
                    f"{a.get('total_elevation_m', 0):.0f}",
                ])

            table = Table(table_data, colWidths=[5 * cm, 2.5 * cm, 3 * cm, 3 * cm, 3 * cm])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D9E75")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 11),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(table)
        else:
            story.append(Paragraph("No hay datos de actividad en este período.", styles["Normal"]))

        story.append(Spacer(1, 1 * cm))

        # Footer note
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(
            "Generado automáticamente por Endurance Platform · Solo para uso interno",
            ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=colors.grey),
        ))

        doc.build(story)
        pdf_bytes = buffer.getvalue()

        # Upload to S3
        filename = f"report_{team_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
        url = upload_image_to_s3.run(
            folder="reports",
            object_id=team_id,
            file_content=pdf_bytes,
            filename=filename,
            content_type="application/pdf",
        )
        return url

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task
def export_athlete_activities_csv(user_id: str) -> str:
    """
    Export all activities for a user as CSV and upload to S3.
    Returns the S3 URL (or a download link after uploading).
    """
    import csv
    from app.tasks._db import run_in_sync_session
    from app.models import Activity
    from sqlalchemy import select

    def _work(session):
        activities = session.execute(
            select(Activity)
            .where(Activity.user_id == user_id)
            .order_by(Activity.started_at.desc())
        ).scalars().all()

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=[
            "date", "title", "discipline", "type",
            "distance_km", "duration_min", "pace_min_km",
            "avg_hr", "elevation_m", "calories", "effort",
        ])
        writer.writeheader()
        for a in activities:
            writer.writerow({
                "date": a.started_at.strftime("%Y-%m-%d") if a.started_at else "",
                "title": a.title,
                "discipline": a.discipline,
                "type": a.activity_type,
                "distance_km": round((a.distance_meters or 0) / 1000, 3),
                "duration_min": round((a.duration_seconds or 0) / 60, 1),
                "pace_min_km": round((a.avg_pace_sec_per_km or 0) / 60, 2),
                "avg_hr": a.avg_heart_rate or "",
                "elevation_m": a.elevation_gain_m or "",
                "calories": a.calories_burned or "",
                "effort": a.perceived_effort or "",
            })
        return buffer.getvalue().encode("utf-8")

    csv_bytes = run_in_sync_session(_work)

    from app.tasks.activities import upload_image_to_s3
    filename = f"activities_{user_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    url = upload_image_to_s3.run(
        folder="exports",
        object_id=user_id,
        file_content=csv_bytes,
        filename=filename,
        content_type="text/csv",
    )
    return url
