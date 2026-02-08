"""
Create Donor, RankingEntry, PIXAlert tables. Run once or as migration.
Run with: uv run python scripts/init_db.py
"""

from stream_workers.db import Base, get_engine


def main():
    engine = get_engine()
    Base.metadata.create_all(engine)
    print("Tables created.")


if __name__ == "__main__":
    main()
