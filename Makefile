include .env
export

.PHONY: dev reset migrate

dev:
	alembic upgrade head
	uvicorn app.main:app --reload

reset:
	PGPASSWORD=$(DB_PASSWORD) psql -h $(DB_HOST) -p $(DB_PORT) -U $(DB_USER) -d $(DB_NAME) -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	@echo "Database reset complete. Run 'make dev' to recreate schema."

migrate:
	alembic revision --autogenerate -m "$(msg)"
