# Contributing to Atlas

First off, thank you for your interest in contributing to Atlas!

Whether you're fixing a typo, improving documentation, adding a new feature, or helping shape the project's direction, your contributions are appreciated.

Atlas is built on the idea that self-hosted infrastructure should be easier to understand, document, and manage. Every contribution helps move that vision forward.

---

# Our Mission

Atlas exists to help people understand and operate their homelabs through safe, explainable, and AI-assisted tooling.

Before proposing a feature, ask yourself:

> **Does this help Atlas better understand the infrastructure?**

If the answer is "yes," it likely aligns with the project's goals.

---

# Ways to Contribute

There are many ways to contribute, including:

## Documentation

* Improve guides
* Fix typos
* Clarify explanations
* Add examples
* Expand tutorials

---

## Development

* Implement new features
* Improve existing code
* Fix bugs
* Improve performance
* Refactor for readability

---

## Testing

Help test Atlas across different environments:

* Fedora
* Ubuntu
* Debian
* Proxmox VE
* Docker
* Docker Compose

Future support may include additional Linux distributions and virtualization platforms.

---

## Ideas

Suggestions are always welcome.

Examples include:

* New discovery modules
* AI workflows
* Monitoring integrations
* Documentation improvements
* Plugin ideas
* CLI enhancements

---

# Before You Start

Please check:

* Existing Issues
* Existing Pull Requests
* The project roadmap

This helps avoid duplicate work.

---

# Development Philosophy

Atlas follows several guiding principles.

## Documentation First

Every significant feature should include documentation.

If a feature cannot be explained clearly, it likely needs refinement.

---

## Explainability

Atlas should be able to explain:

* What it is doing
* Why it is doing it
* What the expected outcome is
* Any associated risks

This philosophy should be reflected in both code and documentation.

---

## Local-First

Whenever practical, Atlas prioritizes self-hosted and local solutions.

Examples include:

* Local AI models
* Self-hosted monitoring
* Local infrastructure management

---

## Safety

Atlas should never encourage unsafe automation.

Changes affecting infrastructure should be:

* Observable
* Logged
* Reversible whenever possible
* Configurable through user approval

---

# Development Setup

Clone the repository:

```bash
git clone https://github.com/<your-username>/atlas.git
cd atlas
```

Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

As the project evolves, installation may transition to modern tooling such as `uv`.

---

# Branch Naming

Please create a feature branch instead of working directly on `main`.

Examples:

```text
feature/docker-discovery

feature/proxmox-support

feature/status-command

feature/media-module

fix/docker-parser

docs/getting-started

refactor/cli
```

---

# Commit Messages

Atlas follows the Conventional Commits specification.

Examples:

```text
feat: add Docker discovery

feat: implement hardware inventory

fix: resolve container parser

docs: improve installation guide

docs: update roadmap

refactor: simplify CLI structure

test: add inventory unit tests

ci: add GitHub Actions workflow

chore: update dependencies
```

---

# Pull Requests

Good pull requests typically:

* Focus on one logical change
* Include clear descriptions
* Update documentation when needed
* Pass automated checks
* Keep changes as small and reviewable as practical

If your change affects user behavior, include an explanation of the expected outcome.

---

# Coding Standards

General principles:

* Favor readability over cleverness.
* Keep functions focused and small.
* Avoid unnecessary complexity.
* Write descriptive names.
* Add comments where intent is not immediately obvious.
* Remove unused code before submitting.

Future coding standards will be documented as the project grows.

---

# Documentation Standards

Documentation is a core feature of Atlas.

Whenever appropriate, include:

* Purpose
* Requirements
* Examples
* Limitations
* Future improvements

Well-written documentation is just as valuable as code.

---

# Reporting Bugs

When reporting an issue, please include:

* Operating system
* Atlas version
* Python version
* Relevant logs
* Steps to reproduce
* Expected behavior
* Actual behavior

Screenshots are welcome when helpful.

---

# Suggesting Features

Feature requests should explain:

* The problem being solved
* Why it matters
* A proposed approach (if you have one)
* Alternative solutions you've considered

Discussion is encouraged before implementation for larger features.

---

# Code of Conduct

Please follow the project's Code of Conduct.

Be respectful, constructive, and welcoming to others.

Atlas is intended to be a friendly and inclusive open-source community.

---

# Recognition

Every contribution matters.

Whether you improve a single sentence, fix a bug, or implement a major feature, you are helping Atlas become a better project.

Thank you for contributing.

---

# Our Philosophy

Atlas is guided by three simple ideas:

**Understand first.**

Build an accurate understanding of infrastructure before making decisions.

**Document continuously.**

Documentation should evolve alongside the system.

**Automate carefully.**

Automation should be transparent, explainable, and under the user's control.

If your contribution supports those principles, you're helping move Atlas in the right direction.

Welcome aboard!
