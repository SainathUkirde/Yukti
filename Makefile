.PHONY: setup generate-data train run-dev run-backend run-frontend test build docker-up docker-down offline-check clean

# ── Setup ──────────────────────────────────────────────────────────────────
setup:
	@echo "==> Installing backend dependencies..."
	python -m pip install -r backend/requirements.txt
	@echo "==> Installing frontend dependencies..."
	cd frontend && npm install
	@echo "==> Copying .env.example..."
	@if not exist .env copy .env.example .env
	@echo "==> Setup complete."

# ── Data generation ────────────────────────────────────────────────────────
generate-data:
	@echo "==> Generating synthetic datasets..."
	python data/generate.py
	@echo "==> Done. Datasets in data/synthetic/"

# ── Model training ─────────────────────────────────────────────────────────
train:
	@echo "==> Training forecaster..."
	python ml/training/train_forecaster.py
	@echo "==> Training fault classifier..."
	python ml/training/train_fault_classifier.py
	@echo "==> Training failure risk model..."
	python ml/training/train_failure_risk.py
	@echo "==> All models trained. Artifacts in models/artifacts/"

# ── Development servers ────────────────────────────────────────────────────
run-dev:
	@echo "==> Starting backend (port 8000) and frontend (port 5173)..."
	@start cmd /k "python -m uvicorn backend.app.main:app --reload --port 8000"
	@start cmd /k "cd frontend && npm run dev"

run-backend:
	@echo "==> Starting backend only..."
	python -m uvicorn backend.app.main:app --reload --port 8000

run-frontend:
	@echo "==> Starting frontend dev server..."
	cd frontend && npm run dev

# ── Tests ──────────────────────────────────────────────────────────────────
test:
	@echo "==> Running simulator tests..."
	python -m pytest simulator/tests/ -v
	@echo "==> Running ML tests..."
	python -m pytest ml/tests/ -v
	@echo "==> Running optimizer tests..."
	python -m pytest optimizer/tests/ -v
	@echo "==> Running backend tests..."
	python -m pytest backend/tests/ -v

# ── Production build ───────────────────────────────────────────────────────
build:
	cd frontend && npm run build
	@echo "==> Frontend built to frontend/dist/"

# ── Docker ─────────────────────────────────────────────────────────────────
docker-up:
	@echo "==> Starting all services with Docker Compose..."
	docker compose up --build -d
	@echo "==> Frontend: http://localhost | Backend: http://localhost:8000"

docker-down:
	docker compose down

# ── Offline check ──────────────────────────────────────────────────────────
offline-check:
	@echo "==> Verifying offline readiness..."
	python -c "import urllib.request, json; r=urllib.request.urlopen('http://localhost:8000/offline-check'); print(json.loads(r.read()))"

# ── Clean ──────────────────────────────────────────────────────────────────
clean:
	@echo "==> Cleaning generated files..."
	@if exist data\synthetic rmdir /s /q data\synthetic
	@if exist models\artifacts rmdir /s /q models\artifacts
	@if exist digital_twin.db del digital_twin.db
	@echo "==> Clean complete."
