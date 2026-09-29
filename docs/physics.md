# Physics Equations & Parameter Table
## Well-to-Surface Digital Twin — Baghewala Heavy Oil Field

> All equations are implemented in `/simulator/` with inline source citations.  
> Parameters marked FIELD_FACT come from the PS. All others are LITERATURE_ASSUMPTION.

---

## 1. Viscosity–Temperature Model

### Walther / ASTM D341 Equation
```
log₁₀(log₁₀(ν + 0.7)) = A − B·log₁₀(T_K)
```
- ν = kinematic viscosity [cSt]  
- T_K = absolute temperature [K]  
- A, B = fluid-specific constants fitted to two known viscosity points  

**Baghewala calibration target** (FIELD_FACT):
- At T = 46°C (319 K): ν ≈ 1000–5000 cSt (heavy crude, 17–19° API)
- At T = 150°C (steam-heated): ν ≈ 5–20 cSt

**Source:** ASTM D341-20 "Standard Practice for Viscosity-Temperature Charts for Liquid Petroleum Products"; also cited in Ahmed, T. (2010) *Reservoir Engineering Handbook*, 4th ed., Gulf Professional Publishing, p.19.

---

## 2. Reservoir Heated Zone — Marx-Langenheim Model

### Steam-Heated Zone Radius
```
A_h(t) = (Q_s · h_s) / (M_R · ΔT_s) · f(t_D)
```
Where:
- A_h = heated area [m²]; r_h = √(A_h/π) [m]
- Q_s = cumulative steam injection [cold-water equivalent m³]
- h_s = steam enthalpy at injection conditions [kJ/kg]
- M_R = volumetric heat capacity of reservoir [kJ/(m³·°C)]
- ΔT_s = T_steam − T_initial [°C]
- f(t_D) = dimensionless heat function accounting for overburden/underburden heat loss  

**Simplified form used (single-zone, uniform sweep):**
```
r_h(t) = sqrt( (Q_s · Q_factor) / π )
T_avg_h = T_initial + ΔT_s · exp(−λ_cool · t_prod)
```
- Q_factor = efficiency factor (default 0.65, LITERATURE_ASSUMPTION)
- λ_cool = cooling decay constant [1/day]

**Source:** Marx, J.W. and Langenheim, R.H. (1959) "Reservoir Heating by Hot Fluid Injection," *Trans. AIME*, 216, 312–315.

---

## 3. Reservoir Cooling Decay

```
T_res(t) = T_initial + (T_peak − T_initial) · exp(−α · t_prod)
```
- T_initial = 46–48°C (FIELD_FACT)
- T_peak = peak reservoir temperature after steam soak [°C]
- α = thermal diffusivity decay rate [1/day], function of reservoir thickness, porosity, heat capacity
- t_prod = days since production start

**Cycle degradation (SOR rise):**
Each subsequent CSS cycle responds with ~5–15% less thermal efficiency due to:
1. Residual water blocking (relative permeability reduction)
2. Reduced oil saturation

```
η_cycle_n = η_cycle_1 · (1 − 0.08)^(n−1)   # 8% per cycle, LITERATURE_ASSUMPTION
```

**Source:** Butler, R.M. (1991) *Thermal Recovery of Oil and Bitumen*, Prentice-Hall; Bursell, C.G. and Pittman, G.M. (1975) "Performance of Steam Displacement in the Kern River Field," *JPT*, 997–1004.

---

## 4. Productivity Index & Vogel IPR

### Productivity Index (viscosity-coupled)
```
PI(T) = PI_ref · (μ_ref / μ(T))
```
- PI_ref = reference productivity index at reference temperature [m³/(day·kPa)]
- μ_ref = reference viscosity [cP]
- μ(T) = viscosity at current temperature [cP]

### Vogel IPR
```
q_o = q_max · [1 − 0.2·(Pwf/Pr) − 0.8·(Pwf/Pr)²]
q_max = PI · Pr / 1.8
```
- q_o = oil rate [m³/day]
- Pwf = flowing bottomhole pressure [kPa]
- Pr = average reservoir pressure [kPa]

**Source:** Vogel, J.V. (1968) "Inflow Performance Relationships for Solution-Gas Drive Wells," *JPT*, 83–92, SPE-1476-PA.

---

## 5. SRP Wave Equation (Rod String Dynamics)

### Damped 1D Wave Equation (Gibbs Method)
```
∂²u/∂t² = c²·∂²u/∂x² − (2β)·∂u/∂t
```
- u(x,t) = rod displacement at depth x and time t [m]
- c = wave speed in steel rod [m/s]: c = sqrt(E/ρ) ≈ 5100 m/s for steel
- β = damping coefficient [1/s], proportional to fluid viscosity and velocity profile
- E = Young's modulus of steel = 2.07×10¹¹ Pa
- ρ = rod steel density = 7850 kg/m³

**Boundary conditions:**
- x=0 (surface): u(0,t) = stroke_length · sin(2π·SPM/60·t) / 2
- x=L (pump): load = rod weight + buoyancy − fluid load + damping

**Damping–viscosity coupling:**
```
β(T) = β₀ · (μ(T) / μ_ref)^0.5
```
Damping increases with viscosity → rod floating emerges when viscous drag exceeds rod weight.

**Source:** Gibbs, S.G. (1963) "Predicting the Behavior of Sucker-Rod Pumping Systems," *JPT*, 769–778, SPE-588-PA. Takacs, G. (2015) *Sucker-Rod Pumping Handbook*, Gulf Professional Publishing, Ch.4.

---

## 6. Dynamometer Card Generation

### Surface Card
```
F_surface(t) = rod_weight_in_fluid + F_damping(t) + F_pump_load(t)
Position(t) = stroke_length/2 · [1 − cos(2π·SPM/60·t)]
```

### Downhole Card (after wave equation solution)
```
F_downhole = F_surface − M_rod·∂²u/∂t² evaluated at x=L
```
Card shape = {(Position, Load)} sampled at 100–200 points per stroke.

**Fault signatures:**
| Fault | Card Distortion |
|---|---|
| Normal | Parallelogram |
| Rod floating | Top curve flattens / load drops mid-upstroke |
| Pump-off | Card shrinks in load axis |
| Gas interference | Irregular bottom spike |
| Fluid pound | Sharp bottom impact spike |
| Pump unsetting | Irregular, shifting card baseline |

**Source:** Takacs, G. (2015) *Sucker-Rod Pumping Handbook*, Ch.5–6; Lea, J.F. et al. (2008) *Gas Well Deliquification*, Elsevier.

---

## 7. Rod Floating Detection

Rod floating occurs when:
```
v_rod_fall < v_plunger_demand
```
```
v_rod_fall = (W_rod_in_fluid) / (3π · μ(T) · D_rod)    # Stokes-like terminal velocity
v_plunger_demand = stroke_length · SPM/60 · π           # peak plunger velocity
```
Risk multiplier:
```
RF_risk = v_plunger_demand / v_rod_fall   # RF_risk > 1 → floating risk
```

**Source:** Takacs, G. (2015) *Sucker-Rod Pumping Handbook*, p.183–195.

---

## 8. Pump Efficiency

```
η_pump = q_actual / q_theoretical
q_theoretical = π/4 · D_plunger² · stroke_length · SPM · pump_fillage
pump_fillage = f(Pwf, gas_fraction, viscosity)
```
Power:
```
P_motor [kW] = (F_peak · stroke_length · SPM) / (60 × 1000 × η_motor)
kWh_per_bbl = P_motor · 24 / (q_oil [bbl/day])
```

**Source:** API RP 11L (2012) "Recommended Practice for Design Calculations for Sucker Rod Pumping Systems"; Takacs (2015) Ch.3.

---

## 9. Steam-Oil Ratio

```
SOR = Q_steam_CWE [bbl] / Q_oil_produced [bbl]
```
- CWE = cold-water equivalent steam volume (accounts for steam quality χ)
- Q_steam_CWE = m_steam · (χ · h_fg + h_f) / h_water_at_ref

**Source:** Butler (1991) *Thermal Recovery*; SPE-13305 "Steam Injection Into Heavy Oil Reservoirs."

---

## 10. Goodman Rod Stress Limit

```
σ_mean = (F_max + F_min) / (2 · A_rod)
σ_alt  = (F_max − F_min) / (2 · A_rod)
Goodman criterion: σ_alt / S_e + σ_mean / S_u ≤ 1.0
```
- S_e = endurance limit of rod steel [MPa]
- S_u = ultimate tensile strength of rod steel [MPa]
- A_rod = rod cross-sectional area [m²]
Violation → constraint engine raises CRITICAL alert.

**Source:** Shigley, J.E. (2011) *Mechanical Engineering Design*, 9th ed., McGraw-Hill, Ch.6; API Spec 11B (2013).

---

## 11. Physics Parameter Table

| Parameter | Symbol | Value | Unit | Category | Source |
|---|---|---|---|---|---|
| Initial reservoir temp | T_initial | 46–48 | °C | FIELD_FACT | PS |
| API gravity | API | 17–19 | °API | FIELD_FACT | PS |
| Reservoir pressure | Pr | 3.5–5.0 | MPa | LITERATURE_ASSUMPTION | Butler 1991 |
| Reservoir depth | D | 700–900 | m | LITERATURE_ASSUMPTION | Indian heavy oil fields |
| Pay zone thickness | h | 15–25 | m | LITERATURE_ASSUMPTION | Jodhpur Sandstone ranges |
| Porosity | φ | 0.20–0.25 | fraction | LITERATURE_ASSUMPTION | Jodhpur Sandstone |
| Permeability | k | 200–800 | mD | LITERATURE_ASSUMPTION | Heavy oil ss ranges |
| Oil viscosity at T_initial | μ₀ | 1000–5000 | cP | FIELD_FACT (range) | PS |
| Oil viscosity at 150°C | μ_hot | 5–20 | cP | LITERATURE_ASSUMPTION | Ahmed 2010 |
| Steam injection rate | q_steam | 50–150 | t/day | LITERATURE_ASSUMPTION | SPE-13305 |
| Steam quality | χ | 0.70–0.85 | fraction | LITERATURE_ASSUMPTION | Butler 1991 |
| Steam injection pressure | P_inj | 3.0–6.0 | MPa | LITERATURE_ASSUMPTION | CSS operations |
| Soak time | t_soak | 7–21 | days | LITERATURE_ASSUMPTION | CSS operations |
| Production cut-off WOR | WOR_cut | 8–12 | — | LITERATURE_ASSUMPTION | Bursell 1975 |
| Rod modulus of elasticity | E | 2.07×10¹¹ | Pa | LITERATURE_ASSUMPTION | API 11B |
| Rod steel density | ρ_rod | 7850 | kg/m³ | LITERATURE_ASSUMPTION | API 11B |
| Wave speed in rod | c | 5100 | m/s | LITERATURE_ASSUMPTION | Gibbs 1963 |
| Stroke length range | SL | 1.0–4.5 | m | LITERATURE_ASSUMPTION | API RP 11L |
| SPM range | SPM | 2–12 | strokes/min | LITERATURE_ASSUMPTION | Takacs 2015 |
| VFD frequency range | f_VFD | 20–60 | Hz | LITERATURE_ASSUMPTION | Standard SRP VFD |
| Pump plunger diameter | D_p | 44–57 | mm | LITERATURE_ASSUMPTION | API RP 11L |
| Rod string length | L_rod | 700–900 | m | LITERATURE_ASSUMPTION | Matches depth |
| Motor efficiency | η_motor | 0.88–0.92 | fraction | LITERATURE_ASSUMPTION | API RP 11L |
| Fracture pressure gradient | FPG | 0.018–0.020 | MPa/m | LITERATURE_ASSUMPTION | Geopressure data |
| M_R (vol. heat capacity) | M_R | 2100 | kJ/(m³·°C) | LITERATURE_ASSUMPTION | Butler 1991 |
| Thermal decay constant | α | 0.05–0.15 | 1/day | LITERATURE_ASSUMPTION | Marx-Langenheim |
| Cycle efficiency degradation | δ_cyc | 0.08 | per cycle | LITERATURE_ASSUMPTION | Bursell 1975 |
| SOR (typical initial) | SOR₁ | 3–5 | bbl/bbl | LITERATURE_ASSUMPTION | SPE-13305 |
| SOR (after 5 cycles) | SOR₅ | 6–10 | bbl/bbl | LITERATURE_ASSUMPTION | Bursell 1975 |
| Rod endurance limit | S_e | 207 | MPa | LITERATURE_ASSUMPTION | API Spec 11B |
| Rod ultimate strength | S_u | 620 | MPa | LITERATURE_ASSUMPTION | API Spec 11B, Grade D |
