---
title: <Task title>
created: YYYY-MM-DD
status: draft
---

# <Task title>

## Context

<!-- Why is this change being made? What problem or need does it address? What prompted it? What is the intended outcome? -->

## Requirements

<!-- What must be true when this task is complete? Bulleted list of concrete requirements. -->

- 

## Technical Design

<!-- How will this be implemented? Cover architecture decisions, component changes, data model changes, API changes. Reference existing functions, utilities, and patterns to reuse (with file paths). Keep it narrative but specific — an implementer should be able to work from this without guessing. -->

## Implementation Plan

<!-- Phased checklist. Each phase groups related changes. Include verification steps inline (type checking, linting, manual testing) at the end of each phase. -->

### Phase 1: <Phase name>

- [ ] **<Task item>** (`path/to/file.py`)
  - Detail of what to change

#### Phase 1 verification

- [ ] `basedpyright` — no new errors
- [ ] `ruff check` — no new errors

### Phase 2: <Phase name>

- [ ] **<Task item>** (`path/to/file.py`)
  - Detail of what to change

#### Phase 2 verification

- [ ] <Verification step>

## Acceptance Criteria

<!-- How to confirm the task is fully complete. Include both automated checks and manual verification steps. -->

- [ ] Type checking passes (`basedpyright`)
- [ ] Linting passes (`ruff check`)
- [ ] Dev server starts without errors
- [ ] <Feature-specific manual checks>

## Risks and Mitigations

<!-- Numbered list of things that could go wrong and how to handle them. Remove this section if there are no notable risks. -->

1. **<Risk>**: <Description>. Mitigation: <How to avoid or handle it>.

## Notes

<!-- Additional context, links, decisions made during planning, follow-up tasks. Remove this section if empty. -->
