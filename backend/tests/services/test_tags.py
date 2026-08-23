"""Governed taxonomy, suggestions, confirmation, and accepted-tag search contracts."""

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import Base, ResearchEvidence, ResearchRun, Source, TagAssignment
from app.services.research.tags import TagService


def test_tag_service_creates_custom_labels_and_preserves_suggestion_evidence(tmp_path) -> None:
    from app.db import create_database_engine

    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'tags.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        with factory() as session:
            source = Source(
                canonical_url="https://example.com/tagged",
                platform="github",
                title="Tagged source",
                raw_text="raw",
                source_markdown="raw",
                import_status="ready",
            )
            session.add(source)
            session.flush()
            run = ResearchRun(source_id=source.id, trigger="manual", status="completed")
            session.add(run)
            session.flush()
            evidence = ResearchEvidence(
                source_id=source.id,
                research_run_id=run.id,
                locator="github://example/tagged@abc/README.md",
                kind="repository_file",
                ordinal=0,
                content="evidence",
                status="included",
            )
            session.add(evidence)
            session.commit()

            tags = TagService(session)
            suggested = tags.suggest(
                source_id=source.id,
                run_id=run.id,
                label="检索增强生成",
                confidence=0.9,
                evidence_ids=(evidence.id,),
            )
            accepted = tags.accept(suggested.id)
            custom = tags.create_custom(source_id=source.id, label="内部评审")
            session.commit()

            assert accepted.status == "accepted"
            assert custom.status == "accepted"
            assert custom.origin == "user"
            assert {assignment.status for assignment in session.scalars(select(TagAssignment))} == {"accepted"}
    finally:
        engine.dispose()
