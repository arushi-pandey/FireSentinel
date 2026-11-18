import { useEffect, useState } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  useMap,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";
import "./App.css";


function MapFocus({ incident }) {
  const map = useMap();

  useEffect(() => {
    if (incident) {
      map.flyTo(
        [incident.lat, incident.lng],
        7,
        {
          duration: 1.2,
        }
      );
    }
  }, [incident, map]);

  return null;
}


function App() {

  const [incidents, setIncidents] = useState([]);
  const [selectedIncident, setSelectedIncident] = useState(null);

  const [incidentLocation, setIncidentLocation] = useState("");

  const [loading, setLoading] = useState(true);

  const [alertOpen, setAlertOpen] = useState(false);
  const [alertSent, setAlertSent] = useState(false);

  const [simulationRunning, setSimulationRunning] =
    useState(false);

  const [simulationStep, setSimulationStep] =
    useState(0);

  const [activeLayer, setActiveLayer] =
    useState("thermal");


  // =====================================================
  // LOAD DATA FROM BACKEND
  // =====================================================

  useEffect(() => {

    fetch("http://127.0.0.1:8000/api/incidents")

      .then((response) => response.json())

      .then((data) => {

        setIncidents(data);
        setSelectedIncident(data[0]);
        setLoading(false);

      })

      .catch((error) => {

        console.error(
          "Backend connection error:",
          error
        );

        setLoading(false);

      });

  }, []);

  // ============================================================
// LOAD INCIDENT LOCATION
// ============================================================

useEffect(() => {
  const loadLocation = async () => {
    if (!selectedIncident?.lat || !selectedIncident?.lng) return;

    try {
      const response = await fetch(
        `http://127.0.0.1:8000/api/location?lat=${selectedIncident.lat}&lng=${selectedIncident.lng}`
      );

      const data = await response.json();

      setIncidentLocation(data.location || "Location unavailable");

    } catch (error) {
      console.log("Location lookup failed:", error);
      setIncidentLocation("Location unavailable");
    }
  };

  loadLocation();
}, [selectedIncident]);

  // =====================================================
  // SIMULATION
  // =====================================================

  useEffect(() => {

    if (!simulationRunning) return;

    if (simulationStep >= 4) {

      setSimulationRunning(false);
      return;

    }

    const timer = setTimeout(() => {

      const incident =
        incidents[simulationStep];

      if (incident) {
        setSelectedIncident(incident);
      }

      setSimulationStep(
        simulationStep + 1
      );

    }, 1300);

    return () => clearTimeout(timer);

  }, [
    simulationRunning,
    simulationStep,
    incidents,
  ]);


  const startSimulation = () => {

    if (!incidents.length) return;

    setSimulationStep(0);
    setSimulationRunning(true);
    setAlertSent(false);

  };


  // =====================================================
  // HELPERS
  // =====================================================

  const getPriorityClass = (priority) => {

    if (priority === "P1")
      return "p1";

    if (priority === "P2")
      return "p2";

    return "p3";

  };


  const getMarkerColor = (priority) => {

    if (priority === "P1")
      return "#ff3b30";

    if (priority === "P2")
      return "#ff9500";

    return "#27d96b";

  };


  const getRiskLabel = (score) => {

    if (score >= 75)
      return "CRITICAL";

    if (score >= 50)
      return "HIGH";

    return "MODERATE";

  };


  const getConfidence = (incident) => {

    if (!incident) return 0;

    if (incident.type === "Industrial Fire")
      return 94;

    if (incident.type === "Persistent Thermal")
      return 91;

    if (incident.type === "Wildfire")
      return 88;

    return 93;

  };


  const getClassificationScores = (incident) => {

    if (!incident) return [];

    switch (incident.type) {

      case "Industrial Fire":
        return [
          ["Industrial Fire", 94],
          ["Persistent Thermal", 3],
          ["Wildfire", 2],
          ["Agricultural Burn", 1],
        ];

      case "Persistent Thermal":
        return [
          ["Persistent Thermal", 91],
          ["Industrial Fire", 5],
          ["Agricultural Burn", 3],
          ["Wildfire", 1],
        ];

      case "Wildfire":
        return [
          ["Wildfire", 88],
          ["Industrial Fire", 5],
          ["Agricultural Burn", 4],
          ["Persistent Thermal", 3],
        ];

      default:
        return [
          ["Agricultural Burn", 93],
          ["Wildfire", 4],
          ["Industrial Fire", 2],
          ["Persistent Thermal", 1],
        ];
    }

  };

  const getRiskBreakdown = (incident) => {
    if (!incident) return [];
  
    return [
      {
        label: "Thermal Intensity",
        icon: "🔥",
        value: Math.round(incident.frp * 0.25),
        max: 25,
      },
      {
        label: "Population Exposure",
        icon: "👥",
        value: Math.round(incident.population * 0.20),
        max: 20,
      },
      {
        label: "Industrial Proximity",
        icon: "🏭",
        value: Math.round(incident.industrial_proximity * 0.20),
        max: 20,
      },
      {
        label: "Persistence",
        icon: "🔄",
        value: Math.round(incident.persistence * 0.15),
        max: 15,
      },
      {
        label: "Wind Exposure",
        icon: "💨",
        value: Math.round(incident.wind_exposure * 0.10),
        max: 10,
      },
      {
        label: "Fire History",
        icon: "📚",
        value: Math.round(incident.fire_history * 0.10),
        max: 10,
      },
    ];
  };

  const getReasons = (incident) => {

    if (!incident) return [];

    const reasons = [];

    if (incident.frp >= 70)
      reasons.push("High thermal intensity");

    if (incident.population >= 60)
      reasons.push("High population exposure");

    if (incident.industrial_proximity >= 70)
      reasons.push(
        "Close industrial infrastructure"
      );

    if (incident.persistence >= 70)
      reasons.push(
        "Persistent thermal activity"
      );

    if (incident.wind_exposure >= 60)
      reasons.push(
        "Wind trajectory increases exposure"
      );

    if (reasons.length === 0)
      reasons.push(
        "Low contextual exposure"
      );

    return reasons;

  };


  // =====================================================
  // ALERT
  // =====================================================

  const sendAlert = async () => {

    if (!selectedIncident) return;

    try {

      await fetch(
        `http://127.0.0.1:8000/api/alerts/${selectedIncident.id}`,
        {
          method: "POST",
        }
      );

      setAlertSent(true);

      setTimeout(() => {
        setAlertOpen(false);
      }, 1800);

    } catch (error) {

      console.error(
        "Alert error:",
        error
      );

    }

  };


  // =====================================================
  // LOADING
  // =====================================================

  if (loading) {

    return (

      <div className="loading-screen">

        <div className="loader-ring">
          🔥
        </div>

        <h1>
          FIRE SENTINEL
        </h1>

        <p>
          INITIALIZING SATELLITE INTELLIGENCE
        </p>

        <div className="loading-line"></div>

      </div>

    );

  }


  if (!selectedIncident) {

    return (

      <div className="loading-screen">

        <h1>
          FIRE SENTINEL
        </h1>

        <p>
          Unable to connect to intelligence backend.
        </p>

      </div>

    );

  }


  const p1Count =
    incidents.filter(
      (i) => i.priority === "P1"
    ).length;

  const p2Count =
    incidents.filter(
      (i) => i.priority === "P2"
    ).length;

  const maxRisk =
    Math.max(
      ...incidents.map(
        (i) => i.risk_score
      )
    );


  return (

    <div className="app">


      {/* =================================================
          TOP NAV
      ================================================= */}

      <header className="topbar">

        <div className="brand-block">

          <div className="brand-row">

            <span className="brand-fire">
              🔥
            </span>

            <div>

              <h1>
                FIRE SENTINEL
              </h1>

              <span className="brand-tag">
                INDUSTRIAL FIRE INTELLIGENCE
              </span>

            </div>

          </div>

        </div>


        <div className="top-status">

          <div className="sync-status">

            <span className="pulse-dot"></span>

            <div>

              <strong>
                SYSTEM OPERATIONAL
              </strong>

              <small>
                INTELLIGENCE PIPELINE ONLINE
              </small>

            </div>

          </div>


          <div className="sync-time">

            <span>
              LAST SYNC
            </span>

            <strong>
              LIVE
            </strong>

          </div>

        </div>

      </header>


      {/* =================================================
          KPI BAR
      ================================================= */}

      <section className="kpi-grid">


        <div className="kpi-card">

          <div className="kpi-icon">
            ◉
          </div>

          <div>

            <span>
              ACTIVE HOTSPOTS
            </span>

            <strong>
              {incidents.length}
            </strong>

            <small>
              THERMAL DETECTIONS
            </small>

          </div>

        </div>


        <div className="kpi-card critical">

          <div className="kpi-icon">
            !
          </div>

          <div>

            <span>
              P1 CRITICAL
            </span>

            <strong>
              {p1Count}
            </strong>

            <small>
              IMMEDIATE RESPONSE
            </small>

          </div>

        </div>


        <div className="kpi-card warning">

          <div className="kpi-icon">
            ▲
          </div>

          <div>

            <span>
              P2 HIGH RISK
            </span>

            <strong>
              {p2Count}
            </strong>

            <small>
              PRIORITY MONITORING
            </small>

          </div>

        </div>


        <div className="kpi-card">

          <div className="kpi-icon">
            ◎
          </div>

          <div>

            <span>
              MAX RISK
            </span>

            <strong>
              {maxRisk}
            </strong>

            <small>
              OUT OF 100
            </small>

          </div>

        </div>


        <div className="kpi-card source-card">

          <div className="satellite-icon">
            🛰
          </div>

          <div>

            <span>
              PRIMARY SENSOR
            </span>

            <strong>
              FIRMS
            </strong>

            <small>
              MODIS / VIIRS
            </small>

          </div>

        </div>

      </section>


      {/* =================================================
          MAIN COMMAND CENTER
      ================================================= */}

      <main className="command-center">


        {/* ================= MAP ================= */}

        <section className="map-panel">

          <div className="panel-header">

            <div>

              <div className="eyebrow">
                GEOSPATIAL INTELLIGENCE
              </div>

              <h2>
                National Thermal Activity
              </h2>

              <p>
                Real-time hotspot visualization & contextual risk
              </p>

            </div>


            <div className="map-live">

              <span className="pulse-dot"></span>

              LIVE FEED

            </div>

          </div>


          {/* MAP */}

          <div className="map-container">

            <MapContainer
              center={[23.5, 78.9]}
              zoom={5}
              scrollWheelZoom={true}
              className="map"
            >

<TileLayer
  attribution="Tiles &copy; Esri"
  url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
/>


              <MapFocus
                incident={selectedIncident}
              />


              {incidents.map(
                (incident) => (

                  <CircleMarker

                    key={incident.id}

                    center={[
                      incident.lat,
                      incident.lng,
                    ]}

                    radius={
                      incident.priority === "P1"
                        ? 15
                        : incident.priority === "P2"
                          ? 12
                          : 9
                    }

                    pathOptions={{

                      color:
                        getMarkerColor(
                          incident.priority
                        ),

                      fillColor:
                        getMarkerColor(
                          incident.priority
                        ),

                      fillOpacity:
                        selectedIncident.id === incident.id
                          ? 0.95
                          : 0.55,

                      weight:
                        selectedIncident.id === incident.id
                          ? 4
                          : 2,

                    }}

                    eventHandlers={{

                      click: () => {

                        setSelectedIncident(
                          incident
                        );

                        setAlertSent(false);

                      },

                    }}

                  >

                    <Popup>

                      <div className="map-popup">

                        <strong>
                          {incident.id}
                        </strong>

                        <b>
                          {incident.type}
                        </b>

                        <span>
                          Risk {incident.risk_score}/100
                        </span>

                        <span>
                          Priority {incident.priority}
                        </span>

                      </div>

                    </Popup>

                  </CircleMarker>

                )
              )}

            </MapContainer>


            {/* MAP HUD */}

            <div className="map-hud top-left">

              <span>
                LAT 23.500
              </span>

              <span>
                LON 78.900
              </span>

            </div>


            <div className="map-hud bottom-left">

              <span className="hud-live">
                ●
              </span>

              THERMAL FEED

            </div>


            {/* LAYER CONTROL */}

            <div className="layer-control">

              <span>
                MAP LAYERS
              </span>

              {[
                ["thermal", "🔥", "THERMAL"],
                ["industrial", "🏭", "INDUSTRIAL"],
                ["population", "👥", "POPULATION"],
                ["wind", "💨", "WIND"],
              ].map(
                ([id, icon, label]) => (

                  <button

                    key={id}

                    className={
                      activeLayer === id
                        ? "active"
                        : ""
                    }

                    onClick={() =>
                      setActiveLayer(id)
                    }

                  >

                    <span>
                      {icon}
                    </span>

                    {label}

                  </button>

                )
              )}

            </div>

          </div>


          {/* MAP LEGEND */}

          <div className="map-footer">

            <div className="legend">

              <span>
                <i className="legend-dot p1-dot"></i>
                P1 CRITICAL
              </span>

              <span>
                <i className="legend-dot p2-dot"></i>
                P2 HIGH
              </span>

              <span>
                <i className="legend-dot p3-dot"></i>
                P3 MODERATE
              </span>

            </div>


           
          </div>

        </section>


        {/* ================= RIGHT INTELLIGENCE ================= */}

        <aside className="intelligence-panel">


          {/* INCIDENT HEADER */}

          <div className="incident-header">

            <div>

              <span className="eyebrow">
                SELECTED INCIDENT
              </span>

              <h2>
                {selectedIncident.id}
              </h2>

              <div className="incident-location">
  📍 {incidentLocation || "Detecting location..."}
</div>

<div className="incident-coordinates">
  {selectedIncident.lat?.toFixed(4)}° N&nbsp;&nbsp;
  {selectedIncident.lng?.toFixed(4)}° E
</div>

            </div>


            <span
              className={
                `priority-badge ${
                  getPriorityClass(
                    selectedIncident.priority
                  )
                }`
              }
            >

              {selectedIncident.priority}

            </span>

          </div>


          <div className="incident-title">

            <strong>
              {selectedIncident.type}
            </strong>

            <span>
              {selectedIncident.name}
            </span>

          </div>


          {/* RISK SCORE */}

          <div className="risk-panel">

            <div className="risk-top">

              <div>

                <span>
                  CONTEXTUAL RISK SCORE
                </span>

                <strong>
                  {selectedIncident.risk_score}
                  <small>/100</small>
                </strong>

              </div>


              <div className="risk-label">

                <b>
                  {getRiskLabel(
                    selectedIncident.risk_score
                  )}
                </b>

                <span>
                  PRIORITY {selectedIncident.priority}
                </span>

              </div>

            </div>


            <div className="risk-track">

              <div
                className="risk-progress"
                style={{
                  width:
                    `${selectedIncident.risk_score}%`,
                }}
              ></div>

            </div>

          </div>


          {/* AI CLASSIFICATION */}

          <div className="intel-section">

            <div className="section-title-row">

              <span>
                AI CLASSIFICATION
              </span>

              <b>
                {getConfidence(
                  selectedIncident
                )}.0% CONFIDENCE
              </b>

            </div>


            <div className="classification-list">

              {getClassificationScores(
                selectedIncident
              ).map(
                ([label, value]) => (

                  <div
                    className="classification-row"
                    key={label}
                  >

                    <div className="classification-label">

                      <span>
                        {label}
                      </span>

                      <b>
                        {value}%
                      </b>

                    </div>


                    <div className="classification-track">

                      <div
                        className={
                          label === selectedIncident.type
                            ? "classification-fill selected"
                            : "classification-fill"
                        }
                        style={{
                          width: `${value}%`,
                        }}
                      ></div>

                    </div>

                  </div>

                )
              )}

            </div>

          </div>


          {/* RISK FACTORS */}

          <div className="intel-section">

            <div className="section-title-row">

              <span>
                RISK FACTORS
              </span>

              <b>
                CONTEXT ENGINE
              </b>

            </div>


            <div className="factor-grid">


              <div className="factor">

                <span>
                  🔥 FRP
                </span>

                <strong>
                  {selectedIncident.frp}
                </strong>

                <div className="mini-track">

                  <i
                    style={{
                      width:
                        `${selectedIncident.frp}%`,
                    }}
                  ></i>

                </div>

              </div>


              <div className="factor">

                <span>
                  🌡 TEMPERATURE
                </span>

                <strong>
                  {selectedIncident.temperature}
                </strong>

              </div>


              <div className="factor">

                <span>
                  👥 POPULATION
                </span>

                <strong>
                  {selectedIncident.population}
                </strong>

                <div className="mini-track">

                  <i
                    style={{
                      width:
                        `${selectedIncident.population}%`,
                    }}
                  ></i>

                </div>

              </div>


              <div className="factor">

                <span>
                  🏭 INDUSTRIAL
                </span>

                <strong>
                  {selectedIncident.industrial_proximity}
                </strong>

                <div className="mini-track">

                  <i
                    style={{
                      width:
                        `${selectedIncident.industrial_proximity}%`,
                    }}
                  ></i>

                </div>

              </div>


              <div className="factor">

                <span>
                  🔄 PERSISTENCE
                </span>

                <strong>
                  {selectedIncident.persistence}
                </strong>

                <div className="mini-track">

                  <i
                    style={{
                      width:
                        `${selectedIncident.persistence}%`,
                    }}
                  ></i>

                </div>

              </div>


              <div className="factor">

                <span>
                  💨 WIND EXPOSURE
                </span>

                <strong>
                  {selectedIncident.wind_exposure}
                </strong>

                <div className="mini-track">

                  <i
                    style={{
                      width:
                        `${selectedIncident.wind_exposure}%`,
                    }}
                  ></i>

                </div>

              </div>

            </div>

          </div>


          {/* WHY CRITICAL */}

          <div className="why-panel">

            <div className="why-title">
              🧠 WHY THIS INCIDENT MATTERS
            </div>


            {getReasons(
              selectedIncident
            ).map(
              (reason) => (

                <div
                  className="reason"
                  key={reason}
                >

                  <span>
                    ✓
                  </span>

                  {reason}

                </div>

              )
            )}

          </div>


          {/* ALERT BUTTON */}

          <button

            className={
              selectedIncident.priority === "P1"
                ? "response-button critical-button"
                : "response-button"
            }

            onClick={() => {
              setAlertOpen(true);
              setAlertSent(false);
            }}

          >

            🚨 GENERATE RESPONSE ALERT

          </button>


        </aside>

      </main>


      {/* =================================================
          BOTTOM INTELLIGENCE STRIP
      ================================================= */}

      <section className="bottom-grid">


        {/* LIVE FEED */}

        <div className="bottom-panel">

          <div className="bottom-title">

            <div>

              <span className="eyebrow">
                LIVE DETECTION FEED
              </span>

              <h3>
                Recent Thermal Events
              </h3>

            </div>

            <span className="feed-status">
              ● LIVE
            </span>

          </div>


          <div className="feed-list">

            {incidents.map(
              (incident, index) => (

                <button

                  key={incident.id}

                  className={
                    selectedIncident.id === incident.id
                      ? "feed-item selected"
                      : "feed-item"
                  }

                  onClick={() =>
                    setSelectedIncident(
                      incident
                    )
                  }

                >

                  <span
                    className={
                      `feed-dot ${
                        getPriorityClass(
                          incident.priority
                        )
                      }`
                    }
                  ></span>


                  <div className="feed-main">

                    <strong>
                      {incident.id}
                    </strong>

                    <span>
                      {incident.type}
                    </span>

                  </div>


                  <div className="feed-risk">

                    <strong>
                      {incident.risk_score}
                    </strong>

                    <span>
                      {incident.priority}
                    </span>

                  </div>


                  <div className="feed-time">

                    {index === 0
                      ? "2 min ago"
                      : `${(index + 1) * 4} min ago`}

                  </div>

                </button>

              )
            )}

          </div>

        </div>


        {/* TIMELINE */}

        <div className="bottom-panel timeline-panel">

          <div className="bottom-title">

            <div>

              <span className="eyebrow">
                INCIDENT TIMELINE
              </span>

              <h3>
                Detection → Decision
              </h3>

            </div>

            <span className="incident-chip">
              {selectedIncident.id}
            </span>

          </div>


          <div className="timeline">

            <div className="timeline-item">

              <div className="timeline-marker">
                01
              </div>

              <div>

                <strong>
                  Thermal anomaly detected
                </strong>

                <span>
                  FIRMS / MODIS / VIIRS
                </span>

              </div>

              <time>
                20:12
              </time>

            </div>


            <div className="timeline-item">

              <div className="timeline-marker">
                02
              </div>

              <div>

                <strong>
                  Context features extracted
                </strong>

                <span>
                  Industrial • Population • Wind
                </span>

              </div>

              <time>
                20:13
              </time>

            </div>


            <div className="timeline-item">

              <div className="timeline-marker">
                03
              </div>

              <div>

                <strong>
                  Incident classified
                </strong>

                <span>
                  {selectedIncident.type}
                </span>

              </div>

              <time>
                20:14
              </time>

            </div>


            <div className="timeline-item">

              <div className="timeline-marker active">
                04
              </div>

              <div>

                <strong>
                  Risk & priority assigned
                </strong>

                <span>
                  Score {selectedIncident.risk_score}
                  {" • "}
                  {selectedIncident.priority}
                </span>

              </div>

              <time>
                NOW
              </time>

            </div>

          </div>

        </div>


        {/* DATA FUSION */}

        <div className="bottom-panel">

          <div className="bottom-title">

            <div>

              <span className="eyebrow">
                DATA FUSION
              </span>

              <h3>
                Intelligence Sources
              </h3>

            </div>

          </div>


          <div className="source-list">

            <div className="source">

              <span>🛰</span>

              <div>
                <strong>
                  NASA FIRMS
                </strong>

                <small>
                  MODIS / VIIRS
                </small>
              </div>

              <i>
                ONLINE
              </i>

            </div>


            <div className="source">

              <span>🌍</span>

              <div>
                <strong>
                  Sentinel-2
                </strong>

                <small>
                  Multispectral imagery
                </small>
              </div>

              <i>
                READY
              </i>

            </div>


            <div className="source">

              <span>🏭</span>

              <div>
                <strong>
                  OpenStreetMap
                </strong>

                <small>
                  Infrastructure context
                </small>
              </div>

              <i>
                READY
              </i>

            </div>


            <div className="source">

              <span>💨</span>

              <div>
                <strong>
                  ERA5
                </strong>

                <small>
                  Wind conditions
                </small>
              </div>

              <i>
                READY
              </i>

            </div>

          </div>

        </div>

      </section>


      {/* =================================================
          FOOTER
      ================================================= */}

      <footer className="footer">

        <span>
          LOGICLOOP • SMART INDIA HACKATHON 2026
        </span>

        <span>
          FIRE SENTINEL v1.0 • PROTOTYPE INTELLIGENCE SYSTEM
        </span>

      </footer>


      {/* =================================================
          RESPONSE MODAL
      ================================================= */}

      {alertOpen && (

        <div
          className="modal-backdrop"
          onClick={() =>
            setAlertOpen(false)
          }
        >

          <div
            className="alert-modal"
            onClick={(event) =>
              event.stopPropagation()
            }
          >

            {!alertSent ? (

              <>

                <div className="modal-icon">
                  🚨
                </div>

                <span className="eyebrow">
                  P1 RESPONSE PROTOCOL
                </span>

                <h2>
                  Generate Emergency Alert
                </h2>

                <p>
                  This will create a response event
                  for{" "}
                  <strong>
                    {selectedIncident.id}
                  </strong>
                  {" "}
                  and prioritize it for emergency
                  response.
                </p>


                <div className="alert-summary">

                  <div>
                    <span>
                      INCIDENT
                    </span>

                    <strong>
                      {selectedIncident.id}
                    </strong>
                  </div>

                  <div>
                    <span>
                      CLASSIFICATION
                    </span>

                    <strong>
                      {selectedIncident.type}
                    </strong>
                  </div>

                  <div>
                    <span>
                      RISK
                    </span>

                    <strong>
                      {selectedIncident.risk_score}/100
                    </strong>
                  </div>

                </div>


                <div className="modal-actions">

                  <button
                    className="cancel-button"
                    onClick={() =>
                      setAlertOpen(false)
                    }
                  >
                    CANCEL
                  </button>


                  <button
                    className="confirm-button"
                    onClick={sendAlert}
                  >
                    CONFIRM ALERT
                  </button>

                </div>

              </>

            ) : (

              <div className="success-state">

                <div className="success-icon">
                  ✓
                </div>

                <span className="eyebrow">
                  RESPONSE DISPATCH
                </span>

                <h2>
                  ALERT GENERATED
                </h2>

                <p>
                  Response protocol initiated for{" "}
                  <strong>
                    {selectedIncident.id}
                  </strong>
                  .
                </p>

                <div className="success-line">
                  ● Emergency team notified
                </div>

                <div className="success-line">
                  ● Incident prioritized
                </div>

                <div className="success-line">
                  ● Event recorded
                </div>

              </div>

            )}

          </div>

        </div>

      )}

    </div>

  );

}

export default App;