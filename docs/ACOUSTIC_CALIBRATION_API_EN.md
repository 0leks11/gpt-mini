# GPT Mini Autonomous Acoustic Calibration API Reference

This document describes the programming interface for autonomous acoustic calibration, the external AI agent integration protocol via Model Context Protocol (MCP), the security and scoping model, room profile lifecycle management, and physical measurement guidelines.

---

## 1. Architecture and Security Principles

1. **Agent Sandboxing (Principle of Least Privilege):**
   - External AI agents interact with GPT Mini strictly via standard I/O over MCP (or authenticated REST API `/api/v1/acoustics/*`).
   - The agent is **strictly prohibited** from SSH access, system shell execution, daemon reboot, volume control, or reading streaming credentials.
   - Any attempt to invoke administrative or foreign endpoints (`/api/v1/system/*`, `/api/v1/voice`, `/api/v1/volume`, `/api/v1/led`, `/api/spotify/*`) is immediately rejected with `401 Unauthorized` or `403 Forbidden`.

2. **Bounded Calibration Sessions (Lease Bounds):**
   - Calibration runs strictly inside a lease-bounded session (`AcousticSession`).
   - Hard limits protect hardware and user quiet hours:
     - `max_duration_secs`: maximum session duration (default: 1800 s, ceiling: 7200 s).
     - `max_volume_pct`: hardware stimulus playback volume limit (default: 50%, ceiling: 70%).
     - `max_runs`: maximum count of stimulus playback jobs (default: 20, ceiling: 50).
   - Exceeding any lease boundary immediately revokes the lease and rolls back to baseline.

3. **Crash Recovery & Non-Destructive RAM Application:**
   - On session creation, a durable `recovery_session.json` record is written to disk storing the `baseline_revision` and baseline configuration.
   - Candidate parameter sets are applied **in-memory (RAM only)** to the active audio loop via an ACK channel without rewriting `config.toml`.
   - In case of power loss or daemon restart, the startup sequence detects `recovery_session.json` and restores the validated baseline configuration automatically.
   - Graceful completion (`finish`) or cancellation (`cancel`) atomically removes the recovery record.

4. **Human Owner In-The-Loop Validation:**
   - No automated candidate can receive the `owner_confirmed` state without explicit human verification.
   - Session closing and permanent profile activation require `confirm_session_owner`.

---

## 2. Scopes and Authorization Matrix

Requests require an `Authorization: Bearer <token>` header.

| Scope | Description | Allowed Endpoints |
|---|---|---|
| `acoustics_read` | Read runtime state, event logs, and job reports | `GET /state`, `GET /events`, `GET /jobs/{id}/report` |
| `acoustics_write`| Manage sessions, apply in-RAM candidates | `POST /sessions`, `POST /sessions/{id}/candidate`, `POST /sessions/{id}/restore` |
| `profiles` | Room profiles CRUD, activation, baseline restore | `GET/POST /profiles`, `PUT/DELETE /profiles/{id}`, `POST /profiles/{id}/activate` |
| `samples` | Upload and stream audio verification records | `GET/POST /samples`, `GET /samples/{id}/audio`, `DELETE /samples/{id}` |
| `jobs` | Execute and stop acoustic measurement jobs | `POST /jobs`, `POST /jobs/{id}/cancel`, `POST /evaluate`, `POST /search` |

---

## 3. REST API Specification (OpenAPI 3.1)

Base URL: `/api/v1/acoustics`

### Key Endpoints:

#### 1. Schema & Runtime State
- `GET /api/v1/acoustics/schema` or `/api/v1/acoustics/openapi.json`:
  Returns the complete, versioned OpenAPI 3.1 specification.
- `GET /api/v1/acoustics/state`:
  Returns audio pipeline status, loaded model SHA256, noise floor, pcm RMS, capabilities, and all 33 acoustic parameters with their limits.

#### 2. Calibration Sessions
- `POST /api/v1/acoustics/sessions`:
  Starts a bounded session. Returns `409 Conflict` if another session is active.
- `GET /api/v1/acoustics/sessions`:
  Retrieves active session state and bounds.
- `POST /api/v1/acoustics/sessions/{id}/candidate`:
  Applies an in-memory candidate (strictly requires all 33 parameters without partial defaults).
- `POST /api/v1/acoustics/sessions/{id}/restore`:
  Reverts the audio loop to the session baseline.
- `POST /api/v1/acoustics/sessions/{id}/confirm_owner`:
  Records live human verification.
- `POST /api/v1/acoustics/sessions/{id}/finish`:
  Closes the session, optionally persisting and activating a named profile (`save_profile_name`, `activate_profile`).
- `POST /api/v1/acoustics/sessions/{id}/cancel`:
  Cancels session and restores baseline.

#### 3. Measurement Jobs
- `POST /api/v1/acoustics/jobs`:
  Executes an acoustic stimulus.
  The `Idempotency-Key: <unique_key>` header prevents duplicate sound playback on network retries.
- `GET /api/v1/acoustics/jobs/{id}/report`:
  Returns job validity analysis (`is_valid`, `validity_reason`), 3-band relative frequency attenuation (100..500 Hz, 500..2000 Hz, 2000..6000 Hz with RT60 disclaimer), and KWS verification metrics.
- `POST /api/v1/acoustics/jobs/{id}/cancel`:
  Idempotently cancels the active audio stimulus.

#### 4. Candidate Evaluation & Search
- `POST /api/v1/acoustics/evaluate`:
  Evaluates settings across a corpus split (`calibration`, `train`, `held_out`).
- `POST /api/v1/acoustics/search`:
  Bounded coordinate parameter search (capped at 20 trials) optimizing:
  $$S = 100 \times \text{recall} - 10 \times \text{FA/hr} - 20 \times \text{own\_leaks} - 2 \times \text{extra\_triggers} - \text{RTF\_penalty}$$

#### 5. Room Profiles
- `GET /api/v1/acoustics/profiles`: List stored room profiles.
- `POST /api/v1/acoustics/profiles`: Create a new named room profile (`schema: 1`).
- `POST /api/v1/acoustics/profiles/{id}/activate`: Permanently activate profile across cold boots.
- `POST /api/v1/acoustics/restore`: Revert to factory defaults.

---

## 4. MCP (Model Context Protocol) Integration

The `scripts/mcp_acoustic_agent.py` adapter runs as an MCP stdio server.

### Environment Setup:
```bash
export GPT_MINI_URL="http://10.77.0.111:8080"
export GPT_MINI_CALIBRATION_TOKEN="calib_..."
export GPT_MINI_TIMEOUT="60.0"
python3 scripts/mcp_acoustic_agent.py
```

### Available MCP Tools:
- `get_openapi_schema`
- `get_acoustic_status`
- `create_acoustic_session`
- `get_acoustic_session`
- `apply_session_candidate`
- `restore_session_baseline`
- `start_acoustic_job` (supports `idempotency_key`)
- `get_acoustic_job_report`
- `evaluate_acoustic_candidate`
- `search_acoustic_candidates`
- `confirm_session_owner`
- `finish_acoustic_session`
- `activate_acoustic_profile`
- `restore_working_profile`

---

## 5. Hardware Capabilities Registry (GPT Mini Target)

| Feature | Value | Constraints & Rationale |
|---|---|---|
| **Microphone Stream** | PCM16 mono @ 16 000 Hz | Hardware ALSA driver captures native 8ch S32LE @ 48 kHz; downmixed by C helper to 16 kHz mono. |
| **Physical Channel** | `ch0` | Configured at startup. Dynamic channel switching is unsupported in this pipeline. |
| **MFCC Feature Extraction** | 30 ms window, 10 ms step, pre-emphasis 0.97 | Fixed by Rustpotter acoustic model design. |
| **Software AEC / NS** | Not connected | KWS bandpass filters and normalizers operate inside KWS only and do not substitute full AEC/NS. |
| **AUX Output** | **Unavailable** | GPT Mini hardware lacks a 3.5 mm AUX jack. Route `aux_out` is disabled in UI and API. |
| **Model Enrollment** | 3–8 phrase templates | 3.8 s recording window (max 4.0 s). Isolated to enrollment wizard on main dashboard. |
