# Architecture: Well-to-Surface Digital Twin
## CSS + SRP Optimization — Baghewala Heavy Oil Field

> **Status:** Phase 1 — Architecture & Design  
> **Prototype disclaimer:** All data is physics-based synthetic, calibrated to published literature.  
> Not validated on real Baghewala field operations.

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     WELL-TO-SURFACE DIGITAL TWIN                    │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │  RESERVOIR   │───>│  WELLBORE    │───>│  SURFACE / SRP       │  │
│  │              │    │              │    │                      │  │
│  │ • Heated zone│    │ • Rod string │    │ • Pumpjack animation │  │
│  │ • Temp decay │    │ • Wave eqn   │    │ • Dyno cards         │  │
│  │ • IPR/PI     │    │ • Drag/visc  │    │ • VFD / motor        │  │
│  │ • SOR        │    │ • Pump barrel│    │ • kWh/bbl            │  │
│  └──────────────┘    └──────────────┘    └──────────────────────┘  │
│         │                   │                       │               │
│         └───────────────────┴───────────────────────┘               │
│                             │                                       │
│                    ┌────────▼────────┐                              │
│                    │   PHYSICS SIM   │  (full + fast surrogate)     │
│                    └────────┬────────┘                              │
│                             │                                       │
│              ┌──────────────┼──────────────┐                        │
│              │              │              │                        │
│     ┌────────▼───┐  ┌───────▼──────┐  ┌───▼──────────┐            │
│     │  ML LAYER  │  │  OPTIMIZER   │  │  SENSOR SIM  │            │
│     │            │  │              │  │              │            │
│     │ • Forecast │  │ • Joint CSS+ │  │ • Noise      │            │
│     │ • Dyno cls │  │   SRP optim  │  │ • Drift      │            │
│     │ • Risk mdl │  │ • Constraint │  │ • Dropouts   │            │
│     │            │  │   engine     │  │ • Spikes     │            │
│     └────────────┘  └──────────────┘  └──────────────┘            │
│                             │                                       │
│                    ┌────────▼────────┐                              │
│                    │   FastAPI +     │                              │
│                    │   WebSocket     │                              │
│                    └────────┬────────┘                              │
│                             │                                       │
│                    ┌────────▼────────┐                              │
│                    │  React Frontend │                              │
│                    │  (Dark SCADA)   │                              │
│                    └─────────────────┘                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Monorepo Structure

```
digital-twin/
├── backend/                        # FastAPI application
│   ├── app/
│   │   ├── main.py                 # FastAPI app, startup, middleware
│   │   ├── api/
│   │   │   ├── wells.py            # GET /wells, /wells/{id}, /wells/{id}/history
│   │   │   ├── cycles.py           # GET/POST /cycles
│   │   │   ├── predict.py          # POST /predict
│   │   │   ├── optimize.py         # POST /optimize (JOINT CSS+SRP)
│   │   │   ├── whatif.py           # POST /whatif
│   │   │   ├── recommendations.py  # GET /recommendations
│   │   │   ├── faults.py           # POST /faults/inject
│   │   │   ├── report.py           # GET /report (PDF)
│   │   │   ├── assistant.py        # POST /assistant (chat)
│   │   │   └── health.py           # GET /health, /offline-check
│   │   ├── ws/
│   │   │   └── stream.py           # WS /ws/stream/{well_id}
│   │   ├── db/
│   │   │   ├── database.py         # SQLAlchemy engine, session
│   │   │   └── models.py           # ORM models
│   │   ├── services/
│   │   │   ├── simulation_service.py   # Orchestrates simulator tick
│   │   │   ├── ml_service.py           # Loads + queries ML models
│   │   │   ├── optimizer_service.py    # Joint optimizer calls
│   │   │   ├── report_service.py       # PDF generation (reportlab)
│   │   │   └── assistant_service.py    # LLM fallback + template explainer
│   │   └── schemas/
│   │       ├── well.py             # Pydantic: WellState, WellConfig
│   │       ├── cycle.py            # Pydantic: CSSCycle, CyclePhase
│   │       ├── srp.py              # Pydantic: SRPState, DynoCard
│   │       ├── prediction.py       # Pydantic: ForecastResult, FaultClass
│   │       ├── optimization.py     # Pydantic: OptimRequest, OptimResult
│   │       ├── recommendation.py   # Pydantic: Recommendation, Explanation
│   │       └── provenance.py       # Pydantic: ProvenanceTag, ProvenancedValue
│   ├── tests/
│   │   ├── test_api_wells.py
│   │   ├── test_api_optimize.py
│   │   ├── test_api_whatif.py
│   │   └── test_websocket.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── simulator/                      # Importable physics engine package
│   ├── __init__.py
│   ├── config.py                   # Default parameters, constants
│   ├── reservoir/
│   │   ├── __init__.py
│   │   ├── heated_zone.py          # Marx-Langenheim heated-zone model
│   │   ├── cooling.py              # Exponential decay toward T_initial
│   │   └── ipr.py                  # Vogel IPR, PI(viscosity) coupling
│   ├── wellbore/
│   │   ├── __init__.py
│   │   └── viscosity.py            # Walther/ASTM D341 viscosity-temperature
│   ├── srp/
│   │   ├── __init__.py
│   │   ├── wave_equation.py        # Damped 1D wave equation (Gibbs method)
│   │   ├── dyno_card.py            # Surface + downhole card generator
│   │   ├── rod_float.py            # Rod floating detection physics
│   │   └── faults.py               # Fault injection: types + card distortion
│   ├── sensor/
│   │   ├── __init__.py
│   │   └── noise.py                # Gaussian noise, drift, spikes, dropouts
│   ├── surrogate/
│   │   ├── __init__.py
│   │   └── fast_surrogate.py       # Vectorized lookup / fitted surrogate
│   ├── well_system.py              # Top-level: orchestrates all sub-models
│   └── tests/
│       ├── test_viscosity.py
│       ├── test_heated_zone.py
│       ├── test_ipr.py
│       ├── test_wave_equation.py
│       ├── test_rod_float.py
│       ├── test_cycle_decline.py   # Cycle 1 best, later cycles worse
│       └── test_surrogate.py
│
├── ml/                             # ML training and inference
│   ├── __init__.py
│   ├── features/
│   │   ├── __init__.py
│   │   ├── dyno_features.py        # Dyno card feature extraction
│   │   └── production_features.py  # Time-series features for forecasting
│   ├── models/
│   │   ├── __init__.py
│   │   ├── forecaster.py           # GBM quantile regression forecaster
│   │   ├── fault_classifier.py     # Feature-based GB fault classifier
│   │   └── failure_risk.py         # Rod failure risk scorer
│   ├── training/
│   │   ├── train_forecaster.py
│   │   ├── train_fault_classifier.py
│   │   └── train_failure_risk.py
│   └── tests/
│       ├── test_forecaster.py
│       ├── test_fault_classifier.py
│       └── test_failure_risk.py
│
├── optimizer/                      # Constraint engine + joint optimizer
│   ├── __init__.py
│   ├── constraints/
│   │   ├── __init__.py
│   │   └── constraint_engine.py    # Hard limits, violation detection
│   ├── whatif/
│   │   ├── __init__.py
│   │   └── whatif_engine.py        # What-if via surrogate, propagation
│   ├── joint_optimizer.py          # Optuna Bayesian opt over surrogate
│   ├── css_planner.py              # Outer loop: CSS cycle parameter planner
│   ├── srp_controller.py           # Inner loop: real-time SPM/VFD adapter
│   ├── explainer.py                # Explanation generator (reason text)
│   └── tests/
│       ├── test_constraints.py
│       ├── test_whatif_propagation.py
│       └── test_optimizer.py
│
├── data/
│   ├── schemas/
│   │   ├── production_history.schema.json
│   │   ├── css_cycle_records.schema.json
│   │   ├── srp_operating_data.schema.json
│   │   ├── rod_failure_history.schema.json
│   │   ├── well_completion.schema.json
│   │   └── fluid_properties.schema.json
│   ├── synthetic/                  # Generated by Phase 3
│   │   ├── production_history.parquet
│   │   ├── css_cycle_records.parquet
│   │   ├── srp_operating_data.parquet
│   │   ├── dyno_cards_labeled.parquet
│   │   └── rod_failure_history.parquet
│   ├── noise_profiles/
│   │   └── sensor_noise_config.json
│   └── generate.py                 # Entry-point: python data/generate.py
│
├── models/
│   └── artifacts/                  # Saved sklearn/XGBoost .joblib files
│       ├── forecaster_q50.joblib
│       ├── forecaster_q10.joblib
│       ├── forecaster_q90.joblib
│       ├── fault_classifier.joblib
│       └── failure_risk.joblib
│
├── frontend/
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── types/
│       │   ├── well.ts             # WellState, WellConfig
│       │   ├── cycle.ts            # CSSCycle, CyclePhase
│       │   ├── srp.ts              # SRPState, DynoCard
│       │   ├── prediction.ts       # ForecastResult, FaultClass
│       │   ├── optimization.ts     # OptimResult, Recommendation
│       │   └── provenance.ts       # ProvenanceTag, ProvenancedValue<T>
│       ├── stores/
│       │   ├── wellStore.ts        # Zustand: live well state
│       │   ├── simStore.ts         # Zustand: simulation controls
│       │   └── uiStore.ts          # Zustand: theme, alerts, panels
│       ├── hooks/
│       │   ├── useWellStream.ts    # WebSocket client hook
│       │   ├── useWhatIf.ts        # Debounced what-if calls
│       │   └── useOptimizer.ts     # Joint optimizer hook
│       ├── components/
│       │   ├── layout/
│       │   │   ├── Sidebar.tsx
│       │   │   ├── TopBar.tsx
│       │   │   └── MainGrid.tsx
│       │   ├── charts/
│       │   │   ├── ProductionChart.tsx
│       │   │   ├── TemperatureHeatmap.tsx
│       │   │   ├── BeforeAfterOverlay.tsx
│       │   │   ├── DynoCard.tsx
│       │   │   └── KPISparkline.tsx
│       │   ├── visuals/
│       │   │   ├── WellCrossSection.tsx    # Animated SVG well
│       │   │   ├── PumpjackAnimation.tsx   # SVG pumpjack at real SPM
│       │   │   ├── CSSTimeline.tsx         # Gantt-style CSS phases
│       │   │   └── FailureRiskGauge.tsx    # Radial risk gauge
│       │   ├── ui/
│       │   │   ├── KPICard.tsx
│       │   │   ├── ProvenanceBadge.tsx
│       │   │   ├── RecommendationCard.tsx
│       │   │   ├── AlertCenter.tsx
│       │   │   ├── FaultInjector.tsx
│       │   │   ├── WhatIfPanel.tsx
│       │   │   ├── AssistantPanel.tsx
│       │   │   └── Tooltip.tsx
│       │   └── screens/
│       │       ├── DemoScreen.tsx          # ONE-SCREEN demo (no scroll)
│       │       ├── MultiWellOverview.tsx
│       │       └── GuidedDemoMode.tsx
│       ├── utils/
│       │   ├── provenance.ts       # Badge color + label lookup
│       │   ├── physics.ts          # Client-side display calculations
│       │   └── format.ts           # Number formatting, units
│       └── assets/
│           └── fonts/              # Inter + JetBrains Mono (local)
│
├── docs/
│   ├── architecture.md             # This file
│   ├── physics.md                  # Physics equations with citations
│   ├── data_strategy.md            # Provenance model, data sources
│   ├── ml_models.md                # Model specs, metrics, limitations
│   ├── api_contract.md             # REST + WebSocket contract
│   ├── deployment.md               # Docker, local, cloud deploy guide
│   └── demo_script.md              # 3-minute SIH demo script
│
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
├── .env.example
├── Makefile
└── README.md
```

---

## 3. Data Flow

```
[Simulator tick]
      │
      ▼
[Sensor noise layer]
      │
      ├──> [WebSocket stream] ──> [React frontend live view]
      │
      ├──> [SQLite DB] ──> [REST API] ──> [React frontend history]
      │
      ├──> [ML Forecaster] ──> [Prediction intervals]
      │
      ├──> [Dyno Feature Extractor] ──> [Fault Classifier] ──> [Alert]
      │
      ├──> [Risk Model] ──> [Failure Risk Score]
      │
      └──> [Joint Optimizer] ──> [CSS + SRP Recommendations]
                │
                └──> [Constraint Engine] ──> [Violation check]
                              │
                              └──> [Explainer] ──> [Recommendation card]
```

---

## 4. Technology Stack

| Layer | Technology | Reason |
|---|---|---|
| Backend | FastAPI 0.111, Python 3.11 | Async, WebSocket, auto OpenAPI |
| Database | SQLite + SQLAlchemy 2.0 | Zero-config, file-based, offline |
| Physics | NumPy, SciPy | Vectorized ODE/PDE solvers |
| ML | scikit-learn 1.4, XGBoost 2.0, LightGBM | CPU-only, lightweight |
| Optimizer | Optuna 3.x + SciPy optimize | Bayesian + gradient-based |
| PDF | ReportLab | Local, no external dependency |
| Frontend | React 18 + Vite 5 + TypeScript | Fast dev + build |
| State | Zustand | Lightweight, no boilerplate |
| Styling | Tailwind CSS 3 + shadcn/ui | Design tokens, dark mode |
| Charts | Apache ECharts (echarts-for-react) | SVG/Canvas, offline |
| Animation | Framer Motion | Transitions + count-up |
| WebSocket | Native browser + FastAPI WS | No socket.io dependency |
| Containerization | Docker + docker-compose | One-command deploy |

---

## 5. Key Design Decisions

1. **Hybrid architecture**: Physics simulator is the ground truth; ML only predicts and classifies. The optimizer calls the surrogate (fast physics approximation), not a pure ML model.

2. **No PyTorch in default install**: All ML uses scikit-learn / XGBoost. A `USE_CNN_CLASSIFIER=true` env flag enables an optional CNN for dyno cards.

3. **Offline-first**: All fonts, icons, model artifacts bundled. WebSocket stream comes from the local simulator. No CDN calls.

4. **Surrogate accuracy**: The fast surrogate is a fitted polynomial/lookup table of the full simulator. Its accuracy (R² vs full sim) is reported in the UI as a "Twin-vs-Sensor deviation" badge.

5. **Provenance everywhere**: Every number in the API response carries a `provenance` field. The frontend renders colored badges. There is a legend on every panel.

6. **Constraint-first recommendations**: Optimizer outputs are always passed through the constraint engine before being shown. Violations are surfaced, not hidden.
