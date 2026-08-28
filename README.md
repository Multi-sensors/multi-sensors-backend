# NavipetBackend

FastAPI backend for the Multi-Sensors research platform.

## Planned responsibilities

- Validate normalized temperature, humidity, and alcohol readings.
- Register sensor metadata.
- Ingest live readings and imported historical datasets.
- Store readings in portable PostgreSQL.
- Provide filtered, paginated history and comparison-ready time series.
- Expose health checks for deployment on Render.

## Planned stack

- Python and FastAPI
- Pydantic validation
- SQLAlchemy and Alembic
- PostgreSQL hosted on Neon or Supabase
- Render deployment

## Status

Planning and research. No API scaffold exists yet. Neon versus Supabase remains an open decision.

## Project documentation

See the [Multi-Sensors organization profile](https://github.com/Multi-sensors) for architecture, roadmap, and the proposed data contract.
