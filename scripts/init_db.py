"""
Create Donor, RankingEntry, PIXAlert, OverlayPaymentLink tables. Run once or as migration.
Run with: uv run python scripts/init_db.py
"""

from sqlalchemy.orm import Session

from stream_workers.db import Base, OverlayPaymentLink, get_engine


def main():
    engine = get_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        if session.get(OverlayPaymentLink, 1) is None:
            session.add(OverlayPaymentLink(id=1, url=None, label=None, active=False))
            session.commit()
    print("Tables created.")


if __name__ == "__main__":
    main()
