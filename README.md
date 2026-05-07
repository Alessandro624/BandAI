# BandAI 🏛️🤖

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CrewAI](https://img.shields.io/badge/CrewAI-Multi--Agent-orange.svg)](https://github.com/joaomdmoura/crewAI)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **Turning bureaucracy into competitive intelligence.**

BandAI is a multi-agent decision intelligence platform designed to automate the discovery, evaluation, and proposal generation for Italian public tenders (*bandi pubblici*). Built on top of [CrewAI](https://github.com/joaomdmoura/crewAI), BandAI helps SMEs overcome the bureaucratic friction of public procurement.

---

## 🛑 The Problem

Italian SMEs consistently fail to participate in public tenders due to:

* **Fragmented Discovery:** Tenders are scattered across hundreds of municipal and national portals.
* **Bureaucratic Friction:** Opaque requirements, dense legal jargon, and strict compliance metrics.
* **High Cost of Bidding:** Assembling a compliant technical and administrative response requires expensive cross-functional collaboration.

## 💡 The Solution

BandAI orchestrates a specialized crew of AI agents in a strict, deterministic pipeline. By utilizing adversarial debate for legal compliance and auction-based mechanisms for document synthesis, BandAI ensures that companies only bid on viable tenders and produce mathematically compliant, evidence-backed proposals.

---

## 🏗️ Multi-Agent Architecture

BandAI's intelligence relies on three distinct operational phases, each managed by specialized agents:

### 1. Discovery Phase: Scout Agent

* **Role:** Opportunity Hunter
* **Action:** Crawls MEPA, ANAC, and regional procurement portals. Extacts structured metadata (deadlines, budget, CPV categories) using custom OCR and NLP pipelines.
* **Mechanism:** Uses *Consensus Polling* to deduplicate overlapping tender notices and establish a single, canonical record.

### 2. Evaluation Phase: Compliance Officer (Adversarial Debate)

* **Role:** Legal & Risk Analyst
* **Action:** Evaluates the company's RAG-indexed credentials against the tender requirements.
* **Mechanism:** Runs an internal debate workflow.
  * 🟢 **Advocate Agent:** Optimistically looks for pathways to eligibility (e.g., consortiums, sub-contracting).
  * 🔴 **Auditor Agent:** Skeptically evaluates risk, looking for missing certifications or financial disqualifiers.
* **Output:** Strict routing decision: `GO`, `CONDITIONAL-GO`, or `NO-GO`.

### 3. Execution Phase: Proposal Architect

* **Role:** Technical Writer & Coordinator
* **Action:** Drafts the final response documents.
* **Mechanism:** Employs an *Auction-Based Contribution Selection*. The Architect asks department-specific agents (e.g., HR, Finance, Engineering) to "bid" their most relevant past performance data. Only the highest-confidence, verifiable evidence is included in the final DOCX/PDF generation.

---

## 🚀 Getting Started

### Prerequisites

* Python 3.10+
* API Key (OpenRouter or Anthropic/Local equivalent)

## Installation

Ensure you have Python >=3.10 <3.14 installed on your system. This project uses [UV](https://docs.astral.sh/uv/) for dependency management and package handling, offering a seamless setup and execution experience.

First, if you haven't already, install uv:

```bash
pip install uv
```

Next, navigate to your project directory and install the dependencies:

(Optional) Lock the dependencies and install them by using the CLI command:

```bash
crewai install
```

## Running the Project

To kickstart your crew of AI agents and begin task execution, run this from the root folder of your project:

```bash
crewai run
```
