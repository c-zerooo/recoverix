# Recoverix Local Offline LLM Integration Guide

This guide explains how to set up and run a local, offline LLM server via `llama.cpp` for the Grounded LLM Evidence Explanation layer in **Recoverix**.

---

## 1. Overview & Architecture

Recoverix provides AI-assisted evidence summaries ("AI Evidence Briefs") alongside strict deterministic forensic scoring and recovery. To ensure complete data privacy, air-gapped forensic operation, and zero external API dependencies, Recoverix can utilize a local offline LLM powered by `llama.cpp`.

```
                    ┌─────────────────────────────────────────┐
                    │      Recoverix Analysis Engine          │
                    │   (FastAPI / Python Forensics Core)     │
                    └────────────────────┬────────────────────┘
                                         │
                             Grounded Forensic Facts
                             (Deterministic Payload)
                                         │
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │        llama.cpp HTTP Server            │
                    │    http://127.0.0.1:8080/v1/chat/...    │
                    └────────────────────┬────────────────────┘
                                         │
                               Local GGUF Model
                         (e.g., Llama-3.2-3B-Instruct)
```

### Safety Invariants
1. **Deterministic Engine Authority:** The local LLM acts exclusively as an explanation layer over deterministic facts. It cannot alter confidence scores, recovery status, provenance, or file classification.
2. **Zero-Trust Fallback:** If the local LLM server is unconfigured, unreachable, or returns invalid JSON schema, Recoverix automatically falls back to `build_deterministic_explanation()`.

---

## 2. Installation of `llama.cpp`

### macOS (Apple Silicon)
```bash
brew install llama.cpp
```

### Linux / Building from Source
```bash
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
cmake -B build
cmake --build build --config Release
```

---

## 3. Acquiring a Local GGUF Model

Download an instruction-tuned GGUF model suitable for JSON output and evidence explanation (e.g., Llama 3.2 3B Instruct or Qwen 2.5 Coder 1.5B Instruct):

```bash
mkdir -p models
# Example: Download Llama-3.2-3B-Instruct GGUF
curl -L -o models/llama-3.2-3b-instruct.Q4_K_M.gguf \
  "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
```

> **Note:** Model binaries (`*.gguf`) are large binary files and are strictly excluded from Git version control. Always keep downloaded model files in `models/` or a local cache directory outside Git tracking.

---

## 4. Starting the Local OpenAI-Compatible Server

Launch the `llama-server` process with OpenAI API endpoint compatibility:

```bash
llama-server \
  -m models/llama-3.2-3b-instruct.Q4_K_M.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  -c 4096 \
  --n-gpu-layers 99
```

---

## 5. Configuring Recoverix Environment Variables

Configure Recoverix to connect to the local `llama.cpp` server:

```bash
export LLM_ENABLED=true
export LLM_BASE_URL=http://127.0.0.1:8080/v1
export LLM_MODEL=llama-3.2-3b-instruct
export LLM_API_KEY=local
```

### Environment Variable Reference
| Variable | Value for Local LLM | Description |
| :--- | :--- | :--- |
| `LLM_ENABLED` | `true` | Enables AI explanation layer attempts |
| `LLM_BASE_URL` | `http://127.0.0.1:8080/v1` | Local OpenAI-compatible API endpoint |
| `LLM_MODEL` | `llama-3.2-3b-instruct` | Model identifier string |
| `LLM_API_KEY` | `local` | Placeholder API key (not enforced by default local server) |

---

## 6. Verification and Testing

### Testing Server Endpoint
```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.2-3b-instruct",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### Running Backend Unit Tests
```bash
pytest tests/test_llm_explainer.py -v
```

---

## 7. Deterministic Fallback Behavior

If `LLM_ENABLED=false`, `LLM_BASE_URL` is unreachable, or the local process is offline, Recoverix degrades seamlessly to deterministic explanation generation without throwing HTTP errors or interrupting evidence recovery workflows.
