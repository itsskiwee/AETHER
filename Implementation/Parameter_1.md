AETHER — Autonomous Earth Observation & Climate Intelligence System
Advanced Aerospace Engineering × Sustainability × Climate Science × Autonomous Systems
Research-grade engineering challenge


I would build AETHER: an orbital intelligence system that determines where Earth-observing satellites should look next to detect, measure, and verify major methane emissions.
The critical distinction is that AETHER doesn't merely show satellite images or mark pollution on a map.
It attempts to answer a much harder question:
Given limited satellite observation opportunities, imperfect environmental measurements, uncertain weather, and potentially thousands of emission sources, what should we observe next to produce the greatest scientifically useful information?
Then it models how those observations could influence real climate decisions.
This combines five serious engineering disciplines:
- Aerospace: orbital propagation, satellite visibility, sensor geometry, spacecraft constraints and observation scheduling.
- Environmental science: methane emissions, atmospheric transport, greenhouse-gas monitoring and measurement uncertainty.
- Applied mathematics: inverse problems, Bayesian inference, constrained optimization and information theory.
- Computer science: geospatial computing, distributed processing, computational modeling and simulation.
- Autonomous decision systems: planning future observations based on evidence gathered from previous observations.
1. The real-world problem
Earth-observing satellites can already detect major methane releases from oil and gas facilities, landfills and other sources.
NASA's EMIT instrument, installed on the International Space Station, produces methane plume measurements. Carbon Mapper also publishes methane observations from aircraft and satellite instruments, including equipment developed by NASA JPL. 

NASA Open Data Portal
+1



But making a detection is not the same as knowing everything necessary to take action.
Imagine a satellite detects a large methane plume over an industrial facility.
Immediately, several scientific questions arise:
1. Is the emission continuing, or was it temporary?
2. How much methane is being released, and how uncertain is that estimate?
3. Which nearby facility is the likely source?
4. Is the next satellite observation likely to see the plume, given the orbit, weather and sensor limitations?
5. Should a limited observation opportunity be spent revisiting this source or investigating a different, potentially larger emission elsewhere?
6. If the facility reports repairs, what additional evidence would support a reduction in emissions?
These are real issues in satellite environmental monitoring. NASA's EMIT Version 2 product explicitly includes plume-specific uncertainty information, and Carbon Mapper publishes quality flags, source observations and emission estimates. 

NASA Open Data Portal
+1



AETHER focuses on the decision layer between detecting a plume and deciding what evidence needs to be collected next.
That is its central research contribution.
2. Why this is directly relevant to NASA
There is an important distinction between building something involving NASA satellites and addressing a genuine NASA research problem.
NASA has already worked on automated observation planning, greenhouse-gas detection and environmental monitoring. Your project should not pretend to invent any of those fields.
AETHER would instead investigate an integrated, uncertainty-aware observation strategy: use existing measurements to quantify what remains unknown, then calculate which physically feasible future observations are likely to reduce that uncertainty most.
NASA's actual observation-science ecosystem makes that a credible direction. You can ground the prototype in published measurement products, rather than constructing a fictional environmental problem.
The intended contribution isn't a new satellite. It's a better algorithm for deciding how limited satellite sensing capacity could be used.
There is no guarantee NASA would adopt it. That would require independent validation, mission-specific engineering and substantial operational review. But the underlying research problem is applicable to the kind of systems space agencies and Earth-observation operators investigate.

3. What is genuinely novel about the project?
Research already exists on autonomous spacecraft scheduling, satellite methane detection and Bayesian modeling of intermittent emissions.
In fact, NASA's earlier Earth Observing-1 autonomous sciencecraft work included onboard planning, and a 2024 scientific paper investigated how to interpret methane non-detections across different sensors. 

AAAI
+1



That's important. We should not enter a technical competition with a recycled problem disguised under a new interface.
The research hypothesis for AETHER is more precise:
A closed-loop satellite scheduling system that explicitly models methane-source persistence, observation uncertainty and spacecraft constraints can allocate limited sensing opportunities more effectively than scheduling based only on emitter magnitude, location or acquisition order.

This is a hypothesis to test, not an established improvement.
The system would combine three feedback loops.
Environmental Observation
Measure a methane plume and its uncertainty

Scientific State Estimation
Update what we believe about the emission source

Orbital Observation Planning
Select the most useful physically feasible next measurement

New Evidence and Replanning
Assimilate observations and repeat the planning cycle

The challenge isn't just finding the biggest methane source.
Sometimes observing a smaller but poorly understood source produces more information than repeatedly photographing a well-characterized large source.
Sometimes a large emission should be prioritized because its continuation is uncertain and confirmation could support an important mitigation decision.
And sometimes a target that looks scientifically important should be rejected because the planned measurement would be too cloudy, too oblique or otherwise unlikely to produce usable data.
That's the intelligence AETHER needs to demonstrate.
4. Aerospace engineering: the orbital observation engine
This should be an actual orbital computation subsystem, not animated satellite objects moving around a globe.
4.1 Orbital propagation
Acquire real orbital element data from CelesTrak and propagate positions using SGP4, which is compatible with general perturbations orbital data. CelesTrak supports TLE and OMM-compatible JSON formats. 

CelesTrak



For each spacecraft, calculate:
\[
\mathbf r_s(t)=\operatorname{SGP4}(E_s,t)
\]

where \(E_s\) is the spacecraft's orbital element set and \(\mathbf r_s(t)\) is its propagated position.
Convert that position from its propagation reference frame into an Earth-fixed frame, accounting for Earth rotation. Use Astropy or another established astrodynamics library for proper frame transformations.
For a candidate observation location \(\mathbf r_g\), compute the line-of-sight vector:
\[
\mathbf d(t)=\mathbf r_g-\mathbf r_s(t)
\]

Then determine whether the target lies within the instrument's physically reachable viewing geometry.
The engine must handle Earth occlusion, instrument field of view, orbital timing, permissible off-nadir pointing and daylight requirements where appropriate.
4.2 Observation feasibility
For a given satellite \(s\), location \(i\) and observation time \(t\), define:
\[
F_{sit}=
\begin{cases}
1 & \text{if the observation is feasible}\\
0 & \text{otherwise}
\end{cases}
\]

Feasibility is not merely geographical visibility.
Constraint	What your engine must calculate
Orbit	Whether the spacecraft can geometrically view the target
Sensor	Whether its swath and spectral capability are suitable
Pointing	Whether the desired attitude is attainable
Slew	Whether it can transition from its preceding observation
Illumination	Whether enough appropriate illumination exists
Cloud conditions	Whether useful retrieval is likely
Energy	Whether the modeled operation fits the power budget
Storage	Whether acquired data fits onboard storage
Downlink	Whether data can be delivered within the modeled latency requirement
Here is the aerospace realism requirement: not every satellite is freely taskable.
For example, EMIT is an ISS-mounted spectrometer with its own observation geometry and operational restrictions, not an arbitrary point-and-shoot spacecraft. Its methane products cover sunlit observations roughly between 52° north and south. 

NASA Open Data Portal
+1



AETHER therefore needs two distinct modes: historical analysis of real missions and counterfactual scheduling of explicitly simulated, taskable satellite instruments.
This prevents a common but serious engineering mistake: treating a satellite's ground-track proximity as proof it can acquire any requested image.
4.3 Autonomous constellation scheduling
The full-scale version uses a simulated constellation of heterogeneous spacecraft.
A wide-swath atmospheric instrument identifies regional anomalies, a higher-resolution spectrometer investigates selected targets, and a follow-up sensor provides another opportunity to assess persistence.
The satellites would differ in field of view, revisit opportunities, sensitivity, storage and pointing characteristics.
When the scheduler assigns one observation, it changes what can be scheduled afterward. This is a time-dependent resource allocation problem, not simply sorting targets by score.

5. Environmental engineering: the methane inference engine
This is the second major component, and I would not simplify it to an arbitrary pollution score.
5.1 Understanding the measurement
Methane-sensitive instruments measure spectral evidence of atmospheric methane enhancement. A plume product can express an excess column concentration in units such as ppm·m.
That quantity is not automatically an emission rate.
To estimate a release rate, you must consider the plume geometry, atmospheric transport, wind conditions and retrieval uncertainty.
One established approach uses integrated mass enhancement:
\[
Q \approx \frac{U_{\mathrm{eff}}\cdot \mathrm{IME}}{L}
\]

where:
Symbol	Physical meaning
\(Q\)	Estimated methane emission rate, kg/s
\(\mathrm{IME}\)	Integrated excess methane mass in the plume, kg
\(U_{\mathrm{eff}}\)	Calibrated effective plume transport speed, m/s
\(L\)	Characteristic plume length, m
This is an approximation with calibration requirements, not a universally valid wind-times-mass formula. The effective wind term, plume segmentation, observation angle and atmospheric conditions introduce uncertainty. The integrated mass enhancement method is discussed in the atmospheric measurement literature, including a 2026 analysis of observation geometry. 

AMT



For a hackathon build, I would ingest the published EMIT emission estimates and uncertainties first. A research extension could independently reconstruct the estimates from plume-enhancement rasters and evaluate differences.
5.2 Model intermittent emissions
A source may not emit continuously.
Define a latent source state:
\[
Z_{i,t}\in\{0,1\}
\]

where \(Z_{i,t}=1\) represents an emitting source at time \(t\).
Use a two-state hidden Markov model or another explicitly specified temporal model to estimate the probability that the source remains active.
Then maintain a conditional distribution over its emission rate \(Q_{i,t}\), rather than storing one absolute number.
This distinction is important because no observed plume does not necessarily mean no emission.
The satellite might have observed during an inactive interval. The source might have emitted below the sensor's detection threshold. Clouds or other retrieval conditions might have prevented a valid detection altogether.
Scientific research has specifically examined sensor-dependent detection probability and Bayesian inference of intermittent methane emissions. 

ACS Publications



Your system should distinguish clear valid non-detection, no observation, and unusable observation.
5.3 Bayesian updates
Let \(D\) represent new observation evidence.
For a simplified binary source-state model:
\[
P(Z=1\mid D)=
\frac{P(D\mid Z=1)P(Z=1)}
{P(D)}
\]

The observation likelihood should account for sensor sensitivity, retrieval conditions and the probable emission rate.
A valid non-detection from a high-sensitivity sensor can reduce the posterior probability of continued emission. An observation blocked by cloud should not be interpreted as comparable negative evidence.
In the full implementation, you would also model changes over time and uncertainty in the estimated source magnitude.
The output is a scientific assessment such as:
Simulated Source CH4-017
Illustrative data

Estimated active probability0.82

Estimated flux650
kg CH₄/hour
Flux uncertaintyWide posterior interval

Next actionAcquire corroborating observation



The values above are synthetic UI examples, not measurements of an actual facility.

Instead of falsely reporting that a leak has stopped, AETHER can quantify how strongly the available observations support that conclusion.

6. The hardest component: an information-theoretic mission optimizer
This is where AETHER becomes a serious algorithmic research project.
Most basic schedulers optimize some form of priority score. Your system should optimize the expected scientific value of information that a future observation can provide, while respecting the spacecraft's physical limitations.
6.1 Quantifying information gain
Suppose the current probability that a source is actively emitting is \(p\).
For the binary component of the source state, its uncertainty can be expressed using Shannon entropy:
\[
H(p)=-p\log_2p-(1-p)\log_2(1-p)
\]

If a potential measurement produces outcome \(Y\), define its expected information gain as:
\[
\operatorname{EIG}(a)
=
H(Z\mid D)
-
\mathbb E_{Y\mid D,a}[H(Z\mid D,Y,a)]
\]

Here \(a\) represents a proposed observation and \(D\) represents existing evidence.
The real optimization should also consider uncertainty in the emission rate, not just the binary active state.
A high-priority observation is one expected to improve a decision-relevant estimate, rather than simply produce another image.
6.2 The scheduling objective
Let \(x_j\) equal 1 if candidate observation \(j\) is selected.
A first implementable optimization is:
\[
\max_{\mathbf x}
\sum_j x_j
\left(
\alpha I_j+
\beta R_j-
\gamma L_j-
\delta C_j
\right)
\]

where:
- \(I_j\) is the expected information gain.
- \(R_j\) is the expected decision relevance of observing the source.
- \(L_j\) is the expected information-delivery latency.
- \(C_j\) is an operational resource cost.
- \(\alpha,\beta,\gamma,\delta\) are explicitly defined objective weights.
Subject to observation feasibility, memory, power, pointing and scheduling constraints.
The decision-relevance term is not automatically equal to the methane volume detected. It must have a clear interpretation, such as reducing uncertainty about a potentially large persistent source.
To avoid counting the same information repeatedly, successive observations of one source must have diminishing or state-dependent marginal value.
6.3 Implementation strategy
Start by computing feasible candidate observation windows through orbital geometry.
Then calculate observation utilities from the current scientific state, predicted weather and sensor capability.
Feed feasible observations into a constraint-programming solver such as Google OR-Tools CP-SAT. Its optional interval and non-overlap capabilities suit time-dependent scheduling problems. 

GitHub



For the initial version, use precomputed approximate information-gain values and a mixed-integer scheduling model.
For the research-level version, introduce a rolling-horizon planner: optimize a limited future window, execute or simulate the next observation, update the scientific state, and solve again.
An even harder extension is belief-state planning, potentially using a partially observable Markov decision process. I would not start there; its computational expense is substantial, and a well-validated rolling-horizon optimizer gives you a meaningful baseline.
This is the research question you ultimately test:
Does uncertainty-aware adaptive scheduling produce more useful evidence per constrained satellite observation than conventional scheduling?
A successful result requires experimental proof, not an impressive-looking score on the dashboard.
7. System architecture
Real Scientific Observations
NASA EMIT • Carbon Mapper • Weather • Orbital Data
Geospatial Ingestion + Provenance Layer
Validation • Data normalization • Quality flags • Spatial indexing
Atmospheric Inference
Source state, methane flux, detection likelihood and uncertainty

Orbital Mechanics
SGP4 propagation, visibility, swaths, pointing and resource limits



Constrained Observation Optimizer
Expected information gain • Observation feasibility • Scheduling
Counterfactual Mission Simulator
Simulated measurement → Bayesian update → Replanning
Mission Control + Public Climate Intelligence
Observation schedules • Evidence timelines • Uncertainty • Evaluation

The critical architecture boundary is between real observations and simulated future observations. Those two data classes must never silently mix.
Recommended engineering stack
Subsystem	Technology	Why
Scientific computation	Python, NumPy, SciPy	Mature numerical and statistical ecosystem
Orbital dynamics	sgp4, Skyfield, Astropy	Propagation, timing and frame transformations
Spatial processing	Rasterio, Xarray, GeoPandas	Satellite raster and vector analysis
Source inference	NumPy/SciPy, PyMC if needed	Probabilistic models and uncertainty
Scheduling	OR-Tools CP-SAT	Constrained mission optimization
Data API	FastAPI, Pydantic	Typed service boundaries
Spatial storage	PostgreSQL/PostGIS	Source locations, footprints and proximity searches
Job execution	Redis, background workers	Data processing and simulation tasks
Frontend	React, TypeScript	Interactive mission controls
Geospatial visualization	deck.gl, CesiumJS	Earth observation and orbital visualization
Validation	Pytest, deterministic simulation	Reproducible scientific experiments
Your main difficulty won't be writing the API. It will be maintaining correct interfaces between orbital geometry, observation likelihoods and the optimizer.
8. Real data you can use
I verified that the project can be grounded in accessible, relevant scientific resources rather than invented measurements.
Source	What it contributes	Important limitation
NASA EMIT L2B Methane V002	Methane plume geometry, enhancement, estimates and uncertainties	Contains confirmed plume products, not continuous global coverage
Carbon Mapper API	Multisensor plume detections, estimated emissions, sources and acquisition metadata	Quality, coverage and access restrictions apply
ECMWF ERA5	Historical wind components and atmospheric conditions	Reanalysis is not a live forecast
CelesTrak GP Data	Orbital elements for propagation and ground-track calculations	Orbital elements are not mission-command schedules
NASA Earthdata	Scientific data access and processing resources	Some data require an Earthdata account
The EMIT Version 2 product is particularly useful. Its methane plume package includes 60 m plume rasters and GeoJSON metadata, and its published description documents an uncertainty estimate and emission-rate field when the relevant criteria are met. 

NASA Open Data Portal



Carbon Mapper's documented interface provides plume and emission products. Its public data is intended for non-commercial public-good uses subject to its licensing terms. 

api.carbonmapper.org
+1



For development, NASA also maintains EMIT Data Resources, including Python tutorials for methane plume time series and spectral analysis. 

GitHub



The practical approach: begin with real published methane plumes, use real orbital inputs, and apply an explicitly parameterized virtual observation instrument. That gives you authentic science without claiming access to NASA's spacecraft controls.

9. The experiment that proves AETHER works
A remarkable engineering prototype needs a falsifiable result.
I would design a controlled mission-planning experiment with the same satellites, environmental conditions, source population and observation budget for every scheduling algorithm.
Experimental setup
Observation horizon72 hours

Candidate sources50–100

Virtual spacecraft3

Competing schedulers4


Proposed benchmark configuration, not an executed experiment or measured result.
The four strategies would be:
Strategy	Scheduling logic
First-available	Observe requests in arrival order
Largest-emitter-first	Prioritize the largest current flux estimate
Static science priority	Rank targets once, then schedule feasible passes
AETHER	Recalculate expected information value after observations
All four must obey identical spacecraft constraints.
What you measure
Scientific performance
Use average posterior uncertainty, calibration of source-active probabilities, error in estimated emission rates, and time required to collect useful corroborating evidence.
Aerospace performance
Use percentage of physically feasible schedules, observation opportunities utilized, modeled data-delivery latency, and resource consumption.
Optimization performance
Record solver runtime, objective value, optimality gap where available, and performance as the number of candidate observations increases.
Climate decision relevance
Measure how quickly high-impact uncertain sources are identified for follow-up, with emphasis on independently evaluating whether the inferred priorities actually correspond to meaningful emissions.
For ground truth, generate a hidden simulated source history, use realistic observation coverage and measurement-error assumptions, and assess each scheduler against the same hidden history. Separately replay real archived observations to evaluate data handling and scientific plausibility.
That separation matters: you cannot claim that a counterfactual satellite would have detected methane merely because the optimizer scheduled the observation. You need a defensible observation model, calibrated where possible against real sensor data.
There is also an important environmental accounting distinction: a better detection or verification schedule does not itself reduce emissions. AETHER can improve the evidence available for mitigation decisions; reductions would need separate confirmation.
10. What the hackathon demonstration should look like
Illustrative mission-control experience
AETHER Mission Control
Simulated methane observation mission








dw.com


Scheduling strategy
Static priorityAdaptive AETHER

Observation conditions
Normal atmospheric conditions

Reduced visibility over Source A


Illustrative scheduling decisions
Source A
Priority 2

Source B
Priority 1

Source C
Priority 3

This interface illustrates the intended interaction. Rankings are handcrafted examples, not calculated results from a working optimizer.

The actual demonstration should go further.
Start with a real NASA methane plume, showing its acquisition time, geographic geometry and measured uncertainty.
Bring up the simulated satellite constellation. Show the physically feasible observation windows over the next 72 hours.
Then introduce an updated atmospheric forecast that reduces the expected usefulness of one observation. The optimizer should replan without violating spacecraft constraints.
Next, simulate a new methane measurement that changes the probability that a source remains active. Run the scheduler again.
Finally, place the adaptive and baseline mission outcomes side by side, reporting posterior error, data-collection latency and observation utility from the same reproducible benchmark.
That is the critical moment: the scheduler must visibly change its decisions because the scientific evidence changed—not because someone hardcoded a scripted animation.
11. Feasibility and engineering priorities
The complete research-grade version is much larger than an ordinary weekend project. I would make a clear separation between the competition deliverable and the long-term architecture.
Stage	Required outcome
1. Scientific foundation	Load real methane plume records with uncertainty and metadata
2. Orbital feasibility	Compute observation windows using actual orbital propagation
3. Mission planning	Solve a constrained schedule for simulated observation-capable satellites
4. Adaptive inference	Update the scientific state following a simulated measurement
5. Benchmark	Compare at least two scheduling strategies under identical constraints
6. Interface	Explain and visualize each observation decision
For a 24–48-hour hackathon, I would target a limited geographic region, 10–20 selected historical plumes, one or two virtual satellites and one working Bayesian state update. I'd prioritize reproducible validation over global coverage.
If you have a team, orbital mechanics, scientific data processing, optimization and the frontend can be developed as independent components against common schemas.
The most advanced extensions belong after the hackathon: a full multisensor emission inversion, probabilistic source attribution, continuous mission rescheduling, larger constellation optimization, calibrated detection models and independent validation across multiple geographic regions.
The genuine technical risks
Risk	Engineering response
Inaccurate orbital assumptions	Validate propagated passes and visibility calculations against independent orbital tools
False scientific certainty	Preserve uncertainty distributions and product quality flags
Cloud-contaminated or missing observations	Explicitly model detection probability and missingness
Incorrect source attribution	Use probable associations, not definitive accusations
Unrealistic satellite capabilities	Maintain documented synthetic sensor specifications
Optimizer exploits flawed simulation	Test against held-out scenarios and alternative observation models
Intractable optimization	Use candidate pruning, rolling horizons and solver time limits
For me, a project that correctly reports uncertainty and limitations is more technically credible than one that promises perfect Earth monitoring.
12. What would make it useful outside the competition?
There are two possible users, with different goals.
For Earth-observation researchers and mission planners: AETHER would be an experimental environment for testing how adaptive acquisition strategies perform under real orbital and scientific constraints. Researchers could compare scheduling methods, study sensor trade-offs and measure the effect of uncertainties on scientific yield.
For environmental agencies, researchers, facility operators and the public: Its observation history and evidence products could help identify unresolved large-emission events, understand uncertainty and determine where additional measurement efforts would be useful.
Methane is particularly relevant to sustainability because its atmospheric lifetime is relatively short compared with carbon dioxide, while its warming impact is substantial. The US EPA estimates a 100-year methane global warming potential of approximately 27–30 times that of CO₂. 

US EPA



The platform's scientific value would come from improving the collection and interpretation of relevant evidence, not from claiming that software alone fixes climate change.
13. My final technical assessment
AETHER — Engineering assessment
Algorithmic complexity	Very high
Aerospace depth	Orbital propagation, sensor geometry, constrained scheduling
Environmental depth	Remote sensing, atmospheric inversion, emissions uncertainty
Research opportunity	Adaptive scientific-value scheduling with quantified uncertainty
Publicly accessible data	Yes, with documented access and licensing restrictions
Hackathon feasibility	Scoped experimental prototype
NASA relevance	Potential mission-planning and Earth-observation research applications