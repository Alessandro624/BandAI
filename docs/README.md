# BandAI Documentation

Technical documentation for the BandAI procurement pipeline.

## Quick Start

Read in this order:

1. [Getting Started](guides/getting_started.md) - install, configure, run
2. [Characters](guides/characters.md) - who the agents are and how they behave
3. [Main Pipeline](architecture/main_pipeline.md) - how the flow works end to end
4. [Crews](architecture/crews.md) - agents, tasks, and build signatures per crew

## Architecture

How the system is built. Start here for the structural overview.

| File | Content |
| ------ | --------- |
| [main_pipeline.md](architecture/main_pipeline.md) | Flow state machine, execution modes (`full`/`scout`/`propose`), entry points, human interaction points, output files, logging |
| [crews.md](architecture/crews.md) | ScoutCrew, ComplianceCrew, ProposalCrew - agents, task chains, build signatures, shared config |
| [models.md](architecture/models.md) | All 11 Pydantic models: knowledge models, scouting models, compliance models, proposal models |
| [tools.md](architecture/tools.md) | 4 custom CrewAI tools: TenderCrawlerTool, ContractDetailTool, ComplianceCheckerTool, ProposalWriterTool |
| [configuration.md](architecture/configuration.md) | Environment variables, LLM providers, portal YAML, startup validation, NO-GO keywords |

## Guides

Practical instructions for using and extending BandAI.

| File | Content |
| ------ | --------- |
| [getting_started.md](guides/getting_started.md) | Prerequisites, installation, configuration, running (all modes), dry run, tests, CLI reference |
| [characters.md](guides/characters.md) | Every agent persona: professional identity, behavioral traits, operational constraints. 11 agents across 3 crews |
| [customization.md](guides/customization.md) | Adding portals, departments, certifications, LLM providers, knowledge sources, tools. Adjusting scoring weights and review limits |

## Reference

Detailed specs for specific subsystems.

| File | Content |
| ------ | --------- |
| [flow_state_machine.md](reference/flow_state_machine.md) | Every state transition in BandAIFlow mapped with method signatures, routing logic, and dead-end states |
| [cli_reference.md](reference/cli_reference.md) | All CLI commands: pipeline, training, memory, debugging, deployment, visualization |
| [knowledge_system.md](reference/knowledge_system.md) | StringKnowledgeSource, company profile structure, chunking strategy, RAG pipeline, graceful degradation |

## Testing

| File | Content |
| ------ | --------- |
| [testing.md](testing.md) | Test layers (unit / mocked flow / LLM smoke), commands, test file inventory, CrewAI mocking strategy, fixtures, demo checklist |

## Project Files

For source-level reference, see the external [README.md](../README.md).
